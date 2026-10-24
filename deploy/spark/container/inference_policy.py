"""Root-managed, account-bound approval for private-data model inference.

This enforces route approval, not provider compliance or general network DLP.
No approval is inferred from a configured credential or a model's name.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

POLICY_PATH = Path('/etc/prime-agent/inference-policy.json')
SUPPORTED_EXTERNAL = {'openai-codex'}


def approvals(owner, now=None):
    try:
        fd = os.open(POLICY_PATH, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 1048576:
                return {}
            data = json.load(stream)
        if data.get('version') != 1:
            return {}
        rows = data.get('owners', {}).get(owner, {})
        result = {}
        for provider, row in rows.items():
            if provider not in SUPPORTED_EXTERNAL or not isinstance(row, dict):
                continue
            models = row.get('models')
            if (row.get('noTraining') is not True or
                    not isinstance(row.get('reviewedUntil'), (float, int)) or
                    not (now if now is not None else time.time()) < row['reviewedUntil'] < float('inf') or
                    not re.fullmatch(r'[0-9a-f]{64}', str(row.get('accountIdSha256', ''))) or
                    not isinstance(row.get('evidence'), str) or not row['evidence'].strip() or
                    not isinstance(models, list) or not 1 <= len(models) <= 64 or
                    any(not isinstance(m, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', m) for m in models)):
                continue
            result[provider] = row
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def approved_models(owner, provider, account_id):
    row = approvals(owner).get(provider, {})
    fingerprint = hashlib.sha256(str(account_id).encode()).hexdigest()
    if not account_id or row.get('accountIdSha256') != fingerprint:
        return []
    return list(row.get('models', []))
