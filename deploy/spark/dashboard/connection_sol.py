"""Trusted host IPMI/SOL driver. Fixed lanplus commands; never task-side UDP."""
import codecs
import os
import pty
import re
import select
import signal
import subprocess
import time
import tty
from urllib.parse import urlsplit

KEYS = {'enter': b'\r', 'escape': b'\x1b', 'tab': b'\t', 'backspace': b'\x7f',
        'up': b'\x1b[A', 'down': b'\x1b[B', 'right': b'\x1b[C', 'left': b'\x1b[D',
        'f1': b'\x1bOP', 'f2': b'\x1bOQ', 'f9': b'\x1b[20~', 'f10': b'\x1b[21~', 'f11': b'\x1b[23~', 'f12': b'\x1b[24~'}


class IPMIUnavailable(RuntimeError):
    """Public fixed diagnostic, never an upstream message or credential."""


def status_failure(stderr, cipher=17):
    text = stderr.decode('utf8', 'replace').lower()
    if any(marker in text for marker in ('no matching cipher', 'invalid cipher', 'invalid integrity', 'no matching authentication', 'no matching integrity')):
        return 'BMC does not accept selected IPMI cipher '+str(cipher)+'; no fallback attempted'
    if 'unauthorized' in text or 'rakp 2 hmac is invalid' in text or 'invalid user' in text:
        return 'BMC rejected IPMI authentication; verify the saved login and IPMI privileges'
    if 'privilege' in text:
        return 'BMC rejected the requested IPMI privilege level'
    return 'Secure IPMI session unavailable; check UDP 623, selected cipher and BMC account access'


def filter_stream(text, secret):
    boundary = max(0, len(text)-len(secret)+1)
    start = text.find(secret)
    while start >= 0:
        if start < boundary < start+len(secret):
            boundary = start
            break
        start = text.find(secret, start+1)
    return text[:boundary].replace(secret, '[credential withheld]'), text[boundary:]


def validate_input(arguments):
    if set(arguments) == {'sessionId', 'requestId', 'key'} and isinstance(arguments['key'], str) and arguments['key'] in KEYS:
        return KEYS[arguments['key']]
    value = arguments.get('text')
    if (set(arguments) == {'sessionId', 'requestId', 'text'} and isinstance(value, str)
            and 1 <= len(value) <= 256 and all(32 <= ord(c) <= 126 and c != '~' for c in value)):
        return value.encode()
    raise ValueError('Use one named console key or 1–256 printable characters; no control/escape sequences')


def command(values, *operation):
    username, password = values.get('username'), values.get('password')
    cipher = values.get('ipmiCipherSuite', 17)
    if type(cipher) is not int or cipher not in (17, 3):
        raise ValueError('Unsupported saved IPMI cipher')
    if (not isinstance(username, str) or not 1 <= len(username) <= 16 or any(ord(c) < 33 or ord(c) > 126 for c in username)
            or not isinstance(password, str) or not 1 <= len(password.encode()) <= 20 or '\x00' in password):
        raise ValueError('IPMI username/password exceeds supported protocol bounds')
    # Username is visible to trusted host admins in argv; password never is.
    return ['/usr/bin/ipmitool', '-I', 'lanplus', '-C', str(cipher), '-H', urlsplit(values['endpoint']).hostname,
            '-U', username, '-E', '-N', '2', '-R', '1', *operation]


def environment(values):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'IPMI_PASSWORD': values['password']}


def status(values):
    # No raw output, BMC identifiers, secrets, or arbitrary command arguments.
    try:
        result = subprocess.run(command(values, 'chassis', 'power', 'status'), env=environment(values),
                                capture_output=True, timeout=15)
        if result.returncode:
            raise IPMIUnavailable(status_failure(result.stderr, values.get('ipmiCipherSuite', 17)))
        text = result.stdout.decode().strip().lower()
        if text not in ('chassis power is on', 'chassis power is off'):
            raise ValueError()
        return {'powerState': 'On' if text.endswith(' on') else 'Off'}
    except IPMIUnavailable:
        raise
    except Exception:
        raise IPMIUnavailable('IPMI status unavailable; check access and LAN transport') from None


class SOL:
    def __init__(self, values):
        self.process = None
        self.master = None
        self.password = values['password']
        self.tail, self.screen = '', ''
        self.connected = False
        self.handshake_tail = ''
        self.decoder = codecs.getincrementaldecoder('utf8')('replace')
        argv = command(values, 'sol', 'activate')
        master, slave = pty.openpty()
        try:
            tty.setraw(slave)
            self.process = subprocess.Popen(argv, env=environment(values), stdin=slave, stdout=slave, stderr=slave,
                                            start_new_session=True, close_fds=True)
            self.master = master
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)

    def read(self):
        if self.master is None:
            raise ValueError('SOL closed')
        collected = b''
        while len(collected) < 16384 and select.select([self.master], [], [], 0)[0]:
            try:
                chunk = os.read(self.master, min(4096, 16384-len(collected)))
            except OSError:
                break
            if not chunk:
                break
            collected += chunk
        # Hold the longest possible split secret suffix until the next read.
        decoded = self.decoder.decode(collected)
        self.handshake_tail = (self.handshake_tail+decoded)[-128:] if not self.connected else ''
        if '[SOL Session operational.' in self.handshake_tail:
            self.connected = True
            self.handshake_tail = ''
        text = self.tail+decoded
        safe, self.tail = filter_stream(text, self.password)
        safe = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', safe)
        safe = ''.join(c for c in safe if ord(c) >= 32 or c in '\n\r\t')
        self.screen = (self.screen+safe)[-32768:]
        # A spawned ipmitool process is not proof that the SOL handshake worked.
        active = self.process.poll() is None
        return {'text': self.screen, 'active': active, 'connected': active and self.connected}

    def send(self, arguments):
        data = validate_input(arguments)
        if self.master is None or self.process.poll() is not None or not self.connected:
            raise ValueError('SOL is not connected; read and verify activation before input')
        while data:
            data = data[os.write(self.master, data):]
        return {'sent': True}

    def close(self):
        if self.master is None:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        finally:
            os.close(self.master)
            self.master, self.password, self.tail, self.screen = None, '', '', ''
            self.handshake_tail = ''
        # Never issue global `sol deactivate`: that can evict another viewer.
