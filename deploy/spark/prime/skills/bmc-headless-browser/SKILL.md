---
name: bmc-headless-browser
description: Inspect and operate JavaScript-based BMC web interfaces through the OpenShell network-operations profile using the system Chromium browser. Use when Redfish or IPMI is insufficient and a BMC web console must be viewed or automated.
---

# BMC Headless Browser

## Saved credentials in Prime WebUI (preferred)

When the owner has saved a target login, use the private saved-connection
interface described in the runtime context, not `BMCBrowser` with a password.
List connections through `POST http://127.0.0.1:31000/connections` using the
in-memory `PRIME_CONNECTION_TOKEN`; never print it or search for raw credentials.
Use only a listed connection offering `browser.open`, `browser.capture` and
`browser.close`. Open with `arguments={'requestId': uuid.uuid4().hex}`; retain
the returned `sessionId` and pass it to capture/close. If no grant exists, ask
the owner to bind their saved target in Settings → My connections.

The trusted isolated worker performs login. Captures return bounded PNG base64;
decode and display as an image instead of printing base64. No cookie, storage,
arbitrary script, selector, navigation or management-control API is exposed.
The saved certificate choice belongs to the owner; a task cannot override it.
Private sessions expire with the task, one-hour lifetime or five minutes idle.
Close when finished. A login-page failure is not successful BMC access; do not
fall back to copying credentials into the legacy arbitrary-code browser.
These private captures return to the task, not the legacy popout below.

## Legacy browser without saved-credential injection

The WebUI's **Console viewer ↗** opens a read-only view of this browser's current
viewport. Frames refresh about once per second while the viewer is visible,
including while the agent waits between operations. Long blocking browser calls
can temporarily leave a stale frame. Closing the popout does not stop the agent.
Do not reveal passwords or tokens on screen; the viewer is owner-authenticated,
but console pixels may contain sensitive information.

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
