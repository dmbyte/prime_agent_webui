"""Task/owner/connection-bound console leases, with continuous revocation checks."""
import hashlib
import json
import re
import threading
import time

from connection_approvals import Approvals
from connection_browser import BrowserSession
import connection_sol


class Sessions:
    def __init__(self, manager, native, browser_factory=BrowserSession, sol_factory=connection_sol.SOL):
        self.manager, self.native = manager, native
        self.browser_factory, self.sol_factory = browser_factory, sol_factory
        self.approvals = Approvals(manager.root)
        self.sessions = {}
        self.lock = threading.RLock()

    def valid(self, session):
        claim = self.manager.verify(session['token'], session['owner'])
        row = self.manager.store._load(session['owner']).get(session['connection'], {})
        return (row.get('revision') == session['revision'] and time.time() < session['expiresAt']
                and time.monotonic()-session['lastUse'] < 300
                and self.manager.eligible(session['owner'], row, claim['projectId']))

    def reap(self, all_sessions=False):
        with self.lock:
            for key, session in list(self.sessions.items()):
                try:
                    valid = not all_sessions and self.valid(session)
                except Exception:
                    valid = False
                if not valid:
                    self.close(key)

    def close(self, key):
        session = self.sessions[key]
        try:
            session['worker'].close()
        finally:
            del self.sessions[key]

    def dispatch(self, request, owner, claim, row, values):
        operation, arguments = request['operation'], request.get('arguments', {})
        if not isinstance(arguments, dict):
            raise ValueError('Invalid console arguments')
        family, action = operation.split('.')
        if family == 'ipmi':
            if action != 'status' or arguments:
                raise ValueError('Unsupported IPMI operation')
            return connection_sol.status(values)
        with self.lock:
            self.reap()
            if action == 'open':
                if (set(arguments) != {'requestId'} or not isinstance(arguments['requestId'], str)
                        or not re.fullmatch(r'[a-f0-9]{32}', arguments['requestId'])):
                    raise ValueError('Open needs a unique 32-hex requestId')
                key = 'pc-'+hashlib.sha256(json.dumps([owner, claim['taskId'], request['connection'],
                                                     family, arguments['requestId']]).encode()).hexdigest()[:16]
                if key in self.sessions:
                    return {'sessionId': key, 'reused': True}
                if len(self.sessions) >= 4 or sum(s['owner'] == owner for s in self.sessions.values()) >= 2:
                    raise ValueError('Private console capacity reached; reuse or close a session')
                if family == 'sol':
                    pending = self.approvals.require(owner, claim, request['connection'], row, operation, arguments)
                    if pending:
                        return pending
                expiry = min(time.time()+3600, claim['expiresAt'], row['expiresAt'])
                worker = self.sol_factory(values) if family == 'sol' else self.browser_factory(self.native, key, values, family, expiry)
                self.sessions[key] = dict(owner=owner, token=request['token'], taskId=claim['taskId'],
                    connection=request['connection'], revision=row['revision'], family=family,
                    worker=worker, expiresAt=expiry, lastUse=time.monotonic())
                try:
                    valid = self.valid(self.sessions[key])
                except Exception:
                    valid = False
                if not valid:
                    self.close(key)
                    raise PermissionError('Console grant changed while opening')
                return {'sessionId': key, 'expiresAt': expiry, 'idleTimeoutSeconds': 300}
            key = arguments.get('sessionId')
            if not isinstance(key, str):
                raise ValueError('Session ID required')
            session = self.sessions.get(key)
            if (not session or session['owner'] != owner or session['taskId'] != claim['taskId']
                    or session['connection'] != request['connection'] or session['family'] != family):
                raise PermissionError('Console does not belong to this task and connection')
            if action in ('capture', 'read', 'close'):
                if set(arguments) != {'sessionId'}:
                    raise ValueError('Unexpected console arguments')
                if action == 'close':
                    self.close(key)
                    return {'closed': True}
                result = session['worker'].read()
            elif action == 'input' and family in ('kvm', 'sol'):
                connection_sol.validate_input(arguments)
                pending = self.approvals.require(owner, claim, request['connection'], row, operation, arguments)
                if pending:
                    return pending
                # User approval is not a substitute for checking a still-valid grant.
                if not self.valid(session):
                    self.close(key)
                    raise PermissionError('Console grant changed before input')
                result = session['worker'].send(arguments)
            else:
                raise ValueError('Unsupported console operation')
            session['lastUse'] = time.monotonic()
            if not self.valid(session):
                self.close(key)
                raise PermissionError('Console grant changed during operation')
            return result
