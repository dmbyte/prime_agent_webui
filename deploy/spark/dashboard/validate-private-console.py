#!/usr/bin/env python3
"""Real Chromium/HTTPS and PTY tests; only temporary synthetic credentials.

Requires playwright and cryptography. PRIME_TEST_CHROME selects a local browser.
The test uses an expired self-signed certificate: strict mode must reject it,
and only the saved-credential exception may permit the isolated test login.
"""
import base64
from datetime import datetime, timedelta, timezone
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
import connections

SECRET = 'synthetic-console'


def main():
    with tempfile.TemporaryDirectory(prefix='prime-private-console-test-') as directory:
        root = Path(directory)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Prime synthetic console fixture')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2))
            .not_valid_after(now-timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                                                       x509.DNSName('localhost')]), critical=False)
            .sign(key, hashes.SHA256()))
        (root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        events = []
        inline_console = False
        profile = 'generic-html5'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def answer(self, code, body, content_type='text/html', cookie=False):
                raw = body.encode(); self.send_response(code)
                self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(raw)))
                if cookie: self.send_header('Set-Cookie', 'session=synthetic-private-cookie; Secure; HttpOnly; SameSite=Strict')
                self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if self.path == '/data':
                    self.answer(200, '{"fixture":true}', 'application/json')
                elif self.path == '/' and inline_console:
                    self.answer(200, '<iframe src="/login-form" width="1000" height="600"></iframe>')
                elif self.path in ('/', '/login-form'):
                    self.answer(200, '''<input type=text><input type=password><button onclick="fetch('/login',{method:'POST',body:JSON.stringify({username:document.querySelector('input[type=text]').value,password:document.querySelector('input[type=password]').value})}).then(r=>{if(r.ok)location='/home'})">Log In</button>''')
                elif self.path in ('/home', '/console', '/console-settings') and 'session=synthetic-private-cookie' in self.headers.get('Cookie', ''):
                    canvas = '''<canvas id=console width=640 height=360 tabindex=0></canvas><script>const c=document.querySelector('#console'); c.getContext('2d').fillText('Synthetic boot screen',20,40); c.addEventListener('keydown',e=>fetch('/event',{method:'POST',body:JSON.stringify({key:e.key})}));</script>'''
                    if profile == 'video':
                        canvas = '''<canvas id=source width=640 height=360 style="display:none"></canvas><video id=console width=640 height=360 muted autoplay tabindex=0></video><script>const c=document.querySelector('#source'),v=document.querySelector('#console'); c.getContext('2d').fillText('Synthetic video console',20,40);v.srcObject=c.captureStream(5);v.play();v.addEventListener('keydown',e=>fetch('/event',{method:'POST',body:JSON.stringify({key:e.key})}));</script>'''
                    label, title = {'generic-html5': ('HTML5 Console', 'Synthetic appliance'),
                        'hpe-ilo': ('HTML5', 'HPE iLO 5'),
                        'dell-idrac': ('Launch Virtual Console', 'Dell iDRAC9'),
                        'supermicro': ('Launch Console', 'Supermicro BMC'),
                        'lenovo-xcc': ('Launch Remote Console', 'Lenovo XClarity Controller'),
                        'dell-popup': ('Start the Virtual Console', 'Dell iDRAC9'),
                        'dell-navigation': ('Launch Virtual Console', 'Dell iDRAC9')}.get(profile, ('HTML5 Console', 'Synthetic appliance'))
                    content = f'<a href="/console">{label}</a>' if self.path != '/console' else canvas
                    if profile == 'dell-popup' and self.path == '/home':
                        content = f'<button onclick="window.open(\'/console\')">{label}</button>'
                    if profile == 'dell-navigation' and self.path == '/home':
                        content = '<a href="/console-settings">Virtual Console</a>'
                    if inline_console and self.path == '/home':
                        content = ('<canvas id=chart width=640 height=360></canvas><button onclick="document.querySelector(\'#console\').style.display=\'block\'">HTML5 Console</button>'
                            +canvas.replace('id=console ', 'id=console style="display:none" '))
                    self.answer(200, '<title>'+title+'</title><h1>'+title+'</h1>'+content+f'<img src="https://localhost:{self.server.server_port}/escape">')
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
            return original_launch(browser_type, **options)
        try:
            https_init = connections.http.client.HTTPSConnection.__init__
            def fixture_https(instance, host, port, **options):
                https_init(instance, '127.0.0.1', server.server_port, **options)
            with mock.patch.object(connections.http.client.HTTPSConnection, '__init__', fixture_https):
                for ignored in (False, True, False):
                    try:
                        data = connections.get_json('https://127.0.0.1', '/data', {}, ignore_certificate_errors=ignored)
                    except ssl.SSLCertVerificationError:
                        assert not ignored
                    else:
                        assert ignored and data == {'fixture': True}
            with mock.patch.object(BrowserType, 'launch', fixture_launch):
                try:
                    strict = Browser({'kind': 'browser', 'endpoint': f'https://127.0.0.1:{server.server_port}', 'username': 'fixture', 'password': SECRET})
                except Exception as error:
                    assert 'ERR_CERT' in str(error), 'Strict browser failed for a non-certificate reason'
                else:
                    strict.close(); raise AssertionError('Strict browser accepted invalid certificate')
                for variant in ('browser', 'kvm', 'kvm-inline', 'hpe-ilo', 'dell-idrac', 'supermicro', 'lenovo-xcc', 'dell-popup', 'dell-navigation', 'video'):
                    inline_console = variant == 'kvm-inline'
                    kind = 'browser' if variant == 'browser' else 'kvm'
                    profile = variant if variant in ('hpe-ilo', 'dell-idrac', 'supermicro', 'lenovo-xcc', 'dell-popup', 'dell-navigation', 'video') else 'generic-html5'
                    payload = {'kind': kind, 'endpoint': f'https://127.0.0.1:{server.server_port}', 'username': 'fixture', 'password': SECRET, 'ignoreCertificateErrors': True}
                    browser = Browser(payload)
                    try:
                        assert payload == {}, 'Login payload retained'
                        capture = browser.call({'action': 'capture'})
                        info = browser.call({'action': 'info'})
                        expected_family = 'generic-html5' if profile == 'video' else 'dell-idrac' if profile.startswith('dell-') else profile
                        assert info['vendorFamily'] == expected_family
                        assert info['consoleReady'] == (kind == 'kvm')
                        assert info['hardwareCertified'] is False
                        if profile == 'video': assert info['renderer'] == 'video'
                        assert base64.b64decode(capture['image']).startswith(b'\x89PNG')
                        assert SECRET not in json.dumps(capture) and 'synthetic-private-cookie' not in json.dumps(capture)
                        for action in ('evaluate', 'cookies', 'storage', 'goto', 'request'):
                            try: browser.call({'action': action})
                            except ValueError: pass
                            else: raise AssertionError('Arbitrary browser operation exposed')
                        if kind == 'kvm':
                            before = events.count('F9')
                            browser.call({'action': 'input', 'key': 'f9'})
                            browser.page.wait_for_timeout(300)
                            assert events.count('F9') == before+1, 'Console key not delivered exactly once'
                        browser.page.goto(f'https://127.0.0.1:{server.server_port}')
                        try: browser.call({'action': 'capture'})
                        except ValueError: pass
                        else: raise AssertionError('Login screen captured')
                        assert 'unexpected-request:/escape' not in events, 'Cross-origin subresource escaped'
                    finally: browser.close()
                    print('PASS: synthetic browser layout '+variant, flush=True)
        finally:
            server.shutdown(); server.server_close(); thread.join()
        print('PASS: direct/browser strict TLS rejection and per-credential exception, login/capture, isolated cookie, KVM input, cross-origin denial and login-screen withholding')

    # An actual PTY process replaces ipmitool only inside this synthetic test.
    child = "import os,sys,time; print('[SOL Session operational. Use ~? for help]'); print('boot '+os.environ['IPMI_PASSWORD']+' ready',flush=True); v=sys.stdin.buffer.read(1); print('key accepted',flush=True); time.sleep(30)"
    values = {'endpoint': 'https://192.168.1.4', 'username': 'fixture', 'password': SECRET}
    with mock.patch.object(connection_sol, 'command', return_value=[sys.executable, '-u', '-c', child]):
        sol = connection_sol.SOL(values)
        process = sol.process
        try:
            time.sleep(.3)
            result = sol.read(); assert SECRET not in result['text'] and result['connected'] and result['active']
            sol.send({'sessionId': 'fixture', 'requestId': 'a'*32, 'key': 'enter'})
            time.sleep(.3); result = sol.read()
            assert '[credential withheld]' in result['text'] and SECRET not in result['text']
        finally: sol.close()
        assert process.poll() is not None
    print('PASS: real SOL PTY, split-secret filter, input and child cleanup; no BMC contacted')


if __name__ == '__main__': main()
