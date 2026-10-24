"""Opt-in OpenShell transport. Only trusted code calls this module.

Every lease has a private, empty sandbox and an endpoint-bound provider. No task
volumes, Prime entrypoint/proxy, general agent code, or user-selected profiles.
The vault remains authoritative; gateway copies are short-lived and reaped.
"""
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

import skill_credentials as credentials

IMAGE = re.compile(r'local/prime-openshell-[a-z-]+:0\.9\.5-[a-f0-9]{12}')
LEASE = re.compile(r'pc-[a-f0-9]{16}')
COMMON = ['/usr/bin/openshell', '--gateway', 'spark-local', '--workspace', 'default']
PYTHON = '/usr/bin/python3.11'


def profile(name, origin, paths):
    """Internal builder, never an API accepting caller-supplied endpoints/rules."""
    host = urlsplit(origin).hostname
    try:
        allowed_ips = [str(ipaddress.ip_address(host))+'/32']
    except ValueError:
        allowed_ips = []
    return {'id': name, 'display_name': 'Prime bounded HTTP operation',
            'description': 'Ephemeral broker lease; no general agent access',
            'credentials': [{'name': 'PRIME_UPSTREAM_TOKEN', 'env_vars': ['PRIME_UPSTREAM_TOKEN'], 'required': True}],
            'endpoints': [{'host': urlsplit(origin).hostname, 'port': 443, 'protocol': 'rest',
                           'enforcement': 'enforce', 'rules': [{'allow': {'method': 'GET', 'path': p}} for p in paths],
                           **({'allowed_ips': allowed_ips} if allowed_ips else {})}],
            'binaries': [PYTHON]}


def http_binding(row, values):
    if row['adapter'] == 'github-readonly':
        return 'https://api.github.com', ['/repos/*/*'], values['token'], 'bearer'
    if row['adapter'] != 'redfish-readonly':
        raise ValueError('Native adapter unavailable')
    encoded = base64.b64encode((values['username']+':'+values['password']).encode()).decode()
    return row['endpoint'], ['/redfish/v1/Systems', '/redfish/v1/Systems/*'], encoded, 'basic'


class NativeRuntime:
    def __init__(self, root, manifest, run=None):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        credentials._private(self.root, directory=True)
        self.manifest = Path(manifest)
        self.run = run or self._run
        self.capacity = threading.BoundedSemaphore(2)

    @staticmethod
    def _run(arguments, *, input=None, env=None, timeout=60):
        # stderr may contain remote error bodies: never propagate it to an API/log.
        try:
            result = subprocess.run(COMMON+arguments, input=input, env=env, capture_output=True, timeout=timeout)
            if result.returncode or len(result.stdout) > 1_100_000:
                raise RuntimeError()
            return result.stdout
        except Exception:
            raise RuntimeError('Isolated connection worker failed') from None

    def image(self, kind='general'):
        image = json.loads(self.manifest.read_text()).get(kind, {}).get('image', '')
        if not IMAGE.fullmatch(image):
            raise ValueError('A reviewed pinned connection image is required')
        return image

    def cleanup(self, name):
        if not LEASE.fullmatch(name):
            raise ValueError('Invalid connection lease')
        # Keep a journal on partial failure, so restart/reaper retries exact IDs.
        # Provider deletion follows sandbox deletion; never leave attached secrets.
        try:
            for command in (['sandbox', 'delete', name], ['provider', 'delete', name], ['profile', 'delete', name]):
                self.run(command)
        except Exception:
            credentials._write(self.root/(name+'.json'), b'{"expiresAt":0}')
            raise
        (self.root/(name+'.json')).unlink(missing_ok=True)
        (self.root/(name+'.policy.json')).unlink(missing_ok=True)

    def reap(self, *, startup=False):
        failed = False
        for path in self.root.glob('pc-*.json'):
            if not LEASE.fullmatch(path.stem):
                continue
            try:
                record = json.loads(credentials._read(path))
            except FileNotFoundError:
                continue  # A completed request may just have removed its journal.
            if startup or record['expiresAt'] <= time.time():
                try:
                    self.cleanup(path.stem)
                except Exception:
                    failed = True
        if failed:
            raise RuntimeError('Expired connection workers need cleanup; new leases denied')

    def lease(self, row, values, expires_at):
        return NativeLease(self, row, values, expires_at)


class NativeLease:
    def __init__(self, runtime, row, values, expires_at):
        self.runtime, self.row = runtime, row
        self.origin, self.paths, self.secret, self.style = http_binding(row, values)
        self.name = 'pc-'+secrets.token_hex(8)  # OpenShell sandbox names are at most 19 bytes.
        self.expiry = min(expires_at, time.time()+120)
        self.directory = None

    def __enter__(self):
        if not self.runtime.capacity.acquire(blocking=False):
            raise RuntimeError('Native connection worker capacity reached; retry later')
        try:
            return self.start()
        except BaseException:
            self.runtime.capacity.release()
            raise

    def start(self):
        self.runtime.reap()
        if self.expiry <= time.time()+5:
            raise PermissionError('Connection grant is expiring')
        image = self.runtime.image()
        credentials._write(self.runtime.root/(self.name+'.json'), json.dumps({'expiresAt': self.expiry}).encode())
        self.directory = tempfile.TemporaryDirectory(prefix='connection-', dir=self.runtime.root)
        folder = Path(self.directory.name)
        profile_path, policy_path = folder/'profile.json', folder/'policy.json'
        credentials._write(profile_path, json.dumps(profile(self.name, self.origin, self.paths)).encode())
        credentials._write(policy_path, json.dumps({
            'version': 1, 'filesystem_policy': {'include_workdir': False,
                'read_only': ['/usr', '/lib', '/etc', '/proc'], 'read_write': ['/tmp', '/dev/null']},
            'landlock': {'compatibility': 'hard_requirement'}, 'network_policies': {}}).encode())
        try:
            self.runtime.run(['profile', 'import', '--file', str(profile_path)])
            # Environment lookup, never KEY=secret in argv or a profile file.
            env = {k: v for k, v in os.environ.items() if k not in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')}
            env['PRIME_UPSTREAM_TOKEN'] = self.secret
            self.runtime.run(['provider', 'create', '--name', self.name, '--type', self.name,
                              '--credential', 'PRIME_UPSTREAM_TOKEN', '--label', 'prime.connection=true'], env=env)
            self.runtime.run(['provider', 'update', self.name, '--credential-expires-at',
                              'PRIME_UPSTREAM_TOKEN='+str(int(self.expiry*1000))])
            self.runtime.run(['sandbox', 'create', '--name', self.name, '--from', image,
                '--provider', self.name, '--policy', str(policy_path), '--cpu', '1', '--memory', '512Mi',
                '--approval-mode', 'manual', '--label', 'prime.connection=true',
                '--detach', '--no-auto-providers', '--no-tty', '--', '/bin/sleep', '120'])
            return self
        except BaseException:
            self.close()
            raise
        finally:
            self.secret = None

    def get_json(self, origin, path, headers):
        if origin != self.origin or time.time() >= self.expiry:
            raise PermissionError('Native connection target or lease denied')
        # Headers from perform() are intentionally discarded. Only the isolated
        # worker sees the placeholder; it constructs the fixed authentication.
        worker = Path(__file__).with_name('connection_http_worker.py').read_text()
        raw = self.runtime.run(['sandbox', 'exec', '--name', self.name, '--no-login-shell', '--no-tty',
                                 '--', PYTHON, '-c', worker],
                               input=json.dumps({'origin': origin, 'path': path, 'style': self.style}).encode(), timeout=30)
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Invalid isolated HTTP response')
        return result

    def close(self):
        try:
            self.runtime.cleanup(self.name)
        finally:
            self.secret = None
            if self.directory:
                self.directory.cleanup()

    def __exit__(self, *_):
        try:
            self.close()
        finally:
            self.runtime.capacity.release()
