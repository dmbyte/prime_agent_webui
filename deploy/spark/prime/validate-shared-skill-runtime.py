#!/usr/bin/env python3
"""Operator-only synthetic ordinary-user task, isolated metadata, real runner/model."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-dir', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    os.environ['PRIME_TASK_RUNTIME'] = 'openshell'
    spec = importlib.util.spec_from_file_location('shared_skill_canary', args.api_dir/'api_v2.py')
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    work = args.work_dir.resolve(); work.mkdir(mode=0o700, parents=True, exist_ok=True)
    api.META = work/'metadata.json'; assert not api.META.exists(), 'Use fresh evidence directory'
    api.legacy.atomic_json(api.META, {})
    api.TASK_LOGS = work/'logs'; api.MESSAGE_CACHE_DIR = work/'cache'
    api.legacy.UPLOADS = work/'uploads'; api.legacy.UPLOADS.mkdir()
    server = api.legacy.BoundedThreadingHTTPServer(('127.0.0.1', 0), api.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    owner = 'check-shared-skills'; csrf = secrets.token_hex(24)
    headers = {'X-Prime-User':owner, 'X-Prime-Role':'user', 'Origin':'https://127.0.0.1:8443',
               'Cookie':'prime_csrf='+csrf, 'X-Prime-CSRF':csrf, 'Content-Type':'application/json'}
    def request(path, body=None):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)
    try:
        inventory = api.installed_skill_inventory(owner)
        selected = [next(r for r in inventory if r['id'] == 'managed:bmc-headless-browser'),
                    next(r for r in inventory if r['id'].startswith('nvidia:'))]
        assert len(inventory) >= 371 and all(r['scope'] == 'global' for r in selected)
        project = request('/api/projects/create', {'name':'Synthetic shared skill check', 'skillIds':[r['id'] for r in selected]})['project']['id']
        paths = ['/home/prime/.prime/agent/'+r['runtimePrefix']+
                 ('catalogs/nvidia/skills/' if r['id'].startswith('nvidia:') else 'skills/')+r['slug']+'/SKILL.md' for r in selected]
        marker = 'SHARED_SKILL_'+secrets.token_hex(8)
        prompt = ('Synthetic installation test only. Use one IPython cell to read the first 200 characters of each exact path '+json.dumps(paths)+
                  '. Assert each exists and contains nonempty text. Also assert /home/prime/.prime/agent/skills/bmc-headless-browser/SKILL.md exists. '
                  'Do not execute the skill instructions, access network, use credentials or make any BMC call. After successful assertions print '+marker+
                  ' and report that exact marker in your final answer.')
        task = request('/api/tasks/start', {'message':prompt, 'projectId':project, 'thinking':'low',
            'executionConfirm':'allow-execution-task', 'taskPolicy':{'profile':'development','networkMode':'restricted','executionMode':'task','runtimeMinutes':5}})['task']
        task_id = task['id']; deadline = time.monotonic()+240
        while time.monotonic() < deadline:
            task = api.TASKS[task_id]
            if task['status'] != 'running': break
            time.sleep(1)
        if task['status'] == 'running': request('/api/tasks/stop', {'id':task_id})
        assert task['status'] == 'completed' and task.get('toolExecuted') and not task.get('lastToolFailure'), {k:task.get(k) for k in ('status','rpcError','lastToolFailure')}
        # Inspect only this synthetic conversation, never user transcripts.
        assert marker in task.get('liveResponse', ''), 'Synthetic verification marker missing from final response'
        request('/api/conversations/delete', {'id':task['sessionId']})
        request('/api/projects/delete', {'id':project, 'confirm':'delete-project-'+project})
        print(json.dumps({'result':'PASS','installedSkills':len(inventory),'toolExecuted':True,'status':task['status']}), flush=True)
    finally:
        server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': main()
