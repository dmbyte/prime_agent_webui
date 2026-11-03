"""Host-only admission barrier shared by every Prime OpenShell producer.

The provisioned inode must never be replaced while services run. Shared leases
cover startup (and the complete task launcher); the updater takes an exclusive
lease before its final inventory check. Missing/unreadable locks fail closed.
"""
from contextlib import contextmanager
import fcntl
from functools import wraps
import os
import stat

LOCK = '/var/lib/prime-runner/openshell-maintenance.lock'


@contextmanager
def admission():
    path = os.environ.get('PRIME_MAINTENANCE_LOCK', LOCK)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise RuntimeError('OpenShell maintenance guard unavailable; contact an administrator') from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError('Invalid OpenShell maintenance guard')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('OpenShell maintenance is in progress; retry when the update completes') from None
        yield
    finally:
        os.close(fd)


def admitted(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with admission():
            return function(*args, **kwargs)
    return guarded
