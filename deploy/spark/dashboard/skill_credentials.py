"""Reviewed credential declarations and an auth-service-only encrypted vault.

There is deliberately no HTTP or model-tool API to read plaintext credentials.
The host service account and root are trusted; this is not an external KMS.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time

MANIFEST = 'credential-requirements.json'
LOCK = threading.RLock()
ID = re.compile(r'[a-z][a-z0-9_-]{0,63}')
BMC_ADAPTERS = {'redfish-readonly', 'bmc-browser', 'bmc-kvm', 'ipmi-sol'}


def target_requirement(key, record):
    """Fixed trusted schema, independent of any installed skill declaration."""
    return dict(key=key, label=record['label'], skillName='Saved target', kind='bmc-target',
                description='One target login, reusable by compatible reviewed tools.',
                fields=[dict(id=name, label=label, required=True) for name, label in
                        [('endpoint', 'Target HTTPS origin'), ('username', 'Username'), ('password', 'Password')]])


def declarations(value):
    if not isinstance(value, dict) or set(value) != {'version', 'credentials'} or value['version'] != 1:
        raise ValueError('Invalid credential manifest')
    rows = value['credentials']
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError('Credential manifest allows at most 16 connections')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'id', 'label', 'description', 'fields', 'adapter'}:
            raise ValueError('Invalid credential declaration')
        key = row.get('id')
        if not isinstance(key, str) or not ID.fullmatch(key) or key in seen:
            raise ValueError('Credential IDs must be unique identifiers')
        seen.add(key)
        label, description = row.get('label'), row.get('description', '')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80 or not isinstance(description, str) or len(description) > 500:
            raise ValueError('Invalid credential labels')
        fields = row.get('fields')
        if not isinstance(fields, list) or not 1 <= len(fields) <= 8:
            raise ValueError('Credentials require 1-8 fields')
        clean, names = [], set()
        for field in fields:
            if not isinstance(field, dict) or set(field) - {'id', 'label', 'required'}:
                raise ValueError('Invalid credential field')
            name, title, required = field.get('id'), field.get('label'), field.get('required', True)
            if (not isinstance(name, str) or not ID.fullmatch(name) or name in names or
                    not isinstance(title, str) or not 1 <= len(title.strip()) <= 80 or type(required) is not bool):
                raise ValueError('Invalid credential field')
            names.add(name)
            clean.append({'id': name, 'label': title.strip(), 'required': required})
        normalized = {'id': key, 'label': label.strip(), 'description': description, 'fields': clean}
        if 'adapter' in row:
            adapter = row['adapter']
            expected = {'github-readonly': {'token'}, **{key: {'endpoint', 'username', 'password'}
                        for key in ('redfish-readonly', 'bmc-browser', 'bmc-kvm', 'ipmi-sol')}}
            if not isinstance(adapter, str) or adapter not in expected or names != expected[adapter]:
                raise ValueError('Unsupported credential adapter or fields')
            normalized['adapter'] = adapter
        result.append(normalized)
    return result


def read_manifest(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('Unsafe credential manifest')
    return declarations(json.loads(path.read_text()))


def requirement_id(skill, declaration):
    # Legacy skill records remain declaration-bound. Reuse requires an explicit
    # saved target and separate reviewed connection grants, never key aliasing.
    content = json.dumps([skill, declaration], sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode()).hexdigest()


def catalog(owner, home=None):
    if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{1,31}', owner):
        raise ValueError('Invalid credential owner')
    home = Path(home or Path.home())
    meta_path = home / '.prime/agent/webui-metadata.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    skills = []
    for key, row in meta.get('skills', {}).items():
        if row.get('owner') != owner or row.get('status') != 'installed' or not row.get('enabled'):
            continue
        if row.get('scope') == 'project':
            project = meta.get('projects', {}).get(row.get('projectId'), {})
            if project.get('owner') != owner or key not in project.get('skillIds', []):
                continue
        skills.append({'id': key, **row})
    # Published metadata only; never read manifests from task-writable folders.
    inventory = home / '.prime/agent/skill-inventories' / (owner + '.json')
    if not inventory.exists():
        inventory = home / '.prime/agent/skill-inventory.json'
    if inventory.exists():
        data = json.loads(inventory.read_text())
        if data.get('owner') == owner:
            skills.extend(data.get('skills', []))
    # Installer-published bundled declarations, never another user's inventory.
    # Only the trusted host account can publish this explicit global catalog.
    shared = home / '.prime/agent/global-credential-inventory.json'
    if shared.exists() or shared.is_symlink():
        data = json.loads(_read(shared))
        if data.get('version') != 1 or data.get('scope') != 'global':
            raise ValueError('Invalid global credential inventory')
        for row in data.get('skills', []):
            if row.get('scope') != 'global' or row.get('projectId') or row.get('owner'):
                raise ValueError('Invalid global credential scope')
            skills.append(row)
    result = {}
    for skill in skills:
        for declaration in declarations({'version': 1, 'credentials': skill.get('credentialRequirements', [])}):
            key = requirement_id(skill['id'], declaration)
            result[key] = dict(declaration, key=key, skillId=skill['id'], skillName=skill.get('name', skill['id']),
                               scope=skill.get('scope', 'user'), projectId=skill.get('projectId'))
    return list(result.values())


def _private(path, directory=False):
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('Credential storage ownership or permissions are unsafe')


def _read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 4 * 1024 * 1024:
            raise ValueError('Credential storage ownership, size or permissions are unsafe')
        return stream.read()


def _write(path, data):
    fd, name = tempfile.mkstemp(prefix='.vault-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Vault:
    def __init__(self, root):
        self.root = Path(root)

    def _path(self, owner):
        if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{1,31}', owner):
            raise ValueError('Invalid credential owner')
        return self.root / (hashlib.sha256(owner.encode()).hexdigest() + '.vault')

    def _cipher(self, create=False):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if create:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private(self.root, directory=True)
        key = self.root / 'master.key'
        if create and not key.exists() and not key.is_symlink():
            if list(self.root.glob('*.vault')):
                raise ValueError('Vault key is missing; restore the protected backup')
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(AESGCM.generate_key(bit_length=256)); stream.flush(); os.fsync(stream.fileno())
        return AESGCM(_read(key))

    def _load(self, owner):
        path = self._path(owner)
        if not self.root.exists() and not self.root.is_symlink():
            return {}
        _private(self.root, directory=True)
        if not path.exists() and not path.is_symlink():
            return {}
        raw = _read(path)
        try:
            data = self._cipher().decrypt(raw[:12], raw[12:], ('prime-vault-v1:' + owner).encode())
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except Exception:
            raise ValueError('Credential vault cannot be opened; restore its matching key and backup') from None

    def _save(self, owner, data):
        cipher = self._cipher(create=True)
        payload = json.dumps(data, separators=(',', ':')).encode()
        if len(payload) > 3 * 1024 * 1024:
            raise ValueError('Credential storage limit reached')
        nonce = os.urandom(12)
        _write(self._path(owner), nonce + cipher.encrypt(nonce, payload, ('prime-vault-v1:' + owner).encode()))

    def view(self, owner, requirements):
        with LOCK:
            saved = self._load(owner)
            rows = []
            for req in requirements:
                stored = saved.get(req['key'], {})
                fields = [dict(field, configured=bool(stored.get('values', {}).get(field['id']))) for field in req['fields']]
                complete = all(field['configured'] for field in fields if field['required'])
                rows.append(dict(req, fields=fields, status='saved' if stored and complete else 'missing',
                                 updatedAt=stored.get('updatedAt'), runtimeAvailable=False,
                                 ignoreCertificateErrors=stored.get('ignoreCertificateErrors') is True))
            # Allow removal after disabling/removing a skill, but never resaving an inactive grant.
            active = {row['key'] for row in requirements}
            for key, stored in saved.items():
                if key not in active:
                    if stored.get('kind') == 'bmc-target':
                        req = target_requirement(key, stored)
                        rows.append(dict(req, fields=[dict(f, configured=True) for f in req['fields']],
                                         status='saved', runtimeAvailable=False, endpoint=stored['values']['endpoint'],
                                         ipmiCipherSuite=stored.get('ipmiCipherSuite', 17),
                                         ignoreCertificateErrors=stored.get('ignoreCertificateErrors') is True))
                    else:
                        rows.append({'key': key, 'label': stored['label'], 'skillName': stored['skillName'],
                                     'fields': [], 'status': 'inactive', 'runtimeAvailable': False})
            return rows

    def change(self, owner, requirements, body):
        if isinstance(body, dict) and body.get('action') == 'save-target':
            return self.save_target(owner, requirements, body)
        if not isinstance(body, dict) or set(body) - {'action', 'key', 'values', 'ignoreCertificateErrors'}:
            raise ValueError('Invalid credential request')
        if 'ignoreCertificateErrors' in body and (body.get('action') != 'save' or type(body['ignoreCertificateErrors']) is not bool):
            raise ValueError('Certificate setting must be true or false on a save request')
        key, action = body.get('key'), body.get('action')
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid credential reference')
        with LOCK:
            saved = self._load(owner)
            if action == 'delete':
                if key not in saved:
                    raise ValueError('Saved credential not found')
                del saved[key]
            elif action == 'save':
                req = next((r for r in requirements if r['key'] == key), None)
                if not req:
                    raise ValueError('Credential requirement is no longer enabled; refresh Settings')
                values = body.get('values')
                names = {field['id'] for field in req['fields']}
                if not isinstance(values, dict) or set(values) - names:
                    raise ValueError('Invalid credential fields')
                previous = saved.get(key, {}).get('values', {})
                for name, value in values.items():
                    if not isinstance(value, str) or len(value.encode()) > 8192 or '\x00' in value:
                        raise ValueError('Credential values must be text of at most 8192 bytes')
                    if value:
                        previous[name] = value
                if any(not previous.get(f['id']) for f in req['fields'] if f['required']):
                    raise ValueError('Complete all required credential fields')
                saved[key] = {'values': previous, 'label': req['label'], 'skillName': req['skillName'], 'updatedAt': int(time.time()),
                              'ignoreCertificateErrors': body.get('ignoreCertificateErrors', saved.get(key, {}).get('ignoreCertificateErrors') is True),
                              'revision': secrets.token_hex(16)}
            else:
                raise ValueError('Unsupported credential action')
            self._save(owner, saved)
        return {'saved': action == 'save', 'deleted': action == 'delete'}

    def save_target(self, owner, requirements, body):
        if set(body) - {'action', 'key', 'name', 'sourceKey', 'values', 'ignoreCertificateErrors', 'ipmiCipherSuite'}:
            raise ValueError('Invalid target credential request')
        from connections import endpoint
        name = body.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError('Target name must be 1-80 printable characters')
        if 'ignoreCertificateErrors' in body and type(body['ignoreCertificateErrors']) is not bool:
            raise ValueError('Certificate setting must be true or false')
        if 'ipmiCipherSuite' in body and (type(body['ipmiCipherSuite']) is not int or body['ipmiCipherSuite'] not in (17, 3)):
            raise ValueError('Select IPMI cipher 17 or explicitly allow legacy encrypted cipher 3')
        key = body.get('key') or secrets.token_hex(32)
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid target reference')
        with LOCK:
            saved = self._load(owner)
            old = saved.get(key, {})
            if body.get('key') and old.get('kind') != 'bmc-target':
                raise ValueError('Saved target not found')
            if not old and sum(r.get('kind') == 'bmc-target' for r in saved.values()) >= 64:
                raise ValueError('At most 64 saved targets per user')
            source = body.get('sourceKey')
            if source:
                # Explicit owner migration only; no task or cross-owner credential reuse.
                if old:
                    raise ValueError('Cannot import over an existing target')
                req = next((r for r in requirements if r['key'] == source and
                            r.get('adapter') in BMC_ADAPTERS and r.get('scope') != 'project'), None)
                if not req or source not in saved:
                    raise ValueError('Select an active user-wide BMC credential')
                old = saved[source]
            values = body.get('values', {})
            if not isinstance(values, dict) or set(values) - {'endpoint', 'username', 'password'}:
                raise ValueError('Invalid target fields')
            merged = dict(old.get('values', {}))
            for field, value in values.items():
                if not isinstance(value, str) or len(value.encode()) > 8192 or '\x00' in value:
                    raise ValueError('Invalid target field value')
                if value:
                    merged[field] = value
            if any(not merged.get(f) for f in ('endpoint', 'username', 'password')):
                raise ValueError('Complete all target credential fields')
            merged['endpoint'] = endpoint(merged['endpoint'])
            saved[key] = dict(kind='bmc-target', values=merged, label=name.strip(), skillName='Saved target',
                              updatedAt=int(time.time()), revision=secrets.token_hex(16),
                              ignoreCertificateErrors=body.get('ignoreCertificateErrors', old.get('ignoreCertificateErrors') is True),
                              ipmiCipherSuite=body.get('ipmiCipherSuite', old.get('ipmiCipherSuite', 17)))
            self._save(owner, saved)
        return {'key': key, 'saved': True, 'deleted': False}

    def delete_owner(self, owner):
        # Prevent a subsequently recreated username from inheriting old secrets.
        with LOCK:
            path = self._path(owner)
            if self.root.exists() or self.root.is_symlink():
                _private(self.root, directory=True)
                if path.exists() or path.is_symlink():
                    _private(path)
                    path.unlink()
