#!/usr/bin/env python3
"""Hold Prime's existing admission inode; fail closed if any user has active work.

This does not stop services, tasks, consoles or sandboxes. Use a systemd unit so
the lease stays held until the entire benchmark process group has terminated.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import urllib.request
from run_screen import NoRedirect

LOCK = '/var/lib/prime-runner/openshell-maintenance.lock'


def idle_metrics(metrics):
    families = {
        'llama': {'llamacpp:requests_processing', 'llamacpp:requests_deferred'},
        'vllm': {'vllm:num_requests_running', 'vllm:num_requests_waiting'},
    }
    found = set()
    for line in metrics.splitlines():
        if not line or line.startswith('#'): continue
        name = line.split()[0].split('{',1)[0]
        if name in set().union(*families.values()):
            found.add(name)
            if float(line.split()[-1]) != 0:
                raise RuntimeError('Inference is busy; no changes made')
    if found not in families.values():
        raise RuntimeError('Cannot verify model is idle')


def idle():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open('http://127.0.0.1:8765/api/health', timeout=10) as response:
        payload = json.load(response)
    if payload.get('ok') is not True or type(payload.get('activeTasks')) is not int:
        raise RuntimeError('Cannot verify aggregate task inventory')
    if payload['activeTasks'] != 0:
        raise RuntimeError('Active task exists; no changes made')
    result = subprocess.run(['openshell', '--gateway', 'spark-local', 'sandbox', 'list', '--all-workspaces', '--ids'], capture_output=True, text=True, timeout=30, check=True)
    if result.stdout.strip():
        raise RuntimeError('Sandbox exists; no changes made')
    with opener.open('http://127.0.0.1:30001/metrics', timeout=10) as response:
        metrics = response.read().decode()
    idle_metrics(metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Supply a command')
    fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError('Invalid root-provisioned maintenance inode')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        idle()
        print('Verified idle; maintenance admission held for synthetic evaluation', flush=True)
        environment = os.environ | {'PRIME_EVAL_MAINTENANCE_HELD': '1'}
        process = subprocess.Popen(command, env=environment)
        # Forward shutdown but keep the lease until the child has exited.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda signum, frame: process.send_signal(signum))
        raise SystemExit(process.wait())
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
