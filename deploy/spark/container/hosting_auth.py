"""Short-lived hosting capabilities issued only by the trusted task launcher."""
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path

import task_common

ROOT = Path('/var/lib/prime-runner')


def issue(owner, task_id, project_id, authorization, root=ROOT):
    if authorization.get('networkMode') not in {'lan', 'full'} or authorization.get('executionMode') == 'deny':
        return None
    if not task_common.SAFE_USER.fullmatch(owner) or not task_common.SAFE_TASK.fullmatch(task_id):
        raise ValueError('Invalid hosting identity')
    if project_id is not None and not re.fullmatch(r'p_[a-f0-9]{24}', project_id):
        raise ValueError('Invalid hosting project')
    directory = root / 'hosting-capabilities'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    claim = dict(owner=owner, taskId=task_id, projectId=project_id,
                 expires=time.time() + 4 * 3600 + 120,
                 digest=hashlib.sha256(secret.encode()).hexdigest())
    path = directory / (task_id + '.json')
    with path.open('x') as stream:
        os.chmod(path, 0o600)
        json.dump(claim, stream)
    return task_id + '.' + secret


def verify(token, owner, root=ROOT):
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}\.[a-f0-9]{64}', token):
        raise PermissionError('Hosting requires an active LAN/Full task capability')
    task_id, secret = token.split('.')
    try:
        claim = json.loads((root / 'hosting-capabilities' / (task_id + '.json')).read_text())
    except (OSError, ValueError):
        raise PermissionError('Hosting task capability has expired') from None
    if (claim['owner'] != owner or claim['expires'] < time.time() or
            not secrets.compare_digest(claim['digest'], hashlib.sha256(secret.encode()).hexdigest())):
        raise PermissionError('Invalid hosting task capability')
    return claim


def revoke(task_id, root=ROOT):
    if task_common.SAFE_TASK.fullmatch(task_id):
        (root / 'hosting-capabilities' / (task_id + '.json')).unlink(missing_ok=True)
