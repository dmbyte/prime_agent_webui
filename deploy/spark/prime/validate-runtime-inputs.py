#!/usr/bin/env python3
"""Operator-only real OpenShell attachment/recovery canary, isolated API metadata.

Run on the Spark while production is idle. Uses a dedicated check-* storage owner,
synthetic data, the real runner/model, and an ephemeral loopback API. Does not read
user prompts/uploads or exercise browser authentication. Leaves evidence under
--work-dir; successful synthetic chats/project are moved to recoverable trash.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-dir', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--owner', default='check-runtime-inputs')
    args = parser.parse_args()
    assert args.owner.startswith('check-'), 'Use a dedicated synthetic check-* owner'
    os.environ['PRIME_TASK_RUNTIME'] = 'openshell'
    spec = importlib.util.spec_from_file_location('input_canary_api', args.api_dir/'api_v2.py')
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    assert api.task_common.SAFE_USER.fullmatch(args.owner)
    work = args.work_dir.resolve(); work.mkdir(mode=0o700, parents=True, exist_ok=True)
    api.META = work/'metadata.json'
    assert not api.META.exists(), 'Use a fresh evidence directory'
    api.legacy.atomic_json(api.META, {})
    api.TASK_LOGS = work/'logs'; api.MESSAGE_CACHE_DIR = work/'cache'
    api.legacy.UPLOADS = work/'uploads'
    api.legacy.UPLOADS.mkdir()
    server = api.legacy.BoundedThreadingHTTPServer(('127.0.0.1', 0), api.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    csrf = secrets.token_hex(24)
    headers = {'X-Prime-User':args.owner, 'X-Prime-Role':'user',
               'Origin':'https://127.0.0.1:8443', 'Cookie':'prime_csrf='+csrf,
               'X-Prime-CSRF':csrf, 'Content-Type':'application/json'}

    def request(path, body):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                                     headers=headers, data=json.dumps(body).encode())
        with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)

    def run(prompt, *, session=None, project=None, tools=False):
        result = request('/api/tasks/start', {'message':prompt, 'sessionId':session,
            'projectId':project, 'thinking':'auto', 'executionConfirm':'allow-execution-task',
            'taskPolicy':{'profile':'development' if tools else 'general', 'networkMode':'restricted',
                          'executionMode':'task' if tools else 'deny', 'runtimeMinutes':5}})
        task_id = result['task']['id']; deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            task = api.TASKS[task_id]
            if task['status'] != 'running': break
            time.sleep(1)
        if task['status'] == 'running':
            request('/api/tasks/stop', {'id':task_id})
            raise AssertionError('Synthetic task exceeded canary deadline')
        assert task['status'] == 'completed', {k:task.get(k) for k in ('status','rpcError','lastToolFailure')}
        assert not task.get('lastToolFailure'), task.get('lastToolFailure')
        if tools: assert task.get('toolExecuted'), 'No tool executed'
        print(json.dumps({'task':task_id,'status':task['status'],'tool':bool(task.get('toolExecuted'))}), flush=True)
        return task

    try:
        # Provision the dedicated owner's storage through the real first-use path.
        seed = run('Synthetic canary: reply READY. No file access, network or other actions.')
        request('/api/conversations/delete', {'id':seed['sessionId']})
        value = 'FILE_'+secrets.token_hex(8)
        source = api.legacy.UPLOADS/'canary.txt'; source.write_text(value)
        api.register_upload(str(source), args.owner)
        file_id = api.upload_rows(args.owner)[0]['id']
        project = request('/api/projects/create', {'name':'Synthetic runtime input check', 'fileIds':[file_id]})['project']['id']
        for legacy in (False, True):
            memory = 'MEMORY_'+secrets.token_hex(8)
            task_id = uuid.uuid4().hex
            sid = api.recover_failed_task_conversation({'id':task_id, 'owner':args.owner,
                'submittedMessage':'Remember this recovery code: '+memory,
                'rpcError':'Synthetic pre-start failure for validation only.',
                'provider':'spark-qwen','model':'qwen3.8-flash-next','thinking':'low',
                'projectId':project}, 'failed')
            path = api.legacy.session_path(sid, api.session_root(args.owner))
            if legacy:
                records = path.read_text().splitlines(); header = json.loads(records[0]); header.pop('cwd')
                old_records = [json.loads(line) for line in records[1:]]
                for record in old_records:
                    if record.get('message', {}).get('role') == 'assistant':
                        for field in ('usage', 'provider', 'model', 'api', 'stopReason'):
                            record['message'].pop(field, None)
                path.write_text(json.dumps(header)+'\n'+''.join(json.dumps(row)+'\n' for row in old_records))
                subprocess.run(['/usr/bin/setfacl','-x',f'u:{api.pwd.getpwnam("prime-runner").pw_uid}',str(path)], check=True)
            task = run('Synthetic validation: use ipython pathlib to read the first project source file. '
                       'Return its contents and the recovery code from the earlier user message. '
                       'No other file access, writes, network, browser or BMC operations.',
                       session=sid, project=project, tools=True)
            assert memory in task.get('liveResponse',''), 'Recovered prompt not in model context'
            assert value in task.get('liveResponse',''), 'Attachment not read by model'
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            assert entries[0]['version'] == 3 and entries[0]['cwd'] == '/project'
            assert all(row.get('id') for row in entries[1:]), 'Native entry migration missing'
            request('/api/conversations/delete', {'id':sid})
            print(json.dumps({'PASS':'legacy recovery + project file' if legacy else 'new recovery + project file'}), flush=True)
        request('/api/projects/delete', {'id':project, 'confirm':'delete-project-'+project})
        print('PASS: real OpenShell continuation, original prompt recall, IPython source read, native session migration.', flush=True)
    finally:
        server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': main()
