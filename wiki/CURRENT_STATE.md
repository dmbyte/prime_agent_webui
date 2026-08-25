# Current State

Last verified: 2026-08-25
Wiki version: `v0051`

## Project summary

The Spark now runs Prime Agent as the local orchestration core with two
concurrently resident NVFP4 models. The operating policy covers 3D-print design,
portfolio evaluation, paper-trading research, and supporting code. The repository
now also contains its first generated, kernel-validated 3D-print design: a vented
case for Raspberry Pi 5 with the iUniker INV001 NVMe HAT+.

## Repository state

- Workspace: `/Users/byte/Documents/Codex/dgx-spark`
- Version control: Git `main`, private GitHub repository
  `https://github.com/dmbyte/prime_agent_webui`, tracking `origin/main`
- Reviewable deployment source: `deploy/spark/`
- Parametric CAD source and generated parts:
  `cad/pi5-iuniker-inv001-case/`
- Target Spark: SSH verified as `dbyte@172.16.253.231`; passwordless sudo works
- Prime Agent: `0.8.0`, installed for `dbyte`; launcher `prime-dgx`
- Browser interface: ttyd 1.7.4 backend on `127.0.0.1:7681`, fronted by Nginx
  1.24 on `127.0.0.1:8443` and `172.16.253.231:8443` with TLS and PAM.
  Nginx allows loopback, RFC1918, and `100.64.0.0/10` VPN sources and denies all
  other source ranges. The backend remains private to the Spark. An Nginx
  systemd pre-start check waits up to 120 seconds for the explicit private LAN
  address before validating the configuration, avoiding the boot-time bind race
  observed on 2026-08-24 while failing closed if the address never appears.
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
  It is now bound to `127.0.0.1:8787`.

## Pre-change recovery state

- Complete baseline: `wiki/SPARK_BASELINE.md`
- Root-only protected artifact on Spark:
  `/var/backups/dgx-spark-baseline-20260823T154649-0500`
- Configuration archive SHA-256:
  `dbac814e640e41293ffc589b5ece0489d7f514e81948b078d227dc66b7fba953`
- All manifest checksums passed.
- The baseline predates Prime installation and the dual-model changes and is the
  authoritative recovery source. It is stored on the same physical Spark.
- The pre-hardening recovery bundle is root-only at
  `/var/backups/prime-security-20260825T151200-0500`; it contains the affected
  configuration and checksums plus the original transcript sanitized in v0051.

## Deployed architecture

- Core framework: **Prime Agent 0.8.0**, selected for exact per-child model choice,
  persistent programmable RLM sessions, long-running work, schedules, skills,
  and a reviewable Continual Harness with snapshots and rollback.
- Default local tier: `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`
  plus its DSpark drafter, served as `nemotron-3.5-lightning` on loopback port
  30000. It uses Marlin, FP8 KV, 3 speculative tokens, 81,920 context, a 12 GiB
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
- After the 81,920-token Nemotron warm-up and tests, Linux reported 39.1 GiB
  available memory (32.15%). The validation gate now requires at least 20% of
  usable RAM, about 24.3 GiB on this Spark.
- Both inference ports and Hermes WebUI bind only to `127.0.0.1`.
- NVFP4 is the checkpoint format. Nemotron's published GB10 recipe uses W4A16
  Marlin rather than native FP4 tensor-core execution.

## Security posture

- Nginx is the only Prime browser listener available to the LAN, on the explicit
  private address and port 8443. Port 80 and the default site are disabled.
  ttyd, the dashboard API, Hermes WebUI, and both inference engines bind only to
  loopback. SSH remains available on port 22.
- The existing Nginx private-source allow rules remain. Per owner direction, no
  host-level CIDR firewall policy was added; UFW remains inactive.
- PAM accepts only members of `prime-web`; `dbyte` is a member. Nginx delays and
  rate-limits failures. Fail2ban reacts after 15 failures in 10 minutes with a
  one-hour nftables ban; this is abuse control, not a CIDR allowlist.
- Nginx suppresses version details and sends CSP, no-sniff, referrer,
  permissions, opener/resource isolation, and no-store headers.
- The API bounds request concurrency, size, and content types; serializes upload
  quota and deletion operations; validates UTF-8 filename bytes; skips individual
  malformed JSONL records; and emits structured security logs without prompts.
- NFS export of `/home/dbyte`, `nfs-server`, and rpcbind services/socket are
  disabled. No NFS exports remain.
- User services have restrictive umasks and compatible systemd confinement. The
  API cannot read the OpenAI credential file and receives only a non-secret
  configuration flag.
- All 19 pending Ubuntu security updates present on 2026-08-25 were installed.
- One transcript with two credential-shaped key occurrences was copied to the
  root-only recovery bundle and redacted. No matching strings remain in active or
  trashed sessions. The key must still be revoked at OpenAI if it remains active.
- Full controls, validation, residual risks, and recovery are in
  `wiki/SECURITY.md`.

## Durable project memory

- `wiki/USE_CASE_ARCHITECTURE.md` is the detailed current design.
- `wiki/AGENT_STACK.md` and `wiki/AGENT_FRAMEWORK.md` contain detailed supporting
  analysis; v0005 and ADR-0005 take precedence where recommendations differ.
- ADR-0005 is the active architecture decision.
- The Pi 5/iUniker enclosure source, printable STLs, assembly preview, dimensions,
  print settings, and mandatory physical fit procedure are in
  `cad/pi5-iuniker-inv001-case/`; ADR-0033 records its mechanical strategy.

## Current CAD artifact

- The enclosure is a rounded two-piece shell measuring 100.6 x 71.6 x 42.4 mm,
  tuned for Bambu PETG Basic on an X2D with a stock 0.4 mm main nozzle.
- It provides long bottom intakes, a honeycomb lid exhaust, vertical exhaust
  slots around all four upper walls, all primary Pi 5 port openings except
  microSD, recessed M2.5 board mounting, and four M3 lid screws.
- Its 2.8 mm walls equal seven nominal nozzle widths, the lid has 0.35 mm sliding
  clearance per side, and the M3 pilots are 2.7 mm. Separate Ethernet/USB bays
  replace the former long opening, keeping the largest wall bridge below 17 mm.
- A separate captive printed plunger operates the Pi 5 native power button without
  wiring an additional switch. It passes through the short end near the USB-C
  corner and uses the supplied v14 reference's 10.6 x 8.3 x 5.6 mm envelope with
  an offset oval LED window through its face. The end has no microSD cutout at the
  owner's request. Control positions remain physical-fit parameters because
  Raspberry Pi labels component geometry approximate.
- Base, lid, and button STLs each validate as a single watertight,
  winding-consistent positive-volume body. A colored exploded GLB and PNG preview
  are generated with the parts.
- The owner confirmed that this INV001 board has the same 85 mm length as the Pi
  5. The compact model now uses an 85 x 56.5 mm plan envelope inside a 95 x 66 mm
  cavity. Owner-supplied photos support the standard Pi mounting pattern and a
  nominal 16 mm brass HAT spacer; because the caliper display was off, the value
  remains a nominal assumption rather than an exact measurement. The explicit
  stack envelope leaves 8 mm of air below the base rim. Board width, exact stacked
  height, and native-button alignment still require physical measurement before a
  final-material print.
- The X2D guide uses the left/main hotend, built-in Bambu PETG Basic preset, 0.20
  mm Standard process as its starting point, four walls, 25% gyroid, five top and
  bottom layers, and no supports or active chamber heat.
- Bambu Studio 02.08.02.61 successfully sliced the compact three-part plate with
  resolved factory X2D/PETG profiles: left/main nozzle only, zero support features,
  zero filament changes, no warnings, and an estimated 2 h 41 m 9 s print time.
  Temporary G-code was discarded; the retained JSON report records the settings.

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
- A paperclip and drag-and-drop tray above the terminal accepts files up to 100
  MiB each. The loopback API streams them into mode-0700
  `~/prime-dgx-agent/uploads/YYYY-MM-DD/` folders as mode-0600 files, with a 2
  GiB total quota, safe stored names, random prefixes, and SHA-256 calculation.
  The UI exposes **Copy path** so the operator can explicitly reference a file in
  the intended prompt. Uploading alone never sends an agent/session command or
  interrupts running work.

## Known gaps

- The credential formerly present in conversation history has been redacted from
  the Spark, but it should still be revoked at OpenAI if it remains active.
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
- The first CAD generator and X2D/PETG slice validation are implemented, but the
  iUniker case has not yet been physically printed and fit-tested. Market-data,
  portfolio, paper-broker, and risk-gateway tools remain undefined.
- No financial strategy has been specified or validated.
- Local application security regression checks are included. GitHub Actions and
  broader release promotion/rollback automation remain undefined.
