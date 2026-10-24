"""Private worker transport. Its control pipe is never mounted into Prime tasks."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
from urllib.parse import urlsplit

from connection_native import COMMON
import skill_credentials as credentials


class BrowserSession:
    def __init__(self, runtime, name, values, kind, expiry):
        self.runtime, self.name, self.process = runtime, name, None
        host = urlsplit(values['endpoint']).hostname
        policy = {'version': 1, 'filesystem_policy': {'include_workdir': False,
            'read_only': ['/usr', '/lib', '/etc', '/proc', '/opt/prime-kernel'],
            'read_write': ['/tmp', '/dev/null', '/dev/urandom', '/dev/random', '/dev/shm']},
            'landlock': {'compatibility': 'hard_requirement'},
            'network_policies': {'bmc': {'endpoints': [{'host': host, 'port': 443, 'protocol': 'tcp',
                'tls': 'skip', 'allowed_ips': [host+'/32']}], 'binaries': [{'path': '/usr/lib/chromium/chromium'}]}}}
        self.policy_path = runtime.root/(name+'.policy.json')
        credentials._write(runtime.root/(name+'.json'), json.dumps({'expiresAt': expiry}).encode())
        credentials._write(self.policy_path, json.dumps(policy).encode())
        try:
            runtime.run(['sandbox', 'create', '--name', name, '--from', runtime.image('network-operations'),
                '--policy', str(self.policy_path), '--cpu', '1', '--memory', '2Gi', '--approval-mode', 'manual',
                '--label', 'prime.connection=true', '--detach', '--no-auto-providers', '--no-tty',
                '--', '/bin/sleep', str(max(1, int(expiry-time.time())))])
            code = Path(__file__).with_name('connection_browser_worker.py').read_text()
            self.process = subprocess.Popen(COMMON+['sandbox', 'exec', '--name', name, '--no-login-shell', '--no-tty',
                '--', '/opt/prime-kernel/bin/python', '-u', '-c', code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, start_new_session=True)
            self.call({'action': 'open', 'kind': kind, **values}, timeout=85)
        except BaseException:
            self.close()
            raise

    def call(self, request, timeout=30):
        payload = json.dumps(request).encode()+b'\n'
        if len(payload) > 32768 or self.process.poll() is not None:
            raise RuntimeError('Private browser unavailable')
        self.process.stdin.write(payload)
        self.process.stdin.flush()
        deadline, raw = time.monotonic()+timeout, b''
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while not raw.endswith(b'\n'):
                if not selector.select(max(0, deadline-time.monotonic())):
                    raise RuntimeError('Private browser timed out')
                chunk = os.read(self.process.stdout.fileno(), min(65536, 1000001-len(raw)))
                if not chunk or len(raw)+len(chunk) > 1000000:
                    raise RuntimeError('Private browser response unavailable')
                raw += chunk
        data = json.loads(raw)
        if data.get('ok') is not True or not isinstance(data.get('result'), dict):
            raise RuntimeError('Private browser failed; login form, TLS or console not supported')
        return data['result']

    def read(self):
        return self.call({'action': 'capture'})

    def send(self, arguments):
        return self.call({'action': 'input', **{k: v for k, v in arguments.items() if k in ('key', 'text')}})

    def close(self):
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process.stdout.close()
            self.process = None
        self.runtime.cleanup(self.name)
        self.policy_path.unlink(missing_ok=True)
