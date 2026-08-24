# Prime dashboard

Last verified: 2026-08-23

## User experience

Open `https://172.16.253.231:8443` and authenticate through PAM. The main area
contains the live Prime terminal. The sidebar provides:

- **Conversations (default):** up to 40 recent Prime sessions showing a short
  topic first, latest-chat date/time second, then model and opaque ID, plus a New conversation
  button. “Conversation” is the user-facing term; “session” remains the storage term.

- **Parameters:** default Nemotron or Qwen local model, thinking level,
  compaction reserve, and recent-context retention. Changes apply to new terminal
  sessions and do not silently replace an active conversation.
- **Usage:** one row per provider/model with tokens and recorded spend for Today
  and Last 30 days. Today begins at local midnight on the Spark; 30 days is rolling.
  Configured/intended models remain visible with zero usage; a planned provider
  that is not operational is explicitly labeled `not configured`. Local inference
  is displayed as $0 API spend.

The compact monitor above the tabs refreshes every two seconds. Its top row shows
CPU, GPU, memory utilization, and power; its bottom row contains CPU, GPU, and
system temperatures.
CPU use is derived from `/proc/stat`, memory from `/proc/meminfo`, GPU use,
temperature, and board power from `nvidia-smi`, CPU temperature from the maximum
ACPI thermal zone, and system temperature from the maximum NVMe sensor. Missing
sensors render as unavailable. Full usage/session data refreshes every 30 seconds.

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
ttyd URL arguments terminate at `prime-web-launch`, which forwards only the exact
two-argument resume form when the ID matches the strict character/length rule and
an existing session file. Every other argument combination is discarded and the
fixed new-conversation launcher runs. New conversation reloads that fixed endpoint.

## Architecture and security

- Static assets: `/var/www/prime-agent/`
- API: `~/prime-dgx-dashboard/api.py`
- API service: `prime-dashboard-api.service`, `127.0.0.1:8765`
- Terminal: ttyd at `127.0.0.1:7681`, base path `/terminal`
- Boundary: Nginx/PAM/TLS at the private-network address

The API runs as `dbyte`, has `NoNewPrivileges`, a private temporary directory,
read-only system protection, and write access under `~/.prime/agent`. Settings
POSTs require an approved HTTPS Origin and a dashboard-specific header; only
known provider/model pairs, thinking levels, and bounded compaction values are
accepted. Settings are atomically written mode 0600. Nginx protects assets, API,
and terminal uniformly.

## Validation and rollback

API health/state/settings passed. The current catalog parsed 36 session files.
Browser verification showed Conversations as the active default, a New conversation button,
metadata-only rows, all seven live telemetry readings, the remaining tabs, and an
active terminal. Click-to-resume returned an active terminal without emitting its
conversation content into validation output. Both services are active; ports 8765 and 7681 remain loopback-only;
both model services and the project gate pass.

Rollback disables `prime-dashboard-api.service`, restores v0014 Nginx and ttyd,
reloads Nginx, and removes static assets only after the terminal is verified.
