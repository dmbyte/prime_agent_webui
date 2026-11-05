# Approval-gated BMC installation controls

`redfish-install` is a separate, opt-in connection, not an expansion of
`redfish-readonly`. It supports standard Redfish ISO insert/eject, `Cd` one-time
boot (`UEFI` or `Legacy`) and `GracefulRestart` on an On system or `On` on an Off
system. There is no force reset/off, arbitrary HTTP, OEM action, automatic
installation sequence or raw-credential fallback. Synthetic tests do not certify
any particular iLO/BMC firmware.

### iLO 4 compatibility limitation

A read-only iLO 4 preflight found legacy `links.ManagedBy`,
`links.VirtualMedia`, `BootSourceOverrideSupported` and HPE OEM media data,
without the body ETags and standard media actions required by this adapter.
The standard observer therefore did not discover that target's virtual media;
`not-advertised` must **not** be interpreted as empty or absent hardware. Separate
read-only legacy discovery found an occupied slot. No media was changed.

HPE documents these pre-Redfish differences in its
[iLO 4 migration guide](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_adaptation).
This adapter does not currently translate them. Missing body ETags do not prove
the firmware has no HTTP-header ETag support. Supporting legacy HPE writes needs
a separately reviewed compatibility implementation and hardware acceptance,
not silently dropping prerequisites, assuming boot mode or guessing actions.
Use a validated standard-compatible target or explicitly plan that extension.

## Owner setup and use

1. Enable the managed **ipmi-redfish-bmc** skill for the intended project. In
   **Settings → My connections**, select an existing reusable target (or save a
   new login) and the **BMC installation controls — approval required** requirement.
   Create a separate project-scoped connection. The UI fixes its transport to
   **Direct trusted broker**. Existing read-only connections are unaffected.
2. Use Network operations with LAN/Full networking and tools enabled. Start a
   new task after creating the connection; running tasks never acquire new grants.
3. Ask Prime to use `prime-workflows` to inspect the selected system/media and
   propose one change. Review its exact target, system, arguments and prerequisite
   ISO/mode in **Settings → My connections → Console and BMC action approvals**.
   Approve once or deny. Approval expires in at most five minutes.
4. Resume the identical request ID after approval. Mount, boot setting, restart
   and eventual eject each need separate approval. Mount refuses occupied media;
   eject can interrupt an installer, so it is not automatic cleanup.

The helper's [usage reference](../deploy/spark/prime/skills/prime-workflows/references/bmc-controls.md)
describes retained steps and receipt lookup. Approval requires the signed-in
owner and CSRF protection; the task cannot approve itself. Credential rotation,
connection revision, scope/account changes and task termination revoke access.

## State and failure boundaries

The broker discovers the selected system and its observed media links, accepts
only standard advertised actions, and requires usable `@odata.etag` values.
Approval binds the payload, route and fresh ETags. Immediately before dispatch it
re-reads state; changed evidence invalidates approval. Requests carry `If-Match`.
Target-level host locks serialize this broker's changes, but do not lock out
other administrators or promise atomicity across multiple BMC resources. A BMC
must correctly implement its ETags/preconditions; no such live certification has
been performed for this adapter.

Boot selection needs a same-task, same-connection acknowledged mount and fresh
readback of the exact image, inserted and write-protected. Restart additionally
needs an acknowledged one-time boot request and matching current override/mode.
Unsupported or incomplete firmware state fails closed. Standard semantics are
defined by the [DMTF Redfish schema guide](https://redfish.dmtf.org/schemas/v1/DSP2046_2025.3.html).

Approval is durably consumed **before** one outbound request. Only HTTP 200/204
is recorded as acknowledged, never as verified installation. Timeout, failed
reply, redirect or asynchronous 202 leaves an **unknown** outcome. The original
ID returns a receipt, not another write. Do not invent a new ID to retry.
Read-only inspection and manual review are required; unknown receipts cannot be
promoted or used for a later boot/restart. No task-monitor URL is followed.

ISO URLs must be credential-free private IPv4 HTTP(S) `.iso` URLs with plain
paths: no DNS, query, fragment, percent escapes, traversal or BMC self-reference.
Use `lan-web-host` to deliberately publish an ISO, verify its hash and intended
client reachability before approval. The broker does not send BMC credentials to
the ISO host. The BMC itself fetches the image; this adapter cannot guarantee its
redirect behavior, network routing, source integrity or ISO-server TLS policy.
Only approve a trusted server and image. Saved target TLS exceptions affect the
broker-to-BMC connection only, not the ISO fetch or global TLS.

## Installation and activation

Fresh installations leave `PRIME_CONNECTION_BMC_WRITES_ENABLED` off. Normal
installation/update copies the new dashboard module and managed declarations;
it does not create a credential or write grant. Existing updates preserve the
administrator's service overrides. Follow the base
[connection activation](connections.md) and [private runtime](connection-extensions.md)
instructions first. Do not widen native OpenShell HTTP method/path policies.

After validation, stage matched `connections.py`, `connection_installation.py`,
`connection_approvals.py`, `connection_broker.py`, `skill_credentials.py` and
`credentials.js` in `~/prime-dgx-dashboard`; publish the JS through the static
installer. Publish managed skills/declarations with the documented
`install-managed-skills.py --publish-shared-only` procedure and install the
matched managed policy. Back up previous files, inventory and registry pointer.

Pre-create `~/.config/prime-agent/connection-installation-locks` as the service
account, mode 0700. Add this drop-in to **auth, dashboard API and connection
broker** user services so UI, grants and execution agree:

```ini
[Service]
Environment=PRIME_CONNECTION_BMC_WRITES_ENABLED=1
```

Add **only to the connection broker**:

```ini
[Service]
ReadWritePaths=%h/.config/prime-agent/connection-installation-locks
```

Preserve its existing approval/runtime exceptions and hardening. Never give the
task or dashboard API write access to the vault, approval ledger or target locks.
Use exclusive maintenance admission plus all-user task/sandbox/model idle checks
before reloading systemd and restarting the three matched services. Do not
interrupt active work or restart inference. Verify authenticated Settings reports
the gate enabled and read-only grants unchanged. No new task image is required.

To disable, set the flag to `0` on all three services and restart while idle.
Retain receipts; disabling does not undo an already sent BMC action. For code
rollback restore matched files/registry/overrides while idle, not old task data
over newer work. The reference deployment's activation status belongs in its
private operational record, not an assertion about another installation.

## Validation

Run `scripts/validate-release.sh`, the skill validator and
`deploy/spark/dashboard/validate-credentials-ui.py` with Playwright/Chromium.
Synthetic tests cover independent approvals, prerequisite/readback mismatches,
ETag drift, occupied media, owner/scope/revocation, strict transport, lost replies,
serialization and durable no-replay behavior. The UI fixture uses synthetic
accounts and targets. A live hardware test requires explicit owner approval for
each proposed action; it is not part of automated release validation.
