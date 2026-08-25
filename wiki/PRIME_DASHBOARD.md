# Prime WebUI

Last verified: 2026-08-25

## User experience

Open `https://172.16.253.231:8443`. The login form verifies the `dbyte` system
password through PAM and creates a Secure, HttpOnly, SameSite=Strict session.
Sessions have a 30-minute idle limit and 12-hour absolute limit; logout revokes
the current in-memory session. State-changing requests require the matching CSRF
cookie/header and an approved Origin.

The default view is a native chat surface rather than an embedded terminal. It
polls persisted Prime JSONL messages while work runs and safely renders headings,
lists, and fenced code. The optional **Advanced console** opens ttyd in a dialog;
normal chat actions never send attach commands to ttyd.

The sidebar includes:

- **Chats:** searchable, optionally archived conversations with topic and latest
  time; new, resume, rename, pin, archive/restore, fork/duplicate, Markdown export,
  recoverable delete, and bulk archive/delete.
- **Usage:** exact Prime provider/model token and cost windows for today and 30
  days. A separate append-only native-request ledger records task status, elapsed
  time, model, usage/cost when Prime emits it, and the associated conversation.
- **Files:** upload progress through HTTPS, size/type/quota metadata, explicit
  prompt selection, safe raster/PDF/text previews, and deletion. ZIP/TAR uploads
  with traversal paths or symbolic/hard links are rejected. Files remain private
  mode 0600 beneath mode-0700 directories.
- **Admin:** service state, storage and upload use, current task admission, guarded
  restarts for the terminal and model services, upload-retention control, and the
  private CA download.
- **Settings:** default model/thinking/context values, searchable configured
  providers, provider switches, and sign-out.

The live monitor preserves CPU/GPU/memory/power on its first row and CPU/GPU/
system temperatures on the second.

## Structured tasks

`api_v2.py` launches Prime's supported noninteractive JSON mode in a separate
process group for each native task. At most four run concurrently. Every task has
a 30-minute wall-time limit and can be stopped by terminating its process group;
Prime persists its normal conversation JSONL. New, resumed, and forked work use
Prime's documented provider/model/thinking/session options rather than terminal
URL arguments.

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
- Native API: `~/prime-dgx-dashboard/api_v2.py`, loopback port 8765
- PAM session broker: `~/prime-dgx-dashboard/auth.py`, loopback port 8764
- Advanced console: ttyd, loopback port 7681
- Models: loopback ports 30000 and 30001
- Nginx: private address/loopback port 8443
- Private CA: `/etc/nginx/prime-agent-ca/`; downloadable public certificate:
  `/prime-webui-ca.crt`

The API's writable scope is `~/.prime/agent` and `~/prime-dgx-agent`; the auth
broker is read-only and unprivileged. PAM invokes Ubuntu's set-group
`unix_chkpwd` helper, so neither Nginx nor the broker process can read `shadow`.

## Validation and recovery

Seven local and deployed security tests pass, including quota/path/privacy and
unsafe-archive cases. A real Nemotron task launched through the native API,
completed in 2.3 seconds, persisted a conversation, returned the exact response,
and recorded 6,268 tokens. Model/private-listener/session-broker/HTTPS/header and
20% memory-gate validation passed.

Positive password entry is intentionally left to the owner; invalid PAM login
returns 401. The private CA must be installed on each client before the browser
will trust the new certificate.

The pre-v0052 root-only recovery bundle is:

`/var/backups/prime-webui-v0052-20260825T153014-0500`
