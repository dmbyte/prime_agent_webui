"""Trusted browser RPC worker, streamed to its own empty OpenShell sandbox.

No arbitrary URL, selector, script, request, cookie/storage, file, or download API.
Only the host broker can write stdin. Never run this inside a general task.
"""
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlsplit


class Browser:
    def __init__(self, request):
        from playwright.sync_api import sync_playwright
        self.runtime = tempfile.TemporaryDirectory(prefix='prime-private-browser-', dir='/tmp')
        self.playwright = self.browser = self.context = None
        self.origin = request['endpoint']
        self.kvm = request['kind'] == 'kvm'
        self.console_frames_before = set()
        try:
            home = self.runtime.name
            env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'XDG_CONFIG_HOME': home, 'XDG_CACHE_HOME': home}
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, env=env,
                args=['--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--no-first-run', '--no-default-browser-check'], timeout=30000)
            self.context = self.browser.new_context(ignore_https_errors=request.get('ignoreCertificateErrors') is True, accept_downloads=False,
                service_workers='block', viewport={'width': 1280, 'height': 720})
            # Guard every navigation, subresource and WebSocket, including redirects
            # and popup requests. The native network policy is a second boundary.
            self.context.route('**/*', lambda route: route.continue_() if self.allowed(route.request.url) else route.abort())
            def websocket(route):
                if self.allowed(route.url, websocket=True):
                    route.connect_to_server()
                else:
                    route.close()
            self.context.route_web_socket('**/*', websocket)
            self.page = self.context.new_page()
            self.page.set_default_timeout(12000)
            self.page.goto(self.origin, wait_until='domcontentloaded', timeout=20000)
            password = self.page.locator('input[type=password]:visible')
            username = self.page.locator('input[type=text]:visible')
            if password.count() != 1 or username.count() != 1:
                raise ValueError('Unsupported login form')
            username.fill(request['username'])
            password.fill(request['password'])
            submit = self.page.get_by_role('button', name=re.compile(r'^(log\s*in|sign\s*in)$', re.I))
            if submit.count() != 1:
                raise ValueError('Unsupported login control')
            submit.click()
            password.wait_for(state='hidden', timeout=15000)
            if not self.allowed(self.page.url):
                raise ValueError('Login left approved BMC')
            if self.kvm:
                self.console_frames_before = {(page, frame.url) for page in self.context.pages for frame in page.frames}
                controls = self.page.get_by_role('link', name=re.compile(r'^HTML5( Remote)? Console$', re.I))
                if controls.count() != 1:
                    controls = self.page.get_by_role('button', name=re.compile(r'^HTML5( Remote)? Console$', re.I))
                if controls.count() != 1:
                    raise ValueError('Unsupported HTML5 console launcher')
                controls.click()
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    if self.canvases():
                        break
                    self.page.wait_for_timeout(100)
                self.surface()
        except BaseException:
            self.close()
            raise
        finally:
            request.clear()  # Never retain the login payload in the request loop.

    def allowed(self, url, websocket=False):
        value, target = urlsplit(url), urlsplit(self.origin)
        return (value.scheme == ('wss' if websocket else 'https') and value.hostname == target.hostname
                and (value.port or 443) == (target.port or 443) and value.username is None and value.password is None)

    def canvases(self):
        found = []
        for page in self.context.pages[:8]:
            for frame in page.frames[:16]:
                if self.kvm and (page, frame.url) in self.console_frames_before:
                    continue  # A pre-existing management chart is not a console.
                if self.allowed(frame.url) and frame.locator('input[type=password]:visible').count() == 0:
                    nodes = frame.locator('canvas:visible')
                    for index in range(min(nodes.count(), 8)):
                        node = nodes.nth(index)
                        box = node.bounding_box()
                        if box and box['width'] >= 320 and box['height'] >= 200:
                            found.append(node)
        return found

    def surface(self):
        nodes = self.canvases()
        if len(nodes) != 1:
            raise ValueError('No unambiguous console surface; control denied')
        return nodes[0]

    def call(self, request):
        action = request['action']
        if action == 'capture':
            if not self.allowed(self.page.url):
                raise ValueError()
            if any(frame.locator('input[type=password]:visible').count() for page in self.context.pages for frame in page.frames):
                raise ValueError('Login content cannot be captured')
            if self.kvm:
                png = self.surface().screenshot(type='png', timeout=10000)
            else:
                png = self.page.screenshot(type='png', full_page=False, mask=[self.page.locator('input,textarea')], timeout=10000)
            if len(png) > 700000:
                raise ValueError()
            return {'mimeType': 'image/png', 'image': base64.b64encode(png).decode()}
        if action == 'input' and self.kvm:
            # Only console focus and approved keys/text; never the management UI.
            surface = self.surface()
            # DOM focus only: an implicit center-click could activate a guest UI
            # button that was not part of the approved key/text action.
            surface.evaluate('(node)=>{node.tabIndex=0;node.focus()}')
            if 'key' in request:
                key = request['key']
                mapping = {'enter': 'Enter', 'escape': 'Escape', 'tab': 'Tab', 'backspace': 'Backspace',
                           'up': 'ArrowUp', 'down': 'ArrowDown', 'left': 'ArrowLeft', 'right': 'ArrowRight'}
                surface.press(mapping.get(key, key.upper()))
            else:
                surface.press_sequentially(request['text'])
            return {'sent': True}
        raise ValueError('Unsupported private browser operation')

    def close(self):
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        finally:
            if self.playwright:
                self.playwright.stop()
            self.runtime.cleanup()


def main():
    browser = None
    try:
        for _ in range(10000):
            raw = sys.stdin.buffer.readline(32769)
            if not raw or len(raw) > 32768 or not raw.endswith(b'\n'):
                break
            try:
                request = json.loads(raw)
                raw = b''
                if request.get('action') == 'open' and browser is None:
                    browser = Browser(request)
                    result = {'opened': True}
                elif request.get('action') == 'close':
                    break
                elif browser:
                    result = browser.call(request)
                else:
                    raise ValueError()
                print(json.dumps({'ok': True, 'result': result}), flush=True)
            except Exception:
                print('{"ok":false}', flush=True)
                break
    finally:
        if browser:
            browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit(1)
