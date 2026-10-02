"""Prime's dependency-free client for the managed LAN hosting broker."""
import json
import os
import socket
from urllib.parse import quote


class WebHost:
    def __init__(self):
        self.socket = os.environ.get('PRIME_HOSTING_SOCKET')
        self.token = os.environ.get('PRIME_HOSTING_TOKEN')
        if not self.socket or not self.token:
            raise PermissionError('LAN hosting needs a newly launched LAN/Full task with tools enabled')

    def _call(self, action, **values):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(170)
            connection.connect(self.socket)
            connection.sendall(json.dumps(dict(action=action, token=self.token, **values)).encode() + b'\n')
            with connection.makefile('rb') as stream:
                raw = stream.readline(131073)
        if not raw or len(raw) > 131072:
            raise RuntimeError('Hosting broker disconnected or returned too much data')
        reply = json.loads(raw)
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'Hosting request failed'))
        return reply['result']

    def list(self):
        return self._call('list')['services']

    def static(self, name, directory, *, scope=None, ttl_hours=24):
        return self._call('create', name=name, directory=directory, kind='static', ttlHours=ttl_hours,
                          **({'scope': scope} if scope else {}))

    def app(self, name, directory, command, *, scope=None, ttl_hours=24):
        return self._call('create', name=name, directory=directory, kind='app', command=command,
                          ttlHours=ttl_hours, **({'scope': scope} if scope else {}))

    def renew(self, service_id, *, ttl_hours=24):
        return self._call('renew', id=service_id, ttlHours=ttl_hours)

    def logs(self, service_id):
        return self._call('logs', id=service_id)

    def stop(self, service_id):
        return self._call('stop', id=service_id)

    @staticmethod
    def file_url(service, relative_path):
        if not isinstance(relative_path, str) or any(not p or p.startswith('.') or '\\' in p or '\x00' in p for p in relative_path.split('/')):
            raise ValueError('Use a public path relative to the publish directory')
        return service['url'].rstrip('/') + '/' + quote(relative_path, safe='/')
