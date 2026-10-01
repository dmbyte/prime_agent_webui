#!/usr/bin/env python3
"""Exercise task startup, HTTP proxy, and IPython browser use without a BMC."""

import http.server
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, "/usr/local/lib/prime-runner")
import openshell_runner


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"fixture":true}' if self.path.startswith('/redfish/') else b'<title>Prime gateway fixture</title>'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


CODE = r'''
import os, subprocess, time, socket, requests
from IPython.core.interactiveshell import InteractiveShell
from ipmi_redfish_bmc import RedfishClient, IPMIClient
fixture = FIXTURE_URL
process = subprocess.Popen(['/usr/local/bin/prime-container-entrypoint', '--cwd', '/project', '--mode', 'rpc'],
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
try:
    for attempt in range(100):
        if process.poll() is not None:
            raise RuntimeError('Task entrypoint exited before readiness')
        try:
            with socket.create_connection(('127.0.0.1',31080),timeout=.2): pass
            if os.path.exists('/tmp/prime-bmc-browser.sock'): break
        except OSError: pass
        time.sleep(.1)
    else: raise RuntimeError('Task gateway did not become ready')
    os.environ.update(HTTP_PROXY='http://127.0.0.1:31080', HTTPS_PROXY='http://127.0.0.1:31080',
                      http_proxy='http://127.0.0.1:31080', https_proxy='http://127.0.0.1:31080')
    assert RedfishClient(fixture,'fixture','fixture').root() == {'fixture':True}
    shell = InteractiveShell.instance()
    shell.user_ns['fixture'] = fixture
    result = shell.run_cell("from bmc_headless_browser import BMCBrowser\nasync with BMCBrowser(fixture) as browser:\n    await browser.goto('/')\n    assert await browser.title() == 'Prime gateway fixture'\n")
    if result.error_before_exec or result.error_in_exec:
        raise RuntimeError('IPython browser fixture failed')
    for _ in range(8):
        with socket.create_connection(('127.0.0.1',31080),timeout=3): pass
    # Direct egress remains denied: the repair must not loosen OpenShell policy.
    from urllib.parse import urlparse
    target=urlparse(fixture)
    try:
        direct=socket.create_connection((target.hostname,target.port),timeout=3)
    except PermissionError: pass
    else:
        direct.close()
        raise AssertionError('Direct egress unexpectedly allowed')
    assert RedfishClient(fixture,'fixture','fixture').root() == {'fixture':True}
    blocked=requests.get('http://127.0.0.2/',proxies={'http':'http://127.0.0.1:31080'},timeout=5)
    assert blocked.status_code == 403
    assert RedfishClient(fixture,'fixture','fixture').root() == {'fixture':True}
    try: IPMIClient('bmc.invalid','fixture','fixture')
    except RuntimeError as error: assert 'UDP transport is not supported' in str(error)
    else: raise AssertionError('Unsupported IPMI did not fail fast')
    assert process.poll() is None
    print('Task gateway passed: Redfish, IPython browser, aborted connections, denied egress, IPMI guidance')
finally:
    process.terminate()
    try: process.wait(5)
    except subprocess.TimeoutExpired: process.kill(); process.wait()
'''


def main():
    if os.geteuid() == 0:
        raise SystemExit("Run as prime-runner")
    owner = os.environ["PRIME_WEB_OWNER"]
    root = Path("/var/lib/prime-runner")
    manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "openshell-image-digests.json"
    host = os.environ.get("PRIME_KVM_TEST_HOST", "172.16.253.231")
    server = http.server.ThreadingHTTPServer((host, 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for network in ("lan", "full"):
            spec = openshell_runner.task_spec(uuid.uuid4().hex, owner,
                {"profile":"network-operations", "networkMode":network, "executionMode":"task",
                 "approvalMode":"manual", "limits":{"memoryGiB":2,"cpus":1,"runtimeMinutes":5}},
                "spark-nemotron", "canary", "low", storage_root=root / "users", image_manifest=manifest,
                policy_root=root / "openshell-policies", workspace_root=Path(f"/home/{owner}/prime-agent/tasks"))
            try:
                subprocess.run(spec["create"], check=True, timeout=90)
                environment = []
                for index, argument in enumerate(spec["execute"]):
                    if argument == "--env": environment.extend([argument, spec["execute"][index+1]])
                code = CODE.replace('FIXTURE_URL', json.dumps(f'http://{host}:{server.server_port}'))
                subprocess.run(['/usr/bin/openshell','--gateway','spark-local','sandbox','exec','--name',
                                spec['name'],'--workdir','/project','--no-tty',*environment,'--',
                                '/opt/prime-kernel/bin/python','-c',code],check=True,timeout=75)
                print(f"{network} task gateway validated", flush=True)
            finally:
                subprocess.run(spec['delete'],check=False,timeout=45)
                spec['policy'].unlink(missing_ok=True)
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
