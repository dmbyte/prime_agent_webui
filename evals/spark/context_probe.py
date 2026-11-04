#!/usr/bin/env python3
"""Synthetic distributed recall / warm follow-up gate; never a general quality score.

Run under maintenance_guard in a bounded systemd unit. No private data, tools,
remote URLs or model-generated code. Reasoning is discarded by the SSE reader.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request

from run_screen import NoRedirect, chat, memory, parse_json

MODEL = 'qwen3.8-flash-next'
MARKERS = {'early': 'CEDAR-4827-AMBER', 'middle': 'BIRCH-9153-TEAL', 'late': 'MAPLE-2609-VIOLET'}
WORDS = ('archive', 'copper', 'meadow', 'window', 'river', 'stone', 'cloud', 'paper',
         'pencil', 'garden', 'basket', 'harbor', 'silver', 'yellow', 'bridge', 'planet')


def post(base, path, payload):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(base + path, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    with opener.open(request, timeout=120) as response:
        return json.load(response)


def messages(rows):
    lines = ['Synthetic archive. Only records explicitly labelled MARKER are relevant.']
    for index in range(rows):
        if index in (0, rows // 2, rows - 1):
            position = 'early' if index == 0 else 'late' if index == rows - 1 else 'middle'
            lines.append(f'MARKER {position}: {MARKERS[position]}')
        digest = hashlib.sha256(f'spark-context-v1-{index}'.encode()).digest()
        lines.append(f'Record {index}: ' + ' '.join(WORDS[b % len(WORDS)] for b in digest[:16]) + '.')
    lines.append('Return only a JSON object with keys early, middle, late and the corresponding MARKER values. Ignore ordinary records.')
    return [{'role': 'system', 'content': 'Read synthetic records accurately. Return only the requested JSON.'},
            {'role': 'user', 'content': '\n'.join(lines)}]


def token_count(base, engine, conversation):
    if engine == 'vllm':
        result = post(base, '/tokenize', {'model': MODEL, 'messages': conversation,
                                       'chat_template_kwargs': {'reasoning_effort': 'low'}})
        return result['count']
    rendered = post(base, '/apply-template', {'model': MODEL, 'messages': conversation,
                                             'reasoning_effort': 'low'})['prompt']
    return len(post(base, '/tokenize', {'content': rendered, 'add_special': False, 'parse_special': True})['tokens'])


def fit_prompt(count, target):
    rows = max(3, target // 22)
    for _ in range(10):
        conversation = messages(rows)
        actual = count(conversation)
        if target - 256 <= actual <= target:
            return conversation, actual, rows
        rows = max(3, int(rows * (target - 128) / actual))
    raise RuntimeError('Could not fit synthetic input to token budget')


def validate_result(reply, metrics, expected, counted, context):
    used = metrics['usage'].get('prompt_tokens')
    # Templates may add a BOS token. Larger differences indicate changed framing
    # or truncation and fail closed rather than claiming near-limit capacity.
    if type(used) is not int or abs(used - counted) > 8 or used + 2048 > context:
        raise ValueError('Prompt count mismatch, truncation or output reservation failure')
    if metrics['finish_reason'] != 'stop' or parse_json(reply['content']) != expected:
        raise ValueError('Recall mismatch or exhausted output budget')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('llama', 'vllm'), required=True)
    parser.add_argument('--port', choices=(30001, 30002), type=int, required=True)
    parser.add_argument('--context', type=int, choices=(131072, 262144), default=262144)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('PRIME_EVAL_MAINTENANCE_HELD'):
        parser.error('Maintenance guard required')
    base = f'http://127.0.0.1:{args.port}'
    count = lambda conversation: token_count(base, args.engine, conversation)
    samples, stop = [(time.time(), *memory())], threading.Event()
    def monitor():
        while not stop.is_set():
            samples.append((time.time(), *memory()))
            stop.wait(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=monitor, daemon=True)
    with args.output.open('x') as out:
        def emit(record):
            out.write(json.dumps(record, allow_nan=False) + '\n')
            out.flush()
            os.fsync(out.fileno())
            print(json.dumps(record), flush=True)
        emit({'type': 'run', 'suite': 'spark-context-v1', 'engine': args.engine,
              'context': args.context, 'effort': 'low', 'max_output_tokens': 2048,
              'cache_state': 'not_flushed; first document and immediate warm follow-up',
              'start_unix': time.time(), 'script_sha256': {
                  name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                  for name in ('context_probe.py', 'run_screen.py')}})
        thread.start()
        completed = False
        try:
            for target in (16000, min(250000, args.context - 12144)):
                conversation, counted, rows = fit_prompt(count, target)
                document_hash = hashlib.sha256(json.dumps(conversation, sort_keys=True).encode()).hexdigest()
                for phase in ('first', 'warm_followup'):
                    if min(s[1] for s in samples) < .15:
                        raise RuntimeError('15% available memory floor violated')
                    expected = MARKERS if phase == 'first' else {'middle': MARKERS['middle']}
                    if phase == 'warm_followup':
                        conversation += [reply, {'role': 'user', 'content': 'Now return only a JSON object with key middle and its MARKER value from the archive.'}]
                        counted = count(conversation)
                    if counted + 8192 > args.context:
                        raise RuntimeError('8K context reserve would be violated')
                    emit({'type': 'request_start', 'target': target, 'phase': phase,
                          'counted_prompt_tokens': counted, 'rows': rows, 'document_sha256': document_hash})
                    begin = len(samples)
                    reply, metrics = chat(base, MODEL, conversation, timeout=1800, deadline=2100)
                    record = {'type': 'case', 'target': target, 'phase': phase, 'metrics': metrics,
                              'response': reply['content'], 'counted_prompt_tokens': counted,
                              'min_available_gib': min((s[2] for s in samples[begin:]), default=memory()[1])}
                    try:
                        validate_result(reply, metrics, expected, counted, args.context)
                    except ValueError as exc:
                        emit(record | {'passed': False, 'reason': str(exc)})
                        raise
                    emit(record | {'passed': True})
            if min(s[1] for s in samples) < .15:
                raise RuntimeError('15% available memory floor violated')
            completed = True
        finally:
            stop.set()
            thread.join(timeout=2)
            emit({'type': 'end', 'completed': completed, 'end_unix': time.time(),
                  'min_available_gib': min((s[2] for s in samples), default=None),
                  'min_available_fraction': min((s[1] for s in samples), default=None)})


if __name__ == '__main__':
    main()
