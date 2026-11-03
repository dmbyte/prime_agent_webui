#!/usr/bin/env python3
"""Temporary FP4 experiment with bounded startup, RAM guard and production restore.

Invoke under maintenance_guard in a systemd user unit with ExecStopPost calling
this same file with --recover. Never changes production service, image or flags.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from run_screen import memory, NoRedirect

NAME = 'prime-eval-qwen-fp4'
PRODUCTION = 'llama-qwen38'
LABEL = 'fp4-20261103'


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


def recover(root):
    marker = root / 'restore-production.json'
    if not marker.exists():
        return
    state = json.loads(marker.read_text())
    production = inspect(PRODUCTION)
    if not production or production['Id'] != state['production_id']:
        raise RuntimeError('Production container identity changed; manual recovery required')
    trial = inspect(NAME)
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


def trial(root, grader_image, disable_qp_moe=False):
    if not os.environ.get('PRIME_EVAL_MAINTENANCE_HELD'):
        raise RuntimeError('Maintenance guard required')
    manifest = json.loads(Path(__file__).with_name('candidate.json').read_text())
    if inspect(NAME):
        raise RuntimeError('Trial container already exists')
    production = inspect(PRODUCTION)
    if not production or not production['State']['Running'] or not healthy(30001):
        raise RuntimeError('Production baseline is not healthy')
    marker = root / 'restore-production.json'
    with marker.open('x') as out:
        json.dump({'production_id': production['Id'], 'started_unix': time.time()}, out)
        out.flush()
        os.fsync(out.fileno())
    stop = threading.Event()
    violation = threading.Event()
    def watchdog():
        low = 0
        while not stop.wait(1):
            ratio, available = memory()
            low = low + 1 if ratio < .15 else 0
            if low >= 3:
                violation.set()
                print(f'Memory floor violated ({available:.1f} GiB available); stopping trial', flush=True)
                container = inspect(NAME)
                if container and container['Config'].get('Labels', {}).get('prime.model-eval') == LABEL:
                    docker('stop', '--time=10', container['Id'], check=False)
                return
    def shutdown(signum, frame):
        raise RuntimeError(f'Trial interrupted by signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, shutdown)
    try:
        docker('stop', '--time=60', production['Id'])
        print('Production model paused; starting isolated candidate', flush=True)
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        environment = {'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'],
                       'NAME': NAME, 'IMAGE': manifest['image'], 'PORT': '30002',
                       'MODEL_DIR': str(root / 'candidate'), 'CACHE_DIR': str(root / 'candidate-cache'),
                       'MAX_MODEL_LEN': '131072', 'MAX_NUM_SEQS': '1',
                       'MAX_NUM_BATCHED_TOKENS': '8192', 'GPU_MEMORY_UTILIZATION': '0.73',
                       'MTP_TOKENS': '4'}
        if disable_qp_moe:
            environment['QP_MOE'] = '0'
        script = root / 'candidate/recipe/serve/prime-trial-serve.sh'
        subprocess.run(['bash', str(script)], env=environment, check=True, timeout=180)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            container = inspect(NAME)
            if violation.is_set() or not container or not container['State']['Running']:
                raise RuntimeError('Candidate exited or exceeded RAM budget')
            if healthy(30002):
                break
            time.sleep(5)
        else:
            raise RuntimeError('Candidate startup exceeded 30 minutes')
        print('Candidate healthy; starting frozen screening suite', flush=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name('run_screen.py')),
                        '--base-url', 'http://127.0.0.1:30002', '--label', 'fp4-131k-low-no-qp-moe' if disable_qp_moe else 'fp4-131k-low',
                        '--engine-container', NAME,
                        '--output', str(root / 'results/fp4-131k-low.jsonl'),
                        '--grader-image', grader_image], check=True, timeout=2400)
        if violation.is_set():
            raise RuntimeError('Trial memory floor violated')
    finally:
        stop.set()
        # Ignore repeated shutdown while restoring; ExecStopPost is the fallback.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        recover(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--grader-image')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--disable-qp-moe', action='store_true', help='Use documented b12x fallback instead of the optional QP_MOE prefill patch')
    args = parser.parse_args()
    if args.recover:
        recover(args.root.resolve())
    else:
        if not args.grader_image:
            parser.error('--grader-image required')
        trial(args.root.resolve(), args.grader_image, args.disable_qp_moe)
