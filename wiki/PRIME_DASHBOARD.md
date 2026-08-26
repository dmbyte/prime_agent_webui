# Prime WebUI

Last verified: 2026-08-25

## User experience

Open `https://172.16.253.231:8443`. The login form verifies the dedicated
`dbyte` WebUI password against a salted-scrypt record and creates a Secure,
HttpOnly, SameSite=Strict session. Set or rotate the password interactively as
`dbyte` with `prime-web-password`; the password is never placed in shell history.
Sessions have a 30-minute idle limit and 12-hour absolute limit; logout revokes
the current in-memory session. State-changing requests require the matching CSRF
cookie/header and an approved Origin.

The default view is a native chat surface rather than an embedded terminal. It
polls persisted Prime JSONL messages while work runs and safely renders headings,
lists, and fenced code. The optional **Advanced console** opens ttyd in a dialog;
normal chat actions never send attach commands to ttyd.

A newly submitted message is rendered immediately with its delivery state. While
the task runs, a live assistant card shows bounded safe lifecycle/tool events,
elapsed time, and available draft response text from Prime's JSON event stream;
private reasoning is not exposed. The composer command selector offers ordinary
Message plus `/steer`, `/follow-up`, and `/stop`. Native WebUI tasks run through
Prime's persistent RPC mode: the initial prompt and authenticated owner commands
use the process's private stdin, while safe events stream from stdout. `/steer`
queues direction at the next turn boundary, `/follow-up` waits until current work
finishes, and Stop sends native `abort`; none requires console attachment.

The active conversation header shows the effective provider/model, effort,
routing mode, and context capacity. Effort is selectable there and applies to
the next message in that conversation; Settings remains the default for new
conversations. A saved active conversation also exposes **Rename** in its header,
which changes the topic and refreshes the sidebar; new conversations hide it.

The sidebar includes:

- **Chats:** searchable, optionally archived conversations with topic and latest
  time; new, resume, rename, pin, archive/restore, fork/duplicate, Markdown export,
  recoverable delete, and bulk archive/delete. Idle, unattached chats can be
  deleted even though Prime labels their persistent lifecycle `live`; actual
  running, streaming, compacting, attached, queued, or unfinished work is blocked.
  Individual and bulk failures are shown to the operator.
  Prime transcript filenames and internal session IDs can differ; opening,
  export, active-work protection, and recoverable deletion resolve either alias
  while recovery retains the real filename.
  Deployment validation resolved all 22 visible rows (nine mismatches) without
  deleting user conversations.
- **Usage:** exact Prime provider/model token and cost windows for today and 30
  days. Every configured provider is a collapsible group whose summary rolls up
  all child-model tokens and spend; expanding it shows model-level values, and
  open groups stay open across periodic refreshes. A separate append-only
  native-request ledger records task status, elapsed
  time, model, usage/cost when Prime emits it, and the associated conversation.
- **Files:** upload progress through HTTPS, size/type/quota metadata, explicit
  prompt selection, safe raster/PDF/text previews, and deletion. ZIP/TAR uploads
  with traversal paths or symbolic/hard links are rejected. Files remain private
  mode 0600 beneath mode-0700 directories.
- **Admin:** service state, storage and upload use, current task admission, guarded
  restarts for the terminal and model services, upload-retention control, and the
  private CA download. Administrators also add/change/disable users, reset
  passwords, revoke sessions, recoverably delete per-user server cache, and delete
  accounts.
- **Settings:** default model/thinking/context values, searchable configured
  providers, provider switches, guarded Prime Agent/WebUI updates, and sign-out.

The live monitor preserves CPU/GPU/memory/power on its first row and CPU/GPU/
system temperatures on the second.

On desktop, drag the divider between the sidebar and chat to resize the sidebar.
The browser remembers widths between 260 and 700 px, constrained to at most 65%
of the viewport. Double-click resets to 370 px. The focused separator also accepts
Left/Right in 20 px steps and Home/End for its limits. Mobile keeps the stacked
layout and hides the divider.

The Archived filter uses a content-width checkbox so its label stays visible at
the minimum sidebar width; conversation rows are constrained to the same boundary.

## Software updates

Settings has two release-aware, confirmed update controls. Every entry into
Settings checks the latest official Prime Agent release and the latest private
`dmbyte/prime_agent_webui` release, compares each with the installed state, and
shows a prominent amber notice with the target version when an update is
available. The release check is also refreshed after an update finishes.

**Update Prime Agent** installs the exact npm version corresponding to the
validated official GitHub release tag inside the existing bundled Node 22
runtime. **Update WebUI from GitHub** requires a clean `main` checkout at the
exact private remote, fetches the latest release tag, resolves its commit,
permits only a fast-forward, compiles the Python entry points, redeploys tracked
assets/services, and restarts the dashboard API. Unreleased commits on `main`
are not advertised as updates. The UI polls running and last-result status.

The long-running dashboard is loopback-only and home-read-only. It can only start
the two named update units; those short-lived services hold separate locks and
have the network/write access needed for npm or Git. The admin-only release
endpoint queries validated GitHub metadata but never accepts a repository or
command from the browser.
Each job writes an atomic mode-0600 result beneath
`~/.prime/agent/update-status/`, allowing Settings to distinguish never-run from
success/failure across service reloads and reboots.
The first WebUI release is titled `.1`, uses valid tag `v0.1.0`, and targets
commit `5d9fd3a`. Prime remains at 0.8.0, matching upstream v0.8.0; the Prime
updater was not run during setup.

## Structured tasks

`api_v2.py` launches Prime's supported noninteractive JSON mode in a separate
process group for each native task. At most four run concurrently. Every task has
a 30-minute wall-time limit and can be stopped by terminating its process group;
Prime persists its normal conversation JSONL. New, resumed, and forked work use
Prime's documented provider/model/thinking/session options rather than terminal
URL arguments.

When Nemotron is the default, deterministic local rules route clear
image/document, 3D/CAD/manufacturing, portfolio/trading, and deep-review prompts
to Qwen. Explicit Qwen/Nemotron requests take precedence. Disabled Qwen produces
a visible fallback, while a manually selected non-Nemotron default is preserved.
The task record and activity overlay expose the effective route and reason.

The activity overlay combines native task state with live Prime agent state,
shows elapsed time/model/status, supports parallel tabs, and provides completed
task logs. Logs are capped, mode 0600, and redact credential-shaped OpenAI keys
and Bearer authorization values. The main chat retains the stop button.

## Data and safety

- Full conversation messages are returned only after session authentication;
  browser rendering uses DOM text nodes and never injects model HTML.
- Authenticated identity/role comes from the loopback broker through Nginx, not a
  browser-controlled header. Chats, uploads, tasks/logs, usage, and metadata are
  owner-filtered. Existing data defaults to `dbyte`; new data records its owner.
- User/cache deletion moves owned server data to mode-0700 per-user recovery
  storage, including chats, uploads, persisted task logs/ownership, and owned
  usage-ledger records. Cache clearing, password reset/change, and deletion revoke
  that user's active sessions. Password creation/reset uses masked dialog fields.
- The deployed compatibility check retained the existing mode-0600 version-1
  credential and recognized it as `dbyte`/admin without rewriting it. The first
  successful management change performs the atomic version-2 store migration.
- The Admin surface groups System, Maintenance, and WebUI users. Service health,
  account role, and enabled state use explicit badges; user operations use a
  responsive two-column action grid. Actions disallowed for the signed-in or
  initial administrator are disabled with explanatory tooltips.
- Conversation metadata is stored atomically in
  `~/.prime/agent/webui-metadata.json`; transcripts remain Prime's JSONL source
  of truth. Delete still moves inactive transcripts to private recovery storage.
- Usage remains derived from Prime's recorded message usage and cost objects.
  It is not a provider invoice and cannot include calls outside Prime.
- Upload preview permits only PNG/JPEG/GIF/WebP, PDF, plain text, CSV, and JSON;
  framed previews are sandboxed. Other types are not rendered inline.
- **Settings providers:** the compact configured-provider filter sits beside an
  admin-only **Add provider** button. A searchable modal lists Prime 0.8.0 API-key
  providers, subscription logins, Azure/AWS/Cloudflare/Vertex cloud variants,
  and custom OpenAI-compatible endpoints. It renders only the fields required by
  the selected provider. Secret fields are write-only, masked, cleared after use,
  stored outside the repository, and never returned by the API. Subscription
  entries open the authenticated Advanced console for Prime's `/login` flow.
- Applying retention requires explicit confirmation and deletes only uploads
  older than 1–365 configured days. Conversation retention is unchanged.

## Deployment

- Static UI: `/var/www/prime-agent/`
- Static asset URL root: `/var/www/prime-agent/assets/`; use the tracked
  `install-static.sh` so login and application scripts are not misplaced.
- Native API: `~/prime-dgx-dashboard/api_v2.py`, loopback port 8765
- Local session broker: `~/prime-dgx-dashboard/auth.py`, loopback port 8764
- Password tool: `/usr/local/bin/prime-web-password`
- Credential record: `~/.config/prime-agent/web-auth.json`, mode 0600
- Advanced console: ttyd, loopback port 7681
- Models: loopback ports 30000 and 30001
- Nginx: private address/loopback port 8443
- Private CA: `/etc/nginx/prime-agent-ca/`; downloadable public certificate:
  `/prime-webui-ca.crt`

The API's writable scope is `~/.prime/agent` and `~/prime-dgx-agent`; the auth
broker is read-only and unprivileged. It reads only the one-way credential record
and does not use PAM, the Linux account password, or `shadow`.

## Validation and recovery

Fourteen local dashboard/auth/security tests and eleven applicable deployed
Python tests pass, including routing, quota/path/privacy, and
unsafe-archive cases. A real Nemotron task launched through the native API,
completed in 2.3 seconds, persisted a conversation, returned the exact response,
and recorded 6,268 tokens. Model/private-listener/session-broker/HTTPS/header and
20% memory-gate validation passed.

The owner completed positive password entry: the browser login returned 200 and
the broker reports the credential configured. Before initial setup, login returns
503; after setup, invalid local-credential login returns 401. Validation never
handled the password or read the one-way record. The private CA must be installed
on each client before the browser trusts the certificate.

The pre-v0056 PAM configuration is preserved root-only at:

`/var/backups/prime-local-auth-v0056-20260825T170500-0500`

The pre-v0060 API/UI/policy and installed web root are preserved root-only with
checksums at:

`/var/backups/prime-routing-v0060-20260825T173500-0500`

The pre-v0061 Usage source and installed assets are preserved root-only with
checksums at:

`/var/backups/prime-usage-v0061-20260825T174000-0500`

The pre-v0062 deletion API/source and installed UI asset are preserved root-only
with checksums at:

`/var/backups/prime-delete-v0062-20260825T174100-0500`

The pre-v0063 source and installed sidebar assets are preserved root-only with
checksums at:

`/var/backups/prime-sidebar-v0063-20260825T174200-0500`

The pre-v0064 API/UI, installed assets, clone commit, and Prime version are
preserved root-only with checksums at:

`/var/backups/prime-updates-v0064-20260825T174800-0500`

The pre-v0065 conversation APIs and deployed Git commit are preserved root-only
with checksums at:

`/var/backups/prime-session-ids-v0065-20260825T175500-0500`

The pre-v0066 single-user credential/auth/API/UI/Nginx state is preserved
root-only with checksums at:

`/var/backups/prime-users-v0066-20260825T180700-0500`

The pre-v0052 root-only recovery bundle is:

`/var/backups/prime-webui-v0052-20260825T153014-0500`
