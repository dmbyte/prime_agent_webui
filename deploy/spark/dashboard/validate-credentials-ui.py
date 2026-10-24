#!/usr/bin/env python3
"""Real browser + real credential HTTP/store, synthetic two-user data only.

Run with Python cryptography/playwright installed. Optionally set
PRIME_TEST_CHROME to a Chromium executable; no production services are contacted.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright
import skill_credentials

root = Path(__file__).parent
spec = importlib.util.spec_from_file_location('credential_browser_auth', root/'auth.py')
auth = importlib.util.module_from_spec(spec); spec.loader.exec_module(auth)


def main():
    os.environ['PRIME_CREDENTIALS_ENABLED'] = '1'  # Isolated loopback fixture only.
    with tempfile.TemporaryDirectory(prefix='prime-credential-browser-') as directory:
        home = Path(directory); agent = home/'.prime/agent'; agent.mkdir(parents=True)
        declaration = {'id': 'login', 'label': 'Service login', 'fields': [
            {'id': 'username', 'label': 'Username'}, {'id': 'token', 'label': 'Token'}]}
        skills = {owner: {'owner': owner, 'status': 'installed', 'enabled': True, 'name': 'Fixture skill',
                          'credentialRequirements': [declaration]} for owner in ['alice', 'bob']}
        (agent/'webui-metadata.json').write_text(json.dumps({'skills': skills}))
        auth.credential_path = lambda: home/'web-auth.json'
        auth.load_users = lambda: {'users': {'alice': {'enabled': True}, 'bob': {'enabled': True}}}
        auth._credential_module = skill_credentials
        catalog = skill_credentials.catalog
        skill_credentials.catalog = lambda owner: catalog(owner, home)
        for owner in ['alice', 'bob']:
            auth.SESSIONS[owner] = {'user': owner, 'role': 'user', 'csrf': owner+'-csrf',
                                    'seen': time.time(), 'persisted': time.time(), 'expires': time.time()+3600}

        class Handler(auth.Handler):
            def do_GET(self):
                if self.path == '/':
                    body = b'<!DOCTYPE html><html><head><title>Credential fixture</title></head><body><button data-panel="settings">Settings</button><main><details data-collapse-key="settings-account"><summary>Account</summary></details></main><script src="/credentials.js"></script></body></html>'
                    self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers(); self.wfile.write(body)
                elif self.path == '/credentials.js':
                    self.send_response(200); self.send_header('Content-Type', 'text/javascript; charset=utf-8'); self.end_headers(); self.wfile.write((root/'credentials.js').read_bytes())
                else: super().do_GET()

        server = auth.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                options = {'headless': True}
                if os.environ.get('PRIME_TEST_CHROME'): options['executable_path'] = os.environ['PRIME_TEST_CHROME']
                browser = p.chromium.launch(**options)
                contexts = []
                try:
                    for owner in ['alice', 'bob']:
                        ctx = browser.new_context(); contexts.append(ctx)
                        ctx.add_cookies([{'name': 'prime_session', 'value': owner, 'url': origin},
                                         {'name': 'prime_csrf', 'value': owner+'-csrf', 'url': origin}])
                    alice, bob = [ctx.new_page() for ctx in contexts]
                    for page in [alice, bob]:
                        page.goto(origin); page.get_by_role('button', name='Settings', exact=True).click()
                        page.locator('#credentialSettings summary').click()
                        page.get_by_text('Required values missing', exact=True).wait_for()
                    alice.get_by_label('Username', exact=True).fill('synthetic-user')
                    alice.get_by_label('Token', exact=True).fill('SYNTHETIC_BROWSER_SECRET')
                    with alice.expect_response(lambda response: response.url.endswith('/auth/credentials') and response.request.method == 'POST') as saved:
                        alice.get_by_role('button', name='Save credentials', exact=True).click()
                    assert saved.value.status == 200, 'Synthetic credential save failed'
                    alice.get_by_text('Saved · tool integration pending', exact=True).wait_for()
                    assert alice.get_by_label('Token', exact=True).input_value() == ''
                    assert 'SYNTHETIC_BROWSER_SECRET' not in alice.content()
                    data = alice.evaluate("async()=>await (await fetch('/auth/credentials')).json()")
                    assert 'SYNTHETIC_BROWSER_SECRET' not in json.dumps(data)
                    bob.get_by_role('button', name='Refresh requirements').click()
                    bob.get_by_text('Required values missing', exact=True).wait_for()
                    alice.get_by_role('button', name='Refresh requirements').click()
                    alice.get_by_text('Saved · tool integration pending', exact=True).wait_for()
                    alice.once('dialog', lambda dialog: dialog.accept())
                    alice.get_by_role('button', name='Delete saved values', exact=True).click()
                    alice.get_by_text('Required values missing', exact=True).wait_for()
                    for path in (home/'skill-vault').iterdir():
                        assert b'SYNTHETIC_BROWSER_SECRET' not in path.read_bytes()
                    print('PASS: real browser save/refresh/delete, blank secret inputs, metadata-only responses and two-user isolation')
                finally: browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': main()
