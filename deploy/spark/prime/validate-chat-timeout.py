#!/usr/bin/env python3
"""Real dashboard/browser + isolated policy API. No models, real chats or BMCs."""
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

dashboard = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('timeout_fixture_api', dashboard/'api_v2.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
temporary = tempfile.TemporaryDirectory()
api.META = Path(temporary.name)/'metadata.json'
api.save_metadata({'conversations': {
    'fixture-chat-one': {'owner':'alice','title':'First fixture'},
    'fixture-chat-two': {'owner':'alice','title':'Second fixture'}}, 'projects':{}})
launched = []


def fixture_launch(message, session_id, **kwargs):
    task = {'id':'a'*32, 'status':'running', 'authorization':kwargs['authorization']}
    api.initialize_task_timer(task)
    launched.append(task)
    return {'id':task['id'], **api.task_timer_view(task)}


api.launch_task = fixture_launch  # Never launch a real sandbox/model from this fixture.


class Handler(api.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/state':
            sessions = [{'id':key, 'topic':row['title'], 'modified':api.now_iso(), **row}
                        for key,row in api.metadata()['conversations'].items()]
            return self.send_json(200, {'settings':{'provider':'spark-qwen','model':'fixture','thinking':'low',
                'reserveTokens':8192,'keepRecentTokens':8192,'enabledProviders':['spark-qwen']},
                'models':[], 'usage':{'windows':{}}, 'sessions':sessions,
                'projects':api.project_catalog('alice'), 'telemetry':{}, 'nativeTasks':[],
                'identity':{'user':'alice','role':'admin'}, 'taskCapabilities':api.task_capabilities('admin')})
        stubs = {'/api/tasks':{'tasks':[], 'prime':{'tasks':[]}}, '/api/telemetry':{'telemetry':{}},
                 '/api/conversations/messages':{'messages':[], 'taskLogs':[]},
                 '/api/files':{'files':[]}, '/api/skills':{'skills':[], 'available':[]}}
        if path in stubs:
            return self.send_json(200, stubs[path])
        name = 'index.html' if path == '/' else path.removeprefix('/assets/')
        if '/' not in name and (dashboard/name).is_file():
            body = (dashboard/name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if name.endswith('.html') else
                             'text/css' if name.endswith('.css') else 'text/javascript')
            self.send_header('Set-Cookie','prime_csrf=fixture; Path=/')
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
origin = f'http://127.0.0.1:{server.server_port}'
api.legacy.ALLOWED_ORIGINS = {origin}
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                                    args=['--disable-dev-shm-usage','--no-zygote'])
        page = browser.new_page(viewport={'width':1440,'height':1000},extra_http_headers={
            'X-Prime-User':'alice','X-Prime-Role':'admin'})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog',lambda dialog:dialog.accept())
        page.goto(origin)
        page.wait_for_function('state?.sessions?.length === 2')
        page.evaluate('openConversation(state.sessions[0])')
        with page.expect_response('**/api/conversations/update') as saved:
            page.get_by_label('Chat task timeout',exact=True).select_option('20160')
        assert saved.value.ok
        assert api.metadata()['conversations']['fixture-chat-one']['taskPolicy']['runtimeMinutes'] == 20160
        page.reload()
        page.wait_for_function('currentSession === "fixture-chat-one" && PrimeTimeout.read("taskTimeout") === 20160')
        page.evaluate('openConversation(state.sessions[1])')
        assert page.locator('#taskTimeout').input_value() == '30'
        page.evaluate('openProjectDialog()')
        page.locator('#projectName').fill('Multiweek fixture')
        page.get_by_label('Project task timeout',exact=True).select_option('40320')
        with page.expect_response('**/api/projects/create') as saved:
            page.locator('#projectForm').evaluate('(form)=>form.requestSubmit()')
        assert saved.value.ok
        page.wait_for_function('state.projects.length === 1')
        project_id = next(iter(api.metadata()['projects']))
        assert api.metadata()['projects'][project_id]['taskPolicy']['runtimeMinutes'] == 40320
        page.evaluate('selectProject(state.projects[0])')
        page.locator('#newConversation').click()
        assert page.locator('#taskTimeout').input_value() == '40320'
        page.locator('#taskTimeout').select_option('10080')
        assert page.evaluate('currentTaskPolicy().runtimeMinutes') == 10080
        assert api.metadata()['projects'][project_id]['taskPolicy']['runtimeMinutes'] == 40320
        selected = page.evaluate('selectedTaskPolicy()')
        assert selected['taskPolicy']['runtimeMinutes'] == 10080, selected
        assert selected['conversationPolicy']['runtimeMinutes'] == 10080, selected
        started = page.request.post(origin+'/api/tasks/start',
            headers={'Origin':origin,'X-Prime-CSRF':'fixture'},
            data={'message':'Synthetic timer check','projectId':project_id, **selected})
        assert started.ok, started.text()
        assert launched[-1]['authorization']['limits']['runtimeMinutes'] == 10080
        assert launched[-1]['_hardDeadlineMonotonic'] > launched[-1]['_deadlineMonotonic']
        page.evaluate('openConversation(state.sessions[0])')
        assert page.locator('#taskTimeout').input_value() == '20160'
        page.screenshot(path=os.environ.get('PRIME_TIMEOUT_SCREENSHOT','/tmp/chat-timeout-test.png'))
        page.set_viewport_size({'width':600,'height':900})
        assert page.locator('#taskTimeout').is_visible()
        page.evaluate('PrimeTimeout.configure("taskTimeout", {maximums:{runtime_minutes:30}})')
        assert page.locator('#taskTimeout').input_value() == '30'
        assert page.locator('#taskTimeout option[value="20160"]').evaluate('(option)=>option.disabled && option.hidden')
        headers = {'Origin':origin,'X-Prime-CSRF':'fixture'}
        payload = {'id':'fixture-chat-one','action':'policy','value':{'runtimeMinutes':129601}}
        assert not page.request.post(origin+'/api/conversations/update',headers=headers,data=payload).ok
        payload['value']['runtimeMinutes'] = 30
        assert not page.request.post(origin+'/api/conversations/update',headers={**headers,'X-Prime-User':'bob'},data=payload).ok
        assert page.request.post(origin+'/api/conversations/update',headers={**headers,'X-Prime-CSRF':'wrong'},data=payload).status == 403
        assert not errors, errors
        browser.close()
    print('PASS: actual chat/project policy saves, reload, isolation, inheritance, task payload, responsive control, role limit, owner/CSRF checks')
finally:
    server.shutdown()
    temporary.cleanup()
