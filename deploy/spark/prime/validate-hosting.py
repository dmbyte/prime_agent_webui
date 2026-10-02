#!/usr/bin/env python3
"""Synthetic LAN hosting fixture; never contacts a BMC or real user service.

Run as prime-runner with HOME=/var/lib/prime-runner, PRIME_WEB_OWNER set.
start leaves two fixture services for an independent LAN check; finish stops
only recorded fixture IDs, revokes fixture capabilities, retains source files.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

sys.path.insert(0, '/usr/local/lib/prime-runner')
import hosting_auth
import openshell_runner

ROOT = Path('/var/lib/prime-runner')


def call(path, payload):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(170)
        connection.connect(str(path))
        connection.sendall(json.dumps(payload).encode() + b'\n')
        with connection.makefile('rb') as stream:
            reply = json.loads(stream.readline(131073))
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error'))
    return reply['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'finish'])
    args = parser.parse_args()
    owner = os.environ['PRIME_WEB_OWNER']
    state_path = ROOT / 'hosting' / owner / 'fixture.json'
    sock = ROOT / 'hosting-access' / owner / 'hosting.sock'
    admin = ROOT / 'hosting' / owner / 'admin.sock'
    if args.action == 'finish':
        state = json.loads(state_path.read_text())
        current = call(admin, {'action':'list'})['services']
        for row in current:
            if row['taskId'] == state['taskId']:
                assert row['name'].startswith('fixture-')
                call(admin, {'action':'stop', 'id':row['id']})
        for task_id in state['capabilities']:
            hosting_auth.revoke(task_id)
        state_path.unlink()
        print('Fixture services stopped; fixture files retained, no user services changed.')
        return
    if state_path.exists():
        raise SystemExit('Finish the previous hosting fixture before starting another')
    task_id = uuid.uuid4().hex
    project = 'p_' + uuid.uuid4().hex[:24]
    other_task = uuid.uuid4().hex
    foreign_task = uuid.uuid4().hex
    policy = {'profile':'development', 'networkMode':'lan', 'executionMode':'task', 'role':'admin'}
    token = hosting_auth.issue(owner, task_id, project, policy)
    token2 = hosting_auth.issue(owner, other_task, project, policy)
    foreign = hosting_auth.issue(owner, foreign_task, 'p_'+uuid.uuid4().hex[:24], policy)
    state = dict(taskId=task_id, capabilities=[task_id, other_task, foreign_task])
    state_path.write_text(json.dumps(state))
    workspace_root = Path(os.environ.get('PRIME_RUNNER_WORKSPACE_ROOT', f'/home/{owner}/prime-agent/tasks'))
    directory = workspace_root / owner / 'hosted' / ('fixture-' + task_id[:12])
    directory.mkdir(parents=True)
    (directory/'index.html').write_text('PRIME_HOSTING_STATIC_PASS\n')
    (directory/'.env').write_text('synthetic private fixture')
    with (directory/'fixture.iso').open('wb') as stream:
        stream.seek(5 * 1024**3)
        stream.write(b'PRIME_ISO_RANGE_PASS')
    (directory/'symlink.iso').symlink_to(directory/'fixture.iso')
    source = '/project/hosted/' + directory.name
    request = dict(action='create', token=token, directory=source, ttlHours=1)
    static = call(sock, dict(request, name='fixture-static-'+task_id[:8], kind='static'))
    # App proves the advertised URL is passed inside the container; WebSocket
    # handshake exercises bidirectional raw TCP forwarding without dependencies.
    (directory/'server.py').write_text('''import os, json, hashlib, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200); self.send_header('Content-Length','0'); self.end_headers()
    def do_GET(self):
        if self.headers.get('Upgrade','').lower() == 'websocket':
            key=self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            self.send_response(101); self.send_header('Upgrade','websocket'); self.send_header('Connection','Upgrade')
            self.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1(key.encode()).digest()).decode()); self.end_headers()
            self.wfile.write(b'\\x81\\x09socket-ok'); self.wfile.flush(); self.close_connection=True; return
        body=json.dumps({'marker':'PRIME_HOSTING_APP_PASS','externalUrl':os.environ['PRIME_HOST_URL']}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
ThreadingHTTPServer((os.environ['HOST'],int(os.environ['PORT'])),Handler).serve_forever()
''')
    app = call(sock, dict(request, name='fixture-app-'+task_id[:8], kind='app', command=['python3','server.py']))
    assert {r['id'] for r in call(sock, dict(action='list',token=token2))['services']} == {static['id'], app['id']}
    assert call(sock, dict(action='list', token=foreign))['services'] == []
    # Verify the real task mount, Landlock policy, installed skill and socket
    # permit discovery by another process in the same project.
    spec = openshell_runner.task_spec(other_task, owner, policy, 'spark-qwen','qwen3.8-flash-next','low',
             storage_root=ROOT/'users', image_manifest=ROOT/'openshell-image-digests.json',
             policy_root=ROOT/'openshell-policies', workspace_root=workspace_root)
    try:
        subprocess.run(spec['create'], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, timeout=90)
        code = "import sys;sys.path.insert(0,'/home/prime/.prime/agent/skills/lan-web-host/scripts');from prime_web_host import WebHost;assert len(WebHost().list())==2;print('TASK_DISCOVERY_PASS')"
        command = ['/usr/bin/openshell','--gateway','spark-local','sandbox','exec','--name',spec['name'],'--no-tty',
                   '--env','PRIME_HOSTING_SOCKET=/run/prime-hosting/hosting.sock','--env','PRIME_HOSTING_TOKEN='+token2,
                   '--','/opt/prime-kernel/bin/python','-c',code]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        assert 'TASK_DISCOVERY_PASS' in result.stdout
    finally:
        subprocess.run(spec['delete'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        spec['policy'].unlink(missing_ok=True)
    hosting_auth.revoke(task_id)
    # Service survives the task's revoked control capability.
    assert len(call(sock, dict(action='list', token=token2))['services']) == 2
    print(json.dumps({'static': static, 'app':app, 'checks':['same-project discovery','foreign-project denial','real task container discovery','task-completion persistence']}, indent=2))


if __name__ == '__main__':
    main()
