# Prime dashboard

Last verified: 2026-08-24

## User experience

Open `https://172.16.253.231:8443` and authenticate through PAM. The main area
contains the live Prime terminal. The sidebar provides:

- **Conversations (default):** up to 40 recent Prime sessions showing a short
  topic first, latest-chat date/time second, then model and opaque ID, plus a New conversation
  button. “Conversation” is the user-facing term; “session” remains the storage term.

- **Parameters:** default model, thinking level, compaction reserve, recent-context
  retention, and a searchable list of every configured/discovered provider. Each
  provider has an enable switch backed by Prime's native `enabledModels`; enabling
  a provider enables all of its currently discovered models. The default-model
  menu contains enabled models only, and its provider cannot be disabled until a
  different enabled default is selected. Changes apply to new terminal sessions
  and do not silently replace an active conversation.
- **Usage:** one row per provider/model with tokens and recorded spend for Today
  and Last 30 days. Today begins at local midnight on the Spark; 30 days is rolling.
  Configured models remain visible with zero usage. Local inference is displayed
  as $0 API spend. GPT-5.4 is configured but cannot accrue usage until API billing
  credits are available.

Usage excludes recorded models that are no longer configured. A provider with
multiple configured models is a collapsed group showing rolled-up tokens/spend;
expanding it reveals each model. Single-model providers remain ordinary rows.

The model rows are not maintained manually. The dashboard invokes Prime's own
authenticated `model list`, caches successful discovery for 60 seconds, unions it
with custom/planned and recorded models, and refreshes the Usage screen every 30
seconds. Failed discovery preserves the last successful catalog. Only rows marked
configured by that resulting catalog are rendered.

The compact monitor above the tabs refreshes every two seconds. Its top row shows
CPU, GPU, memory utilization, and power; its bottom row contains CPU, GPU, and
system temperatures.
CPU use is derived from `/proc/stat`, memory from `/proc/meminfo`, GPU use,
temperature, and board power from `nvidia-smi`, CPU temperature from the maximum
ACPI thermal zone, and system temperature from the maximum NVMe sensor. Missing
sensors render as unavailable. Full usage/session data refreshes every 30 seconds.

## Background activity overlay

The header activity icon polls every three seconds and shows the number of Prime
sessions whose lifecycle is live and activity is not idle. Clicking it opens a
floating overlay that can be dragged, resized from its corner, minimized, and
reopened. Its default location is the top-right of the browser window (top inset
on narrow screens). The header control shows a minus when it can minimize and a
plus when it can expand, with synchronized tooltip and accessibility state.
Concurrent tasks appear as tabs.

Each tab reports sanitized topic, activity, provider/model, thinking level,
message count, timestamps, tool names, and token progress. The API deliberately
does not return full prompts, assistant text, thinking text, tool inputs/results,
or status summaries. Credential-like topics retain the existing sensitive label.

The overlay is event-feed-only. Its deployed JavaScript has no attach command,
attach URL, live-console control, or iframe. A previously offered automatic live
console was retired after its second TUI interfered with a job. Session attachment
itself remains available as an explicit launcher operation, outside normal UI
behavior.

The overlay deliberately has no stop control. While work is active, a control bar
above the main conversation terminal presents **Stop task**. It follows a selected
active sidebar conversation when possible and exposes a running-task selector when
parallel conversations need disambiguation. After explicit browser confirmation,
the API revalidates that the strict session ID is currently active and calls
Prime's native single-agent `stop` command. Success removes the worker from active
tasks while retaining its JSONL conversation for later review or resumption. The
control never invokes Prime's global shutdown and cannot target an idle or
historical session.

## Data semantics

The dashboard reads only `~/.prime/agent/sessions/*.jsonl`. For every assistant
message it uses Prime's recorded `provider`, `model`, and `usage` object. Input,
output, cache, total tokens, calls, and `usage.cost.total` are summed per provider
and time window. Repeated full-context input is intentionally counted per call.

Usage is keyed by the exact Prime provider/model pair. Costs are not an invoice. They exclude calls outside Prime, subscriptions,
minimum charges, taxes, discounts, and credits, and depend on correct pricing
metadata. Providers with zero pricing metadata—including local Spark providers—
show $0.

The session catalog derives a topic from the first user message after explicit
user approval to display that text to authenticated LAN/VPN users. It normalizes
whitespace, caps topics at 96 characters, and replaces credential-like input with
`Sensitive conversation`. Topics are rendered using DOM `textContent`, never HTML.
The API does not send full prompts, summaries, or assistant messages to the browser.
Clicking a conversation reloads the terminal with `--resume` and its opaque ID.
An exact sanitized topic of `attach` is recognized as an attachment-command
artifact and omitted before the 40-conversation limit is applied. The underlying
session file is retained, and the next genuine conversation fills that row.
Right-clicking a row opens a custom context menu with **Delete conversation**.
Deletion requires confirmation and server-side proof that the session is not live.
The JSONL transcript is moved atomically into private recovery storage under
`~/.prime/agent/session-trash/`, rather than unlinked. It disappears from the
conversation catalog, but Usage continues reading trashed transcripts so historical
token and spend totals do not change.
Conversation rows bind their full validated session ID in DOM data. Both ordinary
selection and the context-menu action resolve the session through that exact row
ID; neither uses an array index, preventing a lower row from targeting the first.
ttyd URL arguments terminate at `prime-web-launch`, which forwards only the exact
two-argument resume form when the ID matches the strict character/length rule and
an existing session file. Every other argument combination is discarded and the
fixed new-conversation launcher runs. New conversation reloads that fixed endpoint.
The launcher accepts only `--attach ID --explicit`, where `ID` passes the strict
syntax rule and names an existing session. It forwards that as Prime's native
`attach ID`. A two-argument request from stale cached dashboard code fails closed
with exit 64 and never falls through to a new Prime conversation. The current UI
never constructs either form.

## File uploads

The workspace upload tray accepts the browser file picker or drag and drop. Each
file is streamed through PAM-authenticated private HTTPS to
`~/prime-dgx-agent/uploads/YYYY-MM-DD/`; the API never buffers a whole file in
memory. Files are limited to 100 MiB individually and 2 GiB in aggregate. Upload
directories are mode 0700 and files mode 0600. Supplied names are reduced to a
safe basename and stored with a random prefix; SHA-256 is computed during upload.

After upload, **Copy path** places the exact local Spark path on the clipboard.
Paste that path into the desired Prime prompt. This explicit step is deliberate:
an upload does not generate an attach command, send a message, select a session,
or steer/interrupt a running agent. Files persist until a separately reviewed
retention or deletion policy is implemented.

## Architecture and security

- Static assets: `/var/www/prime-agent/`
- API: `~/prime-dgx-dashboard/api.py`
- API service: `prime-dashboard-api.service`, `127.0.0.1:8765`
- Terminal: ttyd at `127.0.0.1:7681`, base path `/terminal`
- Boundary: Nginx/PAM/TLS at the private-network address
- OpenAI credential: `~/.config/prime-agent/openai.env`, mode 0600, loaded only by
  `prime-web.service`; never stored in deployment source, dashboard responses, or wiki

The API runs as `dbyte`, has `NoNewPrivileges`, a private temporary directory,
read-only system protection, and narrowly scoped write access under
`~/.prime/agent` plus `~/prime-dgx-agent/uploads`. Settings
POSTs require an approved HTTPS Origin and a dashboard-specific header; only
known provider/model pairs, thinking levels, and bounded compaction values are
accepted. Settings are atomically written mode 0600. Nginx protects assets, API,
and terminal uniformly.

## Validation and rollback

API health/state/settings passed. A live upload matched its source size and
SHA-256 and had the documented 0700/0600 permissions. An invalid origin returned
403, unauthenticated HTTPS returned 401, Nginx loaded the 100 MiB streaming
directives, and the temporary validation file was removed. The current catalog parsed 36 session files.
Browser verification showed Conversations as the active default, a New conversation button,
metadata-only rows, all seven live telemetry readings, the remaining tabs, and an
active terminal. Click-to-resume returned an active terminal without emitting its
conversation content into validation output. Both services are active; ports 8765 and 7681 remain loopback-only;
both model services and the project gate pass.

Rollback disables `prime-dashboard-api.service`, restores v0014 Nginx and ttyd,
reloads Nginx, and removes static assets only after the terminal is verified.
