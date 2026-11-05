"""Dependency-free workflow records; existing brokers retain all authority."""
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import urllib.parse
import uuid


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value):
        raise ValueError('Use a 1–80 character alphanumeric step ID with hyphens/underscores')
    return value


def _argv(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 128 or
            any(not isinstance(v, str) or not v or len(v) > 4096 or '\0' in v for v in value)):
        raise ValueError('Supply a bounded nonempty argument list, not a shell string')
    return value


class Records:
    def __init__(self, workspace='/project'):
        self.root = Path(workspace).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Workspace is not a directory')
        self.directory = self.path('.prime-workflows')
        self.directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.directory, 0o700)

    def path(self, value):
        path = Path(value)
        if path.is_absolute() or not path.parts or any(p in ('.', '..') for p in path.parts):
            raise ValueError('Use a workspace-relative path without traversal')
        current = self.root
        for part in path.parts:
            current = current/part
            if current.is_symlink():
                raise ValueError('Symlinks are not accepted')
        if self.root not in current.resolve().parents:
            raise ValueError('Path is outside the workspace')
        return current

    @contextlib.contextmanager
    def lock(self, step):
        path = self.path('.prime-workflows/'+_id(step)+'.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Invalid workflow lock')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def read(self, step):
        path = self.path('.prime-workflows/'+_id(step)+'.json')
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Invalid workflow record')
            raw = stream.read(524289)
        if len(raw) > 524288:
            raise ValueError('Oversized workflow record')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Invalid workflow record')
        return result

    def write(self, step, value):
        target = self.path('.prime-workflows/'+_id(step)+'.json')
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix='.record-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, ensure_ascii=True)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def begin(self, step, specification):
        digest = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()
        old = self.read(step)
        if old:
            if old.get('specificationHash') != digest:
                raise ValueError('Step ID already belongs to different arguments')
            if old.get('state') == 'running':
                old.update(state='unknown', retryAllowed=False)
                self.write(step, old)
            return old, False
        record = {'step': step, 'specificationHash': digest, 'state': 'running',
                  'startedAt': time.time(), 'retryAllowed': False}
        self.write(step, record)
        return record, True

    def receipt(self, step):
        with self.lock(step):
            record = self.read(step)
            if record and record.get('state') == 'running':
                record.update(state='unknown', retryAllowed=False)
                self.write(step, record)
            return record

    def artifacts(self, paths):
        if not isinstance(paths, list) or len(paths) > 128 or len(set(paths)) != len(paths):
            raise ValueError('Supply at most 128 distinct artifact paths')
        rows, total = [], 0
        for name in paths:
            path = self.path(name)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size+total > 2*1024**3:
                    raise ValueError('Artifacts must be regular files totaling at most 2 GiB')
                digest, size = hashlib.sha256(), 0
                while True:
                    chunk = stream.read(1024*1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if total+size > 2*1024**3:
                        raise ValueError('Artifact grew beyond limit')
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise ValueError('Artifact changed during verification')
            total += size
            rows.append({'path': name, 'bytes': size, 'sha256': digest.hexdigest()})
        return rows


class CodingWorkflow(Records):
    def run(self, step, command, *, directory=None, timeout=120, artifacts=None):
        command = _argv(command)
        if type(timeout) not in (int, float) or not 1 <= timeout <= 3600:
            raise ValueError('Timeout must be between 1 and 3600 seconds')
        cwd = self.path(directory) if directory else self.root
        if not cwd.is_dir():
            raise ValueError('Working directory must exist')
        artifacts = [] if artifacts is None else artifacts
        if not isinstance(artifacts, list) or len(artifacts) > 128:
            raise ValueError('Invalid artifact list')
        for name in artifacts:
            self.path(name)
        with self.lock(step):
            record, fresh = self.begin(step, ['command', command, directory, timeout, artifacts])
            if not fresh:
                return record
            process = None
            output, truncated = bytearray(), False
            # Keep the configured task proxy, but never give build children saved
            # connection/hosting capabilities or cloud provider credentials.
            allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'VIRTUAL_ENV', 'PYTHONPATH',
                       'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                       'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}
            env = {k: v for k, v in os.environ.items() if k in allowed}
            try:
                try:
                    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError:
                    record.update(state='not-started')
                    return record
                deadline = time.monotonic()+timeout
                state = None
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map() or process.poll() is None:
                        if time.monotonic() >= deadline:
                            state = 'timed-out'
                            break
                        for key, _ in selector.select(min(.1, max(0, deadline-time.monotonic()))):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                            else:
                                room = max(0, 65536-len(output))
                                output.extend(chunk[:room])
                                truncated |= len(chunk) > room
                record.update(state=state or ('passed' if process.wait() == 0 else 'failed'),
                              exitCode=process.poll(), output=output.decode('utf-8', errors='replace'),
                              outputTruncated=truncated)
                if record['state'] == 'passed':
                    try:
                        record['artifacts'] = self.artifacts(artifacts)
                    except (ValueError, OSError):
                        record.update(state='artifact-error')
                return record
            except BaseException:
                record.update(state='unknown')
                raise
            finally:
                try:
                    if process is not None:
                        cleanup = self._stop(process)
                        record.update(cleanup=cleanup, cleanupVerified=cleanup['groupStopped'],
                                      exitCode=process.poll())
                        process.stdout.close()
                finally:
                    record['finishedAt'] = time.time()
                    self.write(step, record)

    @staticmethod
    def _stop(process):
        # OpenShell can deny negative-PID signals. Never let denied cleanup erase
        # a completed result, and never wait indefinitely for a denied kill.
        stopped = False
        try:
            os.killpg(process.pid, signal.SIGKILL)
            stopped = True
        except ProcessLookupError:
            stopped = True
        except PermissionError:
            if process.poll() is None:
                try:
                    process.kill()
                except (ProcessLookupError, PermissionError):
                    pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        return {'groupStopped': stopped, 'leaderExited': process.poll() is not None}

    def preview(self, step, host, *, name, directory, command=None, ttl_hours=24):
        path = self.path(directory)
        if not path.is_dir() or not directory.startswith('hosted/') or len(Path(directory).parts) < 2:
            raise ValueError('Stage public files in a dedicated directory below hosted/')
        if command is not None:
            _argv(command)
        with self.lock(step):
            record, fresh = self.begin(step, ['preview', name, directory, command, ttl_hours])
            if not fresh:
                return record
            try:
                service = (host.static(name, str(path), ttl_hours=ttl_hours) if command is None else
                           host.app(name, str(path), command, ttl_hours=ttl_hours))
                url = urllib.parse.urlsplit(service['url'])
                address = ipaddress.ip_address(url.hostname or '')
                if (url.scheme != 'http' or address.version != 4 or url.username or url.password
                        or not any(address in ipaddress.ip_network(n) for n in
                                   ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))):
                    raise ValueError('Hosting broker did not return a LAN URL')
                record.update(state='published', service=service, clientReachabilityVerified=False)
            except Exception:
                record.update(state='unknown')
            finally:
                self.write(step, record)
            return record


class BMCWorkflow(Records):
    @staticmethod
    def connections():
        from bmc_html5_kvm import _connection_call
        return _connection_call('list')['connections']

    @staticmethod
    def inspect(connection, *, system_id=None):
        from bmc_html5_kvm import _connection_call, _connection_id
        return _connection_call('call', connection=_connection_id(connection), operation='redfish.installation',
                                arguments={} if system_id is None else {'systemId': system_id})

    def open_console(self, step, connection):
        from bmc_html5_kvm import PrivateKVMClient, _connection_id
        _connection_id(connection)
        with self.lock(step):
            record, fresh = self.begin(step, ['kvm.open', connection])
            if not fresh:
                return record
            record.update(connection=connection, requestId=uuid.uuid4().hex)
            self.write(step, record)
            try:
                client = PrivateKVMClient.open(connection, request_id=record['requestId'])
                record.update(state='opened', sessionId=client.session_id)
            except Exception:
                record.update(state='unknown')
            finally:
                self.write(step, record)
            return record

    def _client(self, console):
        from bmc_html5_kvm import PrivateKVMClient
        record = self.read(console)
        if not record or record.get('state') != 'opened':
            raise ValueError('No known opened console; do not reopen after uncertain dispatch')
        return PrivateKVMClient(record['connection'], record['sessionId'])

    def capture(self, console, filename):
        self.path(filename)
        if Path(filename).suffix != '.png':
            raise ValueError('Choose a workspace PNG path')
        self._client(console).capture(str(self.path(filename)))
        return self.artifacts([filename])[0]

    def key(self, step, console, key):
        if key not in {'enter', 'escape', 'tab', 'backspace', 'up', 'down', 'left', 'right',
                       'f1', 'f2', 'f9', 'f10', 'f11', 'f12'}:
            raise ValueError('Unsupported console key')
        with self.lock(step):
            client = self._client(console)
            record, fresh = self.begin(step, ['kvm.input', client.connection_id, client.session_id, key])
            if not fresh and record['state'] != 'approval-required':
                return record
            if fresh:
                record.update(requestId=uuid.uuid4().hex, connection=client.connection_id)
            record['state'] = 'running'
            self.write(step, record)
            try:
                response = client.input(request_id=record['requestId'], key=key)
                record.update(state='approval-required' if response.get('approvalRequired') else
                              response['actionReceipt']['state'], response=response, effectVerified=False)
            except Exception:
                record.update(state='unknown', effectVerified=False)
            finally:
                self.write(step, record)
            return record

    def action_receipt(self, step):
        from bmc_html5_kvm import PrivateKVMClient
        with self.lock(step):
            record = self.read(step)
            if not record or 'requestId' not in record or 'connection' not in record:
                raise ValueError('No retained request ID')
            return PrivateKVMClient.action_receipt(record['connection'], record['requestId'])

    def close_console(self, console):
        with self.lock(console):
            client = self._client(console)
            record = self.read(console)
            record['state'] = 'closing'
            self.write(console, record)
            try:
                result = client.close()
                record['state'] = 'closed'
                return result
            finally:
                self.write(console, record)
