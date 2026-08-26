# Current State

Last verified: 2026-08-26
Wiki version: `v0078`

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
- Prime has a tracked, globally installed `software-security-review` skill. It
  discovers project capabilities first and conditionally audits applicable web,
  authentication, memory/resource, storage, command/agent, network, cryptography,
  concurrency, supply-chain, and deployment boundaries. It requires concrete
  attack paths, evidence/confidence, negative results, and separate classifications
  for confirmed vulnerabilities, validation needs, reliability, defense in depth,
  and accepted trust assumptions.
  Forward testing eliminated the earlier CSP/Origin false positives but initially
  missed gateway-bypass and shared-execution consequences and invented runtime
  metadata. The refined entrypoint now makes local gateway bypass, execution-
  identity comparison, and metadata non-invention mandatory review gates.
  A machine-readable second test verified Qwen/high was actually used, found the
  header trust area, but still confused direct local bypass with external header
  spoofing and emitted several platform-semantic false positives. The current
  skill therefore includes explicit proxy-header, double-submit CSRF, argv/`--`,
  guarded-import, CSP, and runtime-evidence guardrails plus a decision-dense output
  rule. Local gateway and shared-execution gates must now resolve to a finding or
  an evidence-based negative result.
  A bounded third test cleared the prior argv, CSP, and guarded-import errors but
  incorrectly treated shared execution and local backend bypass as informational
  under a single-user assumption. The current skill rejects that downgrade when
  software exposes distinct accounts/roles or lets less-trusted users launch local
  workloads, and adds precise GET/CORS/CSRF and HTTP-method dispatch guardrails.
  The final tools-disabled, 500-word regression then correctly classified both
  user-influenced direct loopback API forgery and the lack of cross-account
  isolation under shared agent/terminal execution, with concrete attack paths.
- Browser interface: native Prime chat API on `127.0.0.1:8765`, optional ttyd
  1.7.4 console on `127.0.0.1:7681`, and isolated local session broker on
  `127.0.0.1:8764`, fronted by Nginx 1.24 on loopback and
  `172.16.253.231:8443` with private-CA TLS.
  Nginx allows loopback, RFC1918, and `100.64.0.0/10` VPN sources and denies all
  other source ranges. The backend remains private to the Spark. An Nginx
  systemd pre-start check waits up to 120 seconds for the explicit private LAN
  address before validating the configuration, avoiding the boot-time bind race
  observed on 2026-08-24 while failing closed if the address never appears.
- The WebUI no longer uses PAM or the Linux account password. Its unprivileged
  broker verifies a dedicated salted-scrypt credential stored mode 0600 outside
  the repository; Nginx has no `shadow` access. Secure session cookies use
  30-minute idle and 12-hour absolute
  limits; state changes require CSRF and Origin validation.
- The credential store now supports local `admin` and `user` roles. `dbyte` is
  the initial admin and owner of all legacy data. Chats, files, tasks/logs, usage,
  and metadata are isolated by the broker-authenticated owner. Admins can add,
  change, reset, revoke, recoverably clear server data, and delete users; the
  initial/last admin protections remain.
  Recoverable cache clearing includes chats, uploads, persisted task ownership
  and logs, and the user's usage-ledger records, then revokes their sessions.
  Password creation/reset uses masked inputs with the same 12-character minimum.
  Deployment preserved the on-disk version-1 credential mode 0600; the broker
  exposes it virtually as the sole `dbyte` admin until the first management write
  performs the atomic version-2 migration. Negative login remained 401. The v0067
  deployment passed all 25 tests and exact Auth/API/UI hash comparison.
- WebSocket origin enforcement is performed by Nginx against the approved HTTPS
  origins. ttyd's incompatible backend `--check-origin` option is disabled because
  a reverse proxy hides the external origin/host relationship from ttyd.
- The authenticated root page is a native conversation UI with Chats, Usage,
  Files, Admin, and Settings tabs; the terminal is an optional advanced dialog.
  The active conversation header displays the effective model, editable effort,
  routing mode/reason, and context capacity. Effort changes apply to the next
  message in that conversation and persist when that task starts.
  A compact live
  monitor shows CPU/GPU/memory utilization and GPU board power on its first row,
  with CPU/GPU/system temperatures on the second. Its loopback-only API
  runs as `dbyte` under `prime-dashboard-api.service` on port 8765.
  On desktop, the sidebar divider supports pointer and keyboard resizing from
  260–700 px, persists the browser-local choice, and resets on double-click. The
  divider is hidden in the stacked mobile layout.
  The narrow-sidebar Archived checkbox and conversation contents remain within
  the sidebar boundary.
  The Admin tab is visually grouped into System, Maintenance, and WebUI users;
  status/role/state badges and grouped user actions remain readable at the
  default sidebar width. Backend-protected self/initial-admin actions are visibly
  disabled instead of failing only after a click.
  A saved active conversation exposes Rename in the conversation header; new
  conversations hide it, and a successful rename refreshes the header/sidebar.
  The v0068 desktop visual check verified both the full user-action grid and the
  saved-conversation Rename control; all 25 deployed tests passed.
  Settings now uses a compact configured-provider filter beside **Add provider**.
  Its modal catalogs every provider documented by installed Prime 0.8.0: API-key,
  subscription, Azure/AWS/Cloudflare/Vertex, and custom OpenAI-compatible paths.
  Admins can configure required fields without secrets being returned to the
  browser. Provider credentials are global trusted infrastructure, not per-user.
  Deployment and live visual validation confirmed 34 catalog rows and masked
  provider-specific forms. No credential was submitted during testing, and the
  existing credential/model files remained byte-identical to the backup.
  Settings now uses the same grouped card hierarchy as Admin. Entering Settings
  checks the latest published Prime Agent and Prime WebUI releases and shows a
  prominent amber notice and target version when either installed component is
  behind. Prime Agent 0.8.0 currently matches upstream v0.8.0. The first WebUI
  release is titled `.1`, tagged `v0.1.0`, and targets commit `5d9fd3a`.
  Deployment at commit `a0d82b4` passed all 28 tests and live browser inspection:
  Settings reported Agent `0.8.0` / latest `v0.8.0` and WebUI `.1+a0d82b4` /
  latest `.1`, correctly marking both up to date.
  New submissions are now echoed optimistically into the active dialogue before
  the API responds. While Prime runs, its bounded JSON event stream supplies a
  live assistant card with safe status/tool events, elapsed time, and draft answer
  text; private reasoning is never sent to the browser. The composer exposes
  **Message**, `/steer`, `/follow-up`, and `/stop`. WebUI tasks use Prime 0.8.0's
  documented persistent RPC mode rather than one-shot JSON mode, allowing the
  authenticated owner to send native `steer`, `follow_up`, and `abort` commands
  over the task's private stdin channel while events stream from stdout. Hidden
  reasoning and internal RPC bookkeeping are excluded from browser snapshots.
  Deployment commit `4a66709` passed all 30 tests and live browser validation:
  the prompt echoed before task-start completion; lifecycle/tool progress updated
  in the dialogue; `/steer` was queued during an in-flight IPython call; and Prime
  applied it at the next turn boundary, changing the requested two-sentence answer
  into the requested one-sentence final response. No alert or console attachment
  occurred.
- Static HTML is installed in `/var/www/prime-agent/`; JavaScript and CSS are in
  `/var/www/prime-agent/assets/`. The tracked installer preserves this mapping.
- vLLM: `0.27.1` ARM64/CUDA 12.9 image, two user services enabled at boot
- Hermes Agent and Hermes WebUI are no longer installed. The gateway, WebUI,
  runtime/data tree, launchers, legacy model units, SGLang image/directory,
  Hermes model/package caches, and identified Hermes-named project/setup paths
  were removed. Port 8787 is closed.

## Running Web interfaces

- Prime WebUI is the only browser interface reachable from the LAN/VPN, through
  private HTTPS on `172.16.253.231:8443`.
- NVIDIA DGX Dashboard is active on loopback-only `127.0.0.1:11000`; its root
  page identifies itself as `DGX Dashboard`.
- CUPS provides its standard printer-administration UI on loopback-only
  `127.0.0.1:631`.
- ttyd serves Prime's Advanced console on loopback-only `127.0.0.1:7681` and is
  exposed only as the authenticated `/terminal/` component of Prime WebUI, not
  as a separate LAN listener.
- Ports 8764/8765 and 30000/30001 are authentication/dashboard/model APIs rather
  than independent WebUIs. The remaining dynamic Python ports belong to Prime
  kernel workers, not browser interfaces.

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
- The root-only pre-v0052 WebUI recovery bundle is
  `/var/backups/prime-webui-v0052-20260825T153014-0500`.
- The root-only pre-v0060 routing/UI recovery bundle is
  `/var/backups/prime-routing-v0060-20260825T173500-0500`; it contains the prior
  API, UI, policy, installed web root, and checksums.
- The root-only pre-v0061 Usage UI recovery bundle is
  `/var/backups/prime-usage-v0061-20260825T174000-0500`; it preserves both the
  dashboard source and installed JavaScript/CSS with checksums.
- The root-only pre-v0062 deletion recovery bundle is
  `/var/backups/prime-delete-v0062-20260825T174100-0500`; it preserves the prior
  API and source/installed JavaScript with checksums.
- The root-only pre-v0063 sidebar recovery bundle is
  `/var/backups/prime-sidebar-v0063-20260825T174200-0500`; it preserves the prior
  source and installed HTML/JavaScript/CSS with checksums.
- The root-only pre-v0064 update-controls recovery bundle is
  `/var/backups/prime-updates-v0064-20260825T174800-0500`; it preserves prior
  source/installed UI and API files, WebUI clone commit, Prime version, and
  checksums.
- The root-only pre-v0065 conversation-ID recovery bundle is
  `/var/backups/prime-session-ids-v0065-20260825T175500-0500`; it preserves the
  prior APIs, deployed Git commit, and checksums.
- The root-only pre-v0066 user-migration recovery bundle is
  `/var/backups/prime-users-v0066-20260825T180700-0500`; it preserves the prior
  one-way credential, auth/API/UI, auth unit, Nginx, metadata-absence state,
  deployed Git commit, and checksums.
- The root-only pre-v0069 provider-workflow recovery bundle is
  `/var/backups/prime-providers-v0069-20260825T203000-0500`; it preserves the
  credential/provider/model configuration (including explicit absence), prior
  API/UI/unit, deployed Git head, and checksums without exposing their contents.
- The root-only pre-v0070 release-update recovery bundle is
  `/var/backups/prime-releases-v0070-20260825T204000-0500`; it preserves the
  prior API/UI/update scripts and units, deployed Git head, Prime version, and
  checksums without including credentials.
- The root-only pre-v0071 skill-inventory recovery bundle is
  `/var/backups/prime-skill-v0071-20260826T000000-0500`; it preserves the prior
  global Prime skill tree and a checksum manifest. The new skill is additive.
- The root-only pre-v0075 live-dialogue recovery bundle is
  `/var/backups/prime-live-dialogue-v0075-20260826T134500-0500`; it preserves the
  prior tracked and installed API/UI assets with checksums.
- The root-only pre-v0076 steering-fix recovery bundle is
  `/var/backups/prime-steering-v0076-20260826T135500-0500`; it preserves the
  initially deployed v0075 API/UI assets with checksums.
- The root-only pre-v0077 RPC-transport recovery bundle is
  `/var/backups/prime-rpc-v0077-20260826T140000-0500`; it preserves the deployed
  v0076 API/UI assets with checksums.

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
- Native WebUI Prime children may make outbound provider connections. The API
  listener remains loopback-only behind authenticated Nginx, but its former
  systemd loopback-only egress filter was removed because it prevented any cloud
  provider configured through Settings from functioning.
  This egress change was explicitly approved by the owner on 2026-08-25.
- Hermes is not installed. Historical framework analysis still describes it as
  an alternative gateway, but it has no current runtime role.
- When Nemotron is the selected default, native WebUI tasks with clear
  image/document, 3D/CAD/manufacturing, portfolio/trading, or deep-review signals
  route directly to Qwen. Explicit Qwen/Nemotron requests override the automatic
  choice; disabled Qwen falls back visibly, and manually selected non-Nemotron
  defaults are preserved. Mixed Nemotron tasks must actually invoke a Qwen child
  for specialist subtasks rather than merely claim delegation.

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
- After v0060 deployment, both model health endpoints, the dashboard service,
  authenticated HTTPS boundary, installed assets, and deterministic specialist
  routing passed. The Spark reported 41.1 GB available memory (31.5%).
- After the 81,920-token Nemotron warm-up and tests, Linux reported 39.1 GiB
  available memory (32.15%). The validation gate now requires at least 20% of
  usable RAM, about 24.3 GiB on this Spark.
- Both inference ports bind only to `127.0.0.1`.
- NVFP4 is the checkpoint format. Nemotron's published GB10 recipe uses W4A16
  Marlin rather than native FP4 tensor-core execution.

## Security posture

- Nginx is the only Prime browser listener available to the LAN, on the explicit
  private address and port 8443. Port 80 and the default site are disabled.
  ttyd, the dashboard API, and both inference engines bind only to
  loopback. SSH remains available on port 22.
- The existing Nginx private-source allow rules remain. Per owner direction, no
  host-level CIDR firewall policy was added; UFW remains inactive.
- An isolated loopback broker verifies the dedicated `dbyte` WebUI credential
  and issues secure sessions. The credential file is owner-only, rejects links
  and permissive modes, and uses scrypt with a random salt. Nginx delays/rate-
  limits failures. Fail2ban counts only actual 401
  responses from `POST /auth/login`, then reacts after 15 failures in 10 minutes
  with a one-hour nftables ban. Expired-session API polling is not counted.
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
- A private CA now signs the server certificate for the Spark IP, hostname, and
  loopback names. Clients must install `/prime-webui-ca.crt` once to trust it.
- Native tasks use independent process groups, four-task admission control,
  30-minute limits, explicit stop, structured logs, and an append-only usage
  ledger. Native chat, safe Markdown, file catalog/previews/retention, operations
  status, and expanded conversation management are live.
- All 19 pending Ubuntu security updates present on 2026-08-25 were installed.
- One transcript with two credential-shaped key occurrences was copied to the
  root-only recovery bundle and redacted. No matching strings remain in active or
  trashed sessions. The key must still be revoked at OpenAI if it remains active.
- Full controls, validation, residual risks, and recovery are in
  `wiki/SECURITY.md`.
- On 2026-08-25 an unreviewed change replaced the PAM broker with an obsolete
  dashboard server, added a password-acceptance bypass, changed the Prime PAM
  policy to include `nullok`, and recreated the obsolete Nginx PAM policy. The
  altered files are preserved in the root-only recovery directory
  `/var/backups/prime-auth-recovery-20260825T165500-0500`. The reviewed broker
  and PAM policy were restored, the obsolete policy was removed, and all audited
  WebUI, Nginx, systemd, and Fail2ban hashes matched this repository. PAM was
  subsequently retired from the WebUI in v0056.

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
  authenticate as `dbyte` with the dedicated WebUI password. Create or rotate it
  interactively as `dbyte` with `prime-web-password`. Install the downloadable
  Prime private CA on each client to eliminate the trust warning. No SSH tunnel
  is required.
- Run `~/prime-dgx-agent/validate.sh` before and after runtime changes.
- Detailed WebUI operation and rollback are in `wiki/PRIME_DASHBOARD.md`.
- Dashboard settings control the default model, thinking level, compaction reserve,
  recent-context retention, and enabled providers. A searchable switch list shows
  all configured/discovered providers and writes Prime's native `enabledModels`
  setting. Saves are allowlisted, origin/CSRF checked, atomic, and apply to new
  native tasks and advanced-console sessions.
- Entering Settings performs an admin-only release check for both Prime Agent
  and Prime WebUI. Installed and latest versions are displayed separately, and
  an available update produces a prominent notice. The two confirmed, serialized
  one-shot update services then install only the exact published release: the
  Agent updater maps the official GitHub tag to the matching npm version, while
  the WebUI updater resolves and fast-forwards to the private repository's release
  tag before validation and deployment. Unreleased `main` commits are not offered
  as updates. Owner-only atomic status records preserve results across service
  reloads/reboots. The Prime package updater remains installed but has not been
  executed during validation.
- The active header's effort selector overrides the default for the next message
  in that conversation. Task and conversation metadata expose model, effort,
  routing mode/reason, and model context for auditability.
- Usage combines tokens and recorded spend by provider/model in one table, with
  columns for the Spark's current local calendar day and a rolling 30-day window.
  Every configured provider is collapsed by default with rolled-up tokens/spend;
  expansion shows its model rows, and expansion state survives periodic refresh.
  Local Spark providers report $0 API spend. Native launches also append a task
  ledger so completion/elapsed/model/usage can be audited independently.
- Native conversation control uses Prime's supported JSON CLI, not ttyd URL
  arguments. Up to four process-group-isolated tasks run for at most 30 minutes;
  message polling, safe Markdown, explicit stop, parallel activity tabs, elapsed
  time, and redacted downloadable logs are active.
- Conversation search, rename, pin, archive/restore, duplicate/fork, export,
  recoverable deletion, and bulk archive/delete are available. Prime JSONL remains
  the transcript source of truth. Deletion permits Prime conversations that are
  idle and unattached, while actual active/streaming/compacting/queued/unfinished
  work remains protected. UI failures are reported rather than silently ignored.
  Storage operations resolve both the transcript filename ID and Prime's internal
  session ID; 9 of 30 files had differing values when this was deployed.
  Deployed validation resolved all 22 visible catalog rows, including all nine
  mismatches, without deleting user data; 18 applicable deployed tests passed.
- Files are streamed to private storage with 100 MiB/2 GiB limits, metadata,
  safe previews, explicit prompt selection, deletion, and a confirmed 1–365 day
  retention policy. Unsafe archive paths and links are rejected.
- Admin displays services, disk/upload/task status, guarded model/terminal
  restarts, retention, and the private-CA download.

## Known gaps

- A read-only comparative review found that the loopback dashboard API trusts
  Nginx-supplied identity/role headers without authenticating the proxy. A local
  process can forge them; a non-mutating live request with fabricated admin
  headers returned 200 from `/api/admin`.
- WebUI ownership metadata does not isolate the execution environment: native
  Prime tasks and the authenticated Advanced console run as shared Linux user
  `dbyte`, and the console is not restricted by WebUI role. Until process,
  storage, and credential isolation is implemented, WebUI users must be treated
  as mutually trusted. No remediation was made during the report-only review.

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
- The earlier positive PAM login and full browser session were verified before
  PAM was retired: authenticated
  page/token requests returned 200, ttyd accepted `/terminal/ws`, spawned `prime-dgx`, and
  the live browser exposed an active terminal input. No password was handled.
- The owner created the dedicated WebUI credential interactively. Its record is
  mode 0600 inside a mode-0700 directory, the broker reports it configured, and
  the owner's browser login returned 200. Validation never handled the password
  or inspected the one-way record contents.
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
  automated release promotion/rollback remain undefined.
