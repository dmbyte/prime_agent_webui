"""Broker-isolated headless browser for OpenShell BMC tasks."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


def _broker_log(message: str) -> None:
    path = Path(os.environ.get("BMC_BROWSER_LOG", "/tmp/prime-bmc-browser.log"))
    try:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(message.replace("\n", " ")[:2000] + "\n")
    except OSError:
        pass


def _browser_executable() -> str:
    configured = os.environ.get("BMC_BROWSER_EXECUTABLE", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"])
    for candidate in candidates:
        resolved = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if resolved and os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            return resolved
    raise RuntimeError("No supported system Chromium executable is available in this sandbox profile")


def _safe_target(base_url: str, path: str) -> str:
    target = path if urlparse(path).scheme in {"http", "https"} else urljoin(base_url, path.lstrip("/"))
    if urlparse(target).scheme not in {"http", "https"}:
        raise ValueError("Browser targets must use HTTP(S)")
    return target


class _PageProxy:
    def __init__(self, owner: "BMCBrowser"):
        self._owner = owner

    async def goto(self, path: str = "/", **kwargs):
        return await self._owner.goto(path, **kwargs)

    async def title(self) -> str:
        return await self._owner.title()

    async def fill(self, selector: str, value: str) -> None:
        await self._owner.fill(selector, value)

    async def click(self, selector: str, **kwargs) -> None:
        await self._owner.click(selector, **kwargs)

    async def evaluate(self, expression: str, arg=None):
        return await self._owner.evaluate(expression, arg)

    async def screenshot(self, *, path: str | os.PathLike[str], full_page: bool = True) -> Path:
        if not full_page:
            raise ValueError("BMC screenshots are always full-page")
        return await self._owner.screenshot(path)

    def set_default_timeout(self, timeout_ms: int) -> None:
        self._owner.timeout_ms = max(1_000, min(int(timeout_ms), 120_000))


class BMCBrowser:
    """Async browser proxy whose Playwright runtime lives behind a clean broker."""

    def __init__(self, base_url: str, *, ignore_https_errors: bool = False, timeout_ms: int = 30_000):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self.base_url = base_url.rstrip("/") + "/"
        self.ignore_https_errors = bool(ignore_https_errors)
        self.timeout_ms = max(1_000, min(int(timeout_ms), 120_000))
        self._socket: Any = None
        self._reader: Any = None
        self._writer: Any = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._page = _PageProxy(self)

    async def __aenter__(self) -> "BMCBrowser":
        if self._socket is not None:
            raise RuntimeError("This browser instance is already open")
        broker_path = os.environ.get("BMC_BROWSER_BROKER", "/tmp/prime-bmc-browser.sock")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout_ms / 1000 + 5)
        try:
            await asyncio.to_thread(connection.connect, broker_path)
            self._socket = connection
            self._reader = connection.makefile("r", encoding="utf-8")
            self._writer = connection.makefile("w", encoding="utf-8", buffering=1)
            await self._command("start", baseUrl=self.base_url,
                                ignoreHttpsErrors=self.ignore_https_errors,
                                timeoutMs=self.timeout_ms)
            return self
        except BaseException:
            connection.close()
            await self.close()
            raise

    async def __aexit__(self, *_args) -> None:
        await self.close()

    @property
    def page(self) -> _PageProxy:
        if self._socket is None:
            raise RuntimeError("Use BMCBrowser as an async context manager")
        return self._page

    async def _command(self, action: str, **values):
        async with self._lock:
            self._request_id += 1
            request_id = self._request_id
            request = {"id": request_id, "action": action, **values}
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(self._command_blocking, request),
                    self.timeout_ms / 1000 + 5,
                )
            except asyncio.CancelledError:
                self._disconnect()
                raise
            except asyncio.TimeoutError as error:
                self._disconnect()
                raise TimeoutError(f"Browser step '{action}' timed out; {self._diagnostic()}") from error
            if response.get("id") != request_id:
                raise RuntimeError("Browser subprocess protocol lost synchronization")
            if not response.get("ok"):
                raise RuntimeError(f"Browser step '{action}' failed: {response.get('error', 'unknown error')}")
            return response.get("result")

    def _diagnostic(self) -> str:
        path = Path(os.environ.get("BMC_BROWSER_LOG", "/tmp/prime-bmc-browser.log"))
        try:
            return " | ".join(path.read_text(errors="replace").splitlines()[-20:])[-4000:]
        except OSError:
            return "no broker diagnostics"

    def _command_blocking(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._socket is None or self._reader is None or self._writer is None:
            raise RuntimeError("Browser broker is unavailable; use the OpenShell network-operations profile")
        self._writer.write(json.dumps(request, separators=(",", ":")) + "\n")
        self._writer.flush()
        raw = self._reader.readline()
        if not raw:
            raise RuntimeError(f"Browser broker disconnected during '{request.get('action')}'")
        return json.loads(raw)

    async def close(self) -> None:
        if self._socket is None:
            return
        try:
            await self._command("close")
        except BaseException:
            pass
        finally:
            self._disconnect()

    def _disconnect(self) -> None:
        connection, reader, writer = self._socket, self._reader, self._writer
        self._socket = self._reader = self._writer = None
        if connection is not None:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        for stream in (reader, writer):
            if stream is not None:
                try: stream.close()
                except OSError: pass
        if connection is not None:
            try: connection.close()
            except OSError: pass

    async def goto(self, path: str = "/", **kwargs):
        return await self._command("goto", target=_safe_target(self.base_url, path), options=kwargs)

    async def title(self) -> str:
        return str(await self._command("title"))

    async def fill(self, selector: str, value: str) -> None:
        await self._command("fill", selector=selector, value=value)

    async def click(self, selector: str, **kwargs) -> None:
        await self._command("click", selector=selector, options=kwargs)

    async def confirmed_click(self, selector: str, *, confirm: bool = False, **kwargs) -> None:
        if not confirm:
            raise PermissionError("A state-changing BMC click requires confirm=True after explicit user authorization")
        await self.click(selector, **kwargs)

    async def evaluate(self, expression: str, arg=None):
        return await self._command("evaluate", expression=expression, arg=arg)

    async def screenshot(self, filename: str | os.PathLike[str]) -> Path:
        target = Path(filename).expanduser().resolve()
        workspace = Path(os.environ.get("PRIME_WORKSPACE", "/project")).resolve()
        if target != workspace and workspace not in target.parents:
            raise ValueError(f"Screenshots must stay below the task workspace: {workspace}")
        await self._command("screenshot", path=str(target))
        return target


def _worker_main() -> int:
    from playwright.sync_api import sync_playwright

    playwright = browser = context = page = runtime_dir = None
    for raw in sys.stdin:
        request: dict[str, Any] = {}
        close_after = False
        try:
            request = json.loads(raw)
            action = request.get("action")
            if action == "start":
                runtime_dir = tempfile.TemporaryDirectory(prefix="prime-bmc-chromium-", dir="/tmp")
                runtime = Path(runtime_dir.name)
                config, cache = runtime / "config", runtime / "cache"
                config.mkdir(mode=0o700); cache.mkdir(mode=0o700)
                browser_env = dict(os.environ)
                browser_env.update(HOME=str(runtime), XDG_CONFIG_HOME=str(config), XDG_CACHE_HOME=str(cache))
                playwright = sync_playwright().start()
                browser = playwright.chromium.launch(
                    executable_path=_browser_executable(), headless=True, env=browser_env,
                    args=["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
                          "--no-first-run", "--no-default-browser-check"],
                    timeout=request["timeoutMs"],
                )
                context = browser.new_context(ignore_https_errors=request["ignoreHttpsErrors"],
                                              viewport={"width": 1920, "height": 1080})
                page = context.new_page()
                page.set_default_timeout(request["timeoutMs"])
                result = {"ready": True}
            elif page is None:
                raise RuntimeError("Browser worker has not started")
            elif action == "goto":
                response = page.goto(request["target"], **request.get("options", {}))
                result = {"url": page.url, "status": response.status if response else None}
            elif action == "title": result = page.title()
            elif action == "fill": result = page.fill(request["selector"], request["value"])
            elif action == "click": result = page.click(request["selector"], **request.get("options", {}))
            elif action == "evaluate": result = page.evaluate(request["expression"], request.get("arg"))
            elif action == "screenshot":
                page.screenshot(path=request["path"], full_page=True)
                result = request["path"]
            elif action == "close": result, close_after = None, True
            else: raise ValueError("Unsupported browser action")
            response = {"id": request.get("id"), "ok": True, "result": result}
        except BaseException as error:
            response = {"id": request.get("id"), "ok": False,
                        "error": f"{type(error).__name__}: {str(error)[:4000]}"}
        print(json.dumps(response, separators=(",", ":"), default=str), flush=True)
        if close_after:
            break
    for resource in (context, browser, playwright):
        if resource is not None:
            try: resource.close() if resource is not playwright else resource.stop()
            except BaseException: pass
    if runtime_dir is not None:
        runtime_dir.cleanup()
    return 0


def _proxy_connection(connection: socket.socket) -> None:
    """Relay one client to a worker spawned by the pre-Prime broker process."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    if env.get("BMC_BROWSER_DEBUG") == "1":
        env["DEBUG"] = "pw:browser*"
    process = subprocess.Popen(
        [sys.executable, "-m", "bmc_headless_browser", "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True, bufsize=1,
    )
    diagnostics: deque[str] = deque(maxlen=80)
    _broker_log(f"connection accepted; worker pid={process.pid}")

    def drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            diagnostics.append(line.rstrip()[:1000])
            _broker_log(f"worker stderr: {line.rstrip()[:1000]}")

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()
    reader = connection.makefile("r", encoding="utf-8")
    writer = connection.makefile("w", encoding="utf-8", buffering=1)
    try:
        for raw in reader:
            request: dict[str, Any] = {}
            try:
                if len(raw) > 1_048_576:
                    raise ValueError("Browser request is too large")
                request = json.loads(raw)
                _broker_log(f"worker request: {request.get('action')}")
                if process.poll() is not None or process.stdin is None or process.stdout is None:
                    raise RuntimeError("Browser worker exited")
                process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                process.stdin.flush()
                response = process.stdout.readline()
                if not response:
                    process.wait()
                    detail = " | ".join(diagnostics)[-4000:] or f"exit {process.returncode}"
                    raise RuntimeError(f"Browser worker disconnected: {detail}")
                writer.write(response)
                writer.flush()
                _broker_log(f"worker response: {request.get('action')}")
                if request.get("action") == "close":
                    break
            except BaseException as error:
                response = {"id": request.get("id"), "ok": False,
                            "error": f"{type(error).__name__}: {str(error)[:4000]}"}
                writer.write(json.dumps(response, separators=(",", ":")) + "\n")
                writer.flush()
                break
    except (BrokenPipeError, ConnectionError, OSError):
        pass
    finally:
        for stream in (reader, writer):
            try: stream.close()
            except OSError: pass
        try: connection.close()
        except OSError: pass
        if process.stdin is not None:
            try: process.stdin.close()
            except OSError: pass
        if process.poll() is None:
            process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        stderr_thread.join(timeout=1)
        _broker_log(f"worker closed: exit={process.returncode}")


def _daemon_main(socket_path: str = "/tmp/prime-bmc-browser.sock") -> int:
    """Serve private browser sessions from a process started before Prime."""
    target = Path(socket_path)
    if target.exists() or target.is_socket():
        target.unlink()
    previous_umask = os.umask(0o077)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(target))
        os.chmod(target, 0o600)
        server.listen(4)
        _broker_log(f"broker ready: pid={os.getpid()}")
    finally:
        os.umask(previous_umask)
    try:
        while True:
            connection, _ = server.accept()
            threading.Thread(target=_proxy_connection, args=(connection,), daemon=True).start()
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()
        target.unlink(missing_ok=True)


def run() -> dict[str, str]:
    return {"status": "ready", "browser": _browser_executable(), "mode": "headless-broker"}


if __name__ == "__main__" and "--worker" in sys.argv:
    raise SystemExit(_worker_main())
