# Read-only local connections — opt-in pilot

This page describes the read-only operations and credential boundary. The
reference Spark defaults to native HTTP substitution, with explicit per-connection
direct transport available; private browser/KVM/IPMI/SOL adapters are enabled.
See [connection extensions](connection-extensions.md) for live validation limits.
One [saved target](user-credentials.md#reusable-target-logins) may supply several
independently scoped reviewed tool connections without copying its password.

This is the first implementation stage of trusted per-user credential consumption.
It was **activated on the reference Spark on October 24, 2026**, after checking
that all users' task lists, OpenShell sandboxes and shared terminal were idle.
Live synthetic tests passed terminal restrictions, two-user/project isolation,
the pinned sandbox capability handoff, in-flight revocation and task-end cleanup.
Later live iLO 4 Redfish/login/KVM capture tests passed. Read-only IPMI power
status and SOL open/close passed with the separately approved target-only legacy
cipher 3 option; no console input was sent. Real GitHub authentication is unverified.
Do not run the normal updater/installer against
an active installation merely to copy this feature: those workflows restart
services and may rebuild images. Prepare and test a separate staging directory.

## Supported scope

| Adapter | Operation | Result | Required task permission |
|---|---|---|---|
| `github-readonly` | `github.repository`, arguments `{"repository":"owner/name"}` | Private/archived/disabled flags and issue/fork/star counts | Internet or Full, tools enabled |
| `redfish-readonly` | `redfish.systems`, arguments `{}` | Bounded system count/list with ordinal, power, health and state enums | Network operations profile, LAN or Full, tools enabled |

Only these operations are accepted. No generic URL, arbitrary HTTP method, raw
response, shell command or secret-read operation exists. GitHub uses the fixed
`https://api.github.com` origin; choose a fine-grained token limited to intended
repositories with Metadata read permission. Redfish accepts only an exact RFC1918
IPv4 HTTPS origin on port 443. It reads `/redfish/v1/Systems` and at most 16 direct
members, rejecting pagination, external links, traversal and encoded paths.
Use a read-only BMC account. No reset, boot override or write is implemented.

TLS verification is on by default. BMC certificates normally must chain to the
host's trusted CA and contain the selected IP address in their subject alternative
names. An owner can explicitly select **Ignore certificate errors** for that saved
credential in Settings. The direct transport honors it without changing other
credentials or users; native OpenShell transport rejects unsupported exceptions
without fallback. Read the [risk and lifecycle details](user-credentials.md).
DNS targets and nonstandard ports remain unsupported. Prefer valid certificates.

The direct broker does not use environment proxies, store cookies or
return arbitrary upstream strings, headers, serial numbers or OEM payloads.
Both HTTP transports allow only one exact same-origin Redfish trailing-slash
canonical redirect; all other redirects are denied.
Each HTTP response is capped at 1 MiB, each connection has a 10-second socket
timeout, response reads have a bounded elapsed budget and a whole operation has
a 90-second pre-request deadline. One request already in progress may finish
after that deadline; the gateway waits up to 180 seconds. At most eight broker
requests run concurrently. Failures return fixed messages without upstream text.

## Settings workflow

1. An administrator reviews/enables a skill with an approved adapter declaration.
2. The user saves its fields in **Settings → My credentials**.
3. Under **My connections**, choose that requirement, a name, an owned project
   (or explicitly all personal chats), and an expiry from 1 through 90 days.
   Redfish additionally requires confirming the exact saved BMC origin.
   Choose HTTP credential transport explicitly when needed: **Direct trusted
   broker** honors a saved certificate exception; native HTTP requires valid TLS.
4. After runtime activation, a **new** eligible task receives references to the
   connections granted at its launch. An existing task never gains newly added
   connections automatically.
5. Saving/editing/disabling/deleting a connection invalidates its earlier grants.
   Replacing/deleting credentials also invalidates the connection. Renew the
   connection and start a new task after rotation. Remote service revocation is
   still required when a credential is compromised.

"Ready" means configured/eligible, **not a successful live authentication test**.
Setup can be saved while runtime access remains disabled. Connection status in
the UI reflects the auth service's activation flag, not a complete health check
of every deployment component. No real credentials or access tokens are returned
to the browser. The confirmed endpoint and connection name are ordinary settings
metadata; do not put passwords in either field.

## Reviewed declarations

The optional `adapter` property is accepted only for hard-coded reviewed types
with exact field IDs. This pilot uses the two types above; the staged extensions
add three explicit console types. It is reviewed with the skill's existing manifest;
it cannot name an executable, environment destination or arbitrary adapter URL.
For an enabled GitHub skill, include this `credential-requirements.json` in its
reviewed package (this does not automatically install/enable a GitHub skill):

```json
{
  "version": 1,
  "credentials": [{
    "id": "github-readonly",
    "label": "GitHub repository metadata",
    "adapter": "github-readonly",
    "fields": [{"id": "token", "label": "Fine-grained read-only token"}]
  }]
}
```

`redfish-readonly` requires exactly `endpoint`, `username`, and `password` fields.
The managed `ipmi-redfish-bmc` declaration supplies this type. The adapter property
changes the requirement hash, so legacy management credentials remain inactive
and deleteable rather than being silently associated with a new runtime grant.
Do not infer adapters from arbitrary skill names. The managed-skill inventory
publisher also creates a protected `global-credential-inventory.json`: only
installed distribution-managed built-ins receive the reviewed bundled defaults.
All WebUI users, including newly created users, see these declarations, but never
another user's saved values or uploaded skill declarations. Personal and project
upload/review catalogs remain owner-scoped. Run the managed-skill publisher with
`--inventory-only` after upgrading declarations; no image rebuild is needed.

## Trust and data flow

`Settings → encrypted per-user records → trusted local broker → approved service`

The original `skill-vault/` is the only store of upstream secrets. Encrypted
`connections/` records beside it contain references, scope, approved endpoint,
expiry and revision—not copies of the saved passwords/tokens. The auth process
alone writes both stores. Both keys and records require protected backups. Root
and the host service account remain trusted; this does not protect against them.

The dashboard issues random capabilities under `connection-capabilities/`, with
only their digests stored. Claims bind owner, task, project, network/profile,
connection revisions and an expiry no longer than the runner role ceiling. A
Linux boot/process-start identity binds grants to the issuing dashboard process:
restart, crash, PID reuse or reboot cannot revive an old persisted grant. Broker
requests also require an enabled account and a still-running task in protected
metadata. Removing an account deletes its connections and pending capabilities.

The short-lived task capability, **not the upstream credentials**, reaches the
runner through its environment and authenticated Unix channel. The broker strips
it before constructing launcher arguments. The launcher streams it through
OpenShell exec stdin to a mode-0600 temporary file in that task's `/tmp`; the
task relay reads/unlinks it and sets `PRIME_CONNECTION_TOKEN` for Prime. It never
appears in CLI arguments or model prompts. The task can read its own capability,
but can only invoke the named read-only operations while its grant remains valid.
Do not print it or dump the environment. Trusted host processes still have access
to process environments; this is not a defense against a compromised host.

Task requests use the existing model Unix relay, at
`http://127.0.0.1:31000/connections`. The gateway replaces any supplied owner header
with the owner of the Unix listener and forwards only the bounded request to the
loopback broker on port 8767. That port is not published through Nginx or Docker.
Credentials are resolved only inside the local broker. Permission and connection
revision checks run again before returning a result after a network request.

The direct path does **not** alter model routing or native OpenShell network policy.
The separately enabled native transport uses the native placeholder proxy inside
dedicated operation sandboxes, not the general task's sandbox.
The model gateway's capability-based exception retains the task's original
network/profile gates in the broker; Restricted and no-tools tasks get no grant.

Private tool results still require the existing account-qualified cloud routing
policy. Keeping authentication local does not prove data cannot enter cloud
prompts. This pilot does not expand financial authority or authorize publication.

## Install and activate, while idle

Do not perform these steps while tasks or persistent KVM/hosting work would be
interrupted. Check Admin for active work; do not stop it without owner approval.

1. Complete the terminal-route guards, cryptography dependency, backup and
   two-user checks in [credential setup](user-credentials.md). Verify normal
   users cannot access either the shared terminal page or WebSocket.
2. Stage and validate the matched dashboard files (`auth.py`, `api_v2.py`,
   `skill_credentials.py`, `connections.py`, `connection_broker.py`, assets),
   gateway and all three runner components (`runner_client.py`, `runner_broker.py`,
   `runner_launch.py`). Reuse the existing pinned sandbox images: no image change
   is required by this pilot. Do not update only one end of the capability channel.
3. Install `prime-connection-broker.service` as a **user** service for the WebUI
   host account. The normal installer/updater copies this unit but does not start
   or enable it. It defaults to `PRIME_CONNECTIONS_ENABLED=0`.
4. Configure `PRIME_AUTH_CREDENTIAL` consistently for auth, dashboard API and
   connection broker. For runtime activation only, set `PRIME_CONNECTIONS_ENABLED=1`
   in service overrides for `prime-auth`, `prime-dashboard-api`,
   `prime-connection-broker` (user services) and `prime-model-gateway` (system
   service). Credential setup additionally requires `PRIME_CREDENTIALS_ENABLED=1`
   in auth. Do not set an inherited shell variable and assume services receive it.
5. At the approved idle window, reload service definitions and restart the matched
   auth/API/gateway/runner-broker components, then enable/start the connection
   broker. It runs as the WebUI host account, not root or a sandbox. Keep 8767
   bound to loopback. Its unit permits network reads but no filesystem writes.
   Before restarting the API, create
   `~/.config/prime-agent/connection-capabilities` owned by the WebUI host account
   with mode `0700`. Add `ReadWritePaths=%h/.config/prime-agent/connection-capabilities`
   to its service override: `ProtectHome=read-only` otherwise prevents issuing
   grants. Do not grant the API write access to the vault or connection records.
6. First use synthetic records with two users and projects. Then, with owner
   approval, test an actual read-only repository and BMC status request. Verify
   real authentication, the pinned-image stdin handoff, logs without secrets,
   credential revocation and no cross-user/project access before widening use.

Do not treat unit tests as proof of live BMC compatibility or native sandbox
handoff. The reference Spark's real sandbox canary passed; each real service
still needs a read-only authentication test before relying on that connection.
On failure, turn off the connection flags/stop the new broker to deny new calls;
restore matched code backups during an idle window. Retain administrator-only
terminal guards even during rollback; never reopen the shared host console to
ordinary users once vault data exists. Do not remove credential
records/keys as a rollback shortcut. Old task capabilities become unusable after
API restart, without changing stored secrets or conversation history.

## Validation and remaining stages

`scripts/validate-release.sh` includes connection/auth/gateway/runner regressions.
`deploy/spark/dashboard/validate-credentials-ui.py` tests real local HTTP and
browser Settings with synthetic users, project scope, save/delete, secret-free
responses and isolation. It never contacts a BMC, GitHub or a model. On non-Linux
test hosts, the Linux process-identity primitive is mocked in unit fixtures;
production requires Linux `/proc` and fails closed without it.

Remaining: actual GitHub/BMC account authentication and activation of the staged
native HTTP/private console adapters; OAuth consent/refresh and MCP serving/
authorization. Reviewed global inventory is implemented. No cloud vault is
required for this phase.

Upstream references: [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization),
[OpenShell providers](https://docs.nvidia.com/openshell/v0.1.5/how-it-works/providers/overview),
[GitHub repository permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).
