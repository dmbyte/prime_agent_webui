#!/usr/bin/env python3
"""Offline browser-worker and popout test. Run in the network-operations image.

Pass the dashboard source directory; no real BMC or credentials are used.
"""
import base64
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from console_feed import ConsoleFeed, snapshots, watch
from playwright.sync_api import sync_playwright

DASHBOARD = Path(sys.argv[1])
ROOT = None
AUTHORIZED = True


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTHORIZED
        if self.path.startswith('/api/'):
            if not AUTHORIZED:
                self.send_error(403); return
            if self.path.startswith('/api/consoles/frame?id='):
                rows = snapshots(ROOT, self.path.split('id=')[1])
                data = {'session': rows[0] if rows else None}
            else:
                watch(ROOT)
                data = {'sessions': snapshots(ROOT)}
            body = json.dumps(data).encode(); kind = 'application/json'
        elif self.path == '/fixture':
            body = b'<html><title>Viewer test</title><body style="background:navy;color:white;font:60px monospace"><h1>TEST CONSOLE</h1><div id="counter">0</div><script>setInterval(()=>counter.textContent=Number(counter.textContent)+1,400)</script></body></html>'
            kind = 'text/html'
        else:
            name = self.path.removeprefix('/assets/').removeprefix('/')
            if name not in {'console-viewer.html','console-viewer.js','console-viewer.css'}:
                self.send_error(404); return
            body = (DASHBOARD/name).read_bytes()
            kind = 'text/html' if name.endswith('html') else 'text/javascript' if name.endswith('js') else 'text/css'
        self.send_response(200); self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *_args): pass


def main():
    global ROOT, AUTHORIZED
    with tempfile.TemporaryDirectory() as directory:
        ROOT = Path(directory)/'feeds'
        server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}'
        process = subprocess.Popen([sys.executable,'-m','bmc_headless_browser','--worker'],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1,
                                   env={**os.environ,'PRIME_CONSOLE_FEED_DIR':str(ROOT)})
        def call(action, **values):
            process.stdin.write(json.dumps({'id':1,'action':action,**values})+'\n'); process.stdin.flush()
            result=json.loads(process.stdout.readline())
            assert result['ok'], result
            return result.get('result')
        try:
            call('start',baseUrl=url,ignoreHttpsErrors=False,timeoutMs=10000)
            call('goto',target=url+'/fixture')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--disable-dev-shm-usage','--no-zygote'])
                page=browser.new_page(viewport={'width':1100,'height':800})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(url+'/console-viewer.html')
                page.locator('#frame:not([hidden])').wait_for(timeout=12000)
                first=page.locator('#frame').get_attribute('src')
                page.wait_for_function('before => document.querySelector("#frame").src !== before',arg=first,timeout=10000)
                assert page.locator('#frame').evaluate('e=>e.naturalWidth')>0
                page.screenshot(path=os.environ.get('PRIME_VIEWER_TEST_SCREENSHOT', '/tmp/console-viewer-test.png'))
                page.locator('#pause').click()
                page.wait_for_timeout(1200)
                assert 'paused' in page.locator('#status').inner_text().lower()
                page.locator('#pause').click()
                serial=ConsoleFeed('serial','Serial fixture',root=ROOT)
                serial.update(text='BIOS SETUP\n<script>literal, not HTML</script>')
                page.wait_for_function('() => document.querySelectorAll("#source option").length===2')
                page.locator('#source').select_option(serial.id)
                page.locator('#terminal:not([hidden])').wait_for()
                assert '<script>literal' in page.locator('#terminal').inner_text()
                AUTHORIZED=False
                page.wait_for_function('() => document.querySelector("#status").textContent.includes("Sign in")')
                assert page.locator('#frame').get_attribute('src') is None
                assert page.locator('#terminal').inner_text()==''
                assert not errors, errors
                browser.close()
            call('close')
            assert all(row['state']=='closed' for row in snapshots(ROOT) if row['kind']=='browser')
            print('PASS: idle live browser frames, rendered popout, pause/resume, serial text, and auth clearing')
        finally:
            process.stdin.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=5)
            server.shutdown()


if __name__=='__main__': main()
