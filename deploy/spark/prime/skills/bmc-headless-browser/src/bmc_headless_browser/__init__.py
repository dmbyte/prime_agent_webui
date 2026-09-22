"""Subprocess-isolated headless browser for OpenShell BMC tasks."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


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
    """Async browser proxy whose Playwright runtime lives in a clean child process."""

    def __init__(self, base_url: str, *, ignore_https_errors: bool = False, timeout_ms: int = 30_000):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self.base_url = base_url.rstrip("/") + "/"
        self.ignore_https_errors = bool(ignore_https_errors)
        self.timeout_ms = max(1_000, min(int(timeout_ms), 120_000))
        self._process: Any = None
        self._stderr_task: Any = None
        self._stderr = deque(maxlen=80)
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._page = _PageProxy(self)

    async def __aenter__(self) -> "BMCBrowser":
        if self._process is not None:
            raise RuntimeError("This browser instance is already open")
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self._process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "bmc_headless_browser", "--worker",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            await self._command("start", baseUrl=self.base_url,
                                ignoreHttpsErrors=self.ignore_https_errors,
                                timeoutMs=self.timeout_ms)
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *_args) -> None:
        await self.close()

    @property
    def page(self) -> _PageProxy:
        if self._process is None:
            raise RuntimeError("Use BMCBrowser as an async context manager")
        return self._page

    async def _drain_stderr(self) -> None:
        while self._process and self._process.stderr:
            line = await self._process.stderr.readline()
            if not line:
                return
            self._stderr.append(line.decode(errors="replace").rstrip()[:1000])

    def _diagnostic(self) -> str:
        return " | ".join(self._stderr)[-4000:] or "no child-process diagnostics"

    async def _command(self, action: str, **values):
        async with self._lock:
            process = self._process
            if not process or process.returncode is not None or not process.stdin or not process.stdout:
                raise RuntimeError(f"Browser subprocess is unavailable: {self._diagnostic()}")
            self._request_id += 1
            request_id = self._request_id
            request = {"id": request_id, "action": action, **values}
            process.stdin.write((json.dumps(request, separators=(",", ":")) + "\n").encode())
            await process.stdin.drain()
            try:
                raw = await asyncio.wait_for(process.stdout.readline(), self.timeout_ms / 1000 + 5)
            except asyncio.TimeoutError as error:
                process.kill()
                await process.wait()
                raise TimeoutError(f"Browser step '{action}' timed out; {self._diagnostic()}") from error
            if not raw:
                await process.wait()
                raise RuntimeError(f"Browser subprocess exited during '{action}' ({process.returncode}); {self._diagnostic()}")
            response = json.loads(raw)
            if response.get("id") != request_id:
                raise RuntimeError("Browser subprocess protocol lost synchronization")
            if not response.get("ok"):
                raise RuntimeError(f"Browser step '{action}' failed: {response.get('error', 'unknown error')}; {self._diagnostic()}")
            return response.get("result")

    async def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.returncode is None:
                try:
                    await self._command("close")
                except BaseException:
                    process.terminate()
            await asyncio.wait_for(process.wait(), 5)
        except (asyncio.TimeoutError, ProcessLookupError):
            if process.returncode is None:
                process.kill()
                await process.wait()
        finally:
            self._process = None
            if self._stderr_task:
                self._stderr_task.cancel()
                await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._stderr_task = None

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


def run() -> dict[str, str]:
    return {"status": "ready", "browser": _browser_executable(), "mode": "headless-subprocess"}


if __name__ == "__main__" and "--worker" in sys.argv:
    raise SystemExit(_worker_main())
