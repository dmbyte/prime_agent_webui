#!/usr/bin/env python3
"""Offline Chromium fixture for the long-running HTML5 KVM worker.

Run inside the network-operations image; no BMC or credentials are contacted.
"""

import base64
import http.server
import json
import subprocess
import sys
import threading
import time


ROOT = b"""<!doctype html><html><head><title>Fixture login</title></head><body>
<input id='user'><input id='password' type='password' value='must-not-appear'><button id='open' onclick="window.open('/console?view=kvm#screen','_blank')">Console</button>
</body></html>"""
CONSOLE = b"""<!doctype html><html><head><title>Fixture console</title></head><body>
<canvas id='screen' width='800' height='500' tabindex='0' style='background: navy'></canvas>
<script>
const c=document.querySelector('#screen');
c.addEventListener('click',()=>{c.focus();document.title='Focused console'});
window.addEventListener('keydown',e=>{document.title='Key '+e.key});
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = CONSOLE if self.path.startswith("/console") else ROOT
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen([sys.executable, "-m", "bmc_html5_kvm", "--worker"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)

    def call(action, **values):
        process.stdin.write(json.dumps({"action": action, **values}) + "\n")
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        if not response.get("ok"):
            raise AssertionError(f"{action}: {response}")
        return response["result"]

    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        assert call("open", url=url)["status"] == 200
        inspected=call("inspect")
        assert inspected["loginFormPresent"] and inspected["canvasCount"] == 0
        assert 'must-not-appear' not in json.dumps(inspected)
        try:
            call("key",key="F9",confirm=True)
        except AssertionError as error:
            assert 'No focused graphical console' in str(error)
        else: raise AssertionError('Management page accepted console input')
        png=base64.b64decode(call("capture",format="png")["png"])
        assert png.startswith(b'\x89PNG\r\n\x1a\n')
        try:
            call("click", selector="#open", x=.5, y=.5)
        except AssertionError:
            pass  # The confirmation gate must reject this request.
        else:
            raise AssertionError("Unconfirmed input was accepted")
        call("fill", selector="#user", value="fixture", confirm=True)
        call("click", selector="#open", x=.5, y=.5, confirm=True)
        pages = []
        for _ in range(20):
            pages = call("pages")["pages"]
            if len(pages) >= 2:
                break
            time.sleep(.1)
        assert len(pages) >= 2, pages
        call("select_page", index=1)
        jpeg = base64.b64decode(call("capture")["jpeg"])
        assert jpeg.startswith(b"\xff\xd8") and len(jpeg) < 2_000_000
        assert call("inspect")["canvasCount"] == 1
        call("focus_console", selector="#screen", confirm=True)
        call("key", key="F9", confirm=True)
        titles = [page["title"] for page in call("pages")["pages"]]
        assert "Key F9" in titles, titles
        call("close")
        print("KVM browser fixture ready: popup, frame, mouse, key, and confirmation")
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        server.shutdown()


if __name__ == "__main__":
    main()
