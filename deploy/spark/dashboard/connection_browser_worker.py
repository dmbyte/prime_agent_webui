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

STAGES = {'launch', 'navigation', 'login-form', 'login-submit', 'console-launch', 'console-surface'}


class Browser:
    def __init__(self, request):
        from playwright.sync_api import sync_playwright
        self.runtime = tempfile.TemporaryDirectory(prefix='prime-private-browser-', dir='/tmp')
        self.playwright = self.browser = self.context = None
        self.origin = request['endpoint']
        self.kvm = request['kind'] == 'kvm'
        self.console_canvases_before = {}
        self.authenticated = False
        stage = 'launch'
        try:
            home = self.runtime.name
            env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'XDG_CONFIG_HOME': home, 'XDG_CACHE_HOME': home}
            self.playwright = sync_playwright().start()
            proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            proxy_options = {'proxy': {'server': proxy}} if proxy else {}
            self.browser = self.playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, env=env,
                args=['--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--no-first-run', '--no-default-browser-check'], timeout=30000,
                **proxy_options)
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
            stage = 'navigation'
            self.page.goto(self.origin, wait_until='domcontentloaded', timeout=20000)
            stage = 'login-form'
            frame = self.login_frame()
            password = frame.locator('input[type=password]:visible')
            username = frame.locator('input[type=text]:visible, input[type=email]:visible')
            submit = frame.get_by_role('button', name=re.compile(r'^(log\s*in|sign\s*in)$', re.I))
            if submit.count() != 1:
                raise ValueError('Unsupported login control')
            username.fill(request['username'])
            password.fill(request['password'])
            stage = 'login-submit'
            submit.click()
            password.wait_for(state='hidden', timeout=15000)
            if not self.allowed(self.page.url):
                raise ValueError('Login left approved BMC')
            self.authenticated = True
            if self.kvm:
                stage = 'console-launch'
                controls = self.console_launcher()
                self.console_canvases_before = {frame: frame.locator('canvas:visible').element_handles()
                    for page in self.context.pages[:8] for frame in page.frames[:16] if self.allowed(frame.url)}
                controls.click()
                stage = 'console-surface'
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    if self.canvases():
                        break
                    self.page.wait_for_timeout(100)
                self.surface()
        except BaseException as error:
            self.close()
            error.prime_stage = stage
            raise
        finally:
            request.clear()  # Never retain the login payload in the request loop.

    def allowed(self, url, websocket=False):
        value, target = urlsplit(url), urlsplit(self.origin)
        return (value.scheme == ('wss' if websocket else 'https') and value.hostname == target.hostname
                and (value.port or 443) == (target.port or 443) and value.username is None and value.password is None)

    def login_frame(self):
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            candidates = []
            for frame in self.page.frames[:16]:
                if not self.allowed(frame.url):
                    continue
                passwords = frame.locator('input[type=password]:visible').count()
                if passwords:
                    usernames = frame.locator('input[type=text]:visible, input[type=email]:visible').count()
                    if passwords != 1 or usernames > 1:
                        raise ValueError('Ambiguous login form')
                    if usernames == 1:
                        candidates.append(frame)
            if len(candidates) > 1:
                raise ValueError('Ambiguous login frames')
            if candidates:
                return candidates[0]
            self.page.wait_for_timeout(100)
        raise ValueError('Supported login form not found')

    def console_launcher(self):
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            candidates = []
            for frame in self.page.frames[:16]:
                if not self.allowed(frame.url): continue
                # Observed iLO 4 overview uses a short HTML5 label. Never apply
                # that ambiguous shortcut to arbitrary pages or management charts.
                pattern = r'^HTML5( Remote)? Console$'
                if urlsplit(frame.url).path == '/html/summary.html':
                    pattern = r'^(HTML5|HTML5( Remote)? Console)$'
                for role in ('link', 'button'):
                    controls = frame.get_by_role(role, name=re.compile(pattern, re.I))
                    candidates.extend(controls.all())
            if len(candidates) > 1: raise ValueError('Ambiguous HTML5 console launcher')
            if candidates: return candidates[0]
            self.page.wait_for_timeout(100)
        raise ValueError('Unsupported HTML5 console launcher')

    def canvases(self):
        found = []
        for page in self.context.pages[:8]:
            for frame in page.frames[:16]:
                if self.allowed(frame.url) and frame.locator('input[type=password]:visible').count() == 0:
                    nodes = frame.locator('canvas:visible')
                    for index in range(min(nodes.count(), 8)):
                        node = nodes.nth(index)
                        # iLO 4 inserts a new console into an existing frame.
                        # Exclude pre-launch visible elements, not the entire frame;
                        # a management chart must never receive console input.
                        if self.kvm and any(node.evaluate('(node, before) => node === before', before)
                                for before in self.console_canvases_before.get(frame, [])):
                            continue
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
                png = self.page.screenshot(type='png', full_page=False,
                    mask=[frame.locator('input,textarea') for frame in self.page.frames[:16] if self.allowed(frame.url)], timeout=10000)
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
            if self.authenticated:
                # Best effort logout of this private browser's session only.
                # Never call an account-wide session deletion/deactivation API.
                try:
                    controls = []
                    for frame in self.page.frames[:16]:
                        if not self.allowed(frame.url): continue
                        for role in ('link', 'button'):
                            controls.extend(frame.get_by_role(role, name=re.compile(r'^(sign\s*out|log\s*out)$', re.I)).all())
                    if len(controls) == 1: controls[0].click(timeout=2000)
                except Exception:
                    pass
                self.authenticated = False
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
            except Exception as error:
                stage = getattr(error, 'prime_stage', '')
                print(json.dumps({'ok':False, 'stage':stage if stage in STAGES else 'operation'}), flush=True)
                break
    finally:
        if browser:
            browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit(1)
