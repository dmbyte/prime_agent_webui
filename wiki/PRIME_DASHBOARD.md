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

The active conversation header shows the effective provider/model, effort,
routing mode, and context capacity. Effort is selectable there and applies to
the next message in that conversation; Settings remains the default for new
conversations.

The sidebar includes:

- **Chats:** searchable, optionally archived conversations with topic and latest
  time; new, resume, rename, pin, archive/restore, fork/duplicate, Markdown export,
  recoverable delete, and bulk archive/delete. Idle, unattached chats can be
  deleted even though Prime labels their persistent lifecycle `live`; actual
  running, streaming, compacting, attached, queued, or unfinished work is blocked.
  Individual and bulk failures are shown to the operator.
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
  private CA download.
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

Settings has two confirmed update controls. **Update Prime Agent** runs npm
`prime-agent@latest` inside the existing bundled Node 22 runtime. **Update WebUI
from GitHub** currently requires a clean `main` checkout at the exact private
`dmbyte/prime_agent_webui` remote, fetches `origin/main`, permits only a
fast-forward, compiles the Python entry points, redeploys tracked assets/services,
and restarts the dashboard API. The UI polls running and last-result status.

The long-running dashboard remains network-denied and home-read-only. It can only
start the two named update units; those short-lived services hold separate locks
and have the network/write access needed for npm or Git. Release discovery and
installed-versus-release comparison are the next planned update-policy revision.

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
- Conversation metadata is stored atomically in
  `~/.prime/agent/webui-metadata.json`; transcripts remain Prime's JSONL source
  of truth. Delete still moves inactive transcripts to private recovery storage.
- Usage remains derived from Prime's recorded message usage and cost objects.
  It is not a provider invoice and cannot include calls outside Prime.
- Upload preview permits only PNG/JPEG/GIF/WebP, PDF, plain text, CSV, and JSON;
  framed previews are sandboxed. Other types are not rendered inline.
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

The pre-v0052 root-only recovery bundle is:

`/var/backups/prime-webui-v0052-20260825T153014-0500`
