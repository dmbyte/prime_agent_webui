# Wiki and Project Change Log

Entries are newest first. Each material entry links to an immutable state
snapshot. Use ISO dates and describe outcomes, validation, and rollback impact.

## 2026-08-24 — v0032 — Add read-only live task console

- Added a per-task option that attaches the overlay to the actual running Prime
  console, with a control to return to the sanitized event feed.
- Made the overlay console read-only and lazy-loaded only for the selected task;
  the primary terminal remains interactive and ttyd's two-client cap is respected.
- Constrained browser attach requests to strict, existing session IDs; arbitrary
  browser-supplied arguments continue to be discarded.
- Validation: valid/invalid launcher tests and a live attach/return browser check
  passed; the final read-only assets are deployed and full Spark validation passes.
- Rollback: restore v0031 launcher/dashboard assets and remove `live-console.css`.
- Snapshot: [v0032](versions/v0032.md)

## 2026-08-24 — v0031 — Add background activity overlay

- Added an activity icon with active-task count and a floating overlay that is
  draggable, resizable, minimizable, and reopenable.
- Added one tab per parallel working Prime task and a three-second privacy-safe
  event feed for status, model, tools, token progress, and timestamps.
- Excluded prompts, assistant/tool output, thinking text, and secrets from the API.
- Validation: live API returned one task with 14 sanitized events; browser opened
  one tab and minimized the window successfully; full Spark validation passed.
- Rollback: restore v0030 API/HTML/JavaScript and remove `activity.css`.
- Snapshot: [v0031](versions/v0031.md)

## 2026-08-24 — v0030 — Group configured Usage models by provider

- Filtered Usage to the configured/authenticated catalog; historical activity for
  removed models no longer creates a row by itself.
- Added collapsed provider roll-ups for multi-model providers and expandable
  per-model detail; single-model providers stay as direct rows.
- Validation: live browser showed `openai-codex · 13 models` collapsed with its
  rolled-up values, hid GPT-5.6 Sol until expansion, and retained direct OpenAI,
  Nemotron, and Qwen rows.
- Rollback: restore v0029 dashboard HTML, JavaScript, and `usage.css`.
- Snapshot: [v0030](versions/v0030.md)

## 2026-08-24 — v0029 — Automatically discover Usage models

- Replaced manual Usage catalog maintenance with Prime's authenticated live model
  discovery, cached for 60 seconds and combined with configured/recorded models.
- After ChatGPT `/login`, discovered 13 `openai-codex` models and 16 total models,
  including GPT-5.6 Sol, direct OpenAI GPT-5.4, Nemotron, and Qwen.
- Fixed Prime emitting its model table on stderr by parsing both captured streams.
- Validation: API reported all four provider families; the live browser rendered
  representative models from each; both Spark model gates remain healthy.
- Rollback: restore v0028 dashboard API.
- Snapshot: [v0029](versions/v0029.md)

## 2026-08-23 — v0028 — Configure OpenAI GPT-5.4 route

- Loaded the user-supplied rotated key into `prime-web.service` through a mode-0600
  environment file outside the repository and enabled `openai/gpt-5.4` in Prime.
- Added GPT-5.4 to Parameters and corrected the Usage catalog/status.
- Validation: service process received the credential variable name, Prime settings
  enabled GPT-5.4, API/UI marked it configured, and OpenAI accepted authentication
  far enough to return `no credits remaining`. Both Spark model gates still pass.
- Blocker: add OpenAI API billing credits before the route can generate responses.
- Rollback: remove the service EnvironmentFile line, remove GPT-5.4 from enabled
  models, restore v0027 dashboard files, and restart services. Preserve/delete the
  credential file only according to the user's credential-retention decision.
- Snapshot: [v0028](versions/v0028.md)

## 2026-08-23 — v0027 — Correct OpenAI API model mapping

- Verified from installed Prime 0.8.0 code that API-key auth uses provider
  `openai`, `OPENAI_API_KEY`, and default model `gpt-5.4`.
- Verified `gpt-5.6-sol` belongs to Prime's separate `openai-codex`/ChatGPT route,
  so the current dashboard placeholder must not be treated as API-key readiness.
- No credential or runtime configuration changed.
- Snapshot: [v0027](versions/v0027.md)

## 2026-08-23 — v0026 — Show zero-usage models and re-audit OpenAI

- Changed Usage to union configured/intended models with recorded activity, so
  Nemotron, Qwen, and planned OpenAI GPT-5.6 Sol rows are always visible.
- OpenAI is labeled `not configured`; Qwen is configured and shows zero usage.
- Secret-safe audit found empty Prime auth storage, no OpenAI provider, and no
  OpenAI-style key outside conversation history despite Prime's earlier claim.
- Validation: all three rows rendered; four zero-token cells appeared for the two
  unused models; both local models and the full Spark gate passed.
- Rollback: restore v0025 dashboard API and JavaScript.
- Snapshot: [v0026](versions/v0026.md)

## 2026-08-23 — v0025 — Explain missing Usage models

- Verified that Usage is activity-driven rather than a configured-model catalog.
- Found 214 recorded Nemotron calls and no recorded Qwen calls; Qwen remains
  enabled and its inference service is active.
- Verified OpenAI is not configured as a Prime provider and no OpenAI credential
  is present in the service environment.
- No runtime or interface configuration changed.
- Snapshot: [v0025](versions/v0025.md)

## 2026-08-23 — v0024 — Reorder system monitor metrics

- Moved Power to the fourth position on the utilization row and grouped CPU,
  GPU, and System temperature together on the second row.
- Validation: JavaScript syntax passed and the live browser reported the exact
  requested metric order.
- Rollback: restore the v0023 dashboard JavaScript.
- Snapshot: [v0024](versions/v0024.md)

## 2026-08-23 — v0023 — Combine tokens and spend by model

- Replaced separate Tokens and Spend tabs with one Usage screen grouped by exact
  provider/model pair.
- Added side-by-side token and recorded-spend values for local-calendar Today and
  a rolling Last 30 days window.
- Validation: API returned the expected periods/model grouping; the live browser
  showed Model, Today, and Last 30 days with tokens and spend on each row. Full
  Spark validation passed.
- Rollback: restore v0022 dashboard API, HTML, and JavaScript; remove `usage.css`.
- Snapshot: [v0023](versions/v0023.md)

## 2026-08-23 — v0022 — Add click-to-resume conversations

- Made conversation rows interactive: selecting one resumes its existing Prime
  conversation in the embedded terminal.
- Added `prime-web-launch`, which forwards only `--resume` plus a strictly valid
  ID backed by an existing session file; all other browser arguments are ignored.
- Validation: valid resume and arbitrary-argument rejection tests passed; live
  browser click returned an active terminal without emitting conversation content.
  Services, private bindings, both models, and the full validation gate passed.
- Rollback: restore v0021 ttyd unit/dashboard JavaScript and remove the web launcher.
- Snapshot: [v0022](versions/v0022.md)

## 2026-08-23 — v0021 — Rename GitHub repository

- Renamed the private repository from `dmbyte/dgx-spark` to
  `dmbyte/prime_agent_webui` and updated local `origin` for fetch and push.
- Validation: GitHub reports the new name, private visibility, and `main` default;
  local remote URLs match the renamed repository.
- Rollback: rename the repository back and update `origin` only on request.
- Snapshot: [v0021](versions/v0021.md)

## 2026-08-23 — v0020 — Publish private GitHub backup

- Initialized Git on `main`, committed the complete reviewable source/wiki, and
  created private repository `dmbyte/dgx-spark`.
- Pushed `main` and configured it to track `origin/main`.
- Validation: GitHub accepted the push and returned the private repository URL.
- Rollback: delete the GitHub repository only with explicit user confirmation;
  local history remains independently recoverable.
- Snapshot: [v0020](versions/v0020.md)

## 2026-08-23 — v0019 — Prepare private GitHub repository

- Added repository exclusions for caches, environment files, logs, certificates,
  and private keys, and prepared the complete deployment source and wiki for Git.
- Validation: a credential-pattern scan found no matching repository files.
- GitHub CLI is installed but not authenticated; remote creation/push remains
  pending interactive account sign-in.
- Rollback: remove Git metadata and `.gitignore` only if abandoning version control.
- Snapshot: [v0019](versions/v0019.md)

## 2026-08-23 — v0018 — Show conversation topic and last-chat time

- Added a first-line topic derived from the first user message and moved the
  latest message date/time to the second line of every conversation row.
- Added 96-character limits, credential-pattern fallback, and text-only DOM
  rendering after explicit approval for authenticated LAN/VPN topic visibility.
- Validation: all 40 returned rows had topics and last-chat timestamps; maximum
  topic length was 96; browser ordering passed without emitting topic text during
  verification. Both model and private-access gates passed.
- Rollback: restore the v0017 dashboard API and JavaScript.
- Snapshot: [v0018](versions/v0018.md)

## 2026-08-23 — v0017 — Rename sessions as conversations

- Renamed the default sidebar tab from Sessions to Conversations and the action
  from New Session to New conversation; internal Prime storage remains session-based.
- Validation: JavaScript syntax passed and the updated assets were installed.
- Rollback: restore the v0016 HTML and JavaScript assets.
- Snapshot: [v0017](versions/v0017.md)

## 2026-08-23 — v0016 — Add session-first sidebar and Spark monitor

- Made Sessions the default sidebar view, added a New Session control, and
  exposed only timestamp/model/opaque-ID/size metadata for the 40 latest files.
- Added two-second CPU/GPU/memory, temperature, and GPU-board-power telemetry.
- Deferred saved-session resume after rejecting ttyd URL arguments as an
  unnecessary browser-controlled process-argument surface.
- Validation: 36 metadata-only session rows parsed; the live browser showed the
  default Sessions view, New Session, seven current metrics, and active terminal.
  Both models, services, private bindings, and the full validation gate passed.
- Security follow-up: a potential API credential exists in plaintext session
  history; it was not copied into the dashboard/wiki and must be revoked/rotated.
- Rollback: restore v0015 dashboard assets/API and restart the dashboard API.
- Snapshot: [v0016](versions/v0016.md)

## 2026-08-23 — v0015 — Add Prime dashboard sidebar

- Replaced the terminal-only page with an authenticated responsive dashboard
  containing the embedded terminal and Parameters, Tokenomics, and API Spend tabs.
- Added a loopback-only hardened API that atomically updates allowlisted Prime
  defaults and aggregates recorded token/cost usage by provider and period.
- Validation: 34 session files and 182 calls parsed; the live browser showed
  5.4M recorded tokens, $0 local spend, exact 8,192/12,000 settings, all sidebar
  tabs, and an active terminal. API/settings, services, bindings, and gate passed.
- Rollback: disable the dashboard API and restore the v0014 Nginx/ttyd files.
- Snapshot: [v0015](versions/v0015.md)

## 2026-08-23 — v0014 — Repair reverse-proxied WebSocket

- Diagnosed the reconnect loop as ttyd rejecting the valid external HTTPS origin
  because it compared it with the internal loopback reverse-proxy host.
- Moved strict approved-origin enforcement to Nginx's `/ws` location and removed
  ttyd's proxy-incompatible `--check-origin` flag; the backend remains loopback-only.
- Validation: PAM-authenticated page/token requests returned 200, ttyd accepted
  the WebSocket and spawned Prime, and a controlled live-browser check found an
  active terminal input. The complete infrastructure gate also passed.
- Rollback: restore the v0013 unit/site, which restores the reconnect defect; a
  safer functional rollback is to return to the SSH-tunneled v0008 design.
- Snapshot: [v0014](versions/v0014.md)

## 2026-08-23 — v0013 — Enable Nginx PAM account retrieval

- After explicit informed approval, added `www-data` to supplementary group
  `shadow` so Ubuntu PAM can validate `dbyte` for the web interface.
- Restarted Nginx and verified its workers inherited GIDs 33 and 42.
- Validation: the unauthenticated 401 challenge, Nginx syntax, both models,
  private bindings, browser health, and memory floor passed. Positive login
  awaits the user's password-only interactive retry.
- Security consequence: an Nginx compromise can read password hashes. Rollback
  removes `www-data` from `shadow` and restarts Nginx, breaking this PAM method.
- Snapshot: [v0013](versions/v0013.md)

## 2026-08-23 — v0012 — Diagnose repeated PAM prompts

- Confirmed submitted browser credentials receive another 401 because PAM cannot
  retrieve authentication information for `dbyte` from the `www-data` worker.
- Correlated Nginx, PAM, and `unix_chkpwd` logs; this is a server privilege issue,
  not browser credential caching. No password was requested or recorded.
- Did not add Nginx to the sensitive `shadow` group without explicit approval.
  Safer alternatives are client certificates or identity-provider authentication.
- Rollback: none; this was read-only diagnosis and documentation.
- Snapshot: [v0012](versions/v0012.md)

## 2026-08-23 — v0011 — Enable private LAN/VPN browser access

- Published the PAM/TLS Nginx endpoint on the Spark's LAN address and allowed
  loopback, RFC1918, and 100.64.0.0/10 sources while denying all others.
- Kept ttyd and both model APIs loopback-only; added no public tunnel or router
  forwarding and removed the obsolete client SSH tunnel.
- Rotated the certificate for the LAN IP and preserved the v0009 certificate/key
  in a root-only archive.
- Validation: Nginx syntax, Spark-local and direct Mac LAN 401 challenges,
  services, model health, binding policy, and memory floor passed.
- Rollback: restore the v0009 Nginx site and archived certificate.
- Snapshot: [v0011](versions/v0011.md)

## 2026-08-23 — v0010 — Assess public browser exposure

- Verified the Spark is behind NAT on `172.16.253.231/24`, with observed public
  address `47.187.248.92`; no secure tunnel client is installed and UFW is off.
- Did not expose Prime publicly: host binding alone cannot cross NAT, and direct
  forwarding of a command-capable PAM endpoint would create excessive password-
  attack risk.
- Selected a trusted HTTPS identity-aware tunnel, preferably Cloudflare Access,
  as the safe next step; hostname/account authorization is still required.
- Rollback: none; no operational configuration changed.
- Snapshot: [v0010](versions/v0010.md)

## 2026-08-23 — v0009 — Add PAM authentication and TLS

- Installed Ubuntu's Nginx PAM module and placed a dedicated PAM-authenticated
  HTTPS proxy on loopback port 8443 in front of ttyd.
- Kept both layers SSH-tunnel-only, left Nginx outside the `shadow` group, and
  replaced the old client tunnel that bypassed PAM.
- Validation: Nginx syntax, active services, loopback bindings, HTTP 401 without
  credentials, both model checks, and the memory floor passed. Positive PAM
  authentication awaits user confirmation; no password was handled.
- Rollback: remove the Nginx site/PAM policy and restore v0008 tunnel access.
- Snapshot: [v0009](versions/v0009.md)

## 2026-08-23 — v0008 — Add private Prime browser access

- Installed ttyd 1.7.4 and added an enabled user service that launches
  `prime-dgx` on loopback port 7681 with origin checking and a two-client cap.
- Disabled Ubuntu's generic system ttyd service; no browser terminal is exposed
  directly to the LAN. Access uses the existing SSH key through port forwarding.
- Started the client-side SSH tunnel so the URL works immediately.
- Validation: remote and tunneled-local HTTP 200, enabled/active service,
  loopback binding, both model health checks, and the 20 GiB memory floor passed.
- Rollback: disable and stop `prime-web.service`; model and terminal access are
  unaffected.
- Snapshot: [v0008](versions/v0008.md)

## 2026-08-23 — v0007 — Commission Prime and dual-model inference

- Installed and pinned Prime Agent 0.8.0 with Nemotron as the default and exact
  Qwen specialist routing; installed the project policy and acceptance gate.
- Rebudgeted Nemotron to a 12 GiB KV cache and added Qwen3.6 NVFP4 with an 8 GiB
  KV cache. Both 65K-context vLLM services are boot-enabled and loopback-only.
- Validation: both direct text tests, Qwen image input, both Prime provider
  routes, the default Prime route, service state, private binding, and the 20 GiB
  memory gate passed. About 38 GiB remained available after warm-up.
- OpenAI escalation remains deliberately inactive pending a securely supplied
  API credential. No live trading authority or broker integration was added.
- Rollback: use the protected v0006 baseline and `PRIME_DEPLOYMENT.md`.
- Snapshot: [v0007](versions/v0007.md)

## 2026-08-23 — v0006 — Capture pre-change DGX Spark baseline

- Performed a read-only inventory of hardware, firmware, OS, storage, network,
  firewall, services, packages, containers, models, and application revisions.
- Discovered an existing optimized Nemotron 3.5 + DSpark vLLM deployment and an
  older Hermes/WebUI deployment; recorded exact runtime and model settings.
- Created a root-only configuration recovery artifact under `/var/backups` with
  package/runtime manifests and protected Hermes/vLLM/system configuration.
- Validation: every checksum passed; vLLM responded correctly; existing services
  remained running. Hermes WebUI was active but returned an empty direct HTTP
  response, so it is not recorded as application-healthy.
- Rollback: no operational configuration changed. Remove only the new baseline
  directory if explicitly desired; doing so discards recovery evidence.
- Snapshot: [v0006](versions/v0006.md)

## 2026-08-23 — v0005 — Select Prime as long-run capability core

- Corrected the framework choice after clarifying that long-run capability and
  controlled continual improvement matter more than out-of-box integrations.
- Selected Prime Agent as the core; retained Hermes as an optional messaging
  gateway rather than the brain or authority boundary.
- Added promotion gates for continual harness changes: traceable motivation,
  small reversible diffs, frozen evaluations, no permission expansion, and wiki
  history.
- Kept the v0004 model tiers and domain/trading safeguards unchanged.
- Validation: reconciled the decision with current Prime and Hermes architecture
  documentation reviewed for v0003/v0004. No runtime comparison has been run.
- Rollback: supersede ADR-0005 and return Hermes to the core role in a new version.
- Snapshot: [v0005](versions/v0005.md)

## 2026-08-23 — v0004 — Reframe as multimodal personal agent

- Replaced the coding-only Qwen specialist with NVIDIA Qwen3.6-35B-A3B-NVFP4
  for multimodal, spatial, finance, and still-capable coding work.
- Replaced Prime Agent with Hermes Agent because the clarified workload emphasizes
  personal memory, schedules, profiles, messaging, and domain tools.
- Added GPT-5.6 Sol through the OpenAI Responses API as a gated frontier tier.
- Defined CAD validation, timestamped portfolio evidence, paper trading, a
  deterministic risk gateway, human approval, and credential separation.
- Validation: checked Qwen/NVIDIA/vLLM, Hermes, and official OpenAI documentation.
  No runtime, CAD, market-data, or broker integration has been tested.
- Rollback: supersede ADR-0004 and restore v0003 recommendations in a new version.
- Snapshot: [v0004](versions/v0004.md)

## 2026-08-23 — v0003 — Select Prime Agent as prototype scaffold

- Compared Prime Agent and Hermes Agent for the routed local Nemotron/Qwen stack.
- Selected Prime Agent for prototype coding/research orchestration because it
  supports exact per-child model selection, local vLLM providers, persistent
  long tasks, and a reversible continual harness.
- Retained Hermes as the preferred alternative for omnichannel personal-assistant
  and scheduled-automation requirements.
- Validation: checked both projects' current repositories and documentation for
  local endpoints, multi-model behavior, persistence, learning, and security
  boundaries. No local framework benchmark has been run.
- Rollback: supersede ADR-0003 and return the framework choice to evaluation;
  no agent runtime has been installed.
- Snapshot: [v0003](versions/v0003.md)

## 2026-08-23 — v0002 — Recommend two-model DGX Spark agent stack

- Selected Nemotron 3.5 Lightning NVFP4 + DSpark as the fast orchestrator and
  Qwen3-Coder-Next GB10 NVFP4 as the coding/verification specialist.
- Selected two separately budgeted vLLM servers behind a deterministic router.
- Documented the GB10 W4A16/Marlin precision nuance, conservative unified-memory
  envelope, context caps, routing policy, risks, alternatives, and acceptance
  gates.
- Validation: cross-checked NVIDIA hardware and Nemotron documentation, Qwen's
  official model card, the candidate quantization card, and NVIDIA vLLM notes.
  No hardware benchmark has yet been run in this workspace.
- Rollback: supersede ADR-0002 and return architecture status to undecided; no
  runtime implementation exists to remove.
- Snapshot: [v0002](versions/v0002.md)

## 2026-08-23 — v0001 — Initialize durable project wiki

- Added the wiki structure, maintenance rules, current-state page, decision log,
  and immutable version snapshots.
- Recorded the workspace as empty of application implementation and not yet under
  Git version control.
- Validation: inspected the workspace contents and version-control status.
- Rollback: remove the files introduced by this version; no application state is
  affected.
- Snapshot: [v0001](versions/v0001.md)
