#!/usr/bin/env python3
"""Temporary FP4 experiment with bounded startup, RAM guard and production restore.

Invoke under maintenance_guard in a systemd user unit with ExecStopPost calling
this same file with --recover. Never changes production service, image or flags.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from run_screen import chat, memory, NoRedirect

NAME = 'prime-eval-qwen-fp4'
PRODUCTION = 'llama-qwen38'
LABEL = 'fp4-20261103'


def trial_name(value):
    if not re.fullmatch(r'prime-eval-[a-z0-9-]{1,60}', value):
        raise ValueError('Use a distinct prime-eval- container name')
    return value


def validate_settings(context, utilization, restart_checks):
    if context not in (131072, 262144) or not .68 <= utilization <= .80 or restart_checks not in (0, 1, 2):
        raise ValueError('Unreviewed context, GPU allocation or restart count')


def docker(*args, check=True):
    return subprocess.run(['docker', *args], text=True, capture_output=True, timeout=150, check=check)


def inspect(name):
    result = docker('inspect', name, check=False)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def healthy(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(f'http://127.0.0.1:{port}/health', timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def recover(root, recovery_token=None):
    marker = root / 'restore-production.json'
    if not marker.exists():
        return
    state = json.loads(marker.read_text())
    if state.get('recovery_token') != recovery_token:
        print('Recovery marker belongs to another invocation; no changes made', flush=True)
        return
    production = inspect(PRODUCTION)
    if not production or production['Id'] != state['production_id']:
        raise RuntimeError('Production container identity changed; manual recovery required')
    trial = inspect(trial_name(state.get('trial_name', NAME)))
    if trial:
        if trial['Config'].get('Labels', {}).get('prime.model-eval') != LABEL:
            raise RuntimeError('Trial identity mismatch; refusing to stop unrelated container')
        docker('stop', '--time=30', trial['Id'])
    if not production['State']['Running']:
        docker('start', production['Id'])
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if healthy(30001):
            marker.rename(root / 'restored-production.json')
            print('Original IQ4 production container restored and healthy', flush=True)
            return
        time.sleep(5)
    raise RuntimeError('Production restart health deadline exceeded; inspect model logs')


def trial(root, grader_image, disable_qp_moe=False, *, name=NAME, context=131072,
          utilization=.73, probe='screen', restart_checks=0, recovery_token=None):
    name = trial_name(name)
    validate_settings(context, utilization, restart_checks)
    if probe not in ('screen', 'context'):
        raise ValueError('Unknown probe')
    if not os.environ.get('PRIME_EVAL_MAINTENANCE_HELD'):
        raise RuntimeError('Maintenance guard required')
    manifest = json.loads(Path(__file__).with_name('candidate.json').read_text())
    if inspect(name):
        raise RuntimeError('Trial container already exists')
    if (root / 'restored-production.json').exists():
        raise RuntimeError('Use a fresh trial root; preserve prior recovery evidence')
    output = root / 'results' / ('context.jsonl' if probe == 'context' else f'fp4-{context}-low.jsonl')
    if output.exists():
        raise RuntimeError('Result already exists; use a fresh trial root')
    root.joinpath('results').mkdir(exist_ok=True)
    production = inspect(PRODUCTION)
    if not production or not production['State']['Running'] or not healthy(30001):
        raise RuntimeError('Production baseline is not healthy')
    marker = root / 'restore-production.json'
    with marker.open('x') as out:
        json.dump({'production_id': production['Id'], 'trial_name': name,
                   'recovery_token': recovery_token, 'started_unix': time.time()}, out)
        out.flush()
        os.fsync(out.fileno())
    stop = threading.Event()
    violation = threading.Event()
    telemetry = (root / 'results/lifecycle.jsonl').open('x')
    telemetry_lock = threading.Lock()
    def emit(record):
        with telemetry_lock:
            telemetry.write(json.dumps(record | {'unix': time.time()}) + '\n')
            telemetry.flush()
    emit({'type': 'configuration', 'context': context, 'gpu_memory_utilization': utilization,
          'qp_moe': not disable_qp_moe, 'probe': probe, 'restart_checks': restart_checks,
          'trial_name': name, 'image': manifest['image']})
    def watchdog():
        low = 0
        while not stop.wait(1):
            try:
                ratio, available = memory()
            except Exception:
                violation.set()
                print('Memory monitor failed; stopping candidate', flush=True)
                container = inspect(name)
                if container and container['Config'].get('Labels', {}).get('prime.model-eval') == LABEL:
                    docker('stop', '--time=10', container['Id'], check=False)
                return
            emit({'type': 'memory', 'available_fraction': ratio, 'available_gib': available})
            low = low + 1 if ratio < .15 else 0
            if low >= 3:
                violation.set()
                print(f'Memory floor violated ({available:.1f} GiB available); stopping trial', flush=True)
                container = inspect(name)
                if container and container['Config'].get('Labels', {}).get('prime.model-eval') == LABEL:
                    docker('stop', '--time=10', container['Id'], check=False)
                return
    def shutdown(signum, frame):
        raise RuntimeError(f'Trial interrupted by signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, shutdown)
    def ready(started):
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            container = inspect(name)
            if violation.is_set() or not container or not container['State']['Running']:
                raise RuntimeError('Candidate exited or exceeded RAM budget')
            if healthy(30002):
                seconds = time.monotonic() - started
                emit({'type': 'healthy', 'startup_seconds': seconds, 'container_id': container['Id']})
                print(f'Candidate healthy after {seconds:.1f} seconds', flush=True)
                return
            time.sleep(5)
        raise RuntimeError('Candidate startup exceeded 30 minutes')
    thread = None
    try:
        docker('stop', '--time=60', production['Id'])
        print('Production model paused; starting isolated candidate', flush=True)
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        environment = {'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'],
                       'NAME': name, 'IMAGE': manifest['image'], 'PORT': '30002',
                       'MODEL_DIR': str(root / 'candidate'), 'CACHE_DIR': str(root / 'candidate-cache'),
                       'MAX_MODEL_LEN': str(context), 'MAX_NUM_SEQS': '1',
                       'MAX_NUM_BATCHED_TOKENS': '8192', 'GPU_MEMORY_UTILIZATION': str(utilization),
                       'MTP_TOKENS': '4'}
        if disable_qp_moe:
            environment['QP_MOE'] = '0'
        script = root / 'candidate/recipe/serve/prime-trial-serve.sh'
        started = time.monotonic()
        subprocess.run(['bash', str(script)], env=environment, check=True, timeout=180)
        ready(started)
        if probe == 'context':
            print('Starting distributed context / warm-follow-up gate', flush=True)
            subprocess.run([sys.executable, str(Path(__file__).with_name('context_probe.py')),
                            '--engine', 'vllm', '--port', '30002', '--context', str(context),
                            '--output', str(output)], check=True, timeout=4800)
        else:
            print('Candidate healthy; starting frozen screening suite', flush=True)
            subprocess.run([sys.executable, str(Path(__file__).with_name('run_screen.py')),
                            '--base-url', 'http://127.0.0.1:30002', '--label', f'fp4-{context}-low' + ('-no-qp-moe' if disable_qp_moe else ''),
                            '--engine-container', name, '--output', str(output),
                            '--grader-image', grader_image], check=True, timeout=2400)
        for index in range(restart_checks):
            if violation.is_set():
                raise RuntimeError('Trial memory floor violated')
            container_id = inspect(name)['Id']
            docker('stop', '--time=30', container_id)
            started = time.monotonic()
            docker('start', container_id)
            ready(started)
            reply, metrics = chat('http://127.0.0.1:30002', 'qwen3.8-flash-next',
                                  [{'role': 'user', 'content': 'Calculate 37 * 19. Reply with only the integer.'}])
            passed = reply['content'].strip() == '703' and metrics['finish_reason'] == 'stop'
            emit({'type': 'restart_smoke', 'restart': index + 1, 'passed': passed, 'metrics': metrics})
            if not passed:
                raise RuntimeError('Restart inference smoke failed')
        if violation.is_set():
            raise RuntimeError('Trial memory floor violated')
    finally:
        # Keep a second TERM from interrupting recovery or monitor shutdown.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop.set()
        if thread:
            thread.join(timeout=180)
        telemetry.close()
        recover(root, recovery_token)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--grader-image')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--recovery-token', help='Unique invocation ID shared with ExecStopPost; not a credential')
    parser.add_argument('--disable-qp-moe', action='store_true', help='Use documented b12x fallback instead of the optional QP_MOE prefill patch')
    parser.add_argument('--trial-name', default=NAME, type=trial_name)
    parser.add_argument('--context', type=int, choices=(131072, 262144), default=131072)
    parser.add_argument('--gpu-memory-utilization', type=float, default=.73)
    parser.add_argument('--probe', choices=('screen', 'context'), default='screen')
    parser.add_argument('--restart-checks', type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    if args.recovery_token is not None and not re.fullmatch(r'[0-9a-f]{32}', args.recovery_token):
        parser.error('Recovery token must be a fresh 32-character hex invocation ID')
    if args.recover:
        recover(args.root.resolve(), args.recovery_token)
    else:
        if not args.grader_image or not args.recovery_token:
            parser.error('--grader-image and --recovery-token required; use start_experiment.py')
        trial(args.root.resolve(), args.grader_image, args.disable_qp_moe,
              name=args.trial_name, context=args.context, utilization=args.gpu_memory_utilization,
              probe=args.probe, restart_checks=args.restart_checks, recovery_token=args.recovery_token)
