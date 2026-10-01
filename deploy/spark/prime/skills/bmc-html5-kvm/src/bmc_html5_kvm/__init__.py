"""Reconnectable client and isolated worker for a bounded HTML5 BMC console."""

from __future__ import annotations

import base64
import json
import os
import re
import select
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse


SOCKET = "/run/prime-gateway/kvm.sock"
MAX_FRAME = 2_000_000
KEYS = {"Enter", "Escape", "Tab", "Backspace", "Delete", "Insert", "Home", "End",
        "PageUp", "PageDown", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        *(f"F{number}" for number in range(1, 13))}


def _origin(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("BMC URL must be absolute HTTP(S) without embedded credentials")
    return _page_origin(value)


def _page_origin(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Page must have an HTTP(S) origin without embedded credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, f"{parsed.hostname.lower()}:{port}"


def _allowed_initial_redirect(source: str, target: str) -> bool:
    if _page_origin(source) == _page_origin(target):
        return True
    old, new = urlparse(source), urlparse(target)
    return (old.scheme == "http" and new.scheme == "https" and old.hostname == new.hostname
            and old.port in {None, 80} and new.port in {None, 443})


def _display_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _broker(request: dict) -> dict:
    path = os.environ.get("PRIME_KVM_SOCKET", SOCKET)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(65)
    try:
        try:
            connection.connect(path)
        except FileNotFoundError as error:
            raise RuntimeError(
                "KVM control socket is missing. Start a new Network operations task "
                "with LAN/VPN or Full network egress. If already selected, the "
                "administrator must check the KVM broker and task socket mount."
            ) from error
        except ConnectionRefusedError as error:
            raise RuntimeError("KVM control socket exists but its broker is not accepting connections") from error
        with connection.makefile("rwb", buffering=0) as stream:
            stream.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            raw = stream.readline(3_500_001)
        if not raw or len(raw) > 3_500_000:
            raise RuntimeError("KVM broker returned no bounded response")
        response = json.loads(raw)
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "KVM broker failed")))
        return response.get("result") or {}
    finally:
        connection.close()


class KVMClient:
    """A session handle; each method reconnects to a broker outside Prime tasks."""

    def __init__(self, session_id: str):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Invalid KVM session ID")
        self.session_id = session_id

    @classmethod
    def create(cls, base_url: str, *, ignore_https_errors: bool = False) -> "KVMClient":
        _origin(base_url)
        result = _broker({"action": "create", "url": base_url,
                          "ignoreHttpsErrors": bool(ignore_https_errors)})
        return cls(result["sessionId"])

    @classmethod
    def connect(cls, session_id: str) -> "KVMClient":
        handle = cls(session_id)
        handle.status()  # Reject expired or unknown sessions immediately.
        return handle

    @staticmethod
    def list_sessions() -> list[dict]:
        return _broker({"action": "list"})["sessions"]

    def _call(self, action: str, **values) -> dict:
        return _broker({"action": action, "sessionId": self.session_id, **values})

    def status(self) -> dict:
        return self._call("status")

    def pages(self) -> list[dict]:
        return self._call("pages")["pages"]

    def inspect(self) -> dict:
        """Read bounded page/frame/control metadata; never form values."""
        return self._call("inspect")

    def select_frame(self, index: int) -> dict:
        if not isinstance(index, int) or not 0 <= index < 16:
            raise ValueError("KVM frame index must be 0–15")
        return self._call("select_frame", index=index)

    def focus_console(self, selector: str = "canvas", *, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("Console focus requires target/action-specific authorization")
        if not isinstance(selector, str) or not selector or len(selector) > 256:
            raise ValueError("Invalid console selector")
        return self._call("focus_console", selector=selector, confirm=True)

    def select_page(self, index: int) -> dict:
        if not 0 <= index <= 7:
            raise ValueError("KVM page index must be 0–7")
        return self._call("select_page", index=index)

    def capture(self, filename: str | os.PathLike[str] = "kvm-frame.png") -> Path:
        workspace = Path(os.environ.get("PRIME_WORKSPACE", "/project")).resolve()
        target = (workspace / Path(filename)).resolve()
        if workspace not in target.parents or target.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError("Save KVM screenshots below the task workspace as PNG or JPEG; use capture('kvm-frame.png') or /project/kvm-frame.jpg")
        kind = "png" if target.suffix.lower() == ".png" else "jpeg"
        result = self._call("capture", format=kind)
        frame = base64.b64decode(result[kind], validate=True)
        signature = b"\x89PNG\r\n\x1a\n" if kind == "png" else b"\xff\xd8"
        if len(frame) > MAX_FRAME or not frame.startswith(signature):
            raise ValueError("KVM frame is not a bounded PNG/JPEG image")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(frame)
        os.chmod(target, 0o600)
        return target

    def fill(self, selector: str, value: str, *, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("KVM form input requires target/action-specific authorization")
        if not selector or len(selector) > 256 or len(value) > 4096:
            raise ValueError("Invalid KVM form input")
        return self._call("fill", selector=selector, value=value, confirm=True)

    def click(self, selector: str, x: float = .5, y: float = .5, *, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("KVM mouse input requires target/action-specific authorization")
        if not selector or len(selector) > 256 or not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError("Invalid KVM selector or normalized coordinates")
        return self._call("click", selector=selector, x=float(x), y=float(y), confirm=True)

    def key(self, key: str, *, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("KVM keyboard input requires target/action-specific authorization")
        if not isinstance(key, str) or (key not in KEYS and not (len(key) == 1 and 32 <= ord(key) <= 126)):
            raise ValueError("Unsupported KVM key")
        return self._call("key", key=key, confirm=True)

    def type_text(self, value: str, *, confirm: bool = False) -> dict:
        if not confirm:
            raise PermissionError("KVM text input requires target/action-specific authorization")
        if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(not 32 <= ord(c) <= 126 for c in value):
            raise ValueError("KVM text must be 1–128 printable ASCII characters")
        return self._call("type_text", value=value, confirm=True)

    def close(self) -> None:
        self._call("close")


def _start_proxy() -> subprocess.Popen | None:
    if not Path("/run/prime-gateway/network.sock").is_socket():
        return None
    proxy = subprocess.Popen(["/usr/bin/python3", "/usr/local/lib/prime-gateway-relay.py", "network"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ.update(HTTP_PROXY="http://127.0.0.1:31080", HTTPS_PROXY="http://127.0.0.1:31080",
                      ALL_PROXY="http://127.0.0.1:31080", NO_PROXY="127.0.0.1,localhost,::1")
    for _ in range(20):
        if proxy.poll() is not None:
            raise RuntimeError("BMC network proxy exited during startup")
        try:
            with socket.create_connection(("127.0.0.1", 31080), timeout=.1):
                break
        except OSError:
            time.sleep(.05)
    else:
        proxy.terminate()
        raise RuntimeError("BMC network proxy did not become ready")
    return proxy


def _inspect_frame(frame) -> dict:
    return frame.evaluate("""() => {
      const visible=e=>!!(e.getClientRects().length && e.getBoundingClientRect().width && e.getBoundingClientRect().height);
      const selector=e=>{
        if(e.id) return '#'+CSS.escape(e.id);
        const path=[];
        while(e && e.tagName!=='HTML') {
          const tag=e.tagName.toLowerCase();
          const siblings=Array.from(e.parentElement?.children||[]).filter(n=>n.tagName===e.tagName);
          path.unshift(tag+':nth-of-type('+(siblings.indexOf(e)+1)+')'); e=e.parentElement;
        }
        return 'html > '+path.join(' > ');
      };
      const controls=Array.from(document.querySelectorAll('button,a,input,canvas,video,object,embed,applet')).filter(visible).slice(0,50).map(e=>({
        tag:e.tagName.toLowerCase(), selector:selector(e),
        label:(e.getAttribute('aria-label')||e.getAttribute('title')||(e.tagName==='INPUT'?'':e.innerText)||'').trim().slice(0,100),
        inputType:e.tagName==='INPUT'?e.type:null,
        width:Math.round(e.getBoundingClientRect().width),height:Math.round(e.getBoundingClientRect().height)
      }));
      return {controls,canvasCount:controls.filter(e=>e.tag==='canvas').length,
        loginFormPresent:Array.from(document.querySelectorAll('input[type=password]')).some(visible),
        legacyPluginPresent:!!document.querySelector('applet,object,embed'),
        focusedTag:document.activeElement?.tagName.toLowerCase()||null,
        note:'A management/login page is not a server console. Inspect a screenshot and identify the console before sending input.'};
    }""")


def _require_console_focus(frame):
    if not frame.evaluate("""() => {
      const e=document.activeElement;
      return document.hasFocus() && !!e && ['CANVAS','VIDEO'].includes(e.tagName) && e.getBoundingClientRect().width>50 && e.getBoundingClientRect().height>50;
    }"""):
        raise ValueError("No focused graphical console surface. Use inspect(), select the actual console page/frame, then focus_console() after inspecting its screenshot. Do not send keys to the iLO management page.")


def _frame_info(frame, index, origin):
    row = {"index": index, "url": _display_url(frame.url), "consoleSurfaces": []}
    try:
        if frame.url != "about:blank" and _page_origin(frame.url) != origin:
            row["readable"] = False
            return row
        details = _inspect_frame(frame)
        row.update(readable=True, loginFormPresent=details["loginFormPresent"],
                   legacyPluginPresent=details["legacyPluginPresent"])
        row["consoleSurfaces"] = [{"frameIndex":index, "selector":c["selector"], "tag":c["tag"],
                                   "width":c["width"], "height":c["height"]}
                                  for c in details["controls"] if c["tag"] in {"canvas","video"}
                                  and c["width"]>50 and c["height"]>50][:8]
    except Exception:
        row["readable"] = False  # A frame may navigate/detach during inspection.
    return row


def worker_main() -> int:
    """Serve line-framed calls inside one dedicated OpenShell sandbox."""
    from playwright.sync_api import sync_playwright

    proxy = _start_proxy()
    runtime = tempfile.TemporaryDirectory(prefix="prime-kvm-", dir="/tmp")
    home = Path(runtime.name)
    (home / "config").mkdir(mode=0o700)
    (home / "cache").mkdir(mode=0o700)
    browser_env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
                       XDG_CACHE_HOME=str(home / "cache"))
    playwright = browser = context = None
    selected = 0
    selected_frame = 0
    origin = None
    try:
        for raw in sys.stdin:
            request = {}
            stop = False
            try:
                if len(raw) > 16_384:
                    raise ValueError("KVM request exceeds limit")
                request = json.loads(raw)
                action = request.get("action")
                if action == "open":
                    if browser is not None:
                        raise RuntimeError("KVM browser is already open")
                    origin = _origin(request["url"])
                    playwright = sync_playwright().start()
                    browser = playwright.chromium.launch(
                        executable_path="/usr/bin/chromium", headless=True, env=browser_env,
                        args=["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
                              "--no-first-run", "--no-default-browser-check"], timeout=30_000)
                    context = browser.new_context(ignore_https_errors=bool(request.get("ignoreHttpsErrors")),
                                                  viewport={"width": 1600, "height": 900},
                                                  accept_downloads=False)
                    page = context.new_page()
                    page.set_default_timeout(20_000)
                    response = page.goto(request["url"], wait_until="domcontentloaded", timeout=30_000)
                    if not _allowed_initial_redirect(request["url"], page.url):
                        raise ValueError("BMC login redirected to a different origin; use its explicit trusted URL")
                    origin = _page_origin(page.url)
                    result = {"url": _display_url(page.url), "status": response.status if response else None}
                elif action == "close":
                    result, stop = {}, True
                elif context is None:
                    raise RuntimeError("KVM browser is not open")
                elif action == "pages":
                    result = {"pages": [{"index": index, "url": _display_url(page.url), "title": page.title()[:160]}
                                         for index, page in enumerate(context.pages[:8]) if not page.is_closed()]}
                else:
                    pages = context.pages
                    if not 0 <= selected < len(pages) or pages[selected].is_closed():
                        raise RuntimeError("Selected KVM page has closed")
                    page = pages[selected]
                    if action == "select_page":
                        index = request["index"]
                        if not isinstance(index, int) or not 0 <= index < min(8, len(pages)):
                            raise ValueError("KVM page index is unavailable. Use indexes from pages(); an embedded iframe is not a page. Use inspect() and select_frame(index) for it.")
                        candidate = pages[index]
                        if candidate.url != "about:blank" and _page_origin(candidate.url) != origin:
                            raise ValueError("KVM page is outside the configured BMC origin")
                        selected = index
                        selected_frame = 0
                        result = {"index": index, "url": _display_url(candidate.url)}
                    else:
                        if page.url != "about:blank" and _page_origin(page.url) != origin:
                            raise ValueError("Selected KVM page navigated outside the configured BMC origin")
                        frames = page.frames[:16]
                        if action == "select_frame":
                            index = request.get("index")
                            if not isinstance(index, int) or not 0 <= index < len(frames):
                                raise ValueError("KVM frame index is unavailable")
                            if frames[index].url != "about:blank" and _page_origin(frames[index].url) != origin:
                                raise ValueError("Frame is outside the configured BMC origin")
                            selected_frame = index
                        if not 0 <= selected_frame < len(frames):
                            raise ValueError("Selected frame disappeared; inspect and select it again")
                        frame = frames[selected_frame]
                        if frame.url != "about:blank" and _page_origin(frame.url) != origin:
                            raise ValueError("Frame is outside the configured BMC origin")
                        if action == "status":
                            result = {"url": _display_url(page.url), "selectedPage": selected, "selectedFrame": selected_frame, "pageCount": len(pages)}
                        elif action == "select_frame":
                            result = {"index": selected_frame, "url": _display_url(frame.url)}
                        elif action == "inspect":
                            frame_info = [_frame_info(f,i,origin) for i,f in enumerate(frames)]
                            result = {"selectedPage": selected, "pageCount": len(pages), "selectedFrame": selected_frame,
                                      "frames": frame_info,
                                      "consoleSurfaces": [s for f in frame_info for s in f["consoleSurfaces"]],
                                      **_inspect_frame(frame)}
                        elif action == "capture":
                            kind = request.get("format", "jpeg")
                            if kind not in {"jpeg", "png"}:
                                raise ValueError("KVM screenshots support PNG or JPEG")
                            data = page.screenshot(type=kind, **({"quality":70} if kind == "jpeg" else {}), scale="css", animations="disabled",
                                                   timeout=20_000)
                            if len(data) > MAX_FRAME:
                                raise ValueError("KVM frame exceeds 2 MB")
                            result = {kind: base64.b64encode(data).decode()}
                        elif action in {"fill", "click", "key", "type_text", "focus_console"}:
                            if request.get("confirm") is not True:
                                raise PermissionError("KVM input requires explicit confirmation")
                            if action == "fill":
                                if not isinstance(request.get("selector"), str) or len(request["selector"]) > 256 or len(request.get("value", "")) > 4096:
                                    raise ValueError("Invalid KVM fill request")
                                frame.locator(request["selector"]).fill(request["value"], timeout=20_000)
                            elif action == "focus_console":
                                selector = request.get("selector")
                                if not isinstance(selector,str) or not selector or len(selector)>256:
                                    raise ValueError("Invalid console selector")
                                locator = frame.locator(selector)
                                if locator.count() != 1 or not locator.is_visible():
                                    raise ValueError("Select exactly one visible console canvas/video from inspect(); this may only be a management page")
                                if not locator.evaluate("e => ['CANVAS','VIDEO'].includes(e.tagName) && e.getBoundingClientRect().width>50 && e.getBoundingClientRect().height>50"):
                                    raise ValueError("Selected element is not a graphical console surface")
                                locator.click(timeout=20_000)
                                locator.evaluate("e => { if(!e.hasAttribute('tabindex')) e.setAttribute('tabindex','-1'); e.focus(); }")
                                _require_console_focus(frame)
                            elif action == "click":
                                selector = request.get("selector")
                                x, y = request.get("x"), request.get("y")
                                if not isinstance(selector, str) or len(selector) > 256 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in (x, y)):
                                    raise ValueError("Invalid KVM click request")
                                if selector.strip().lower() in {"body", "html", "*"}:
                                    raise ValueError("Choose a specific visible control from inspect(); clicking the whole management page does not focus a console")
                                locator = frame.locator(selector)
                                if locator.count() != 1:
                                    raise ValueError("KVM click selector must match exactly one element")
                                box = locator.bounding_box(timeout=20_000)
                                if not box:
                                    raise ValueError("KVM element has no visible bounds")
                                page.mouse.click(box["x"] + box["width"] * x, box["y"] + box["height"] * y)
                            elif action == "key":
                                _require_console_focus(frame)
                                key = request.get("key")
                                if key not in KEYS and not (isinstance(key, str) and len(key) == 1 and 32 <= ord(key) <= 126):
                                    raise ValueError("Unsupported KVM key")
                                page.keyboard.press(key)
                            else:
                                _require_console_focus(frame)
                                value = request.get("value")
                                if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(not 32 <= ord(c) <= 126 for c in value):
                                    raise ValueError("Invalid KVM text")
                                page.keyboard.type(value)
                            result = {"accepted": True}
                        else:
                            raise ValueError("Unsupported KVM action")
                reply = {"ok": True, "result": result}
            except BaseException as error:
                # Never return form values or raw browser diagnostics: they may
                # contain credentials or page content.
                detail = str(error)[:300] if isinstance(error, (ValueError, PermissionError, RuntimeError)) else "browser operation failed"
                reply = {"ok": False, "error": f"{type(error).__name__}: {detail}"}
            print(json.dumps(reply, separators=(",", ":")), flush=True)
            if stop:
                break
    finally:
        for resource in (context, browser):
            if resource is not None:
                try:
                    resource.close()
                except BaseException:
                    pass
        if playwright is not None:
            playwright.stop()
        if proxy is not None:
            proxy.terminate()
            try:
                proxy.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proxy.kill()
        runtime.cleanup()
    return 0


def server_main(socket_path: str) -> int:
    """Keep the stdio worker alive behind a private per-session Unix socket.

    OpenShell's exec CLI is not a durable bidirectional stdin relay. This
    server is detached inside its own sandbox and communicates with the host
    broker through a dedicated, owner-scoped volume instead.
    """
    target = Path(socket_path)
    if target.parent != Path("/run/prime-kvm-worker") or not re.fullmatch(r"worker-[a-f0-9]{32}\.sock", target.name):
        raise ValueError("Invalid private KVM worker socket path")
    if target.exists():
        raise RuntimeError("KVM worker socket already exists")
    prior_umask = os.umask(0o077)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(target))
        os.chmod(target, 0o600)
        server.listen(2)
        server.settimeout(5)
    finally:
        os.umask(prior_umask)
    process = subprocess.Popen([sys.executable, "-m", "bmc_html5_kvm", "--worker"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, bufsize=1)
    try:
        while process.poll() is None:
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(60)
                raw = connection.makefile("rb").readline(16_385)
                if not raw or len(raw) > 16_384:
                    continue
                process.stdin.write(raw.decode("utf-8"))
                process.stdin.flush()
                ready, _, _ = select.select([process.stdout], [], [], 45)
                if not ready:
                    break
                answer = process.stdout.readline(3_500_001)
                if not answer or len(answer) > 3_500_000:
                    break
                connection.sendall(answer.encode("utf-8"))
                if json.loads(raw).get("action") == "close":
                    break
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        server.close()
        target.unlink(missing_ok=True)
    return 0
