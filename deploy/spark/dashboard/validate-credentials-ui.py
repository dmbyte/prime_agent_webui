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
import connections
from connection_approvals import Approvals

root = Path(__file__).parent
spec = importlib.util.spec_from_file_location('credential_browser_auth', root/'auth.py')
auth = importlib.util.module_from_spec(spec); spec.loader.exec_module(auth)


def main():
    os.environ['PRIME_CREDENTIALS_ENABLED'] = '1'  # Isolated loopback fixture only.
    with tempfile.TemporaryDirectory(prefix='prime-credential-browser-') as directory:
        home = Path(directory); agent = home/'.prime/agent'; agent.mkdir(parents=True)
        declaration = {'id': 'login', 'label': 'Service login', 'adapter': 'github-readonly', 'fields': [
            {'id': 'token', 'label': 'Token'}]}
        skills = {owner: {'owner': owner, 'status': 'installed', 'enabled': True, 'name': 'Fixture skill',
                          'credentialRequirements': [declaration]} for owner in ['alice', 'bob']}
        project_id = 'p_'+'1'*24
        (agent/'webui-metadata.json').write_text(json.dumps({'skills': skills, 'projects': {project_id: {'owner': 'alice', 'name': 'Fixture project'}}}))
        auth.credential_path = lambda: home/'web-auth.json'
        auth.load_users = lambda: {'users': {'alice': {'enabled': True}, 'bob': {'enabled': True}}}
        auth._credential_module = skill_credentials
        catalog = skill_credentials.catalog
        skill_credentials.catalog = lambda owner, *args: catalog(owner, home)
        original_manager = connections.Connections
        connections.Connections = lambda root=None, **kwargs: original_manager(root, home)
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
                    alice.get_by_label('Token', exact=True).fill('SYNTHETIC_BROWSER_SECRET')
                    with alice.expect_response(lambda response: response.url.endswith('/auth/credentials') and response.request.method == 'POST') as saved:
                        alice.get_by_role('button', name='Save credentials', exact=True).click()
                    assert saved.value.status == 200, 'Synthetic credential save failed'
                    alice.get_by_text('Saved · configure access in My connections', exact=True).wait_for()
                    assert alice.get_by_label('Token', exact=True).input_value() == ''
                    assert 'SYNTHETIC_BROWSER_SECRET' not in alice.content()
                    data = alice.evaluate("async()=>await (await fetch('/auth/credentials')).json()")
                    assert 'SYNTHETIC_BROWSER_SECRET' not in json.dumps(data)
                    bob.get_by_role('button', name='Refresh requirements').click()
                    bob.get_by_text('Required values missing', exact=True).wait_for()
                    alice.locator('#connectionSettings summary').first.click()
                    alice.get_by_label('Connection name', exact=True).fill('Fixture connection')
                    alice.get_by_label('Allow use in', exact=True).select_option(project_id)
                    alice.get_by_role('button', name='Add connection', exact=True).click()
                    alice.get_by_text('Fixture connection', exact=True).wait_for()
                    connection_data = alice.evaluate("async()=>await (await fetch('/auth/connections')).json()")
                    assert len(connection_data['connections']) == 1
                    assert connection_data['connections'][0]['projectId'] == project_id
                    assert not connection_data['runtimeEnabled']
                    assert 'SYNTHETIC_BROWSER_SECRET' not in json.dumps(connection_data)
                    bob_data = bob.evaluate("async()=>await (await fetch('/auth/connections')).json()")
                    assert bob_data['connections'] == [] and bob_data['projects'] == []
                    # Exercise the actual authenticated Settings approval path.
                    # This is an isolated UI fixture; it never invokes an adapter.
                    meta = json.loads((agent/'webui-metadata.json').read_text())
                    task_id = 'a'*32
                    meta['tasks'] = {task_id: {'owner': 'alice', 'projectId': project_id, 'status': 'running'}}
                    (agent/'webui-metadata.json').write_text(json.dumps(meta))
                    manager = original_manager(home, home)
                    connection_id = connection_data['connections'][0]['id']
                    connection = manager.store._load('alice')[connection_id]
                    pending = Approvals(home).require('alice', {'taskId': task_id, 'expiresAt': time.time()+300},
                        connection_id, connection, 'sol.input', {'sessionId': 'synthetic-session', 'requestId': 'a'*32, 'key': 'f9'})
                    decision = {'action': 'decide-console', 'id': pending['approvalId'], 'approve': True}
                    assert bob.evaluate("async body=>(await fetch('/auth/connections',{method:'POST',headers:{'Content-Type':'application/json','X-Prime-CSRF':'bob-csrf'},body:JSON.stringify(body)})).status", decision) == 400
                    assert alice.evaluate("async body=>(await fetch('/auth/connections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).status", decision) == 403
                    alice.get_by_role('button', name='Refresh connections', exact=True).click()
                    alice.get_by_role('button', name='Allow once', exact=True).click()
                    alice.get_by_role('button', name='Allow once', exact=True).wait_for(state='detached')
                    assert json.loads(skill_credentials._read(home/'connection-approvals'/(pending['approvalId']+'.json')))['state'] == 'approved'
                    assert alice.evaluate("async body=>(await fetch('/auth/connections',{method:'POST',headers:{'Content-Type':'application/json','X-Prime-CSRF':'alice-csrf'},body:JSON.stringify(body)})).status", decision) == 400
                    alice.get_by_text('Fixture connection', exact=True).click()
                    alice.once('dialog', lambda dialog: dialog.accept())
                    alice.get_by_role('button', name='Delete connection', exact=True).click()
                    alice.get_by_text('Fixture connection', exact=True).wait_for(state='detached')
                    alice.get_by_role('button', name='Refresh requirements').click()
                    alice.get_by_text('Saved · configure access in My connections', exact=True).wait_for()
                    alice.once('dialog', lambda dialog: dialog.accept())
                    alice.get_by_role('button', name='Delete saved values', exact=True).click()
                    alice.get_by_text('Required values missing', exact=True).wait_for()
                    for path in (home/'skill-vault').iterdir():
                        assert b'SYNTHETIC_BROWSER_SECRET' not in path.read_bytes()
                    print('PASS: real browser credential and project-scoped connection save/delete, blank secret inputs, metadata-only responses, staged status and two-user isolation')
                finally: browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': main()
