#!/usr/bin/env python3
"""End-to-end broker fixture through LAN OpenShell; no BMC is contacted."""

import http.server
import os
import sys
import tempfile
import threading
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent / "skills/bmc-html5-kvm/src"))
from bmc_html5_kvm import KVMClient


PAGE = b"""<!doctype html><title>Fixture login</title>
<input id='password' type='password'><button id='open' onclick="window.open('/framed?view=kvm#screen','_blank')">Open console</button>"""
CONSOLE = b"""<!doctype html><title>Fixture console</title>
<canvas id='screen' width='800' height='500' tabindex='0' style='background:navy'></canvas>
<script>const c=document.querySelector('canvas');
c.addEventListener('click',()=>{c.focus();document.title='Focused console'});
window.addEventListener('keydown',e=>parent.document.title='Key '+e.key);</script>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (CONSOLE if self.path == "/console" else b'<title>Framed console</title><iframe src="/console" width="900" height="600"></iframe>' if self.path.startswith('/framed') else PAGE)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main() -> None:
    host = os.environ.get("PRIME_KVM_TEST_HOST", "172.16.253.231")
    os.environ["PRIME_KVM_SOCKET"] = "/var/lib/prime-runner/gateway/dbyte/lan/kvm.sock"
    server = http.server.ThreadingHTTPServer((host, 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    kvm = None
    try:
        kvm = KVMClient.create(f"http://{host}:{server.server_port}/")
        session_id = kvm.session_id
        assert kvm.inspect()["loginFormPresent"]
        try:
            kvm.key("F9",confirm=True)
        except RuntimeError as error:
            assert "No focused graphical console" in str(error)
        else: raise AssertionError("Login page accepted console keyboard input")
        assert any(row["sessionId"] == session_id for row in KVMClient.list_sessions())
        kvm.click("#open", confirm=True)
        pages = []
        for _ in range(30):
            pages = kvm.pages()
            if len(pages) >= 2:
                break
            time.sleep(.1)
        assert len(pages) >= 2, pages
        kvm.select_page(1)
        inspection=kvm.inspect()
        assert len(inspection['frames'])==2
        assert inspection['consoleSurfaces'][0]['selector']=='#screen'
        kvm.select_frame(inspection['consoleSurfaces'][0]['frameIndex'])
        assert kvm.inspect()['canvasCount']==1
        # A fresh client connection models the next Prime task reconnecting.
        kvm = KVMClient.connect(session_id)
        with tempfile.TemporaryDirectory() as directory:
            os.environ["PRIME_WORKSPACE"] = directory
            frame = kvm.capture(str(Path(directory) / "frame.jpg"))
            assert frame.stat().st_size > 100
            assert kvm.capture(str(Path(directory)/'frame.png')).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        kvm.focus_console("#screen", confirm=True)
        kvm.key("F9", confirm=True)
        assert any(row["title"] == "Key F9" for row in kvm.pages())
        reused = KVMClient.create(f"http://{host}:{server.server_port}/")
        assert reused.session_id == session_id
        assert any(row["title"] == "Key F9" for row in reused.pages())
        try:
            KVMClient.create(f"http://{host}:{server.server_port}/redfish/v1/")
        except RuntimeError as error:
            assert "Redfish is an API" in str(error)
        else:
            raise AssertionError("Redfish URL incorrectly accepted for KVM")
        print("Persistent KVM broker ready: reconnect, frame, input, reuse without reload, and API URL rejection")
    finally:
        if kvm is not None:
            kvm.close()
        server.shutdown()


if __name__ == "__main__":
    main()
