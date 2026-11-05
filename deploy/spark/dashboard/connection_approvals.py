"""Human-only, exact-action approvals, separate from credential use permission."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import time

import skill_credentials as credentials

ID = re.compile(r'a_[a-f0-9]{64}')
ATTEMPTED = {'dispatching', 'acknowledged', 'unknown', 'consumed'}
MAX_RECORDS = 8192


class Approvals:
    def __init__(self, root):
        self.root = root/'connection-approvals'

    @contextlib.contextmanager
    def lock(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        credentials._private(self.root, directory=True)
        parent = os.open(self.root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        fd = os.open(self.root/'lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _save(self, path, record):
        credentials._write(path, json.dumps(record).encode())
        # Rename alone is not a durable consume-before-send boundary.
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _find(self, owner, claim, connection_id, nonce):
        if not isinstance(nonce, str) or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            raise ValueError('Use the original 32-hex requestId for this action')
        matches = []
        for path in self.root.glob('a_*.json'):
            row = json.loads(credentials._read(path))
            if (row['owner'] == owner and row['taskId'] == claim['taskId']
                    and row['connection'] == connection_id and row['arguments'].get('requestId') == nonce):
                matches.append((path, row))
        if len(matches) > 1:
            # Older versions allowed the same nonce with different arguments.
            raise PermissionError('Ambiguous historical action; review manually, do not replay')
        return matches[0] if matches else (None, None)

    @staticmethod
    def _receipt(path, row):
        state = row['state']
        if state in ('dispatching', 'consumed'):
            state = 'unknown'
        acknowledged = ('BMC acknowledged the request; verify current media/boot/console state. This is not proof of installation.' if row['operation'].startswith('redfish.') else
                        'SOL worker created; read must report connected before input.' if row['operation'] == 'sol.open'
                        else 'Worker acknowledged input; verify the target using capture/read.')
        return {'actionReceipt': {'id': path.stem, 'requestId': row['arguments']['requestId'],
                'operation': row['operation'], 'state': state, 'retryAllowed': False,
                'effectVerified': False,
                'message': (acknowledged if state == 'acknowledged'
                            else 'Action may have been sent or may still be running. Do not resend or create a replacement ID; inspect the target and ask the user.') }}

    def previous(self, owner, claim, connection_id, row, operation, arguments):
        """Recover a receipt even after session closure, without dispatching anything."""
        with self.lock():
            path, existing = self._find(owner, claim, connection_id, arguments.get('requestId'))
            if existing:
                if (existing['revision'] != row['revision'] or existing['operation'] != operation
                        or existing['arguments'] != arguments):
                    raise PermissionError('Action ID is bound to different arguments; do not replay')
                if existing['state'] in ATTEMPTED:
                    return self._receipt(path, existing)

    def receipt(self, owner, claim, connection_id, arguments):
        if set(arguments) != {'requestId'}:
            raise ValueError('Receipt lookup needs only the original requestId')
        with self.lock():
            path, row = self._find(owner, claim, connection_id, arguments['requestId'])
            if row is None:
                raise ValueError('Action receipt not found; this is not permission to resend')
            if row['state'] in ATTEMPTED:
                return self._receipt(path, row)
            return {'actionReceipt': {'id': path.stem, 'requestId': arguments['requestId'],
                    'operation': row['operation'], 'state': row['state'] if row['expiresAt'] > time.time() else 'expired',
                    'retryAllowed': False, 'effectVerified': False}}

    def finish(self, owner, claim, connection_id, arguments, acknowledged):
        with self.lock():
            path, row = self._find(owner, claim, connection_id, arguments['requestId'])
            if not row or row['state'] != 'dispatching':
                raise PermissionError('Action receipt is not dispatching; do not replay')
            row.update(state='acknowledged' if acknowledged else 'unknown', completedAt=time.time())
            self._save(path, row)
            return self._receipt(path, row)

    def history(self, owner):
        with self.lock():
            rows = []
            for path in self.root.glob('a_*.json'):
                row = json.loads(credentials._read(path))
                if row['owner'] == owner and row['state'] in ATTEMPTED:
                    rows.append(dict(self._receipt(path, row)['actionReceipt'], taskId=row['taskId'],
                                     connection=row['connection'], attemptedAt=row.get('attemptedAt', 0)))
            return sorted(rows, key=lambda r: r['attemptedAt'], reverse=True)[:20]

    def acknowledged_arguments(self, owner, claim, connection_id, row, nonce, operation):
        """Internal prerequisite evidence, never a new approval or a secret API."""
        with self.lock():
            _, previous = self._find(owner, claim, connection_id, nonce)
            if (not previous or previous['revision'] != row['revision'] or previous['operation'] != operation
                    or previous['state'] != 'acknowledged'):
                raise PermissionError('Required acknowledged action is unavailable; reconcile before continuing')
            return dict(previous['arguments'])

    def require(self, owner, claim, connection_id, row, operation, arguments, *, preconditions=None):
        nonce = arguments.get('requestId')
        if not isinstance(nonce, str) or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            raise ValueError('Console input needs a fresh 32-hex requestId; retry the same ID after approval')
        record = {'owner': owner, 'taskId': claim['taskId'], 'connection': connection_id,
                  'revision': row['revision'], 'operation': operation, 'arguments': arguments}
        if preconditions is not None:
            record['preconditions'] = preconditions
        key = 'a_'+hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        with self.lock():
            path = self.root/(key+'.json')
            found_path, existing = self._find(owner, claim, connection_id, nonce)
            if existing:
                if found_path != path:
                    raise PermissionError('Action ID is bound to different arguments; do not replay')
                if existing['state'] in ATTEMPTED:
                    return self._receipt(path, existing)
                if existing['expiresAt'] <= time.time() or existing['state'] not in ('pending', 'approved'):
                    raise PermissionError('Console approval expired or denied; ask the user before requesting a new action')
                if existing['state'] == 'approved':
                    existing.update(state='dispatching', attemptedAt=time.time())
                    self._save(path, existing)
                    return None
            else:
                active = 0
                records = list(self.root.glob('a_*.json'))
                if len(records) >= MAX_RECORDS:
                    raise ValueError('Console receipt storage full; administrator review required, no actions discarded')
                for pending in records:
                    old = json.loads(credentials._read(pending))
                    if old.get('expiresAt', 0) > time.time() and old['state'] in ('pending', 'approved'):
                        active += 1
                if active >= 128:
                    raise ValueError('Console approval queue full')
                record.update(state='pending', expiresAt=min(time.time()+300, claim['expiresAt'], row['expiresAt']))
                self._save(path, record)
        return {'approvalRequired': True, 'approvalId': key, 'message': 'Review the exact action in Settings → My connections, then retry with the same requestId.'}

    def pending(self, owner):
        if not self.root.exists():
            return []
        with self.lock():
            result = []
            for path in self.root.glob('a_*.json'):
                row = json.loads(credentials._read(path))
                if row['expiresAt'] > time.time() and row['owner'] == owner and row['state'] == 'pending':
                    result.append(dict(row, id=path.stem))
            return result

    def decide(self, owner, key, approve, manager):
        if not isinstance(key, str) or not ID.fullmatch(key) or type(approve) is not bool:
            raise ValueError('Invalid console approval')
        with self.lock():
            path = self.root/(key+'.json')
            row = json.loads(credentials._read(path))
            task = manager.metadata().get('tasks', {}).get(row['taskId'], {})
            connection = manager.store._load(owner).get(row['connection'], {})
            if (row['owner'] != owner or row['state'] != 'pending' or row['expiresAt'] <= time.time()
                    or task.get('owner') != owner or task.get('status') != 'running'
                    or connection.get('revision') != row['revision']
                    or not manager.eligible(owner, connection, task.get('projectId'))):
                raise ValueError('Console approval is no longer available')
            row['state'] = 'approved' if approve else 'denied'
            self._save(path, row)
        return {'approved': approve}
