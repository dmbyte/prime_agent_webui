#!/usr/bin/env python3
"""Actual Prime/OpenShell coding and browser/console canary with no user state.

Fresh volumes, fixed-loopback model proxy, no provider credentials or network
gateway. Operator holds maintenance admission; cleanup also runs in recovery.
This does not exercise the production WebUI, grants or persistent KVM broker.
"""
import argparse
import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import queue
import re
import signal
import socketserver
import stat
import subprocess
import threading
import time
import uuid

from run_screen import chat, memory, parse_json

COMMON = ['openshell', '--gateway', 'spark-local']
IMAGE = 'local/prime-openshell-network-operations:0.9.5-7dbc3b2ed45e'
IMAGE_ID = 'sha256:7dbc3b2ed45ed22036e4a0d24dfc5ab71f15fafff0e87660d8beeead2099f22e'
VERSION = 'spark-agent-v1'


def valid_action_counts(events):
    return (isinstance(events, dict) and events.keys() == {'login', 'key'}
            and all(type(value) is int and value == 1 for value in events.values()))


def read_png(path):
    """Read only a bounded regular PNG, never an agent-created host symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 8 <= info.st_size <= 8*1024*1024:
            raise ValueError('Invalid evaluation image file')
        data = stream.read(8*1024*1024 + 1)
    if len(data) > 8*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid evaluation PNG')
    return data


def command(args, **kwargs):
    try:
        return subprocess.run(args, text=True, capture_output=True, check=True, timeout=kwargs.pop('timeout', 120), **kwargs)
    except subprocess.CalledProcessError as exc:
        # This standalone harness never receives credentials or user content.
        raise RuntimeError(f'Evaluation command failed: {exc.stderr[-1600:]}') from exc


def cleanup(root, invocation=None):
    marker = root / 'agent-runtime.json'
    if not marker.exists(): return
    state = json.loads(marker.read_text())
    if state.get('invocation') != invocation:
        print('Agent runtime belongs to another invocation; no changes made', flush=True)
        return
    nonce = state['nonce']
    if not re.fullmatch('[a-f0-9]{32}', nonce): raise ValueError('Invalid evaluation identity')
    name = 'pe-' + nonce[:16]
    # Only this locally recorded random sandbox identity; never list/delete users.
    result = subprocess.run(COMMON + ['sandbox', 'get', name, '--output', 'json'], capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        record = json.loads(result.stdout)
        if record.get('name') != name or record.get('labels', {}).get('prime.eval') != nonce:
            raise RuntimeError('Sandbox identity mismatch')
        command(COMMON + ['sandbox', 'delete', name], timeout=90)
    elif not any(s in result.stderr.lower() for s in ('not found', 'notfound')):
        raise RuntimeError('Cannot establish sandbox cleanup state: ' + result.stderr[:200])
    for suffix in ('state', 'project', 'gateway', 'fixture'):
        volume = 'prime-eval-' + nonce + '-' + suffix
        result = subprocess.run(['docker', 'volume', 'inspect', volume], text=True, capture_output=True, timeout=15)
        if result.returncode == 0:
            if json.loads(result.stdout)[0].get('Labels', {}).get('prime.eval') != nonce:
                raise RuntimeError('Volume identity mismatch')
            command(['docker', 'volume', 'rm', volume])
        elif 'no such volume' not in result.stderr.lower():
            raise RuntimeError('Cannot establish volume cleanup state')
    marker.rename(root / 'agent-runtime-cleaned.json')


def sandbox_exec(name, args, **kwargs):
    return command(COMMON + ['sandbox', 'exec', '--name', name, '--no-tty', '--no-login-shell',
                            '--workdir', '/project', '--env', 'IPYTHONDIR=/tmp/ipython', '--', *args], **kwargs)


class UnixHTTP(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def proxy_handler(port, records):
    if port not in (30001, 30002): raise ValueError('Unreviewed model endpoint')
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            body = json.dumps({'externalModels': [], 'localModel': 'spark-qwen/qwen3.8-flash-next'}).encode()
            self.send_response(200 if self.path == '/routing-models' else 404)
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            try: size = int(self.headers.get('Content-Length', '0'))
            except ValueError: self.send_error(400); return
            if self.path != '/spark-qwen/v1/chat/completions' or not 0 < size <= 8*1024*1024:
                self.send_error(403); return
            raw = self.rfile.read(size)
            try: payload = json.loads(raw)
            except ValueError: self.send_error(400); return
            if not isinstance(payload, dict) or payload.get('model') != 'qwen3.8-flash-next': self.send_error(403); return
            records.append({'unix': time.time(), 'effort': payload.get('reasoning_effort'),
                            'max_tokens': payload.get('max_tokens'), 'messages': len(payload.get('messages', [])),
                            'tools': [x.get('function', {}).get('name') for x in payload.get('tools', [])]})
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=300)
            try:
                connection.request('POST', '/v1/chat/completions', raw, {'Content-Type': 'application/json'})
                reply = connection.getresponse()
                self.send_response(reply.status); self.send_header('Content-Type', reply.getheader('Content-Type', 'application/json'))
                self.send_header('Connection', 'close'); self.end_headers()
                while data := reply.read1(65536): self.wfile.write(data); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # The bounded RPC client may disconnect after its final event.
                pass
            finally: connection.close()
    return Proxy


def rpc(name, prompt, effort):
    args = COMMON + ['sandbox', 'exec', '--name', name, '--no-tty', '--no-login-shell', '--workdir', '/project']
    for value in ('HOME=/home/prime', 'IPYTHONDIR=/home/prime/.prime/ipython',
                  'PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python',
                  'NO_PROXY=127.0.0.1,localhost', 'PYTHONPATH=/eval',
                  'PRIME_TASK_PROFILE=network-operations', 'PRIME_NETWORK_MODE=restricted'):
        args += ['--env', value]
    args += ['--', '/usr/local/bin/prime-container-entrypoint', '--cwd', '/project', '--mode', 'rpc',
             '--daemon-socket', '/tmp/eval-' + uuid.uuid4().hex + '.sock', '--provider', 'spark-qwen',
             '--model', 'qwen3.8-flash-next', '--thinking', effort]
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = queue.Queue()
    def read():
        for line in process.stdout: lines.put(line)
        lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    started = time.monotonic(); final = ''; tools = 0; failures = 0; ended = False; diagnostics = []
    process.stdin.write(json.dumps({'id': 'fixture', 'type': 'prompt', 'message': prompt}) + '\n'); process.stdin.flush()
    try:
        while time.monotonic() - started < 600:
            try: line = lines.get(timeout=1)
            except queue.Empty: continue
            if line is None: break
            try: event = json.loads(line)
            except ValueError: continue
            kind = event.get('type')
            if kind == 'tool_execution_end':
                tools += 1; result = event.get('result') or {}; details = result.get('details') or {}
                failed = bool(event.get('isError') or result.get('isError') or details.get('status') == 'error')
                failures += int(failed)
                if failed: diagnostics.append({'tool_error': result})
                print(json.dumps({'tool': event.get('toolName'), 'failed': failed, 'step': tools}), flush=True)
            elif kind == 'message_end':
                message = event.get('message') or {}
                if message.get('role') == 'assistant':
                    final = '\n'.join(x.get('text', '') for x in message.get('content', []) if x.get('type') == 'text')
            elif kind == 'agent_end': ended = True; break
            elif kind in ('error', 'response') and (event.get('error') or event.get('success') is False):
                diagnostics.append(event)
        return {'seconds': time.monotonic() - started, 'ended': ended, 'tools': tools, 'tool_errors': failures,
                'final': final[:4000], 'diagnostics': str(diagnostics)[:6000]}
    finally:
        process.stdin.close()
        try: process.wait(10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try: process.wait(10)
            except subprocess.TimeoutExpired: process.kill(); process.wait()


CODE_PROMPT = '''Work only in this synthetic evaluation workspace. Use ipython to create /project/range_server.py with parse_range(header, size), returning a tuple(status, start, end). Support single HTTP byte ranges: inclusive start-end, open-ended start-, and suffix -N. Clamp ends and oversized suffixes to file size; malformed or unsatisfiable ranges (including multi-range and zero suffix) return (416,None,None). No header returns (200,0,size-1), except empty file returns (200,None,None). A range on an empty file is unsatisfiable. Support sizes beyond 4 GiB. Do not use network, install packages, delegate, or read other workspaces. Run the trusted tests with subprocess.run(['/opt/prime-kernel/bin/python','/eval/agent_fixture.py','verify-code'],check=True,capture_output=True,text=True), print the result, and repair any implementation error. End with RANGE_APP_PASS only if all tests pass, plus a short explanation of edge cases. You must actually create and test the file, not just describe it.'''
BROWSER_PROMPT = '''This is a synthetic test ONLY at http://127.0.0.1:8123, no real BMC or saved credentials. Use the installed BMCBrowser via ipython to visit '/', fill #user and #password with the literal 'fixture', click #login (explicitly authorized for this fake page), wait for title 'Evaluation panel', and save /project/browser.png. Use one async with BMCBrowser(...) block and top-level await, not asyncio.run. Close the browser afterward. Then import FixtureConsole from agent_fixture (PYTHONPATH=/eval), the test-only transport to the installed real HTML5 KVM worker. Use c=FixtureConsole(); c.call('open',url='http://127.0.0.1:8123/panel'); inspect with c.call('inspect'). Before console focus, verify c.call('key',key='F9',confirm=True) raises RuntimeError. Inspect consoleSurfaces, select_frame with the discovered frameIndex, capture via c.capture('/project/console-before.png'), then focus_console using its selector and confirm=True. Send exactly one F9 with confirm=True, explicitly authorized on this fake console only. Verify c.call('pages') eventually includes title 'Evaluation F9 received'. Capture /project/console-after.png. Keep the session open for 10 seconds and capture /project/console-later.png, then close in finally. Never send any other key or contact another address. If unexpected errors occur, report them; do not repeat the key. End BROWSER_CONSOLE_PASS only after every check actually passes. No package installation or delegation.'''
BROWSER_PROMPT += '''\nInstalled API reference: from bmc_headless_browser import BMCBrowser. Constructor BMCBrowser('http://127.0.0.1:8123'), async methods goto('/'), fill(selector,value), confirmed_click(selector,confirm=True), title(), screenshot('/project/browser.png'). For FixtureConsole: c.call('select_frame',index=discovered_frame_index); c.call('focus_console',selector=discovered_selector,confirm=True). Do not use bash or guess imports; these APIs are installed in the IPython kernel.'''
TASK_PROMPT = CODE_PROMPT + '\nThen complete this second part in the same task:\n' + BROWSER_PROMPT + '\nReturn BOTH pass markers in the final answer only if both parts pass. Keep the report concise.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--port', type=int, choices=(30001, 30002), default=30001)
    parser.add_argument('--cleanup', action='store_true'); args = parser.parse_args(); root = args.root.resolve()
    # CLI invocation ownership is supplied through the parent's private run ID.
    invocation = os.environ.get('PRIME_EVAL_INVOCATION')
    if args.cleanup: cleanup(root, invocation); return
    if not invocation or not re.fullmatch('[a-f0-9]{32}', invocation): parser.error('Invocation ID required')
    if not os.environ.get('PRIME_EVAL_MAINTENANCE_HELD'): parser.error('Maintenance guard required')
    nonce = uuid.uuid4().hex; name = 'pe-' + nonce[:16]
    image = json.loads(command(['docker', 'image', 'inspect', IMAGE]).stdout)[0]
    if image['Id'] != IMAGE_ID: raise RuntimeError('Task image identity changed')
    work = root / 'agent-work'; work.mkdir(mode=0o700)
    for suffix in ('state', 'project', 'gateway', 'fixture'):
        path = work / suffix; path.mkdir(mode=0o700)
        command(['setfacl', '-m', f'u:995:rwx,d:u:995:rwx,d:u:{os.getuid()}:rwx,m::rwx', str(path)])
    (work/'fixture/agent_fixture.py').write_bytes(Path(__file__).with_name('agent_fixture.py').read_bytes())
    agent = work/'state/agent'; agent.mkdir()
    models = {'providers': {'spark-qwen': {'baseUrl': 'http://127.0.0.1:31000/spark-qwen/v1', 'api': 'openai-completions', 'apiKey': 'evaluation-placeholder',
        'compat': {'supportsDeveloperRole': False, 'supportsReasoningEffort': True, 'thinkingFormat': 'openai'},
        'models': [{'id': 'qwen3.8-flash-next', 'name': 'Local evaluation only', 'reasoning': True, 'input': ['text', 'image'], 'contextWindow': 262144, 'maxTokens': 8192,
                    'thinkingLevelMap': {'low': 'low', 'medium': 'medium', 'high': 'xhigh'}}]}}}
    (agent/'models.json').write_text(json.dumps(models))
    (agent/'settings.json').write_text(json.dumps({'defaultProvider': 'spark-qwen', 'defaultModel': 'qwen3.8-flash-next', 'telemetry': {'enabled': False, 'noticeShown': True}}))
    policy = root/'agent-policy.yaml'
    policy.write_text('version: 1\nfilesystem_policy:\n  include_workdir: true\n  read_only:\n    - /usr\n    - /lib\n    - /proc\n    - /etc\n    - /opt/prime-kernel\n    - /eval\n    - /run/prime-gateway\n  read_write:\n    - /home/prime/.prime\n    - /project\n    - /tmp\n    - /dev/null\n    - /dev/urandom\n    - /dev/random\n    - /dev/shm\nlandlock:\n  compatibility: hard_requirement\nnetwork_policies: {}\n')
    with (root/'agent-runtime.json').open('x') as out: json.dump({'nonce': nonce, 'invocation': invocation}, out); out.flush(); os.fsync(out.fileno())
    server = None; records = []; samples = [memory()]; stop = threading.Event()
    def monitor():
        while not stop.wait(1): samples.append(memory())
    thread = threading.Thread(target=monitor, daemon=True); thread.start()
    def shutdown(*_): raise RuntimeError('Probe interrupted')
    signal.signal(signal.SIGTERM, shutdown)
    out = (root/'results/agent.jsonl').open('x')
    def emit(value):
        out.write(json.dumps(value) + '\n'); out.flush(); os.fsync(out.fileno()); print(json.dumps(value), flush=True)
    try:
        mounts = []
        for suffix, target in (('state', '/home/prime/.prime'), ('project', '/project'), ('gateway', '/run/prime-gateway'), ('fixture', '/eval')):
            volume = 'prime-eval-' + nonce + '-' + suffix
            command(['docker', 'volume', 'create', '--label', 'prime.eval=' + nonce,
                     '--label', 'openshell.ai/sandbox-attachable=true',
                     '--label', 'openshell.ai/sandbox-attachable-workspace=default',
                     '--driver', 'local', '--opt', 'type=none', '--opt', 'o=bind', '--opt', 'device=' + str(work/suffix), volume])
            mounts.append({'type': 'volume', 'source': volume, 'target': target, 'read_only': suffix in ('fixture', 'gateway')})
        server = UnixHTTP(str(work/'gateway/model.sock'), proxy_handler(args.port, records))
        command(['setfacl', '-m', 'u:995:rw,m::rw', str(work/'gateway/model.sock')])
        threading.Thread(target=server.serve_forever, daemon=True).start()
        command(COMMON + ['sandbox', 'create', '--name', name, '--from', IMAGE, '--policy', str(policy),
            '--driver-config-json', json.dumps({'docker': {'mounts': mounts}}), '--cpu', '4', '--memory', '4Gi',
            '--approval-mode', 'manual', '--label', 'prime.eval=' + nonce, '--detach', '--no-auto-providers', '--no-tty', '--', '/bin/sleep', 'infinity'])
        emit({'type': 'run', 'version': VERSION, 'port': args.port, 'sandbox': name, 'image_id': IMAGE_ID,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'fixture_sha256': hashlib.sha256(Path(__file__).with_name('agent_fixture.py').read_bytes()).hexdigest(),
              'prompts_sha256': hashlib.sha256(TASK_PROMPT.encode()).hexdigest()})
        # Start only our synthetic loopback fixture, detached inside this sandbox.
        sandbox_exec(name, ['/opt/prime-kernel/bin/python', '-c', "import subprocess; log=open('/project/fixture-server.log','a'); subprocess.Popen(['/opt/prime-kernel/bin/python','/eval/agent_fixture.py','serve'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)"])
        # Fail fixture/runtime plumbing before spending model tokens on it.
        preflight = sandbox_exec(name, ['/opt/prime-kernel/bin/python', '/eval/agent_fixture.py', 'preflight'])
        emit({'type': 'preflight', 'result': preflight.stdout[-2000:]})
        # Production owns one Prime runtime per task sandbox. Reusing the same
        # sandbox for another entrypoint leaves daemon workers from the first
        # runtime and can exhaust its process/thread budget.
        result = rpc(name, TASK_PROMPT, 'medium')
        emit({'type': 'agent_task', **result})
        case_passes = []
        for label in ('coding', 'browser_console'):
            marker = 'RANGE_APP_PASS' if label == 'coding' else 'BROWSER_CONSOLE_PASS'
            passed = result['ended'] and result['tools'] > 0 and marker in result['final'].splitlines()
            if label == 'coding':
                verified = json.loads(sandbox_exec(name, ['/opt/prime-kernel/bin/python', '/eval/agent_fixture.py', 'verify-code']).stdout)
                passed &= verified.get('passed') is True
            else:
                verified = json.loads(sandbox_exec(name, ['/opt/prime-kernel/bin/python', '/eval/agent_fixture.py', 'events']).stdout)
                passed &= valid_action_counts(verified)
                for filename in ('browser.png', 'console-before.png', 'console-after.png', 'console-later.png'):
                    path = work/'project'/filename
                    try: read_png(path)
                    except (OSError, ValueError): passed = False
            emit({'type': 'case', 'case': label, 'passed': bool(passed), 'verification': verified})
            case_passes.append(bool(passed))
        if not all(case_passes): raise RuntimeError('Agent task failed independent checks')
        sandbox_exec(name, ['/opt/prime-kernel/bin/python', '/eval/agent_fixture.py', 'vision'])
        for width, expected in ((640, 'LARCH-6284'), (1280, 'BEECH-9157')):
            data = base64.b64encode(read_png(work/f'project/vision-{width}.png')).decode()
            reply, metrics = chat(f'http://127.0.0.1:{args.port}', 'qwen3.8-flash-next', [{'role': 'user', 'content': [
                {'type': 'text', 'text': 'Read the image. Return only JSON with keys status and code. No other fields.'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}}]}])
            passed = metrics['finish_reason'] == 'stop' and parse_json(reply['content']) == {'status': 'READY', 'code': expected}
            emit({'type': 'case', 'case': f'vision_{width}', 'passed': passed, 'response': reply['content'], 'metrics': metrics})
            if not passed: raise RuntimeError('Vision mismatch')
        if min(x[0] for x in samples) < .15: raise RuntimeError('Memory floor violated')
        emit({'type': 'acceptance', 'passed': True})
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        stop.set(); thread.join(2)
        emit({'type': 'end', 'min_available_gib': min(x[1] for x in samples), 'model_requests': records})
        out.close()
        try: cleanup(root, invocation)
        finally:
            if server: server.shutdown(); server.server_close()


if __name__ == '__main__': main()
