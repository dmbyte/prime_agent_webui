"""Seed reviewed shared packages into each user's own task storage, never another user's files."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid

ROOT = Path('/usr/local/share/prime-agent/shared-skills')


def register(entry, relative):
    if entry.is_symlink():
        old = os.readlink(entry)
        if not re.fullmatch(r'\.\./shared-skills/[a-f0-9]{64}/(?:skills/[a-z0-9-]+|catalogs/nvidia)', old):
            return  # Never replace a personal link.
        if old == str(relative): return
        temporary = entry.with_name('.shared-link-'+uuid.uuid4().hex)
        try:
            temporary.symlink_to(relative); os.replace(temporary, entry)
        finally: temporary.unlink(missing_ok=True)
    elif not entry.exists():
        entry.symlink_to(relative)


def provision(agent, root=ROOT, trusted_uid=0):
    manifest = root/'current.json'
    if not manifest.exists():
        return
    for path in (root, manifest):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != trusted_uid or info.st_mode & 0o022:
            raise ValueError('Unsafe shared skill registry')
    data = json.loads(manifest.read_text())
    generation = data['generation']
    if not re.fullmatch(r'[a-f0-9]{64}', generation):
        raise ValueError('Invalid shared skill generation')
    source = root/generation
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Shared skill source missing')
    destination = agent/'shared-skills'
    destination.mkdir(mode=0o700, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Unsafe user shared skill directory')
    descriptor = os.open(destination/'lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        target = destination/generation
        if target.is_symlink():
            raise ValueError('Unsafe user shared skill generation')
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=destination) as temporary:
                copied = Path(temporary)/'package'
                shutil.copytree(source, copied)
                os.rename(copied, target)
        # Register defaults for normal skill discovery, without replacing personal
        # skills. Explicit project selections use the generation path directly.
        skills = agent/'skills'
        skills.mkdir(mode=0o700, exist_ok=True)
        if skills.is_symlink():
            raise ValueError('Unsafe personal skill registry')
        for folder in sorted((target/'skills').iterdir()):
            entry = skills/folder.name
            register(entry, Path('..')/'shared-skills'/generation/'skills'/folder.name)
        catalog = target/'catalogs/nvidia'
        if catalog.is_dir():
            catalogs = agent/'catalogs'
            catalogs.mkdir(mode=0o700, exist_ok=True)
            if catalogs.is_symlink():
                raise ValueError('Unsafe personal catalog directory')
            entry = catalogs/'nvidia'
            register(entry, Path('..')/'shared-skills'/generation/'catalogs/nvidia')
    finally:
        os.close(descriptor)
