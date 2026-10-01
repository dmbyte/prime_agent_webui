---
name: bmc-html5-kvm
description: Maintain a bounded, reconnectable HTML5 BMC KVM session across Prime tasks; capture the console and send confirmed keyboard or mouse input. Initial target is HPE iLO 5.
---

# Long-running HTML5 BMC KVM

Use with the `network-operations` profile and **LAN/VPN or Full network** mode. The
owner-scoped KVM broker creates a separate OpenShell sandbox, so the browser
can remain open after the current Prime task ends. A session lasts at most
eight hours and expires after 45 minutes without a client request. It does
not survive a broker restart, host reboot, or a BMC-imposed idle timeout.
Never promise uninterrupted installation or virtual media. HPE iLO 5 is the
first target, but an actual iLO 5 console has not yet been validated; other
BMCs require their own validation too.
The launcher supplies `PRIME_KVM_SOCKET` for the owner's KVM control channel in
both supported network modes; keep that value rather than replacing it with a
guessed path. `KVMClient.list_sessions()` checks broker availability without
contacting a BMC. A missing control socket indicates a deployment or task-mount
problem, not proof that the selected profile was denied. Report the exact error.
Changes to the chat's controls apply when a new task starts.
For iLO 5, the account needs Remote Console privilege, the feature must be
enabled, and the installed license must support it. iLO's own idle timeout can
close the console before the broker's limit and interrupt console-mounted
virtual media; do not assume broker heartbeats override that policy.

First call `KVMClient.list_sessions()` and reconnect to a matching target with
`KVMClient.connect(session_id)`. There are only two concurrent sessions per
owner. Repeated `create` for the same URL and TLS setting reuses the existing
session without reloading its page. Never blindly close another active console
to make room. Redfish API URLs are not console pages and are rejected by this
adapter; use `RedfishClient` for those. Do not infer console success from loading
an API page or login page.

Use exactly `KVMClient.create(base_url, ignore_https_errors=False)` for a new
connection or `KVMClient.connect(session_id)` for an existing one. Do not call
`KVMClient(base_url, ...)`: the low-level constructor accepts only a session ID.
If no matching session exists, create one with `KVMClient.create("https://bmc.example")`; retain the
returned session ID in the conversation (not credentials) to reconnect later
with `KVMClient.connect(id)`. The broker holds Chromium, not a password. Use
`pages()` to find the popup that contains the HTML5 console, then
`select_page(index)`. Capture a frame into the task workspace and inspect it
before sending input. Browser screenshots are on demand, not a video stream.
Login forms may be filled using `fill(..., confirm=True)` only after the user
authorizes this exact BMC login; never record credentials in the transcript,
source, screenshot filenames, or logs. `click`, `key`, and `type_text` also
require exact-target, exact-action user authorization and `confirm=True`.
They can change BIOS, boot or installation state. After each consequential
input, capture and inspect another frame. Do not send blind keys. Do not mount
or eject virtual media, reset power, save BIOS settings, or start an installer
without specific authorization. The adapter offers no virtual-media API.

The selected page must remain at the BMC's origin; normal query/fragment routes
and an initial same-host HTTP-to-HTTPS upgrade are supported, not cross-host
redirects or HTTPS downgrades. `inspect()` returns bounded control selectors,
frame indexes, and `loginFormPresent` without form values. Its `consoleSurfaces`
list identifies visible canvas/video surfaces with exact `frameIndex` and
`selector` fields across same-origin frames. Use that list instead of guessing
selectors or assuming frame 0. Select the inspected surface's frame with
`select_frame(surface['frameIndex'])` before focusing its selector. If the list
is empty, wait briefly for loading or open the observed console control; do not
fall back to a management frame. Use `select_frame(index)` for a same-origin iframe console.
An iLO login/management page is NOT the server console; credentials go into
observed login fields with `fill`, not through console keyboard input. If only
legacy plugin controls are present, report that compatibility limit.

Capture PNG or JPEG with `capture('kvm-frame.png')` (relative paths are placed
under `/project`) or an absolute path below `/project`. Inspect the image before
input. Never claim the installer booted merely because media is mounted or a
one-time boot override was consumed. Keyboard/text input is rejected unless
a visible canvas/video console is focused. After identifying the actual console,
use `focus_console(selector, confirm=True)`; a canvas alone is not proof of a
working server connection. Mouse coordinates are
fractions of the element's bounding box, not host-screen pixels. iLO may close
an idle remote console independently. If it disconnects, report that state;
do not silently refresh a virtual-media installation.

```python
from bmc_html5_kvm import KVMClient

kvm = KVMClient.create("https://bmc.example", ignore_https_errors=True)
print(kvm.session_id)
pages = kvm.pages()
print(pages)
inspection = kvm.inspect()
print(inspection)
# Stay on page 0 unless pages() actually lists a separate console popup.
# An iframe is not a new page: use select_frame(index) from inspection['frames'].
# Never assume select_page(1) is valid. Inspect the current login page first.
frame = kvm.capture("ilo-console.png")
print(frame)
# After user approval for the exact target and key:
kvm.focus_console("canvas", confirm=True)  # Only if inspect() and the image identify it.
kvm.key("F9", confirm=True)
kvm.capture("/project/ilo-after-f9.jpg")
# A later task can use KVMClient.connect(kvm.session_id).
# Call kvm.close() when the console is no longer needed.
```
