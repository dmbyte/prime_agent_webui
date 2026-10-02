#!/usr/bin/env python3
"""One model-driven, synthetic test through the production task launcher."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parents[1]/'container'))
from task_common import broker_command


def main():
    owner = os.environ['USER']
    task_id = uuid.uuid4().hex
    address = os.environ.get('PRIME_HOSTING_TEST_IP', '172.16.253.231')
    directory = '/project/hosted/agent-fixture-' + task_id[:12]
    policy = {'profile':'development', 'networkMode':'lan', 'executionMode':'task',
              'approvalMode':'manual', 'role':'admin', 'limits':{'cpus':2,'memoryGiB':4,'runtimeMinutes':10}}
    prompt = f'''Synthetic LAN hosting validation. Use only the fixture directory {directory}; do not contact any BMC or alter existing services.
Read /home/prime/.prime/agent/skills/lan-web-host/SKILL.md in ipython first.
Then import its actual WebHost client, create that fixture directory and index.html containing PRIME_AGENT_HOST_FIXTURE.
Create ONE static service named agent-fixture-{task_id[:12]}, task scope, one-hour TTL. Assert its returned externalUrl equals url and starts http://{address}: and its status is running. Assert your service appears in WebHost.list().
Use try/finally to stop ONLY the service you created. Verify it no longer appears in your list. Do not make HTTP requests yourself, invent tool APIs, or print environment variables/tokens. Do not retry failed operations.
Return PRIME_HOSTING_AGENT_PASS only if every assertion passed and cleanup succeeded; otherwise report the exact failure. This test is explicitly authorized to publish that synthetic file on the LAN.'''
    process = subprocess.Popen(broker_command(task_id, owner, policy,'spark-qwen','qwen3.8-flash-next','high'),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    events = queue.Queue()
    def read():
        for line in process.stdout:
            events.put(line)
        events.put(None)
    threading.Thread(target=read, daemon=True).start()
    start = time.monotonic()
    final, steps = '', 0
    try:
        process.stdin.write(json.dumps({'type':'prompt','id':'hosting-fixture','message':prompt})+'\n')
        process.stdin.flush()
        while time.monotonic()-start < 600:
            try:
                line = events.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError('Task ended before report')
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get('type')
            if kind == 'runtime_stage':
                print(event.get('label'), flush=True)
            if kind == 'tool_execution_end':
                steps += 1
                result = event.get('result') or {}
                if event.get('isError') or result.get('isError') or (result.get('details') or {}).get('status') == 'error':
                    raise RuntimeError('Hosting fixture tool step failed; inspect the synthetic session')
            if kind == 'message_end':
                message = event.get('message') or {}
                if message.get('role') == 'assistant':
                    final = '\n'.join(p.get('text','') for p in message.get('content',[]) if p.get('type') == 'text')
            if kind == 'agent_end':
                break
        assert steps and 'PRIME_HOSTING_AGENT_PASS' in final, 'No successful tool-driven final report'
        print(json.dumps(dict(result='PASS', taskId=task_id, toolSteps=steps, seconds=round(time.monotonic()-start,1), final=final[:400])))
    finally:
        process.stdin.close()
        try:
            process.wait(15)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(30)
        process.stdout.close()


if __name__ == '__main__':
    main()
