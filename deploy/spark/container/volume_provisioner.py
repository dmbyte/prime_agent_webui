"""Register fixed per-owner OpenShell volumes; never expose Docker to tasks.

Only the trusted prime-runner UID may request reconciliation. The request has
one owner identifier, not Docker arguments, source paths or arbitrary operations.
Existing conflicting volume definitions fail closed and are never removed.
"""
import json
import os
from pathlib import Path
import pwd
import re
import socket
import socketserver
import stat
import struct
import subprocess
import threading

SOCKET = '\0prime-volume-provisioner-v1'
ROOT = Path('/var/lib/prime-runner')
LABELS = {'openshell.ai/sandbox-attachable': 'true',
          'openshell.ai/sandbox-attachable-workspace': 'default'}
LOCK = threading.Lock()


def volume_specs(owner, workspace_root, root=ROOT):
    if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{1,31}', owner):
        raise ValueError('Invalid storage owner')
    return {
        f'prime-{owner}-prime': root / 'users' / owner / 'prime',
        f'prime-{owner}-workspace': Path(workspace_root) / owner,
        **{f'prime-{owner}-gateway-{mode}': root / 'gateway' / owner / mode
           for mode in ('restricted', 'internet', 'lan', 'full')},
        f'prime-{owner}-kvm': root / 'kvm' / owner,
        f'prime-{owner}-hosting': root / 'hosting-access' / owner,
    }


def validate_source(path, runner_uid):
    # Reject symlinks in every component, including owner-controlled descendants.
    if path != path.resolve(strict=True):
        raise ValueError('Storage source contains a symlink')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != runner_uid or info.st_mode & 0o007:
        raise ValueError('Storage source has unsafe ownership or permissions')


def docker(*args):
    return subprocess.run(['/usr/bin/docker', 'volume', *args], capture_output=True,
                          text=True, timeout=15, check=False)


def validate_volume(record, name, path):
    if (record.get('Name') != name or record.get('Driver') != 'local' or
            record.get('Options') != {'type': 'none', 'o': 'bind', 'device': str(path)} or
            record.get('Labels') != LABELS):
        raise ValueError('Existing OpenShell storage registration conflicts; administrator review required')


def reconcile(body, workspace_root, runner_uid, root=ROOT):
    if not isinstance(body, dict) or set(body) != {'owner'}:
        raise ValueError('Invalid storage request')
    specs = volume_specs(body['owner'], workspace_root, root)
    with LOCK:
        # Validate all sources before changing any Docker metadata.
        for path in specs.values():
            validate_source(path, runner_uid)
        for name, path in specs.items():
            result = docker('inspect', name)
            if result.returncode:
                if 'no such volume' not in result.stderr.lower():
                    raise ValueError('Docker storage service is unavailable')
                result = docker('create', '--driver', 'local', '--opt', 'type=none',
                                '--opt', 'o=bind', '--opt', f'device={path}',
                                *[arg for key, value in LABELS.items() for arg in ('--label', f'{key}={value}')], name)
                if result.returncode:
                    raise ValueError('Could not register OpenShell storage')
                result = docker('inspect', name)
            if result.returncode:
                raise ValueError('Could not verify OpenShell storage')
            records = json.loads(result.stdout)
            if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
                raise ValueError('Invalid Docker storage response')
            validate_volume(records[0], name, path)
    return {'ok': True, 'volumes': len(specs)}


def provision(owner):
    """Runner-side call: socket is host-only and is never mounted in a task."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(45)
        try:
            conn.connect(SOCKET)
            conn.sendall(json.dumps({'owner': owner}).encode() + b'\n')
            data = conn.makefile('rb').readline(2049)
            reply = json.loads(data) if len(data) <= 2048 else {}
        except (OSError, ValueError):
            raise RuntimeError('OpenShell user storage service unavailable; ask an administrator to check prime-volume-provisioner') from None
        if not reply.get('ok'):
            raise RuntimeError('OpenShell user storage provisioning failed: ' + reply.get('error', 'invalid response'))


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != self.server.runner_uid:
            return
        try:
            line = self.rfile.readline(257)
            if len(line) > 256 or not line.endswith(b'\n'):
                raise ValueError('Invalid storage request')
            reply = reconcile(json.loads(line), self.server.workspace_root, self.server.runner_uid)
        except (OSError, ValueError, subprocess.SubprocessError):
            # Do not return Docker stderr or filesystem details to task logs.
            reply = {'ok': False, 'error': 'registration failed; check source ownership and existing volume definitions'}
        self.wfile.write(json.dumps(reply).encode() + b'\n')


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def main():
    if os.geteuid() != 0:
        raise SystemExit('Storage provisioner must run as its protected system service')
    web_owner = os.environ.get('PRIME_WEB_OWNER', 'dbyte')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{1,31}', web_owner):
        raise SystemExit('Invalid WebUI owner')
    workspace_root = Path(os.environ.get('PRIME_RUNNER_WORKSPACE_ROOT', f'/home/{web_owner}/prime-agent/tasks'))
    if not workspace_root.is_absolute() or workspace_root != workspace_root.resolve(strict=True):
        raise SystemExit('Invalid workspace root')
    with Server(SOCKET, Handler) as server:
        server.runner_uid = pwd.getpwnam('prime-runner').pw_uid
        server.workspace_root = workspace_root
        server.serve_forever()


if __name__ == '__main__':
    main()
