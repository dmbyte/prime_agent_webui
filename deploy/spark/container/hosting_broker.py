#!/usr/bin/env python3
"""Capability-scoped LAN hosting. No Docker socket or credentials in services."""
import collections
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import threading
import time
import uuid

import hosting_auth
import openshell_runner
import task_common

ROOT = Path('/var/lib/prime-runner')
COMMON = ['/usr/bin/openshell', '--gateway', 'spark-local']
MAX_SERVICES = 4
PORTS = range(18080, 18112)
RFC1918 = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def lan_address(configured=None):
    """Fail closed on ambiguity; never advertise a Docker, loopback or public IP."""
    interfaces = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'addr', 'show'], text=True))
    candidates = {a['local'] for row in interfaces
                  if row.get('operstate') == 'UP' and not row['ifname'].startswith(('lo', 'docker', 'br-', 'veth', 'cni'))
                  for a in row.get('addr_info', []) if a.get('scope') == 'global'
                  and any(ipaddress.ip_address(a['local']) in n for n in RFC1918)}
    if configured:
        if configured not in candidates:
            raise ValueError('Hosting bind IP must be an assigned RFC1918 LAN address on an active non-container interface')
        return configured
    route = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'route', 'get', '1.1.1.1'], text=True))
    preferred = route[0].get('prefsrc') if route else None
    if preferred in candidates:
        return preferred
    if len(candidates) == 1:
        return candidates.pop()
    raise ValueError('Set PRIME_HOSTING_LAN_IP to the intended Spark LAN IPv4 address')


def source_directory(workspace, source):
    """Only an explicitly staged subtree in /project/hosted is mountable."""
    if not isinstance(source, str) or not source.startswith('/project/hosted/'):
        raise ValueError('Stage public files/app in a dedicated /project/hosted/<directory> first')
    relative = source[len('/project/'):]
    parts = relative.split('/')
    if len(parts) < 2 or any(not p or p.startswith('.') or '\\' in p or '\x00' in p for p in parts):
        raise ValueError('Invalid public directory')
    current = workspace
    for part in parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError('Public directory must exist and have no symlink ancestors')
    return relative


def visible(row, claim):
    return (row['scope'] == 'task' and row['taskId'] == claim['taskId'] or
            row['scope'] == 'project' and bool(claim.get('projectId')) and row['projectId'] == claim['projectId'])


def sandbox_spec(owner, row, root=ROOT):
    image = openshell_runner.image_for_profile('development', root / 'openshell-image-digests.json')
    name = 'ph-' + row['id'][:16]
    policy = root / 'openshell-policies' / (name + '.yaml')
    policy.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    policy.write_text('\n'.join([
        'version: 1', 'filesystem_policy:', '  include_workdir: true',
        '  read_only:', '    - /usr', '    - /lib', '    - /proc', '    - /etc',
        '    - /opt/prime-kernel', '    - /site',
        '  read_write:', '    - /tmp', '    - /dev/null', '    - /dev/urandom',
        '    - /dev/random', '    - /dev/shm',
        'landlock:', '  compatibility: hard_requirement', 'network_policies: {}', '']))
    os.chmod(policy, 0o600)
    mounts = {'docker': {'mounts': [{'type': 'volume', 'source': f'prime-{owner}-workspace',
                                    'target': '/site', 'subpath': row['relative'], 'read_only': True}]}}
    create = COMMON + ['sandbox', 'create', '--name', name, '--from', image,
                       '--policy', str(policy), '--driver-config-json', json.dumps(mounts),
                       '--cpu', '2', '--memory', '1Gi', '--approval-mode', 'manual',
                       '--label', f'prime.owner={owner}', '--label', 'prime.hosting=true',
                       '--label', 'prime.hosting-id=' + row['id'],
                       '--detach', '--no-auto-providers', '--no-tty', '--', '/bin/sleep', 'infinity']
    if row['kind'] == 'static':
        code = Path(__file__).with_name('hosting_server.py').read_text()
        command = ['/usr/bin/python3', '-c', code]
    else:
        command = row['command']
    # A minimal explicit environment, no proxy, model gateway or inherited keys.
    launch = COMMON + ['sandbox', 'exec', '--name', name, '--workdir', '/site', '--no-tty', '--',
                       '/usr/bin/env', '-i', 'HOME=/tmp', 'PATH=/opt/prime-kernel/bin:/usr/local/bin:/usr/bin:/bin',
                       'HOST=127.0.0.1', 'PORT=8000', 'PYTHONDONTWRITEBYTECODE=1',
                       'PRIME_HOST_URL=' + row['url'], 'PUBLIC_URL=' + row['url'], *command]
    forward = COMMON + ['forward', 'service', name, '--target-port', '8000',
                        '--local', f"{row['address']}:{row['port']}"]
    return dict(name=name, policy=policy, create=create, launch=launch, forward=forward,
                delete=COMMON + ['sandbox', 'delete', name])


class HostingBroker:
    def __init__(self, owner, root=ROOT, workspace_root=None, address=None):
        if not task_common.SAFE_USER.fullmatch(owner):
            raise ValueError('Invalid hosting owner')
        self.owner, self.root = owner, Path(root)
        self.workspace = Path(workspace_root or os.environ.get('PRIME_RUNNER_WORKSPACE_ROOT', f'/home/{owner}/prime-agent/tasks')) / owner
        self.address = address or lan_address(os.environ.get('PRIME_HOSTING_LAN_IP'))
        self.directory = self.root / 'hosting' / owner
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state = self.directory / 'services.json'
        self.rows = json.loads(self.state.read_text()) if self.state.exists() else {}
        self.processes, self.logs = {}, {}
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.connections = threading.BoundedSemaphore(16)

    def save(self):
        temporary = self.state.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.rows))
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state)

    def view(self, row):
        result = {k: row[k] for k in ('id', 'name', 'scope', 'taskId', 'projectId', 'kind', 'source',
                                       'url', 'address', 'port', 'createdAt', 'expiresAt', 'status')}
        result['externalUrl'] = result['url']
        result['expiresInSeconds'] = max(0, int(row['expiresAt'] - time.time()))
        result['access'] = 'Unauthenticated HTTP on the LAN; selected files/app only, not Internet publishing'
        return result

    def _record_output(self, service_id, process):
        output = self.logs.setdefault(service_id, collections.deque(maxlen=100))
        for line in iter(lambda: process.stdout.readline(4096), ''):
            output.append(line[:1000].rstrip())
        process.stdout.close()

    def _spawn(self, service_id, command):
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self.processes.setdefault(service_id, []).append(process)
        threading.Thread(target=self._record_output, args=(service_id, process), daemon=True).start()
        return process

    def _stop(self, row):
        for process in self.processes.pop(row['id'], []):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
        name = 'ph-' + row['id'][:16]
        result = subprocess.run(COMMON + ['sandbox', 'delete', name], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=40)
        if result.returncode and not any(message in result.stderr.lower() for message in ('not found', 'notfound')):
            raise RuntimeError('Hosting container cleanup failed; service record retained for retry')
        (self.root / 'openshell-policies' / (name + '.yaml')).unlink(missing_ok=True)
        return result.returncode

    def _start(self, row):
        source_directory(self.workspace, row['source'])
        spec = sandbox_spec(self.owner, row, self.root)
        result = subprocess.run(spec['create'], capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
        if result.returncode:
            self.logs.setdefault(row['id'], collections.deque(maxlen=100)).append(result.stderr[-2000:])
            raise RuntimeError('OpenShell hosting sandbox creation failed; use logs(id) for details')
        worker = self._spawn(row['id'], spec['launch'])
        forward = self._spawn(row['id'], spec['forward'])
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not self.stopping.is_set():
            if worker.poll() is not None or forward.poll() is not None:
                break
            connection = http.client.HTTPConnection(row['address'], row['port'], timeout=2)
            try:
                connection.request('HEAD', '/')
                response = connection.getresponse()
                response.read(1024)
                if 100 <= response.status < 600:
                    row['status'] = 'running'
                    self.save()
                    return
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(.25)
        raise RuntimeError('Hosted HTTP server did not become ready; use logs(id) for details')

    def dispatch(self, request, admin=False):
        if not isinstance(request, dict):
            raise ValueError('Expected a hosting request object')
        claim = None if admin else hosting_auth.verify(request.get('token'), self.owner, self.root)
        action = request.get('action')
        with self.lock:
            if action == 'list':
                return {'services': [self.view(r) for r in self.rows.values() if admin or visible(r, claim)]}
            if action == 'create':
                if admin:
                    raise PermissionError('Create through an authorized task')
                if len(self.rows) >= MAX_SERVICES:
                    raise RuntimeError('Four hosting services already exist; list/reuse or stop one first')
                name, scope, kind = request.get('name'), request.get('scope', 'project' if claim.get('projectId') else 'task'), request.get('kind', 'static')
                if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', name):
                    raise ValueError('Use a short lowercase hyphenated service name')
                if scope not in {'task', 'project'} or scope == 'project' and not claim.get('projectId'):
                    raise ValueError('Project hosting requires a task launched under that project')
                if kind not in {'static', 'app'}:
                    raise ValueError('Hosting kind must be static or app')
                if any(r['name'] == name and visible(r, claim) for r in self.rows.values()):
                    raise ValueError('Service name already exists; list and reuse it or explicitly stop it')
                source = request.get('directory')
                relative = source_directory(self.workspace, source)
                command = request.get('command', [])
                if kind == 'app' and (not isinstance(command, list) or not 1 <= len(command) <= 64 or
                                     any(not isinstance(c, str) or not c or len(c) > 4096 or '\x00' in c for c in command)):
                    raise ValueError('App requires a bounded argument array, not a shell command string')
                ttl = request.get('ttlHours', 24)
                if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 1 <= ttl <= 72:
                    raise ValueError('Hosting lifetime must be 1–72 hours')
                port = None
                occupied = {r['port'] for r in self.rows.values()}
                for candidate in PORTS:
                    if candidate in occupied:
                        continue
                    try:
                        with socket.socket() as probe:
                            probe.bind((self.address, candidate))
                        port = candidate
                        break
                    except OSError:
                        pass
                if port is None:
                    raise RuntimeError('No free LAN hosting port in 18080–18111')
                service_id = uuid.uuid4().hex
                row = dict(id=service_id, name=name, scope=scope, kind=kind, source=source, relative=relative,
                           taskId=claim['taskId'], projectId=claim.get('projectId'), command=command if kind == 'app' else [],
                           address=self.address, port=port, url=f'http://{self.address}:{port}/',
                           createdAt=time.time(), expiresAt=time.time() + ttl * 3600, status='starting')
                self.rows[service_id] = row
                self.save()  # Journal before creating resources, for crash recovery.
                try:
                    self._start(row)
                except Exception:
                    self._stop(row)
                    row['status'] = 'failed'
                    self.save()
                    raise RuntimeError(f"Hosting {service_id} failed; inspect logs and stop it before retrying") from None
                return self.view(row)
            row = self.rows.get(request.get('id'))
            if not row or not (admin or visible(row, claim)):
                raise LookupError('Hosting service not found in this task/project')
            if action == 'logs':
                return {'id': row['id'], 'lines': list(self.logs.get(row['id'], []))[-50:]}
            if action == 'stop':
                self._stop(row)
                del self.rows[row['id']]
                self.logs.pop(row['id'], None)
                self.save()
                return {'id': row['id'], 'status': 'stopped', 'sourceFilesRetained': True}
            if action == 'renew':
                ttl = request.get('ttlHours', 24)
                if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 1 <= ttl <= 72:
                    raise ValueError('Hosting lifetime must be 1–72 hours')
                row['expiresAt'] = time.time() + ttl * 3600
                self.save()
                return self.view(row)
            raise ValueError('Supported hosting actions: create, list, logs, renew, stop')

    def recover(self):
        for row in list(self.rows.values()):
            try:
                self._stop(row)
                if row['expiresAt'] <= time.time():
                    del self.rows[row['id']]
                    self.logs.pop(row['id'], None)
                elif row['status'] in {'starting', 'running'}:
                    if row['address'] != self.address:
                        raise RuntimeError('LAN address changed; stop and recreate service')
                    self._start(row)
            except Exception as error:
                self._stop(row)
                row['status'] = 'failed'
                self.logs.setdefault(row['id'], collections.deque(maxlen=100)).append(str(error)[:500])
        self.save()

    def maintain(self):
        with self.lock:
            changed = False
            for row in list(self.rows.values()):
                if row['expiresAt'] <= time.time():
                    self._stop(row)
                    del self.rows[row['id']]
                    self.logs.pop(row['id'], None)
                    changed = True
                elif row['status'] == 'running' and any(p.poll() is not None for p in self.processes.get(row['id'], [])):
                    self._stop(row)
                    row['status'] = 'failed'
                    changed = True
            if changed:
                self.save()

    def _client(self, connection, admin):
        try:
            connection.settimeout(180)
            with connection.makefile('rwb', buffering=0) as stream:
                raw = stream.readline(32769)
                if not raw or len(raw) > 32768:
                    raise ValueError('Hosting request exceeds limit')
                try:
                    reply = {'ok': True, 'result': self.dispatch(json.loads(raw), admin)}
                except Exception as error:
                    reply = {'ok': False, 'error': str(error)[:500]}
                stream.write(json.dumps(reply).encode() + b'\n')
        except (OSError, ValueError):
            pass
        finally:
            connection.close()
            self.connections.release()

    def serve(self):
        self.recover()
        listeners = []
        paths = [(self.root / 'hosting-access' / self.owner / 'hosting.sock', False),
                 (self.directory / 'admin.sock', True)]
        for path, admin in paths:
            if path.exists():
                if not path.is_socket():
                    raise RuntimeError('Hosting socket path is occupied')
                path.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            os.chmod(path, 0o600)
            server.listen(16)
            server.settimeout(1)
            listeners.append((server, path))
            def accept(server=server, admin=admin):
                while not self.stopping.is_set():
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    if self.connections.acquire(blocking=False):
                        threading.Thread(target=self._client, args=(connection, admin), daemon=True).start()
                    else:
                        connection.close()
            threading.Thread(target=accept, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: self.stopping.set())
        signal.signal(signal.SIGINT, lambda *_: self.stopping.set())
        try:
            while not self.stopping.wait(2):
                self.maintain()
        finally:
            for server, path in listeners:
                server.close()
                path.unlink(missing_ok=True)
            with self.lock:
                for row in self.rows.values():
                    self._stop(row)
            # Desired state is retained; recover recreates unexpired services.


if __name__ == '__main__':
    HostingBroker(os.environ['PRIME_WEB_OWNER']).serve()
