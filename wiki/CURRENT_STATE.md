# Current State

Last verified: 2026-08-24
Wiki version: `v0041`

## Project summary

The Spark now runs Prime Agent as the local orchestration core with two
concurrently resident NVFP4 models. The operating policy covers 3D-print design,
portfolio evaluation, paper-trading research, and supporting code.

## Repository state

- Workspace: `/Users/byte/Documents/Codex/dgx-spark`
- Version control: Git `main`, private GitHub repository
  `https://github.com/dmbyte/prime_agent_webui`, tracking `origin/main`
- Reviewable deployment source: `deploy/spark/`
- Target Spark: SSH verified as `dbyte@172.16.253.231`; passwordless sudo works
- Prime Agent: `0.8.0`, installed for `dbyte`; launcher `prime-dgx`
- Browser interface: ttyd 1.7.4 backend on `127.0.0.1:7681`, fronted by Nginx
  1.24 on `127.0.0.1:8443` and `172.16.253.231:8443` with TLS and PAM.
  Nginx allows loopback, RFC1918, and `100.64.0.0/10` VPN sources and denies all
  other source ranges. The backend remains private to the Spark.
- With explicit user approval, `www-data` is a supplementary member of `shadow`
  (GID 42), allowing the Nginx PAM module to retrieve authentication data.
  Nginx was restarted and all inspected workers inherited groups `33 42`.
- WebSocket origin enforcement is performed by Nginx against the approved HTTPS
  origins. ttyd's incompatible backend `--check-origin` option is disabled because
  a reverse proxy hides the external origin/host relationship from ttyd.
- The authenticated root page is a dashboard with an embedded Prime terminal and
  a default Conversations view plus Parameters and Usage tabs. A compact live
  monitor shows CPU/GPU/memory utilization and GPU board power on its first row,
  with CPU/GPU/system temperatures on the second. Its loopback-only API
  runs as `dbyte` under `prime-dashboard-api.service` on port 8765.
- vLLM: `0.27.1` ARM64/CUDA 12.9 image, two user services enabled at boot
- Hermes WebUI remains installed and active but is not the orchestration core.

## Pre-change recovery state

- Complete baseline: `wiki/SPARK_BASELINE.md`
- Root-only protected artifact on Spark:
  `/var/backups/dgx-spark-baseline-20260823T154649-0500`
- Configuration archive SHA-256:
  `dbac814e640e41293ffc589b5ece0489d7f514e81948b078d227dc66b7fba953`
- All manifest checksums passed.
- The baseline predates Prime installation and the dual-model changes and is the
  authoritative recovery source. It is stored on the same physical Spark.

## Deployed architecture

- Core framework: **Prime Agent 0.8.0**, selected for exact per-child model choice,
  persistent programmable RLM sessions, long-running work, schedules, skills,
  and a reviewable Continual Harness with snapshots and rollback.
- Default local tier: `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`
  plus its DSpark drafter, served as `nemotron-3.5-lightning` on loopback port
  30000. It uses Marlin, FP8 KV, 3 speculative tokens, 65,536 context, a 12 GiB
  KV cache, and at most two sequences.
- Multimodal/deep local tier: `nvidia/Qwen3.6-35B-A3B-NVFP4`, served as
  `qwen3.6-35b-a3b` on loopback port 30001. It uses Marlin, FP8 KV, 65,536
  context, an 8 GiB KV cache, and at most two sequences.
- Frontier API tier: OpenAI GPT-5.4 through the Responses API. A rotated key is
  loaded from a rootless user-service environment file outside the repository;
  the dashboard and wiki never receive its value. Authentication/configuration
  succeeded, but the first request was refused because the API account has no
  credits remaining. GPT-5.6 Sol remains a separate `openai-codex`/ChatGPT route.
- Hermes Agent is optional as an outer messaging/personal-assistant gateway when
  its channels and integrations are valuable; it is not the source of truth or
  autonomous decision authority.

## Domain boundaries

- 3D designs are generated as parametric CadQuery/OpenSCAD/FreeCAD models and
  verified by CAD kernels, mesh checks, slicers, renders, and physical tests.
- Portfolio reports use timestamped authoritative data and deterministic metrics;
  model memory is never a market-data source.
- Trading starts in paper mode only.
- Models may propose trades but cannot hold broker credentials, alter risk limits,
  approve orders, or call unrestricted live-order tools.
- Any future live execution requires a separate deterministic risk gateway,
  explicit human approval, idempotency, limits, kill switch, and audit trail.

## Verified Spark envelope

- Both endpoints passed simultaneous health, text generation, and routing tests;
  Qwen also passed a data-URL image test.
- After warm-up and tests, Linux reported about 38 GiB available memory and less
  than 1 MiB swap used. The acceptance floor is 20 GiB available memory.
- Both inference ports bind only to `127.0.0.1`. Hermes WebUI still listens on
  all interfaces at port 8787; that pre-existing exposure is unchanged.
- NVFP4 is the checkpoint format. Nemotron's published GB10 recipe uses W4A16
  Marlin rather than native FP4 tensor-core execution.

## Durable project memory

- `wiki/USE_CASE_ARCHITECTURE.md` is the detailed current design.
- `wiki/AGENT_STACK.md` and `wiki/AGENT_FRAMEWORK.md` contain detailed supporting
  analysis; v0005 and ADR-0005 take precedence where recommendations differ.
- ADR-0005 is the active architecture decision.

## Operations

- Launch Prime with `prime-dgx`; Nemotron is the default and Qwen is available
  as `spark-qwen/qwen3.6-35b-a3b` for exact child routing.
- LAN and routed private-VPN clients open `https://172.16.253.231:8443` and
  authenticate as `dbyte` with the Spark system password. The certificate is
  self-signed, so clients receive a trust warning until a private-CA certificate
  is installed. No SSH tunnel is required.
- Run `~/prime-dgx-agent/validate.sh` before and after runtime changes.
- Detailed settings, browser access, hashes, tests, and rollback are in
  `wiki/PRIME_DEPLOYMENT.md`.
- Dashboard settings control the default model, thinking level, compaction reserve,
  recent-context retention, and enabled providers. A searchable switch list shows
  all configured/discovered providers and writes Prime's native `enabledModels`
  setting. The default-model list follows enabled providers; the current default
  cannot be disabled until another enabled default is selected. Saves are
  allowlisted, origin checked, atomic, and apply to new terminal sessions.
- Usage combines tokens and recorded spend by provider/model in one table, with
  columns for the Spark's current local calendar day and a rolling 30-day window.
  Local Spark providers correctly report $0 API spend.
- Usage unions the intended/configured catalog with recorded activity, so
  Nemotron, Qwen, and OpenAI GPT-5.4 always have rows. Qwen currently shows zero
  usage. GPT-5.4 is configured and selectable under Parameters but will remain at
  zero until OpenAI billing credits are added and a request succeeds.
- The Usage catalog automatically runs Prime's authenticated model discovery and
  refreshes it at most once per minute; the screen itself refreshes every 30
  seconds. After ChatGPT `/login`, it discovered 13 `openai-codex` models plus
  direct OpenAI and the two Spark models (16 total), including GPT-5.6 Sol.
- Usage renders configured/authenticated models only. Providers with multiple
  models are collapsed by default into a provider row whose Today and Last 30
  days figures sum all child models; expanding reveals per-model rows. Providers
  with one configured model remain direct rows.
- A header activity icon shows the count of working background Prime tasks. It
  opens a top-right floating, draggable, natively resizable, minimizable overlay. Parallel
  tasks become tabs; each tab shows model/status/message count and a privacy-safe
  event timeline (task received, tool running/completed, response update, token
  count) without full prompts, model output, tool output, or secrets.
- The overlay header shows a minus while expanded and changes to a plus while
  minimized; its tooltip, accessible label, and `aria-expanded` state change with it.
- The activity overlay is event-feed-only and its JavaScript contains no attach
  command, attach URL, live-console iframe, or automatic attachment behavior.
  Explicit session attachment remains available through `prime-web-launch` only
  when a strict existing session ID is accompanied by the deliberate
  `--explicit` marker. This prevents stale cached two-argument UI requests from
  attaching or starting Prime while preserving intentional attachment capability.
- A control bar above the main conversation terminal appears while tasks are
  active. It follows a selected active conversation and provides a task selector
  when parallel work exists, plus a confirmation-gated **Stop task** button. The
  activity overlay has no stop control. The API still accepts only strict IDs that
  are currently active, invokes Prime's native single-agent stop command, and
  leaves saved conversation history available without stopping other agents or
  the Prime supervisor.
- The Conversations view lists the 40 most recently modified Prime session files.
  Each row shows a sanitized, 96-character maximum topic derived from the first
  user message, then the timestamp of the latest chat, followed by model and opaque
  ID. It does not return full prompts, summaries, or assistant messages. Clicking
  a row resumes that Prime conversation in the embedded terminal; New conversation
  starts the fixed default launcher.
- Sessions whose sanitized first-user topic is exactly `attach` are treated as UI
  command artifacts and excluded before the 40-row limit. Their JSONL files are
  retained; genuine older conversations fill the vacated list positions.
- Right-clicking a conversation opens a custom menu with **Delete conversation**.
  After confirmation, an inactive transcript is atomically moved to private mode-
  0700 recovery storage at `~/.prime/agent/session-trash/`; active/live sessions
  are rejected. Deleted conversations disappear from the catalog, while their
  recorded tokens and spend remain included in Usage. Each rendered row carries
  its exact full session ID, so selection and deletion target that row directly
  rather than inferring identity from its list position.

## Known gaps

- A potential OpenAI API credential was found in plaintext Prime session history
  during validation. It is not reproduced in the repository or wiki and is not
  exposed by the dashboard. The credential must be revoked/rotated; removal or
  redaction of the sensitive session remains pending explicit user direction.
- The earlier conversation-history key remains sensitive and should still be
  revoked if that specific key was not the rotated credential now in use.
- Installed Prime source establishes that OpenAI API-key authentication uses
  provider `openai`, environment variable `OPENAI_API_KEY`, and default model
  `gpt-5.4`. Its `gpt-5.6-sol` model belongs to provider `openai-codex` through
  the ChatGPT backend, not the OpenAI API-key route. The dashboard now correctly
  represents `openai/gpt-5.4`.
- OpenAI authentication is configured, but API requests are blocked by an empty
  account credit balance. Add credits in the OpenAI Platform billing settings.

- No throughput/latency benchmark or long concurrent soak has run.
- Spend is only as complete as Prime session records and provider/model pricing
  metadata; it excludes subscriptions, taxes, credits, and calls outside Prime.
- Positive PAM login and the full browser session are verified: authenticated
  page/token requests returned 200, ttyd accepted `/terminal/ws`, spawned `prime-dgx`, and
  the live browser exposed an active terminal input. No password was handled.
- Security consequence: an Nginx compromise can now read system password hashes
  for offline attack. Removing `www-data` from `shadow` revokes that access but
  also breaks the current PAM design.
- Public access is prohibited. The Spark has only RFC1918 address
  `172.16.253.231/24`, routes through `172.16.253.1`, and is behind NAT; the
  observed public address was `47.187.248.92`. No Cloudflare/Tailscale edge
  client is installed and UFW is inactive. Nginx explicitly denies non-private
  source ranges; router/firewall port forwarding must remain disabled.
- If a VPN assigns addresses outside RFC1918 or `100.64.0.0/10`, its exact CIDR
  must be reviewed and allowlisted before those clients can connect.
- Existing Spark configuration is now documented; the protected snapshot is on
  the same physical Spark and is not a substitute for an off-device disk backup.
- Prime's local routing policy and infrastructure gate are implemented. The
  frozen domain prompt suite and OpenAI credential/route remain incomplete.
- CAD, market-data, portfolio, paper-broker, and risk-gateway tools are undefined.
- No financial strategy has been specified or validated.
- Development, testing, release, and rollback procedures remain undefined.
