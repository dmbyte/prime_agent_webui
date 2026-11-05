---
name: bmc-html5-kvm
description: Inspect and control saved-target HTML5 consoles for iLO, iDRAC, Supermicro, Lenovo XCC or generic HTML5 layouts through task-bound connections, approved input and durable receipts. Discover compatibility; never assume hardware certification.
---

# Saved-target HTML5 BMC KVM

For vendor differences, capability status and unsupported layouts, read
[compatibility.md](references/compatibility.md). Console UI support is separate
from Redfish/OEM media and power support. A working HTML5 console does not grant
permission to change media, boot, power or another operator's console session.

Prefer the installed `prime-workflows` helper for retained open diagnostics:
`b.open_console(step, connection)` returns `opened`, `compatibility-blocked` or
`unknown`. On success `b.console_status(step)` reports the detected UI family
and renderer; inspect a capture before any input. On compatibility-blocked,
report the bounded stage/reason and stop, without changing IDs or trying another
credential. The lower-level client below remains available for known layouts.

Use `PrivateKVMClient` for console control. It uses the task's saved connection
grant, not a password in tool code. Network operations, LAN/Full access, tools
enabled and an enabled owner/project connection are required. Never print the
token/environment, retrieve the password or bypass missing access through another
browser, raw worker, socket or network tool. Ask the owner to configure Settings
→ My connections and start a new task if access is missing.

```python
import uuid
from bmc_html5_kvm import PrivateKVMClient

connections = PrivateKVMClient.connections()  # list of id/name/operations objects
print(connections)  # select the user's intended target, never guess
# Once that exact connection is identified:
open_id = uuid.uuid4().hex  # retain across retries of this open
kvm = PrivateKVMClient.open(connection_id, request_id=open_id)
image_path = kvm.capture('console-before.png')  # PNG Path below /project
# Inspect image_path using attach_image; a login page is NOT a server console.
step_id = uuid.uuid4().hex  # retain for this exact user-requested action
result = kvm.input(request_id=step_id, key='f9')
print(result)
```

`input()` sends a request, not an automatic keypress. If `approvalRequired` is
true, tell the owner to review **Settings → My connections → Console and BMC action
approvals**. Only after their approval, retry `kvm.input` with the same ID and
identical arguments. Do not rerun a cell that regenerates IDs. Do not poll faster
than five seconds or longer than five minutes. Never self-approve.

Input accepts one lowercase named key (`enter`, `escape`, `tab`, `backspace`,
`up`, `down`, `left`, `right`, `f1`, `f2`, `f9`, `f10`, `f11`, `f12`) or one
`text` string of 1–256 printable ASCII characters, excluding `~`. Never enter
passwords through console text. The adapter focuses the identified console;
no arbitrary selector, mouse click, shell or script interface is available.

## Outcome and retry rules

- `actionReceipt.state == 'acknowledged'`: the worker acknowledged the input.
  Capture and inspect the target; this is NOT proof of boot/installer success.
- `state == 'unknown'`: input may have occurred or may still be running. STOP.
  Inspect capture and ask the owner. Never resend, change IDs, reopen a session
  or switch tools to try the same action again automatically.
- After a lost/malformed response, reconcile without needing a live session:
  `PrivateKVMClient.action_receipt(connection_id, step_id)` returns a dictionary
  containing `actionReceipt`. A missing receipt does not authorize another send.
- Receipts survive session closure and broker restart; current task/grant checks
  still apply. A new task cannot consume an old task's approval. Only a new
  explicit human approval can authorize a separate action after review.

`capture()` saves PNG only, returns a `Path`, and never returns a pages list.
`connections()` returns a list. `input()` and `action_receipt()` return dictionary
envelopes. Do not confuse these shapes or infer failure of input from a later
polling/parse error. `kvm.close()` closes only this task's session.

Private sessions last at most one hour, expire after five minutes idle, and are
revoked with their task/connection. They do not have the legacy cross-task lease
or general KVM popout. Do not promise uninterrupted virtual media or multi-day
console operation. The private broker supports only reviewed login/HTML5 layouts;
unsupported launchers are compatibility failures, not permission to guess or
expose secrets. Reviewed layout families include iLO, iDRAC, Supermicro, Lenovo
XCC and explicit generic HTML5/noVNC launchers. This is not certification of all
versions: iLO 4 had prior live login/capture evidence; other firmware needs its
own live acceptance. Legacy Java/ActiveX-only consoles are not HTML5 support.
Do not reboot, change boot overrides, virtual media or BIOS settings merely to
test a console. Screenshots can contain private OS data and remain subject to
external-inference privacy controls.

## Legacy read-only sessions

`KVMClient.list_sessions()` and `KVMClient.connect(session_id)` can inspect an
existing owner-scoped legacy session. `pages()` returns a validated list of
`{index, url, title}` objects; raw worker/broker replies use `{'pages': [...]}`.
Use observed indexes for `select_page`/`select_frame`; `inspect()` lists frames
and console surfaces. `capture('frame.png')` supports PNG/JPEG below `/project`.
`fill`, `click`, `key`, `type_text`, and `focus_console` are disabled at both client
and broker, even with `confirm=True`. A new legacy session cannot automate login.

The existing read-only popout samples without input or extending idle lifetime.
Legacy sessions are owner-shared, at most two, expire after 45 minutes idle/eight
hours total and do not survive restart. Do not close someone else's session.
The low-level worker is an internal implementation, NOT an alternative control
path. Generic browser scripts are not covered by the receipt guarantee and must
not be used to evade this migration.
