#!/usr/bin/env python3
"""Run an actual Prime model/IPython task through the broker against a fake BMC.

Run as the WebUI owner, never root. This does not contact a real BMC. The test
creates a synthetic Prime conversation and a temporary local HTTP fixture.
"""
import http.server
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "container"))
from task_common import broker_command

EVENTS = {"login": 0, "key": 0}
LOGIN = b'''<title>Fixture login</title><input id="user"><input id="password" type="password">
<button id="login" onclick="fetch('/login',{method:'POST'}).then(()=>location.href='/panel?view=console#screen')">Log in</button>'''
PANEL = b'''<title>Fixture panel</title><iframe src="/console" width="900" height="600"></iframe>'''
CONSOLE = b'''<canvas id="screen" tabindex="0" width="800" height="500" style="background:navy"></canvas>
<script>document.querySelector('canvas').getContext('2d').fillText('TEST CONSOLE ONLY',30,30);
window.addEventListener('keydown',e=>{if(e.key==='F9'){e.preventDefault();fetch('/key',{method:'POST'}).then(()=>parent.document.title='Fixture F9 received')}});</script>'''


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PANEL if self.path.startswith('/panel') else CONSOLE if self.path == '/console' else LOGIN
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == '/login': EVENTS['login'] += 1
        elif self.path == '/key': EVENTS['key'] += 1
        else: self.send_error(404); return
        self.send_response(204)
        self.end_headers()

    def log_message(self,*_args): pass


def main():
    if os.geteuid()==0: raise SystemExit('Run as WebUI owner')
    owner=os.environ.get('USER','dbyte')
    host=os.environ.get('PRIME_KVM_TEST_HOST','172.16.253.231')
    server=http.server.ThreadingHTTPServer((host,0),Fixture)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://{host}:{server.server_port}/'
    policy={'profile':'network-operations','networkMode':'full','executionMode':'task','approvalMode':'auto',
            'confirmationMode':'always','limits':{'memoryGiB':8,'cpus':4,'runtimeMinutes':10}}
    prompt=f'''This is an authorized automated test against ONLY the local fake BMC at {url}. Do not contact any real BMC or touch real server state.
Use the installed bmc-html5-kvm skill via ipython. Read /home/prime/.prime/agent/skills/bmc-html5-kvm/SKILL.md first using pathlib; do not guess package locations or use a bash tool. Use real tool calls; do not merely describe the test.
After reading the skill, perform the workflow ONCE in one ipython cell with try/finally cleanup. If any assertion fails, close this fixture session and report failure immediately; do not restart or repeat the workflow.
Create with KVMClient.create('{url}', ignore_https_errors=False). Inspect the login page, verify loginFormPresent, save a PNG under /project, and verify that key('F9', confirm=True) is rejected before a console is focused (catch that expected RuntimeError).
This fake login and console are expressly authorized for testing: fill #user with fixture and #password with fixture, then click #login. After the same-origin query/fragment redirect, wait until inspect()['consoleSurfaces'] contains #screen, then select_frame with that surface's frameIndex (do not guess index 0). Capture another PNG, focus_console('#screen', confirm=True), and send F9 exactly once. Verify pages() eventually reports title 'Fixture F9 received'.
Call create again with the same URL and ignore_https_errors=False and confirm the session ID is unchanged and the title remains. Capture a JPEG too. Close ONLY this fixture session in finally. Never close other sessions. Each capture must return an existing file with the appropriate PNG/JPEG signature.
Use the synchronous KVMClient API; do not invent methods. If any unexpected error occurs report it rather than claiming success. Return a concise final report with PRIME_KVM_TASK_PASS only if ALL checks passed, otherwise PRIME_KVM_TASK_FAIL. The login page is not the server console.'''
    # Match the production WebUI's per-task adapter facts, not just its broker.
    os.environ['PRIME_TASK_RUNTIME']='openshell'
    sys.path.insert(0,str(Path(__file__).parent.parent/'dashboard'))
    import api_v2
    settings={'provider':'spark-nemotron','model':'nemotron-3.5-lightning',
              'enabledModels':['spark-nemotron/nemotron-3.5-lightning','spark-qwen/qwen3.8-flash-next']}
    route=api_v2.route_task(prompt,settings,profile=policy['profile'])
    provider,model=route['provider'],route['model']
    if '--nemotron' in sys.argv: provider,model=api_v2.NEMOTRON_ROUTE
    elif '--qwen' in sys.argv: provider,model=api_v2.QWEN_ROUTE
    print('Test route:',provider,model,flush=True)
    command=broker_command(uuid.uuid4().hex,owner,policy,provider,model,'max')
    prompt += api_v2.runtime_context(policy)
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    lines=queue.Queue()
    def reader():
        for line in process.stdout: lines.put(line)
        lines.put(None)
    threading.Thread(target=reader,daemon=True).start()
    process.stdin.write(json.dumps({'id':'test-prompt','type':'prompt','message':prompt})+'\n')
    process.stdin.flush()
    failures=[]; final=''; tools=0; ended=False
    deadline=time.monotonic()+360
    try:
        while time.monotonic()<deadline:
            try: line=lines.get(timeout=1)
            except queue.Empty: continue
            if line is None: break
            try: event=json.loads(line)
            except ValueError: continue
            kind=event.get('type')
            if kind=='tool_execution_end':
                tools+=1
                result=event.get('result') or {}
                details=result.get('details') or {}
                failed=event.get('isError') or result.get('isError') or details.get('status')=='error'
                if failed:
                    failures.append(str(details.get('errorEname') or 'tool error'))
                    print('Failure type:',failures[-1],flush=True)
                print(f'Tool step {tools}: {event.get("toolName")} {"FAILED" if failed else "returned"}',flush=True)
                if failed: raise RuntimeError('Unexpected tool failure; stopping this test rather than allowing retries')
            elif kind=='message_end':
                message=event.get('message') or {}
                if message.get('role')=='assistant':
                    final='\n'.join(p.get('text','') for p in message.get('content',[]) if p.get('type')=='text')
            elif kind=='agent_end':
                ended=True; break
        if not ended: raise RuntimeError('Prime test did not finish within six minutes')
        print('Fixture evidence:',EVENTS,'toolErrors:',failures,'finalReport:',final[:1800],flush=True)
        assert tools>0 and not failures, 'Unexpected tool failure'
        assert EVENTS=={'login':1,'key':1}, 'Expected login and exactly one console key were not observed'
        assert 'PRIME_KVM_TASK_PASS' in final and 'PRIME_KVM_TASK_FAIL' not in final, 'Prime did not report verified success'
        print('Actual Prime task passed model → broker → OpenShell → IPython → KVM → final report',flush=True)
    finally:
        process.stdin.close()
        try: process.wait(15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        server.shutdown()


if __name__=='__main__': main()
