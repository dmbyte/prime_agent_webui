"""Bounded, owner-workspace console snapshots. No control commands or history."""
import base64
import json
import math
import os
import re
import stat
import time
import threading
import uuid
from pathlib import Path

MAX_BYTES = 2_800_000
ID = re.compile(r"[a-f0-9]{32}")


def directory(root, create=False):
    root = Path(root)
    if create:
        root.mkdir(mode=0o770, parents=False, exist_ok=True)
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def read_record(fd, name):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(handle, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Invalid console snapshot")
        row = json.loads(stream.read(MAX_BYTES + 1))
    if not isinstance(row, dict) or not ID.fullmatch(str(row.get("id", ""))) or name != row['id'] + '.json':
        raise ValueError("Invalid console snapshot identity")
    return row


def watch(root):
    fd = directory(root, create=True)
    try:
        handle = os.open('.watch', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o660, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(handle).st_mode):
                raise ValueError("Invalid viewer heartbeat")
            # The dashboard and runner share this file through workspace ACLs.
            # Neither may chmod a heartbeat created by the other identity.
            os.utime(handle, None)
        finally:
            os.close(handle)
    finally:
        os.close(fd)


def snapshots(root, selected=None):
    if selected is not None and not ID.fullmatch(str(selected)):
        raise ValueError("Invalid console identifier")
    try:
        fd = directory(root)
    except FileNotFoundError:
        return []
    try:
        rows = []
        names = [selected + '.json'] if selected else sorted(os.listdir(fd))[:128]
        for name in names:
            if not re.fullmatch(r'[a-f0-9]{32}\.json', name):
                continue
            try:
                row = read_record(fd, name)
                timestamp = float(row['updatedAt'])
                if not math.isfinite(timestamp) or row.get('kind') not in {'browser', 'kvm', 'serial'}:
                    continue
                age = max(0, time.time() - timestamp)
                if age > 3600:
                    continue
                clean = {k: row.get(k) for k in ('id', 'kind', 'title', 'taskId', 'state', 'updatedAt', 'frameAt')}
                clean['title'] = str(clean.get('title') or row['kind'])[:120]
                clean['stale'] = age > 15
                if selected:
                    encoded = row.get('image')
                    if encoded:
                        data = base64.b64decode(encoded, validate=True)
                        if len(data) > 2_000_000 or not data.startswith(b'\xff\xd8'):
                            raise ValueError('Invalid console image')
                        clean['image'] = encoded
                    clean['text'] = str(row.get('text') or '')[:20000]
                rows.append(clean)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(rows, key=lambda r: float(r['updatedAt']), reverse=True)[:32]
    finally:
        os.close(fd)


class ConsoleFeed:
    def __init__(self, kind, title, *, root=None, session_id=None):
        self.root = Path(root or os.environ.get('PRIME_CONSOLE_FEED_DIR', '/project/.prime-console'))
        self.id = session_id or uuid.uuid4().hex
        self._closed = False
        self._lock = threading.RLock()
        if not ID.fullmatch(self.id):
            raise ValueError('Invalid console identifier')
        task = os.environ.get('PRIME_TASK_ID', '')
        self.row = dict(id=self.id, kind=kind, title=str(title)[:120], taskId=task if ID.fullmatch(task) else None,
                        state='active', frameAt=None, image=None, text='')
        self.update()

    def watched(self):
        try:
            fd = directory(self.root)
            try:
                info = os.stat('.watch', dir_fd=fd, follow_symlinks=False)
                return stat.S_ISREG(info.st_mode) and time.time() - info.st_mtime < 5
            finally:
                os.close(fd)
        except OSError:
            return False

    def update(self, *, image=None, text=None, state='active'):
        with self._lock:
            if not self._closed or state == 'closed':
                self._update(image=image, text=text, state=state)

    def _update(self, *, image=None, text=None, state='active'):
        # Viewing must never break an agent operation, including standalone use.
        try:
            self.row.update(state=state, updatedAt=time.time())
            if image is not None:
                if len(image) > 2_000_000 or not image.startswith(b'\xff\xd8'):
                    return
                self.row.update(image=base64.b64encode(image).decode(), frameAt=time.time())
            if text is not None:
                self.row.update(text=str(text)[:20000], frameAt=time.time())
            if state == 'closed' or (self.row['kind'] != 'serial' and not self.watched()):
                self.row.update(image=None, text='')
            data = json.dumps(self.row, separators=(',', ':')).encode()
            if len(data) > MAX_BYTES:
                return
            fd = directory(self.root, create=True)
            temp = '.' + uuid.uuid4().hex
            try:
                # Only bounded latest snapshots are retained; never a recording.
                for name in os.listdir(fd):
                    if re.fullmatch(r'[a-f0-9]{32}\.json', name):
                        if time.time() - os.stat(name, dir_fd=fd, follow_symlinks=False).st_mtime > 3600:
                            os.unlink(name, dir_fd=fd)
                if len(os.listdir(fd)) > 64 and not os.path.exists(self.root / (self.id + '.json')):
                    return
                handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660, dir_fd=fd)
                with os.fdopen(handle, 'wb') as stream:
                    os.fchmod(stream.fileno(), 0o660)
                    stream.write(data)
                os.replace(temp, self.id + '.json', src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try: os.unlink(temp, dir_fd=fd)
                except FileNotFoundError: pass
                os.close(fd)
        except (OSError, ValueError, TypeError):
            pass

    def close(self):
        with self._lock:
            self._closed = True
            self.update(state='closed')
