"""Headless BMC browser using OpenShell's preinstalled Chromium."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


def _browser_executable() -> str:
    configured = os.environ.get("BMC_BROWSER_EXECUTABLE", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"])
    for candidate in candidates:
        resolved = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if resolved and os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            return resolved
    raise RuntimeError("No supported system Chromium executable is available in this sandbox profile")


class BMCBrowser:
    """Async, headless-only browser for BMC web consoles."""

    def __init__(self, base_url: str, *, ignore_https_errors: bool = False, timeout_ms: int = 30_000):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self.base_url = base_url.rstrip("/") + "/"
        self.ignore_https_errors = bool(ignore_https_errors)
        self.timeout_ms = int(timeout_ms)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "BMCBrowser":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            executable_path=_browser_executable(),
            headless=True,
            args=["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"],
        )
        self._context = await self._browser.new_context(
            ignore_https_errors=self.ignore_https_errors,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self

    async def __aexit__(self, *_args) -> None:
        await self.close()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Use BMCBrowser as an async context manager")
        return self._page

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    async def goto(self, path: str = "/", **kwargs):
        target = path if urlparse(path).scheme in {"http", "https"} else urljoin(self.base_url, path.lstrip("/"))
        return await self.page.goto(target, **kwargs)

    async def title(self) -> str:
        return await self.page.title()

    async def fill(self, selector: str, value: str) -> None:
        await self.page.fill(selector, value)

    async def click(self, selector: str, **kwargs) -> None:
        await self.page.click(selector, **kwargs)

    async def confirmed_click(self, selector: str, *, confirm: bool = False, **kwargs) -> None:
        if not confirm:
            raise PermissionError("A state-changing BMC click requires confirm=True after explicit user authorization")
        await self.page.click(selector, **kwargs)

    async def evaluate(self, expression: str, arg=None):
        return await self.page.evaluate(expression, arg)

    async def screenshot(self, filename: str | os.PathLike[str]) -> Path:
        target = Path(filename).expanduser().resolve()
        workspace = Path(os.environ.get("PRIME_WORKSPACE", "/project")).resolve()
        if target != workspace and workspace not in target.parents:
            raise ValueError(f"Screenshots must stay below the task workspace: {workspace}")
        target.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(target), full_page=True)
        return target


def run() -> dict[str, str]:
    return {"status": "ready", "browser": _browser_executable(), "mode": "headless"}
