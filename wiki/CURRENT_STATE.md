# Current State

Last verified: 2026-08-23  
Wiki version: `v0020`

## Project summary

The Spark now runs Prime Agent as the local orchestration core with two
concurrently resident NVFP4 models. The operating policy covers 3D-print design,
portfolio evaluation, paper-trading research, and supporting code.

## Repository state

- Workspace: `/Users/byte/Documents/Codex/dgx-spark`
- Version control: Git `main`, private GitHub repository
  `https://github.com/dmbyte/dgx-spark`, tracking `origin/main`
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
  a default Conversations view plus Parameters, Tokens, and Spend tabs. A compact live
  monitor shows CPU/GPU/memory utilization, CPU/GPU/system temperature, and GPU
  board power. Its loopback-only API
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
- Frontier tier policy: GPT-5.6 Sol through the OpenAI Responses API for selected
  difficult work. This route is not live because no OpenAI API credential has
  been supplied; no credential is stored in the repository or wiki.
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
- Dashboard settings control the default local model, thinking level, compaction
  reserve, and recent-context retention. Saves are allowlisted, origin checked,
  atomic, and apply to new terminal sessions.
- Tokenomics sums Prime's recorded per-call input, output, cache, total-token, and
  cost fields for Today, 7 days, or All. API Spend is recorded cost by provider;
  local Spark providers correctly report $0 API spend.
- The Conversations view lists the 40 most recently modified Prime session files.
  Each row shows a sanitized, 96-character maximum topic derived from the first
  user message, then the timestamp of the latest chat, followed by model and opaque
  ID. It does not return full prompts, summaries, or assistant messages. New conversation
  reloads the embedded terminal; saved conversations
  are currently informational and cannot be resumed from the sidebar.

## Known gaps

- A potential OpenAI API credential was found in plaintext Prime session history
  during validation. It is not reproduced in the repository or wiki and is not
  exposed by the dashboard. The credential must be revoked/rotated; removal or
  redaction of the sensitive session remains pending explicit user direction.
- Browser-controlled session resumption is deferred. ttyd URL arguments were
  rejected because they would allow URL-controlled process arguments; a future
  implementation needs a narrowly validated server-side session selector.

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
