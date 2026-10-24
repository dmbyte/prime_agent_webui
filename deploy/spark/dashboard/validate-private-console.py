#!/usr/bin/env python3
"""Real Chromium/HTTPS and PTY tests; only temporary synthetic credentials.

Requires playwright and cryptography. PRIME_TEST_CHROME selects a local browser.
The test trusts only its ephemeral certificate's SPKI in its own browser. This
test-only launch patch is never installed in a connection worker or task image.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import time
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from playwright.sync_api import BrowserType
from connection_browser_worker import Browser
import connection_sol

SECRET = 'synthetic-console'


def main():
    with tempfile.TemporaryDirectory(prefix='prime-private-console-test-') as directory:
        root = Path(directory)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Prime synthetic console fixture')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                                                       x509.DNSName('localhost')]), critical=False)
            .sign(key, hashes.SHA256()))
        (root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        spki = base64.b64encode(hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)).digest()).decode()
        events = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def answer(self, code, body, content_type='text/html', cookie=False):
                raw = body.encode(); self.send_response(code)
                self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(raw)))
                if cookie: self.send_header('Set-Cookie', 'session=synthetic-private-cookie; Secure; HttpOnly; SameSite=Strict')
                self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if self.path == '/':
                    self.answer(200, '''<input type=text><input type=password><button onclick="fetch('/login',{method:'POST',body:JSON.stringify({username:document.querySelector('input[type=text]').value,password:document.querySelector('input[type=password]').value})}).then(r=>{if(r.ok)location='/home'})">Log In</button>''')
                elif self.path in ('/home', '/console') and 'session=synthetic-private-cookie' in self.headers.get('Cookie', ''):
                    canvas = '''<canvas width=640 height=360 tabindex=0></canvas><script>const c=document.querySelector('canvas'); c.getContext('2d').fillText('Synthetic boot screen',20,40); c.addEventListener('keydown',e=>fetch('/event',{method:'POST',body:JSON.stringify({key:e.key})}));</script>'''
                    self.answer(200, ('<a href="/console">HTML5 Console</a>' if self.path == '/home' else canvas)+f'<img src="https://localhost:{self.server.server_port}/escape">')
                else:
                    events.append('unexpected-request:'+self.path); self.answer(404, '')
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.path == '/login':
                    assert json.loads(body) == {'username': 'fixture', 'password': SECRET}
                    self.answer(200, '{}', 'application/json', cookie=True)
                elif self.path == '/event':
                    events.append(json.loads(body)['key']); self.answer(200, '{}', 'application/json')
                else: self.answer(404, '')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(root/'cert.pem', root/'key.pem')
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        original_launch = BrowserType.launch
        def fixture_launch(browser_type, **options):
            options['executable_path'] = os.environ.get('PRIME_TEST_CHROME', '/usr/bin/chromium')
            options['args'] += ['--ignore-certificate-errors-spki-list='+spki]
            return original_launch(browser_type, **options)
        try:
            with mock.patch.object(BrowserType, 'launch', fixture_launch):
                for kind in ('browser', 'kvm'):
                    payload = {'kind': kind, 'endpoint': f'https://127.0.0.1:{server.server_port}', 'username': 'fixture', 'password': SECRET}
                    browser = Browser(payload)
                    try:
                        assert payload == {}, 'Login payload retained'
                        capture = browser.call({'action': 'capture'})
                        assert base64.b64decode(capture['image']).startswith(b'\x89PNG')
                        assert SECRET not in json.dumps(capture) and 'synthetic-private-cookie' not in json.dumps(capture)
                        for action in ('evaluate', 'cookies', 'storage', 'goto', 'request'):
                            try: browser.call({'action': action})
                            except ValueError: pass
                            else: raise AssertionError('Arbitrary browser operation exposed')
                        if kind == 'kvm':
                            browser.call({'action': 'input', 'key': 'f9'})
                            browser.page.wait_for_timeout(300)
                            assert 'F9' in events, 'Console key not delivered'
                        browser.page.goto(f'https://127.0.0.1:{server.server_port}')
                        try: browser.call({'action': 'capture'})
                        except ValueError: pass
                        else: raise AssertionError('Login screen captured')
                        assert 'unexpected-request:/escape' not in events, 'Cross-origin subresource escaped'
                    finally: browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()
        print('PASS: real HTTPS login/capture, isolated cookie, KVM input, cross-origin denial and login-screen withholding')

    # An actual PTY process replaces ipmitool only inside this synthetic test.
    child = "import os,sys,time; print('boot '+os.environ['IPMI_PASSWORD']+' ready',flush=True); v=sys.stdin.buffer.read(1); print('key accepted',flush=True); time.sleep(30)"
    values = {'endpoint': 'https://192.168.1.4', 'username': 'fixture', 'password': SECRET}
    with mock.patch.object(connection_sol, 'command', return_value=[sys.executable, '-u', '-c', child]):
        sol = connection_sol.SOL(values)
        process = sol.process
        try:
            time.sleep(.3)
            result = sol.read(); assert SECRET not in result['text']
            sol.send({'sessionId': 'fixture', 'requestId': 'a'*32, 'key': 'enter'})
            time.sleep(.3); result = sol.read()
            assert '[credential withheld]' in result['text'] and SECRET not in result['text']
        finally: sol.close()
        assert process.poll() is not None
    print('PASS: real SOL PTY, split-secret filter, input and child cleanup; no BMC contacted')


if __name__ == '__main__': main()
