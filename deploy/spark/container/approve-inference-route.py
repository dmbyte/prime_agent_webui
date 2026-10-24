#!/usr/bin/env python3
"""Administrator attestation for the existing protected Codex OAuth route.

Does not inspect account training settings or guarantee provider compliance.
Run only after independently reviewing the actual account and applicable terms.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--review-days', type=int, default=30)
    parser.add_argument('--evidence', default='')
    parser.add_argument('--confirm-no-training', action='store_true')
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as administrator, outside task sandboxes')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{2,32}', args.owner):
        parser.error('Invalid owner')
    if not args.revoke and (not args.confirm_no_training or not args.evidence.strip() or
            len(args.evidence) > 1000 or not 1 <= args.review_days <= 90 or
            not 1 <= len(args.model) <= 64 or
            any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', m) for m in args.model)):
        parser.error('Require exact models, reviewed no-training confirmation, non-secret evidence, and 1-90 review days')
    path = Path('/etc/prime-agent/inference-policy.json')
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        parser.error('Unsafe policy directory')
    data = {'version': 1, 'owners': {}}
    if path.exists() or path.is_symlink():
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 1048576:
                parser.error('Unsafe policy file')
            data = json.load(stream)
        if data.get('version') != 1 or not isinstance(data.get('owners'), dict):
            parser.error('Unsupported policy schema')
    owner = data['owners'].setdefault(args.owner, {})
    if args.revoke:
        owner.pop('openai-codex', None)
    else:
        root = Path('/var/lib/prime-runner/credentials')
        auth_path = root / 'users' / args.owner / 'auth.json'
        if not auth_path.exists():
            auth_path = root / 'global/auth.json'
        with os.fdopen(os.open(auth_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))) as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != pwd.getpwnam('prime-runner').pw_uid
                    or info.st_mode & 0o077 or info.st_size > 1048576):
                parser.error('Unsafe credential file')
            account = (json.load(stream).get('openai-codex') or {}).get('accountId')
        if not isinstance(account, str) or not account:
            parser.error('No installed Codex account')
        owner['openai-codex'] = {
            'accountIdSha256': hashlib.sha256(account.encode()).hexdigest(),
            'models': sorted(set(args.model)), 'noTraining': True,
            'reviewedUntil': time.time() + args.review_days * 86400,
            'evidence': args.evidence.strip(),
        }
    # Keep the previous root-only policy, not any provider credential, for recovery.
    if path.exists():
        backup = path.with_name('inference-policy.before-' + str(time.time_ns()) + '.json')
        with backup.open('x') as stream:
            os.chmod(backup, 0o600)
            stream.write(path.read_text())
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print('Inference route approval revoked.' if args.revoke else 'Inference route approval recorded; gateway rechecks it on each new request.')


if __name__ == '__main__':
    main()
