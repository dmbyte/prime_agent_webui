"""Local read-only connection pilot. Never return raw credentials or HTTP bodies.

The auth process alone writes connection records. The trusted dashboard issues
task capabilities. The separate broker reads both; neither operation is exposed
as a general-purpose secret retrieval API.
"""
import base64
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import ssl
import time
import urllib.parse

import skill_credentials as credentials

ADAPTERS = {'github-readonly': ['github.repository'], 'redfish-readonly': ['redfish.systems']}
CONSOLE_ADAPTERS = {'bmc-browser': ['browser.open', 'browser.capture', 'browser.close'],
                    'bmc-kvm': ['kvm.open', 'kvm.capture', 'kvm.input', 'kvm.close'],
                    'ipmi-sol': ['ipmi.status', 'sol.open', 'sol.read', 'sol.input', 'sol.close']}
ADAPTERS.update(CONSOLE_ADAPTERS)


class UnsupportedCertificatePolicy(ValueError):
    """Fixed public error; never contains upstream data or credential values."""

TASK = re.compile(r'[a-f0-9]{32}')
CONNECTION = re.compile(r'c_[a-f0-9]{32}')
PROJECT = re.compile(r'p_[a-f0-9]{24}')
RFC1918 = tuple(ipaddress.ip_network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
MAX_RESPONSE = 1024 * 1024


def process_identity(pid):
    """Linux boot/process-start binding: persisted grants die with the issuer."""
    if type(pid) is not int or pid <= 0:
        raise PermissionError('Invalid task issuer')
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    if fields[0] in ('Z', 'X'):
        raise PermissionError('Task issuer is no longer active')
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()+':'+fields[19]


def configuration_root():
    return Path(os.environ.get('PRIME_AUTH_CREDENTIAL', str(Path.home()/'.config/prime-agent/web-auth.json'))).parent


def endpoint(value):
    """Pilot BMC targets are exact RFC1918 IPv4 HTTPS origins; never DNS or URLs."""
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError('Use an HTTPS URL with a private LAN IPv4 address')
    try:
        parsed = urllib.parse.urlsplit(value)
        address = ipaddress.ip_address(parsed.hostname or '')
        if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or parsed.port not in (None, 443) or address.version != 4
                or not any(address in network for network in RFC1918)
                or value not in (f'https://{address}', f'https://{address}/', f'https://{address}:443', f'https://{address}:443/')):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Use an HTTPS private LAN IPv4 origin on port 443, without a path') from None
    return f'https://{address}'


def permitted(row, context):
    if context.get('executionMode') == 'deny':
        return False
    mode = context.get('networkMode', 'restricted')
    if row['adapter'] in CONSOLE_ADAPTERS:
        return (os.environ.get('PRIME_CONNECTION_CONSOLES_ENABLED') == '1' and mode in ('lan', 'full')
                and context.get('profile') == 'network-operations')
    return (row['adapter'] == 'github-readonly' and mode in ('internet', 'full') or
            row['adapter'] == 'redfish-readonly' and mode in ('lan', 'full')
            and context.get('profile') == 'network-operations')


class Connections:
    def __init__(self, root=None, home=None):
        self.root = Path(root or configuration_root())
        self.home = Path(home or Path.home())
        configured_auth = os.environ.get('PRIME_AUTH_CREDENTIAL')
        self.auth_path = Path(configured_auth) if configured_auth and Path(configured_auth).parent == self.root else self.root/'web-auth.json'
        self.store = credentials.Vault(self.root/'connections')
        self.vault = credentials.Vault(self.root/'skill-vault')
        self.native = None
        self.sessions = None

    def metadata(self):
        path = self.home/'.prime/agent/webui-metadata.json'
        return json.loads(path.read_text()) if path.exists() else {}

    def requirements(self, owner):
        return credentials.catalog(owner, self.home)

    def eligible(self, owner, row, project_id=None):
        req = next((r for r in self.requirements(owner) if r['key'] == row['credentialKey']
                    and r.get('adapter') == row['adapter']), None)
        if not req or not row['enabled'] or row['expiresAt'] <= time.time():
            return False
        stored = self.vault._load(owner).get(row['credentialKey'], {})
        if not stored or stored.get('revision', stored.get('updatedAt')) != row['credentialRevision']:
            return False
        if row['projectId'] and row['projectId'] != project_id:
            return False
        if project_id and self.metadata().get('projects', {}).get(project_id, {}).get('owner') != owner:
            return False
        return req.get('scope') != 'project' or req.get('projectId') == project_id

    def view(self, owner):
        from connection_approvals import Approvals
        rows = self.store._load(owner)
        requirements = self.requirements(owner)
        saved = self.vault._load(owner)
        return {'connections': [dict(row, id=key,
                    status='ready' if self.eligible(owner, row, row['projectId']) and row['credentialKey'] in saved else 'unavailable',
                    operations=ADAPTERS[row['adapter']]) for key, row in rows.items()],
                'requirements': [dict(key=r['key'], label=r['label'], skillName=r['skillName'], adapter=r['adapter'],
                                      saved=r['key'] in saved, projectId=r.get('projectId'))
                                 for r in requirements if r.get('adapter') in ADAPTERS],
                'projects': [{'id': key, 'name': row.get('name', key)} for key, row in self.metadata().get('projects', {}).items()
                             if row.get('owner') == owner],
                'runtimeEnabled': os.environ.get('PRIME_CONNECTIONS_ENABLED') == '1',
                'consoleRuntimeEnabled': os.environ.get('PRIME_CONNECTION_CONSOLES_ENABLED') == '1',
                'consoleApprovals': [dict(pending, endpoint=rows.get(pending['connection'], {}).get('endpoint'),
                                         name=rows.get(pending['connection'], {}).get('name'))
                                     for pending in Approvals(self.root).pending(owner)]}

    def change(self, owner, body):
        if isinstance(body, dict) and body.get('action') == 'decide-console':
            from connection_approvals import Approvals
            if set(body) != {'action', 'id', 'approve'}:
                raise ValueError('Invalid console approval')
            return Approvals(self.root).decide(owner, body['id'], body['approve'], self)
        if not isinstance(body, dict) or set(body) - {'action', 'id', 'name', 'credentialKey', 'projectId', 'endpoint', 'expiresAt', 'enabled'}:
            raise ValueError('Invalid connection request')
        key = body.get('id') or 'c_' + secrets.token_hex(16)
        if not isinstance(key, str) or not CONNECTION.fullmatch(key):
            raise ValueError('Invalid connection reference')
        with credentials.LOCK:
            rows = self.store._load(owner)
            if body.get('action') == 'delete':
                if key not in rows:
                    raise ValueError('Connection not found')
                del rows[key]
            elif body.get('action') == 'save':
                if body.get('id') and key not in rows:
                    raise ValueError('Connection not found')
                if key not in rows and len(rows) >= 32:
                    raise ValueError('At most 32 connections per user')
                name, expiry = body.get('name'), body.get('expiresAt')
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
                    raise ValueError('Connection name must be 1-80 printable characters')
                if type(expiry) not in (int, float) or not math.isfinite(expiry) or not time.time() < expiry <= time.time() + 90*86400:
                    raise ValueError('Connection expiry must be within 90 days')
                if type(body.get('enabled', True)) is not bool:
                    raise ValueError('Invalid enabled setting')
                project_id = body.get('projectId') or None
                if project_id and (not isinstance(project_id, str) or not PROJECT.fullmatch(project_id)
                                  or self.metadata().get('projects', {}).get(project_id, {}).get('owner') != owner):
                    raise ValueError('Project not available')
                req = next((r for r in self.requirements(owner) if r['key'] == body.get('credentialKey') and r.get('adapter') in ADAPTERS), None)
                if not req or req.get('scope') == 'project' and req.get('projectId') != project_id:
                    raise ValueError('Reviewed credential requirement not available in this scope')
                record = self.vault._load(owner).get(req['key'], {})
                stored = record.get('values', {})
                if any(not stored.get(f['id']) for f in req['fields'] if f['required']):
                    raise ValueError('Save the required credentials first')
                target = 'https://api.github.com' if req['adapter'] == 'github-readonly' else endpoint(body.get('endpoint'))
                if req['adapter'] != 'github-readonly' and endpoint(stored.get('endpoint')) != target:
                    raise ValueError('Approved endpoint must match the saved credential endpoint')
                rows[key] = dict(name=name.strip(), credentialKey=req['key'], adapter=req['adapter'], projectId=project_id,
                                 endpoint=target, expiresAt=expiry, enabled=body.get('enabled', True), revision=secrets.token_hex(16),
                                 credentialRevision=record.get('revision', record.get('updatedAt')))
            else:
                raise ValueError('Unsupported connection action')
            self.store._save(owner, rows)
        return {'id': key, 'saved': body['action'] == 'save', 'deleted': body['action'] == 'delete'}

    def delete_owner(self, owner):
        self.store.delete_owner(owner)
        # Revoking all capabilities prevents username recreation from reviving grants.
        directory = self.root/'connection-capabilities'
        if directory.exists():
            credentials._private(directory, directory=True)
            for path in directory.glob('*.json'):
                if json.loads(credentials._read(path)).get('owner') == owner:
                    path.unlink()

    def issue(self, owner, task_id, project_id, authorization):
        if os.environ.get('PRIME_CONNECTIONS_ENABLED') != '1':
            return None
        if not isinstance(task_id, str) or not TASK.fullmatch(task_id):
            raise ValueError('Invalid task identity')
        rows = {key: row['revision'] for key, row in self.store._load(owner).items()
                if self.eligible(owner, row, project_id) and permitted(row, authorization)}
        if not rows:
            return None
        secret = secrets.token_hex(32)
        ceiling = {'user': 30, 'power_user': 120, 'admin': 90*24*60}.get(authorization.get('role'), 30)
        claim = dict(owner=owner, taskId=task_id, projectId=project_id, connections=rows,
                     issuerPid=os.getpid(), issuerIdentity=process_identity(os.getpid()),
                     authorization={key: authorization.get(key) for key in ('profile', 'networkMode', 'executionMode')},
                     expiresAt=time.time()+ceiling*60, digest=hashlib.sha256(secret.encode()).hexdigest())
        directory = self.root/'connection-capabilities'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        credentials._private(directory, directory=True)
        path = directory/(task_id+'.json')
        # IDs are fresh per launch; never replace an existing task grant.
        fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(claim, stream)
        return task_id+'.'+secret

    def revoke(self, task_id):
        if isinstance(task_id, str) and TASK.fullmatch(task_id):
            directory = self.root/'connection-capabilities'
            if directory.exists():
                credentials._private(directory, directory=True)
                (directory/(task_id+'.json')).unlink(missing_ok=True)

    def verify(self, token, expected_owner):
        if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}\.[a-f0-9]{64}', token):
            raise PermissionError('Active task connection grant required')
        task_id, secret = token.split('.')
        directory = self.root/'connection-capabilities'
        credentials._private(directory, directory=True)
        claim = json.loads(credentials._read(directory/(task_id+'.json')))
        if (claim['owner'] != expected_owner or claim['taskId'] != task_id or claim['expiresAt'] <= time.time()
                or process_identity(claim['issuerPid']) != claim['issuerIdentity']
                or not secrets.compare_digest(claim['digest'], hashlib.sha256(secret.encode()).hexdigest())):
            raise PermissionError('Task connection grant denied')
        users = json.loads(credentials._read(self.auth_path)).get('users', {})
        if not users.get(expected_owner) or not users[expected_owner].get('enabled', True):
            raise PermissionError('Account unavailable')
        task = self.metadata().get('tasks', {}).get(task_id, {})
        if task.get('owner') != expected_owner or task.get('status') != 'running' or task.get('projectId') != claim['projectId']:
            raise PermissionError('Task is no longer active')
        return claim

    def dispatch(self, request, expected_owner, transport=None):
        if os.environ.get('PRIME_CONNECTIONS_ENABLED') != '1':
            raise PermissionError('Connections are not activated')
        if not isinstance(request, dict) or set(request) - {'token', 'action', 'connection', 'operation', 'arguments'}:
            raise ValueError('Invalid connection operation')
        claim = self.verify(request.get('token'), expected_owner)
        rows = self.store._load(expected_owner)
        allowed = {key: row for key, row in rows.items() if claim['connections'].get(key) == row['revision']
                   and self.eligible(expected_owner, row, claim['projectId']) and permitted(row, claim['authorization'])}
        if request.get('action') == 'list':
            return {'connections': [dict(id=key, name=row['name'], operations=ADAPTERS[row['adapter']]) for key, row in allowed.items()]}
        row = allowed.get(request.get('connection'))
        if request.get('action') != 'call' or not row or request.get('operation') not in ADAPTERS[row['adapter']]:
            raise PermissionError('Connection operation not granted')
        record = self.vault._load(expected_owner).get(row['credentialKey'], {})
        if record.get('revision', record.get('updatedAt')) != row['credentialRevision']:
            raise PermissionError('Saved credentials changed; renew this connection')
        values = record.get('values', {})
        ignore_certificate_errors = record.get('ignoreCertificateErrors') is True
        deadline = time.monotonic()+90
        def still_authorized():
            self.verify(request['token'], expected_owner)
            current = self.store._load(expected_owner).get(request['connection'], {})
            if current.get('revision') != row['revision'] or not self.eligible(expected_owner, current, claim['projectId']):
                raise PermissionError('Connection changed during operation')
        def bounded_transport(*args):
            if time.monotonic() >= deadline:
                raise ValueError('Connection operation timed out')
            still_authorized()
            return transport(*args) if transport else get_json(*args, ignore_certificate_errors=ignore_certificate_errors)
        if row['adapter'] in CONSOLE_ADAPTERS:
            if self.sessions is None:
                raise PermissionError('Private console runtime is not activated')
            result = self.sessions.dispatch(request, expected_owner, claim, row,
                                            dict(values, ignoreCertificateErrors=ignore_certificate_errors))
        elif self.native is not None and transport is None:
            if ignore_certificate_errors:
                # The inspected proxy verifies upstream TLS, independently of the
                # worker. Do not silently bypass it or change every user's policy.
                raise UnsupportedCertificatePolicy()
            with self.native.lease(row, values, min(claim['expiresAt'], row['expiresAt'])) as lease:
                def native_transport(*args):
                    if time.monotonic() >= deadline:
                        raise ValueError('Connection operation timed out')
                    still_authorized()
                    return lease.get_json(*args)
                result = perform(row, values, request['operation'], request.get('arguments', {}), native_transport)
        else:
            result = perform(row, values, request['operation'], request.get('arguments', {}), bounded_transport)
        # Defense in depth against an approved upstream echoing an exact secret.
        encoded = json.dumps(result)
        for name, value in values.items():
            if name != 'endpoint' and value and value in encoded:
                raise ValueError('Upstream result withheld by credential protection')
        # Do not return data if the task/connection was revoked during the request.
        still_authorized()
        return result


def get_json(origin, path, headers, *, ignore_certificate_errors=False):
    """Direct TLS only: no environment proxies, redirects, cookies or retries."""
    host = urllib.parse.urlsplit(origin).hostname
    context = ssl.create_default_context()
    if ignore_certificate_errors is True:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    connection = http.client.HTTPSConnection(host, 443, timeout=10, context=context)
    try:
        connection.request('GET', path, headers={'Accept': 'application/json', 'User-Agent': 'Prime-Connections/1', **headers})
        response = connection.getresponse()
        if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
            raise ValueError('Upstream rejected read-only request; check access and TLS configuration')
        if response.getheader('Content-Type', '').split(';')[0].strip().lower() not in ('application/json', 'application/json;odata.metadata=minimal'):
            raise ValueError('Expected an upstream JSON response')
        chunks, size, deadline = [], 0, time.monotonic()+15
        while True:
            if time.monotonic() >= deadline:
                raise ValueError('Upstream read timed out')
            chunk = response.read1(min(65536, MAX_RESPONSE+1-size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_RESPONSE:
                raise ValueError('Upstream response exceeds limit')
        raw = b''.join(chunks)
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Expected an upstream object')
        return result
    finally:
        connection.close()


def perform(row, values, operation, arguments, transport):
    if not isinstance(arguments, dict):
        raise ValueError('Operation arguments must be an object')
    if operation == 'github.repository':
        if set(arguments) != {'repository'} or not isinstance(arguments['repository'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_.-]{1,100}', arguments['repository']):
            raise ValueError('Supply repository as owner/name')
        if any(part in ('.', '..') for part in arguments['repository'].split('/')):
            raise ValueError('Invalid repository')
        token = values.get('token', '')
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError('Saved GitHub token is invalid')
        data = transport('https://api.github.com', '/repos/'+arguments['repository'], {'Authorization': 'Bearer '+token})
        result = {'repository': arguments['repository']}
        for key in ('private', 'archived', 'disabled'):
            if type(data.get(key)) is bool:
                result[key] = data[key]
        for key in ('stargazers_count', 'forks_count', 'open_issues_count'):
            if type(data.get(key)) is int and 0 <= data[key] <= 10**12:
                result[key] = data[key]
        return result
    if operation != 'redfish.systems' or arguments:
        raise ValueError('Unsupported operation or arguments')
    target = endpoint(values.get('endpoint'))
    if target != row['endpoint'] or not values.get('username') or not values.get('password') or ':' in values['username']:
        raise ValueError('Saved BMC credentials do not match this connection')
    encoded = base64.b64encode((values['username']+':'+values['password']).encode()).decode()
    headers = {'Authorization': 'Basic '+encoded}
    collection = transport(target, '/redfish/v1/Systems', headers)
    members = collection.get('Members')
    if not isinstance(members, list) or len(members) > 16 or collection.get('Members@odata.nextLink'):
        raise ValueError('Unsupported or oversized Redfish collection')
    result = []
    for index, member in enumerate(members):
        path = member.get('@odata.id') if isinstance(member, dict) else None
        if not isinstance(path, str) or not re.fullmatch(r'/redfish/v1/Systems/[A-Za-z0-9_-]{1,80}/?', path):
            raise ValueError('Redfish member target is outside the approved collection')
        data = transport(target, path, headers)
        status = data.get('Status') if isinstance(data.get('Status'), dict) else {}
        # No names, serial numbers, OEM data, headers, URLs or arbitrary strings.
        result.append({'index': index, 'powerState': data.get('PowerState') if data.get('PowerState') in ('On', 'Off', 'PoweringOn', 'PoweringOff', 'Paused') else 'Unknown',
                       'health': status.get('Health') if status.get('Health') in ('OK', 'Warning', 'Critical') else 'Unknown',
                       'state': status.get('State') if status.get('State') in ('Enabled', 'Disabled', 'StandbyOffline', 'StandbySpare', 'Starting', 'InTest', 'UnavailableOffline', 'Absent', 'Updating', 'Deferring', 'Quiesced') else 'Unknown'})
    return {'systems': result}
