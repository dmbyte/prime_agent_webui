# Native HTTP and private console connections — staged

The original proposal's **item 2 (trusted local connection service) is live**.
**Item 3 is implemented and tested in isolated staging, not activated on the
reference Spark.** Existing read-only GitHub/Redfish connections still use the
direct host transport. No production service, model, task, user session, normal
browser, or persistent KVM session was restarted for this staging work.

## Native OpenShell HTTP transport

`PRIME_CONNECTION_HTTP_TRANSPORT=openshell` on the connection broker selects
native substitution for the existing GitHub/Redfish operations. The default is
`direct`; there is **no automatic fallback** after a native failure.

For each bounded operation the trusted broker creates an ephemeral provider
profile, provider and empty sandbox. Reviewed policy allows only the fixed host,
GET methods and repository/Redfish-system paths. Private-IP endpoints also get
an exact `/32` network pin. The worker uses the native inspected proxy, **not**
Prime's entrypoint or HTTP relay. No task, project, home, socket or user volume is
mounted. The only executing workload is the fixed reviewed Python worker.

The provider is populated through the CLI's environment lookup, never a secret
in argv or a profile file. The worker receives an opaque placeholder. For Basic
authentication the provider holds the encoded username/password pair, and the
proxy substitutes it in the Authorization header. TLS verification remains on;
redirects, cookies, arbitrary methods/URLs and raw error returns are disallowed.
The same bounded summary filters remain at the host broker. Grants are checked
before every read and again before returning results.

The vault is authoritative, but this path necessarily creates **temporary copies
in trusted OpenShell gateway state**. A lease expires within 120 seconds and
deletes its exact sandbox/provider/profile on exit. A protected secret-free
journal retries failed cleanup; startup reaps previous leases before serving.
Failure to reap an expired lease denies new native leases. Expiry/deletion is
not secure erasure of gateway storage or backups: protect those like the vault.
Root, the WebUI host account and OpenShell gateway administrators remain trusted.

Native sandbox names are limited to 19 bytes. The operation image must have the
reviewed immutable Prime tag; its Python executable is `/usr/bin/python3.11`.
Limits are one CPU and 512 MiB per HTTP sandbox, with at most two native HTTP
leases at once. The broker admits at most eight requests overall. This is
isolation-first, not a low-latency pooled transport.

## Private console adapters

All require Network operations, LAN/Full access, tools enabled, the original
task's owner/project/revision-bound capability, and the separate
`PRIME_CONNECTION_CONSOLES_ENABLED=1` activation gate.

| Reviewed adapter | Operations | Additional human approval |
|---|---|---|
| `bmc-browser` | `browser.open`, `browser.capture`, `browser.close` | No control API; only login and masked viewport capture |
| `bmc-kvm` | `kvm.open`, `kvm.capture`, `kvm.input`, `kvm.close` | Every exact input |
| `ipmi-sol` | `ipmi.status`, `sol.open`, `sol.read`, `sol.input`, `sol.close` | Opening SOL and every exact input |

Declarations require exactly `endpoint`, `username`, `password`. An endpoint is
an explicit HTTPS private IPv4 origin on port 443; for IPMI it identifies the
target host, **not a claim that IPMI uses HTTPS**. IPMI uses UDP 623, lanplus and
cipher suite 17; there is no weak-cipher or unencrypted fallback. Use a minimally
privileged BMC account. IPMI username is at most 16 ASCII characters; password
at most 20 UTF-8 bytes. A protocol/account mismatch fails closed.

### Browser/KVM boundary

Each credential-backed browser lives in a separate empty OpenShell sandbox,
controlled only by the broker's private stdin/stdout channel. It never uses the
task browser daemon or the existing general KVM socket. Passwords enter through
that private pipe, not task code, environment or argv. Browser profiles/cookies
remain in the isolated worker; capture/input responses never expose storage,
cookies, page source, arbitrary script, arbitrary selectors or request APIs.

Network policy pins Chromium to the exact BMC IP and TCP 443. This is an opaque
TLS transport, not native HTTP secret substitution; Chromium must independently
verify the BMC certificate. Its trust store must trust the CA and the certificate
must match the selected IP. No ignore-TLS setting is offered. HTTP requests,
redirects, subresources, popup/frame access and WebSockets are restricted to that
same HTTPS/WSS origin. Service workers and downloads are disabled.

The initial conservative login adapter recognizes one visible username text
field, one password field and an unambiguous Log In/Sign In button. KVM additionally
requires an HTML5 (Remote) Console link/button and one visible canvas at least
320×200 in a newly opened/navigated page or frame; existing management charts are
excluded. **This has been tested against a synthetic compatible UI, not yet against
the user's iLO 5 firmware.** Ambiguous/missing controls are an unsupported layout,
not permission to guess selectors, weaken TLS or inject a secret into task code.

Login screens are withheld; browser captures mask inputs/textareas. KVM captures
only the console canvas. Input uses DOM focus, not an unapproved mouse click.
Console content itself can contain private data: these controls protect login
credentials and session interfaces, not arbitrary secrets displayed by an OS or
a compromised BMC. Do not treat a screenshot as automatically safe for cloud
inference. Existing data-routing/privacy gates remain independent.

### IPMI/SOL boundary

Raw IPMI/SOL does not work through the general task's HTTP proxy. The dedicated
host-side adapter invokes only fixed `/usr/bin/ipmitool` operations and a PTY.
The password is in that child process's private environment, never argv or task
environment. The username is visible to trusted host administrators in argv.
No shell, arbitrary command, power/reset or global `sol deactivate` endpoint exists.
Closing terminates only the child started for that session, not another viewer.
The BMC may take time to release a disconnected SOL payload; the adapter does not
forcefully clear it. Read returns bounded text, with exact password filtering
across chunk boundaries, not a full VT100 renderer or general redaction engine.

### Action approvals and session lifecycle

The agent opens with `arguments={"requestId":"<fresh uuid hex>"}` and retains the
returned `sessionId`. Read/capture/close take only that session ID. Input adds a
fresh request ID and either one supported `key` or 1–256 printable ASCII `text`
characters (no controls or IPMI escape sequences).

When `approvalRequired` is returned, the owner reviews **Settings → My connections
→ Console action approvals**. Refresh the section to see new requests. The page
shows target, task, operation and exact arguments. **Allow once** or **Deny** is
authenticated, CSRF-protected and owner-only; there is no task-facing approval
API. Approval expires after five minutes and is bound to the exact request and
connection revision. The agent retries the same request ID; an approved input
is consumed before execution and cannot be replayed. An uncertain/failed input
requires a new explicit approval, never an automatic duplicate.

Keys/text can affect firmware or the running OS. Do not approve them merely
because the credential is saved; confirm the target and intended effect first.
Never type passwords through model-generated console input. This path does not
inherit a chat's blanket tool approval as permission to control the console.

Sessions are task-bound, not shared across chats/users/projects. Maximum two per
user, four total, one-hour lifetime and five-minute idle limit, further shortened
by task/connection expiry. A five-second reaper closes revoked/expired sessions;
an in-flight bounded worker operation may delay that check. Calls also revalidate
before/after use. Task completion, account disable, credential rotation or
connection revision changes revoke access. Console sandboxes have one CPU and
2 GiB caps. SOL children are in the broker's service control group. An API/broker
restart invalidates/reaps the old leases; no attempt is made to restore login
cookies. Existing general console popouts are unchanged; the new private path
returns captures to the requesting task, not the older shared console feed.

## Install/activate only after validation and an idle window

Normal installers/updaters copy the Python modules, UI and declarations, but
**do not enable these extension flags or restart anything to activate them**.
Normal full updates still perform their documented service restarts; do not use
one to stage files while users are working. Work from a separate source export.

1. Retain all existing [credential and terminal guards](user-credentials.md) and
   the [read-only pilot](connections.md). Back up the matching live files/units,
   vault keys/records and OpenShell state privately. Do not put backups in Git.
2. Stage all dashboard Python modules and `credentials.js`, plus matched
   `api_v2.py` runtime guidance. Existing pinned images already contain Chromium,
   Playwright and Python; no image rebuild is needed for the tested fixture.
   Real internal CA trust may require a reviewed operation-image change. Do not
   grant a general task writable access to trust roots or broker code.
3. Provide the broker a protected copy of the **actual deployed** pinned image
   manifest; verify its tags against the installed images. Set
   `PRIME_CONNECTION_IMAGE_MANIFEST` to that absolute path. Install the distro's
   `ipmitool` at `/usr/bin/ipmitool` if enabling IPMI/SOL; no automatic package
   installation occurs from model instructions or credential declarations.
4. Pre-create `~/.config/prime-agent/connection-runtime` and
   `~/.config/prime-agent/connection-approvals`, owned by the WebUI service account,
   mode 0700. The auth process may decide approvals; the broker may create/consume
   them. General tasks and the dashboard API must not be granted write access.
5. For the broker's user-service override, add only the intended flags:

   ```ini
   [Service]
   Environment=PRIME_CONNECTION_HTTP_TRANSPORT=openshell
   Environment=PRIME_CONNECTION_CONSOLES_ENABLED=1
   Environment=PRIME_CONNECTION_IMAGE_MANIFEST=/absolute/protected/connection-images.json
   ReadWritePaths=%h/.config/prime-agent/connection-runtime
   ReadWritePaths=%h/.config/prime-agent/connection-approvals
   ReadWritePaths=%h/.config/openshell/gateways/spark-local
   TasksMax=96
   ```

   Choose `direct` and/or leave consoles at `0` when enabling only one path.
   The OpenShell client directory exception is required because the CLI writes
   and removes its `last_sandbox` selection. Do not make the vault writable by
   this service. Preserve `ProtectHome=read-only`, `ProtectSystem=strict`,
   `NoNewPrivileges=yes` and `KillMode=control-group`. Verify the exact client
   write paths under the hardened unit in staging before activating it.
6. Console activation also requires `PRIME_CONNECTION_CONSOLES_ENABLED=1` on
   **auth and dashboard API** so Settings and new-task grant issuance agree with
   the broker. Existing tasks never gain new connections. The gateway and runner
   capability channel is unchanged. Publish reviewed managed declarations only
   when ready; changed browser/KVM requirement IDs require users to resave and
   re-consent. Older encrypted records remain removable; no silent migration.
7. Pass the tests below, then verify an approved real read-only BMC login/status
   request with the target's actual certificate and firmware. Do not reboot,
   change boot settings or send input as a connection test. Explicitly approve
   any separate console-input test. Check all users' live tasks and persistent
   sandboxes before restarting the matched services in an idle window. Validate
   revocation and zero residual test resources afterward.

Rollback: disable the extension flags and close/reap their exact `pc-*` leases;
restore matched source/units while idle. Keep the old direct read-only broker,
administrator-only terminal guards, credentials and history. Do not indiscriminately
delete sandboxes or roll back OpenShell just to disable these adapters.

## Reproducible tests and remaining gates

- `scripts/validate-release.sh`: authorization, no-fallback, lifecycle, closed
  command/operation schemas, redaction and approval replay unit regressions.
  All 360 tests (335 dashboard and 25 managed-skill tests) passed locally and
  from a clean source export on the reference Spark.
- `validate-credentials-ui.py`: real browser/HTTP, two-user separation, project
  settings, CSRF, human action approval and repeated-decision rejection.
- `validate-private-console.py`: real HTTPS/Chromium login, cookies, capture,
  cross-origin denial, canvas keys and PTY lifecycle, using local synthetic data.
  Its certificate SPKI exception is test-only, never a production bypass. It has
  also passed inside the actual pinned Linux OpenShell network-operations image.
- On the Spark, explicitly opt into the synthetic public echo test:

  ```sh
  python3 deploy/spark/dashboard/validate-native-connections.py \
    --allow-synthetic-external-canary \
    --state /absolute/private/staging/native-validation \
    --manifest /absolute/reviewed/image-digests.json
  ```

  This sends generated dummy Bearer/Basic values only to `https://httpbin.org`.
  Both substitution paths, opaque worker environment, denied paths, credential
  expiry and resource cleanup have passed against OpenShell 0.1.5. Do not run
  this against the production runtime journal; its startup cleanup owns its
  staging directory. No saved user credentials are read.
  The native canary also passed under a transient hardened user service with
  read-only home, strict filesystem protection, no new privileges and only the
  documented runtime/client write exceptions.

Passing fixtures is not proof of iLO firmware compatibility, actual provider
permissions or internal certificate trust. The first approved live target check
found no matching saved login and rejected its weak, expired certificate before
sending credentials. Save credentials through Settings, never chat; repair the
target certificate in a separately approved maintenance window, not by disabling
TLS verification. Real-target tests, complete matched console-service validation,
and idle-window activation remain explicit deployment gates.
OAuth refresh, MCP serving and richer vendor-specific console adapters remain
future work; no cloud vault or cloud credential transfer has been added.

Upstream basis: [OpenShell provider profiles](https://docs.nvidia.com/openshell/v0.1.5/how-it-works/providers/profiles)
and [network policy schema](https://docs.nvidia.com/openshell/v0.1.5/how-it-works/policies/schema).
