#!/usr/bin/env python3
"""Offline real-browser + actual API timer fixture; no model or BMC calls."""
import http.server
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

dashboard = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('timer_fixture_api', dashboard/'api_v2.py')
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
task = {'id':'f'*32, 'owner':'alice', 'status':'running', 'topic':'Synthetic long-running task',
        'started':api.now_iso(), 'startedEpoch':time.time(), 'authorization':{'role':'admin'},
        'lastOutputEpoch':time.time()}
api.initialize_task_timer(task)
task['_deadlineMonotonic'] = time.monotonic()+299
task['deadlineEpoch'] = time.time()+299
api.TASKS[task['id']] = task

PAGE = b'''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/task-timer.css"><h1>Timer fixture</h1>
<script src="/task-timer.js"></script><script>
async function request(url,options={}){
const r=await fetch(url,{...options,headers:{...options.headers,'X-Prime-User':'alice','X-Prime-Role':'admin','X-Prime-CSRF':'fixture'}});
const body=await r.json();if(!r.ok)throw Error(body.error||'Request failed');return body;}
async function poll(){const body=await request('/api/tasks');PrimeTaskTimer.render(body.tasks,request);}
poll();setInterval(poll,200);
</script>'''

class Handler(api.Handler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Type','text/html')
            self.send_header('Set-Cookie','prime_csrf=fixture; Path=/'); self.end_headers(); self.wfile.write(PAGE)
        elif self.path in ('/task-timer.js','/task-timer.css'):
            name=self.path[1:]
            self.send_bytes(200,(dashboard/name).read_bytes(),'text/javascript' if name.endswith('.js') else 'text/css')
        else: super().do_GET()
    def log_message(self,*args): pass

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
origin=f'http://127.0.0.1:{server.server_port}'
api.legacy.ALLOWED_ORIGINS={origin}
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--disable-dev-shm-usage','--no-zygote'])
        page=browser.new_page(viewport={'width':1100,'height':800}); errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin)
        page.get_by_text('This task is nearing its time limit').wait_for()
        page.get_by_role('button',name='Keep deadline').click()
        assert task['timerRevision']==0
        original=task['_deadlineMonotonic']
        page.get_by_role('button',name='Extend 30 minutes').click()
        page.wait_for_function('document.querySelector("#taskTimerPrompts").hidden')
        assert task['_deadlineMonotonic']==original+1800 and task['timerRevision']==1
        headers={'Origin':origin,'X-Prime-User':'alice','X-Prime-Role':'admin','X-Prime-CSRF':'fixture'}
        result=page.request.post(origin+'/api/tasks/extend',headers=headers,data={'id':task['id'],'timerRevision':0})
        assert result.ok and task['timerRevision']==1, 'Duplicate extension added time twice'
        denied=page.request.post(origin+'/api/tasks/extend',headers={**headers,'X-Prime-User':'bob'},data={'id':task['id'],'timerRevision':1})
        assert not denied.ok and task['timerRevision']==1
        denied=page.request.post(origin+'/api/tasks/extend',headers={**headers,'X-Prime-CSRF':'wrong'},data={'id':task['id'],'timerRevision':1})
        assert denied.status==403
        task['_deadlineMonotonic']=time.monotonic()+120;task['deadlineEpoch']=time.time()+120
        page.get_by_role('button',name='Extend 30 minutes').wait_for()
        page.reload();page.get_by_role('button',name='Extend 30 minutes').wait_for()
        page.screenshot(path=os.environ.get('PRIME_TIMER_TEST_SCREENSHOT','/tmp/task-timer-test.png'))
        task['_deadlineMonotonic']=time.monotonic()-1
        assert api.task_deadline_expired(task,0)
        denied=page.request.post(origin+'/api/tasks/extend',headers=headers,data={'id':task['id'],'timerRevision':1})
        assert not denied.ok
        task['status']='timed_out'
        page.wait_for_function('document.querySelector("#taskTimerPrompts").hidden')
        assert not errors,errors
        browser.close()
    print('PASS: five-minute warning, keep/extend, actual API deadline, retry deduplication, owner/CSRF checks, reload and expiry')
finally: server.shutdown()
