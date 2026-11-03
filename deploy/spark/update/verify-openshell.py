#!/usr/bin/env python3
"""Synthetic updater acceptance under its exclusive admission lease. No vault/model.

Uses a private scratch sandbox without host volumes/providers/network access.
Tests actual runtime, IPython, streaming, interrupted exec and cleanup.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import subprocess
import tempfile

COMMON = ['/usr/bin/openshell', '--gateway', 'spark-local', '--workspace', 'default']


def run(args, timeout=90):
    result = subprocess.run(COMMON+args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Synthetic sandbox acceptance failed: '+(result.stderr+result.stdout)[-4000:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    assert subprocess.check_output(['/usr/bin/openshell', '--version'], text=True).strip() == 'openshell '+args.version
    assert re.search(r'Version:\s*'+re.escape(args.version)+r'\b', run(['status']))
    manifest = Path.home()/'.config/prime-agent/connection-images.json'
    image = json.loads(manifest.read_text())['general']['image']
    assert re.fullmatch(r'local/prime-openshell-general:0\.9\.5-[a-f0-9]{12}', image)
    name = 'pu-'+secrets.token_hex(8)
    process = None
    with tempfile.TemporaryDirectory(prefix='prime-update-canary-') as directory:
        policy = Path(directory)/'policy.json'
        policy.write_text(json.dumps({'version': 1, 'filesystem_policy': {'include_workdir': False,
            'read_only': ['/usr', '/lib', '/etc', '/proc', '/opt/prime-kernel'],
            'read_write': ['/tmp', '/dev/null', '/dev/urandom', '/dev/random']},
            'landlock': {'compatibility': 'hard_requirement'}, 'network_policies': {}}))
        try:
            run(['sandbox', 'create', '--name', name, '--from', image, '--policy', str(policy),
                 '--cpu', '1', '--memory', '1Gi', '--approval-mode', 'manual', '--detach',
                 '--no-auto-providers', '--no-tty', '--', '/bin/sleep', '180'])
            execute = ['sandbox', 'exec', '--name', name, '--no-login-shell', '--no-tty', '--',
                       '/opt/prime-kernel/bin/python', '-u', '-c']
            output = run(execute+["import os; os.environ['IPYTHONDIR']='/tmp/ipython'; from IPython.core.interactiveshell import InteractiveShell; r=InteractiveShell.instance().run_cell('assert 37*19 == 703'); assert r.success; print('PRIME_RUNTIME_OK')"])
            assert 'PRIME_RUNTIME_OK' in output
            process = subprocess.Popen(COMMON+execute+["import time; print('PRIME_STREAM_OK',flush=True); time.sleep(120)"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(30), 'No streamed output'
                assert b'PRIME_STREAM_OK' in os.read(process.stdout.fileno(), 4096)
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
            assert 'AFTER_CANCEL' in run(execute+["print('AFTER_CANCEL')"])
        finally:
            if process:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                process.stdout.close()
            run(['sandbox', 'delete', name], timeout=45)
        # Check names, not IDs, to confirm the exact temporary resource is gone.
        assert name not in run(['sandbox', 'list', '--all-workspaces'])
    print('PASS: gateway version, fresh sandbox, IPython, streaming, exec cancellation and cleanup')


if __name__ == '__main__':
    main()
