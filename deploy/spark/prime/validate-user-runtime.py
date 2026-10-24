#!/usr/bin/env python3
"""Operator-only localhost canary through the real WebUI task API.

Uses synthetic prompts, no uploaded files or existing conversation. Run on the
Spark as its trusted WebUI host account, only while user tasks are idle. Does not
test browser login: forwarded headers model the authenticated reverse proxy.
Successful test chats are moved to recoverable conversation trash by default.
"""
import argparse
import json
import secrets
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', required=True)
    parser.add_argument('--role', choices=('user', 'power_user', 'admin'), default='user')
    parser.add_argument('--effort', choices=('auto', 'medium'), default='auto')
    parser.add_argument('--tool', action='store_true')
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    csrf = secrets.token_hex(24)
    headers = {'X-Prime-User': args.owner, 'X-Prime-Role': args.role,
               'Origin': 'https://127.0.0.1:8443', 'Cookie': 'prime_csrf='+csrf,
               'X-Prime-CSRF': csrf, 'Content-Type': 'application/json'}

    def request(path, body=None):
        req = urllib.request.Request('http://127.0.0.1:8765'+path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    assert not any(t['status'] == 'running' for t in request('/api/tasks')['tasks']), 'User already has an active task'
    marker = 'PRIME_USER_RUNTIME_PASS_703'
    prompt = ('Synthetic runtime validation. Do not read or write files, use network, or touch BMCs. '
              'Compute 37 times 19. Respond exactly '+marker+'.')
    if args.tool:
        prompt = ('Synthetic in-memory tool validation. No file access, network, browser or BMC activity. '
                  'Use the ipython tool to calculate 37*19 and assert it equals 703. '
                  'After the assertion passes respond exactly '+marker+'.')
    task = request('/api/tasks/start', {'message': prompt, 'thinking': args.effort,
        'executionConfirm': 'allow-execution-task',
        'taskPolicy': {'profile': 'development' if args.tool else 'general', 'networkMode': 'restricted',
                       'executionMode': 'task' if args.tool else 'deny', 'runtimeMinutes': 5}})['task']
    task_id = task['id']; start = time.monotonic(); last_stage = None
    print(json.dumps({'task': task_id, 'owner': args.owner, 'effort': task['thinking'], 'runtime': task['runtime']}), flush=True)
    try:
        while time.monotonic()-start < 300:
            task = next(t for t in request('/api/tasks')['tasks'] if t['id'] == task_id)
            stage = task.get('progress')
            if stage != last_stage:
                print(json.dumps({'stage': stage}), flush=True); last_stage = stage
            if task['status'] != 'running': break
            time.sleep(2)
        assert task['status'] == 'completed', json.dumps({'status':task['status'], 'error':task.get('rpcError')})
        assert marker in task.get('liveResponse',''), 'Missing synthetic final report'
        assert task['thinking'] == ('low' if args.effort == 'auto' else 'medium')
        assert task['provider'] == 'spark-qwen' and task['runtime'] == 'openshell'
        assert not args.tool or task.get('toolExecuted'), 'No real tool call'
        assert not task.get('lastToolFailure'), 'Tool ended with an error'
        session = task['sessionId']
        print(json.dumps({'PASS': True, 'seconds': round(time.monotonic()-start,1),
                          'session': session, 'toolExecuted': bool(task.get('toolExecuted'))}), flush=True)
        if not args.keep:
            request('/api/conversations/delete', {'id': session})
            print('Synthetic conversation moved to recoverable trash.', flush=True)
    finally:
        if task['status'] == 'running': request('/api/tasks/stop', {'id': task_id})


if __name__ == '__main__': main()
