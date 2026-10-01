---
name: bmc-headless-browser
description: Inspect and operate JavaScript-based BMC web interfaces through the OpenShell network-operations profile using the system Chromium browser. Use when Redfish or IPMI is insufficient and a BMC web console must be viewed or automated.
---

# BMC Headless Browser

Use this skill only in the `network-operations` OpenShell profile with LAN access.
It controls the Chromium already present in that immutable image; it never installs
OS packages or downloads a second browser at task time.
The image starts a private per-task browser broker before Prime. `BMCBrowser`
connects to that broker automatically, keeping Chromium out of Prime's forked
IPython kernel while preserving the same async API.

Import `BMCBrowser` from `bmc_headless_browser` and use it as an async context
manager. Supply credentials at runtime. Never put credentials in source, prompts,
screenshots, logs, or saved browser state. Self-signed BMC certificates require the
caller to opt in with `ignore_https_errors=True`.
Keep all calls inside the same `async with` block. In Prime's IPython tool,
use top-level `await`; do not nest `asyncio.run()` inside its running event loop.
A closed-session error requires opening a new browser context, not changing the
Network operations profile.

Read-only navigation and inspection are permitted when the task authorizes BMC
access. Clicking a control that changes power, firmware, boot configuration,
accounts, networking, or other persistent state requires the user's explicit
authorization for that exact action. Use `confirmed_click(..., confirm=True)` only
after receiving it. Save screenshots only below the task workspace.

This browser broker is for bounded web-page actions, not a persistent HTML5
KVM session. It does not continuously capture the iLO video canvas or provide
a verified keyboard/mouse injection path into that canvas. The page also closes
with the Prime/OpenShell task (normally limited to 30 minutes). Do not present
it as long-running installer KVM; use the `ipmi-redfish-bmc` SOL capability for
configured serial text consoles, or the separate `bmc-html5-kvm` skill for
bounded, reconnectable graphical-console sessions. Closing an HTML5 console may disconnect locally
mounted virtual media.

```python
from bmc_headless_browser import BMCBrowser

async with BMCBrowser("https://bmc.example", ignore_https_errors=True) as browser:
    await browser.goto("/")
    title = await browser.title()
```
