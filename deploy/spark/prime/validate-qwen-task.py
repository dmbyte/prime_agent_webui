#!/usr/bin/env python3
"""Synthetic Qwen-only smoke tests through the deployed OpenShell broker.

Run as WebUI owner with no active user task. Creates test conversations, performs
only in-memory calculations, and prints public results, never reasoning content.
"""
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
sys.path.insert(0, str(Path(__file__).parents[1]/'dashboard'))
os.environ['PRIME_TASK_RUNTIME']='openshell'
import api_v2
from task_common import broker_command


def run(prompt, profile, marker, expected, require_tool=False):
    settings=api_v2.legacy.settings_view()
    route=api_v2.route_task(prompt,settings,profile=profile)
    effort,reason=api_v2.resolve_effort('auto',prompt,route,profile)
    assert (route['provider'],route['model'])==api_v2.QWEN_ROUTE
    assert effort==expected
    policy={'profile':profile,'networkMode':'restricted','executionMode':'task',
            'approvalMode':'manual','confirmationMode':'ask','role':'admin',
            'limits':{'memoryGiB':4,'cpus':2,'runtimeMinutes':10}}
    process=subprocess.Popen(broker_command(uuid.uuid4().hex,os.environ.get('USER','dbyte'),policy,
                             route['provider'],route['model'],effort),
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,bufsize=1)
    lines=queue.Queue()
    def reader():
        for line in process.stdout: lines.put(line)
        lines.put(None)
    threading.Thread(target=reader,daemon=True).start()
    final=''; tools=0; ended=False; actual_state=None; start=time.monotonic()
    print('Testing',profile,effort,flush=True)
    try:
        process.stdin.write(json.dumps({'id':'smoke-state','type':'get_state'})+'\n')
        process.stdin.write(json.dumps({'id':'smoke','type':'prompt','message':prompt+api_v2.runtime_context(policy)})+'\n')
        process.stdin.flush()
        while time.monotonic()-start<600:
            try: line=lines.get(timeout=1)
            except queue.Empty: continue
            if line is None: break
            try: event=json.loads(line)
            except ValueError: continue
            kind=event.get('type')
            if kind=='response' and event.get('id')=='smoke-state':
                actual_state=event.get('data') or {}
                assert actual_state.get('thinkingLevel')==effort, 'Prime did not select the expected effort'
                assert (actual_state.get('model') or {}).get('id')=='qwen3.8-flash-next', 'Prime selected the wrong model'
                assert (actual_state.get('model') or {}).get('contextWindow')==262144, 'Isolated context metadata is stale'
            elif kind=='tool_execution_end':
                tools+=1; result=event.get('result') or {}; details=result.get('details') or {}
                assert not (event.get('isError') or result.get('isError') or details.get('status')=='error'), 'Tool failed'
            elif kind=='message_end':
                message=event.get('message') or {}
                if message.get('role')=='assistant':
                    assert message.get('stopReason')!='error', 'Model error'
                    final='\n'.join(p.get('text','') for p in message.get('content',[]) if p.get('type')=='text')
            elif kind=='agent_end': ended=True; break
        assert ended and marker in final, 'Missing successful final report'
        assert actual_state, 'No runtime state acknowledgement'
        assert not require_tool or tools>0, 'Missing real tool execution'
        print(json.dumps({'profile':profile,'effort':effort,'tool_steps':tools,
                          'seconds':round(time.monotonic()-start,2),'final':final[:500]}),flush=True)
    finally:
        process.stdin.close()
        try: process.wait(15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        process.stdout.close()


if __name__=='__main__':
    if os.geteuid()==0: raise SystemExit('Run as WebUI owner, not root')
    run('Synthetic validation only. Do not access any files, network or tools. Calculate 37 times 19 and respond exactly PRIME_QWEN_LOW_PASS=703.',
        'general','PRIME_QWEN_LOW_PASS=703','low')
    run('Synthetic in-memory code validation only. Do not access files, network, BMCs, or other external systems. '
        'Use ipython to implement a function that strips whitespace and lowercases strings, removes empty strings and duplicates while preserving first occurrence. '
        'Run assertions for empty input, [" A ", "a", "B", ""], and [" x", "Y ", "X"]. '
        'Use one short cell with no file writes. Return PRIME_QWEN_CODE_PASS only after all assertions pass.',
        'development','PRIME_QWEN_CODE_PASS','high',True)
