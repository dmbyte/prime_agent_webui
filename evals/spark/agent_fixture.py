"""Trusted synthetic fixtures, executed ONLY inside the evaluation sandbox."""
import base64
import asyncio
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

EVENTS = {'login': 0, 'key': 0}
LOGIN = '''<title>Evaluation login</title><input id=user><input id=password type=password>
<button id=login onclick="fetch('/login',{method:'POST'}).then(()=>location='/panel')">Log in</button>'''
PANEL = '<title>Evaluation panel</title><iframe src="/console" width=900 height=600></iframe>'
CONSOLE = '''<canvas id=screen width=800 height=500 tabindex=0></canvas><script>
let c=document.querySelector('canvas'),x=c.getContext('2d');x.fillStyle='navy';x.fillRect(0,0,800,500);
x.fillStyle='white';x.font='32px sans-serif';x.fillText('SYNTHETIC BOOT: READY',40,90);
c.addEventListener('keydown',e=>{if(e.key==='F9'){e.preventDefault();fetch('/key',{method:'POST'}).then(()=>parent.document.title='Evaluation F9 received')}});
</script>'''


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(EVENTS) if self.path == '/events' else PANEL if self.path == '/panel' else CONSOLE if self.path == '/console' else LOGIN
        raw = body.encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html'); self.send_header('Content-Length', str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_POST(self):
        if self.path == '/login': EVENTS['login'] += 1
        elif self.path == '/key': EVENTS['key'] += 1
        else: self.send_error(404); return
        self.send_response(204); self.end_headers()

    def log_message(self, *_): pass


class FixtureConsole:
    """Test-only transport to the installed real KVM worker, not the user broker.

    call(action, **values) uses the worker's actual action schema. capture(path)
    writes a PNG below /project. No saved target, credentials or user session.
    """
    def __init__(self):
        self.process = subprocess.Popen([sys.executable, '-m', 'bmc_html5_kvm', '--worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def call(self, action, **values):
        self.process.stdin.write(json.dumps({'action': action, **values}) + '\n'); self.process.stdin.flush()
        result = json.loads(self.process.stdout.readline(3500001))
        if not result.get('ok'): raise RuntimeError(result.get('error', 'Worker failure'))
        return result['result']

    def capture(self, path):
        path = Path(path).resolve()
        if Path('/project') not in path.parents: raise ValueError('Only evaluation project outputs allowed')
        data = base64.b64decode(self.call('capture', format='png')['png'])
        if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Invalid PNG')
        path.write_bytes(data)
        return str(path)

    def close(self):
        try:
            if self.process.poll() is None: self.call('close')
        finally:
            if self.process.poll() is None: self.process.terminate()
            try: self.process.wait(5)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()


def verify_code():
    # Model-generated code is imported in OpenShell, NEVER on the host.
    spec = importlib.util.spec_from_file_location('range_server', '/project/range_server.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    cases = [(None, 10, (200, 0, 9)), ('bytes=2-5', 10, (206, 2, 5)),
             ('bytes=8-', 10, (206, 8, 9)), ('bytes=-3', 10, (206, 7, 9)),
             ('bytes=5-99', 10, (206, 5, 9)), ('bytes=10-', 10, (416, None, None)),
             ('bytes=5-2', 10, (416, None, None)), ('bytes=-0', 10, (416, None, None)),
             ('bytes=0-1,4-5', 10, (416, None, None)), ('garbage', 10, (416, None, None)),
             (None, 0, (200, None, None)), ('bytes=0-', 0, (416, None, None)),
             ('bytes=4294967296-', 5368709120, (206, 4294967296, 5368709119))]
    for header, size, expected in cases:
        assert tuple(module.parse_range(header, size)) == expected, (header, size)
    print(json.dumps({'passed': True, 'checks': len(cases)}))


def vision_fixtures():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='prime-vision-', dir='/tmp') as runtime, sync_playwright() as p:
        home = Path(runtime)
        (home/'config').mkdir(); (home/'cache').mkdir()
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                   env=dict(os.environ, HOME=runtime, XDG_CONFIG_HOME=str(home/'config'), XDG_CACHE_HOME=str(home/'cache')),
                                   args=['--disable-dev-shm-usage', '--disable-gpu', '--no-zygote'])
        try:
            for width, height, tag in ((640, 360, 'LARCH-6284'), (1280, 720, 'BEECH-9157')):
                page = browser.new_page(viewport={'width': width, 'height': height})
                page.set_content('<body style="background:#123;color:white;font:32px sans-serif;padding:40px">'
                                 f'<h2>TEST STATUS: READY</h2><p>Code: {tag}</p></body>')
                page.screenshot(path=f'/project/vision-{width}.png'); page.close()
        finally: browser.close()


def preflight():
    from bmc_headless_browser import BMCBrowser
    socket = '/tmp/eval-browser-preflight.sock'
    os.environ['BMC_BROWSER_BROKER'] = socket
    daemon = subprocess.Popen([sys.executable, '-m', 'bmc_headless_browser', '--daemon', socket],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    async def browse():
        async with BMCBrowser('http://127.0.0.1:8123') as browser:
            await browser.goto('/')
            assert await browser.title() == 'Evaluation login'
    try:
        for _ in range(100):
            if Path(socket).exists(): break
            time.sleep(.1)
        asyncio.run(browse())
        console = FixtureConsole()
        try:
            console.call('open', url='http://127.0.0.1:8123/panel')
            assert console.call('inspect')['consoleSurfaces']
        finally: console.close()
        vision_fixtures()
        print(json.dumps({'browser': True, 'console': True, 'image_generation': True}))
    finally:
        daemon.terminate()
        try: daemon.wait(5)
        except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()


if __name__ == '__main__':
    if sys.argv[1] == 'serve': http.server.ThreadingHTTPServer(('127.0.0.1', 8123), Handler).serve_forever()
    elif sys.argv[1] == 'verify-code': verify_code()
    elif sys.argv[1] == 'vision': vision_fixtures()
    elif sys.argv[1] == 'preflight': preflight()
    elif sys.argv[1] == 'events':
        print(urllib.request.urlopen('http://127.0.0.1:8123/events', timeout=5).read().decode())
