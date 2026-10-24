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


class Approvals:
    def __init__(self, root):
        self.root = root/'connection-approvals'

    @contextlib.contextmanager
    def lock(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        credentials._private(self.root, directory=True)
        fd = os.open(self.root/'lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def require(self, owner, claim, connection_id, row, operation, arguments):
        nonce = arguments.get('requestId')
        if not isinstance(nonce, str) or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            raise ValueError('Console input needs a fresh 32-hex requestId; retry the same ID after approval')
        record = {'owner': owner, 'taskId': claim['taskId'], 'connection': connection_id,
                  'revision': row['revision'], 'operation': operation, 'arguments': arguments}
        key = 'a_'+hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        with self.lock():
            path = self.root/(key+'.json')
            if path.exists():
                existing = json.loads(credentials._read(path))
                if existing['expiresAt'] <= time.time() or existing['state'] not in ('pending', 'approved'):
                    raise PermissionError('Console approval expired or was already consumed; use a new requestId')
                if existing['state'] == 'approved':
                    existing['state'] = 'consumed'
                    credentials._write(path, json.dumps(existing).encode())
                    return None
            else:
                active = 0
                for pending in self.root.glob('a_*.json'):
                    if json.loads(credentials._read(pending)).get('expiresAt', 0) <= time.time():
                        pending.unlink()
                    else:
                        active += 1
                if active >= 128:
                    raise ValueError('Console approval queue full')
                record.update(state='pending', expiresAt=min(time.time()+300, claim['expiresAt'], row['expiresAt']))
                credentials._write(path, json.dumps(record).encode())
        return {'approvalRequired': True, 'approvalId': key, 'message': 'Review the exact console action in Settings → My connections, then retry with the same requestId.'}

    def pending(self, owner):
        if not self.root.exists():
            return []
        with self.lock():
            result = []
            for path in self.root.glob('a_*.json'):
                row = json.loads(credentials._read(path))
                if row['expiresAt'] <= time.time():
                    path.unlink()
                elif row['owner'] == owner and row['state'] == 'pending':
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
            credentials._write(path, json.dumps(row).encode())
        return {'approved': approve}
