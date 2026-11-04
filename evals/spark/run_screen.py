#!/usr/bin/env python3
"""Synthetic loopback-only screening. Run under maintenance_guard.py, not alongside users."""
import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid

from suite import VERSION, canonical, suite, suite_hash


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        error = urllib.error.HTTPError(req.full_url, code, 'Redirects forbidden for local evaluation', headers, fp)
        error.close()
        raise error


def equivalent(actual, expected):
    if isinstance(expected, bool) or expected is None:
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8)
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(equivalent(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(equivalent(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def parse_json(content):
    # Accept a single JSON code fence, but no surrounding prose or guessed repair.
    text = content.strip()
    if text.startswith('```json\n') and text.endswith('\n```'):
        text = text[8:-4]
    return json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def chat(base, model, messages, tools=None, *, max_tokens=2048, timeout=180, deadline=240):
    payload = {'model': model, 'messages': messages, 'temperature': 0,
               'max_tokens': max_tokens, 'reasoning_effort': 'low', 'stream': True,
               'stream_options': {'include_usage': True}}
    if tools:
        payload.update(tools=tools, tool_choice='auto')
    request = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    start = time.monotonic()
    first = first_generated = last_generated = None
    content, calls, usage, finish = '', {}, {}, None
    done = False
    # Disable proxy environment variables even for loopback requests.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        for line in response:
            if time.monotonic() - start > deadline:
                raise TimeoutError('total response deadline')
            if not line.startswith(b'data: '):
                continue
            data = line[6:].strip()
            if data == b'[DONE]':
                done = True
                break
            event = json.loads(data)
            usage = event.get('usage') or usage
            for choice in event.get('choices', []):
                delta = choice.get('delta', {})
                # Deliberately do not persist internal reasoning text.
                if any(delta.get(key) for key in ('content', 'tool_calls', 'reasoning', 'reasoning_content')):
                    last_generated = time.monotonic() - start
                    if first_generated is None:
                        first_generated = last_generated
                if (delta.get('content') or delta.get('tool_calls')) and first is None:
                    first = time.monotonic() - start
                content += delta.get('content') or ''
                for call in delta.get('tool_calls', []):
                    index = call['index']
                    current = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                    current['id'] += call.get('id') or ''
                    for key in ('name', 'arguments'):
                        current['function'][key] += call.get('function', {}).get(key) or ''
                finish = choice.get('finish_reason') or finish
            if len(content) + len(json.dumps(calls)) > 100000:
                raise ValueError('response size limit')
    elapsed = time.monotonic() - start
    if not done or finish not in ('stop', 'tool_calls', 'length'):
        raise ValueError('incomplete_or_invalid_stream')
    return {'role': 'assistant', 'content': content, **({'tool_calls': list(calls.values())} if calls else {})}, {
        'seconds': elapsed, 'visible_ttft_seconds': first, 'usage': usage, 'finish_reason': finish,
        'first_generated_seconds': first_generated,
        'decode_tokens_per_second_estimate': ((usage.get('completion_tokens', 0) - 1) / (last_generated - first_generated)
            if first_generated is not None and last_generated > first_generated and usage.get('completion_tokens', 0) > 1 else None),
        'completion_tokens_per_total_second': usage.get('completion_tokens', 0) / elapsed}


def grade_code(case, response, image):
    code = response.get('code') if isinstance(response, dict) else None
    if not isinstance(code, str) or len(code) > 16000:
        return False, 'invalid_code_response'
    name = 'prime-screen-code-' + uuid.uuid4().hex
    script = Path(__file__).with_name('code_grader.py').read_text()
    command = ['docker', 'run', '--rm', '-i', '--name', name, '--runtime=runc',
               '-e', 'NVIDIA_VISIBLE_DEVICES=void', '--network=none', '--read-only',
               '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=32',
               '--memory=128m', '--memory-swap=128m', '--cpus=1', '--user=65534:65534',
               '--log-driver=none', '--entrypoint=python3', image, '-I', '-c', script]
    payload = {'code': code, 'function': case['function'], 'tests': case['tests']}
    try:
        result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, timeout=12)
        if result.returncode or len(result.stdout) > 4096:
            return False, 'sandbox_failed'
        verdict = json.loads(result.stdout)
        return verdict.get('passed') is True, verdict.get('reason', 'no_reason')
    except (subprocess.TimeoutExpired, ValueError):
        return False, 'sandbox_timeout_or_invalid_output'
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def memory():
    values = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line and line.split()[1].isdigit()}
    return values['MemAvailable'] / values['MemTotal'], values['MemAvailable'] / 2**20


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:30001')
    parser.add_argument('--model', default='qwen3.8-flash-next')
    parser.add_argument('--label', required=True)
    parser.add_argument('--engine-container', default='llama-qwen38')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--grader-image', required=True, help='Immutable sha256 Docker image ID with Python 3')
    parser.add_argument('--split', choices=['development', 'holdout', 'all'], default='all')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    url = urllib.parse.urlsplit(args.base_url)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1') or url.path or url.username or url.query or url.fragment:
        parser.error('Only direct loopback HTTP is allowed')
    if not args.grader_image.startswith('sha256:') or len(args.grader_image) != 71:
        parser.error('Use an immutable grader image ID')
    if not os.environ.get('PRIME_EVAL_MAINTENANCE_HELD'):
        parser.error('Run through the maintenance guard')
    engine = json.loads(subprocess.run(['docker', 'inspect', args.engine_container], capture_output=True, text=True, timeout=15, check=True).stdout)[0]
    # Do not dump environment, labels, mounts or arbitrary command arguments:
    # another deployment could put credentials there. Record only relevant flags.
    flags = ('--ctx-size', '--parallel', '--cache-type-k', '--cache-type-v', '--spec-draft-n-max',
             '--batch-size', '--ubatch-size', '--max-model-len', '--max-num-seqs',
             '--max-num-batched-tokens', '--gpu-memory-utilization', '--kv-cache-dtype', '--speculative-config')
    command = engine['Config'].get('Cmd') or []
    engine_record = {'container_id': engine['Id'], 'image_id': engine['Image'], 'started_at': engine['State']['StartedAt'],
                     'memory_limit_bytes': engine['HostConfig']['Memory'],
                     'flags': {flag: command[command.index(flag)+1] for flag in flags if flag in command and command.index(flag)+1 < len(command)}}
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,temperature.gpu,clocks.sm,power.draw', '--format=csv,noheader'], capture_output=True, text=True, timeout=15)
    engine_record['gpu_start'] = gpu.stdout.strip() if gpu.returncode == 0 else 'unavailable'
    cases = [c for c in suite() if args.split == 'all' or c['split'] == args.split]
    if args.limit:
        cases = cases[:args.limit]
    stop = threading.Event()
    samples = []
    def monitor():
        while not stop.is_set():
            samples.append((time.time(), *memory()))
            stop.wait(1)
    thread = threading.Thread(target=monitor, daemon=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        def emit(record):
            out.write(json.dumps(record, allow_nan=False) + '\n')
            out.flush()
            os.fsync(out.fileno())
        emit({'type': 'run', 'label': args.label, 'suite': VERSION, 'suite_sha256': suite_hash(),
              'engine': engine_record, 'platform': platform.platform(),
              'start_unix': time.time(), 'configuration': vars(args) | {'output': str(args.output)},
              'script_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}})
        thread.start()
        completed = False
        try:
            for repeat in range(args.repeats):
                for case in cases:
                    if samples and min(s[1] for s in samples) < 0.15:
                        raise RuntimeError('15% available memory floor violated; aborting screen')
                    begin = len(samples)
                    case_started = time.monotonic()
                    metrics, response = [], None
                    passed, reason = False, 'not_run'
                    try:
                        messages = [{'role': 'system', 'content': 'You are being evaluated on synthetic fixtures. Follow the task precisely. Return only requested JSON. Never perform real actions.'}, {'role': 'user', 'content': case['prompt']}]
                        reply, timing = chat(args.base_url, args.model, messages, case.get('tools'))
                        metrics.append(timing)
                        if case.get('tools'):
                            calls = reply.get('tool_calls', [])
                            expected = case['call']
                            if len(calls) != 1 or calls[0]['function']['name'] != expected['name'] or not equivalent(parse_json(calls[0]['function']['arguments']), expected['arguments']):
                                raise ValueError('wrong_tool_contract')
                            messages += [reply, {'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': canonical(case['tool_result'])}]
                            reply, timing = chat(args.base_url, args.model, messages)
                            metrics.append(timing)
                        response = reply['content']
                        if any(m['finish_reason'] == 'length' for m in metrics):
                            raise ValueError('output_budget_exhausted')
                        actual = parse_json(response)
                        if case.get('kind') == 'code':
                            passed, reason = grade_code(case, actual, args.grader_image)
                        else:
                            passed = equivalent(actual, case['expected'])
                            reason = 'match' if passed else 'fixture_mismatch'
                    except Exception as exc:
                        reason = type(exc).__name__ + ': ' + str(exc)[:200]
                    segment = samples[begin:]
                    record = {'type': 'case', 'id': case['id'], 'domain': case['domain'], 'split': case['split'], 'repeat': repeat,
                              'case_seconds': time.monotonic() - case_started,
                              'passed': passed, 'reason': reason, 'metrics': metrics, 'response': response,
                              'min_available_gib': min((s[2] for s in segment), default=memory()[1])}
                    emit(record)
                    print(json.dumps({k: record[k] for k in ('id', 'passed', 'reason', 'min_available_gib')}), flush=True)
            completed = True
        finally:
            stop.set()
            thread.join(timeout=2)
            emit({'type': 'end', 'completed': completed, 'end_unix': time.time(), 'min_available_gib': min((s[2] for s in samples), default=None)})


if __name__ == '__main__':
    main()
