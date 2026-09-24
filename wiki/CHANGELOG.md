# Wiki and Project Change Log

Entries are newest first. Each material entry links to an immutable state
snapshot. Use ISO dates and describe outcomes, validation, and rollback impact.

## 2026-09-24 — v0175 — Preserve rotated Codex credentials and reliable fallback

- Traced the task 502 to OpenAI's `refresh_token_reused` response; both remaining
  copied credentials were expired while local Nemotron and Qwen were healthy.
- Prevented updates from overwriting a newer gateway credential with an older
  host copy by comparing OAuth expiry values before synchronization.
- Added sanitized actionable Codex sign-in errors to task output and journald.
- Made explicit slash-model directives override conflicting model names later
  in the prompt, then restarted the preserved failed request on Qwen.
- All 121 dashboard tests and release validation pass.
- Decision: [ADR-0103](decisions/0103-preserve-gateway-oauth-rotation.md).
- Snapshot: [v0175](versions/v0175.md)

## 2026-09-24 — v0174 — Recover protected chat access after abrupt shutdown

- Confirmed the power failure preserved all conversation files and the durable
  authenticated browser session.
- Found an interrupted-task ACL mask of `---` on the protected agent directory;
  repaired it and restored 40 owner-visible chats plus 2 projects in the API.
- Added a broker pre-start recovery helper that restores traversal, conversation,
  project-source, skill, trash, and task-workspace ACLs before accepting tasks.
- Published the repair as v0.5.39 and aligned the documented install version.
- All 119 dashboard tests pass.
- Decision: [ADR-0102](decisions/0102-recover-task-acls-at-broker-start.md).
- Snapshot: [v0174](versions/v0174.md)

## 2026-09-23 — v0173 — Fix false task-broker exits

- A real repaired-kernel canary spawned exact-model Qwen and successfully used
  `agent_message.send`, then reproduced a false broker failure at teardown.
- Replaced buffered stdin reads in the daemon forwarding thread with unbuffered
  file-descriptor reads, eliminating the fatal interpreter-finalization lock.
- Made legacy workspace copies migration-only so updates preserve current data.
- The deployed shutdown canary acknowledged state/abort, cleaned its sandbox,
  and produced no fatal or broker-exit event.
- Decision: [ADR-0101](decisions/0101-use-unbuffered-runner-control-input.md).
- Snapshot: [v0173](versions/v0173.md)

## 2026-09-23 — v0172 — Install Prime's bundled kernel skills

- A real v0.5.36 canary found `agent_message` exposed only as an unavailable
  placeholder because the custom kernel omitted Prime's own skill packages.
- Installed and import-verified all eleven bundled Python-backed skills in the
  immutable kernel and rebuilt all six OpenShell images.
- Decision: [ADR-0100](decisions/0100-install-bundled-skills-in-immutable-kernel.md).
- Snapshot: [v0172](versions/v0172.md)

## 2026-09-23 — v0171 — Align Prime task runtime and Qwen delegation

- Found that WebUI tasks still ran Prime 0.8.0 after the host had advanced to
  0.9.5, while the live managed policy still named removed Qwen 3.6.
- Rebuilt and pinned all six OpenShell images with Prime 0.9.5 and corrected
  the policy to use exact-model `rlm.spawn` plus kernel-only agent messaging.
- Made install/update refresh older managed policies with a timestamped backup
  without overwriting unrelated custom `AGENTS.md` files.
- All 118 dashboard tests and release validation pass.
- Decision: [ADR-0099](decisions/0099-align-prime-host-and-openshell-runtimes.md).
- Snapshot: [v0171](versions/v0171.md)

## 2026-09-23 — v0170 — Expand Qwen to 98K with Q4 KV

- Expanded Qwen's single context slot from 32,768 to 98,304 tokens and changed
  K/V cache from Q8 to Q4; Prime now advertises the matching limit.
- Rebalanced Nemotron to 65,536 context, a 2 GiB FP8 KV reserve, and a 0.35
  startup memory ceiling while retaining two sequences and three draft tokens.
- Passed exact 32K and 78K Qwen prompts plus a 77,034-token long-range recall
  test. Warm short-context decode reached 44.76 model-eval token/s and 78K
  decode measured 29.56 token/s.
- Both engines remained healthy in the stressed state with 15.44% available
  memory. The 2 GiB Nemotron cache supports 275,587 tokens / 4.21 full contexts.
- Decision: [ADR-0098](decisions/0098-use-q4-kv-for-qwen-98k-context.md).
- Snapshot: [v0170](versions/v0170.md)

## 2026-09-22 — v0169 — Activate OpenShell images during WebUI updates

- Published and deployed v0.5.33 with all six exact image IDs.
- A final genuine Prime task using the installed release became browser-ready
  in 0.46 seconds, navigated read-only to the BMC with HTTP 200, and completed.
- Found that the in-app WebUI updater refreshed code but not immutable images;
  changed it to run the reviewed identity-verifying OpenShell installer before
  reporting update success on OpenShell hosts.
- Published and deployed v0.5.34. A live already-current updater run rebuilt
  and matched all six pinned images; all WebUI/OpenShell services are active
  and diagnostic sandboxes/candidate artifacts were removed.
- Snapshot: [v0169](versions/v0169.md)

## 2026-09-22 — v0168 — Repair Chromium policy and isolate its broker

- Proved Chromium's crashpad/NSS failure came from creation-time OpenShell
  denial of random devices and shared memory; direct container execution was
  healthy, and a fresh corrected sandbox passed NSS initialization.
- Added the required device grants to every generated task policy and moved
  browser workers behind a private pre-Prime Unix-socket broker that inherits
  the approved recipe egress bridge.
- A genuine WebUI API task opened three browser sessions in 0.46–0.48 seconds;
  its read-only BMC navigation returned HTTP 200 and the task completed.
- Pinned exact normalized IDs for all six v0.5.33 ARM64 OpenShell images.
- Decision: [ADR-0097](decisions/0097-start-browser-broker-before-prime.md).
- Snapshot: [v0168](versions/v0168.md)

## 2026-09-22 — v0167 — Deploy and verify the BMC browser fix

- The v0.5.29 activation gate rejected a manifest built with one extra skill
  directory before installing any image. Rebuilt from the installer's exact
  context and published superseding v0.5.30 at `ea2a323`.
- Deployed v0.5.30; all six installed images match, and WebUI/OpenShell services
  are active.
- A genuine Prime task on the final installed network image completed browser
  enter, page creation, and close in 21.8 seconds. No BMC was contacted.
- Removed all diagnostic sandboxes, candidate tags, profiler files, temporary
  manifests, and build trees.
- Snapshot: [v0167](versions/v0167.md)

## 2026-09-22 — v0166 — Fix Prime browser page creation

- Reworked `BMCBrowser` 1.1.0 so Playwright/Chromium run in a clean worker
  subprocess behind the existing async API, with bounded requests, captured
  diagnostics, and forced cleanup on timeout.
- A genuine Prime task using the candidate completed browser enter, page
  creation, and close in 11.8 seconds where the old adapter timed out.
- Rebuilt and pinned all six deterministic OpenShell image IDs. All 113
  dashboard tests, four managed-skill tests, and release validation pass.
- Decision: [ADR-0096](decisions/0096-isolate-playwright-from-prime-kernel.md).
- Snapshot: [v0166](versions/v0166.md)

## 2026-09-22 — v0165 — Prove OpenShell browser path works outside Prime kernel

- Created an ephemeral sandbox via the same approved OpenShell create/exec
  path, image, volumes, and task-style limits used by Prime. `BMCBrowser`
  launched and created its page successfully; the sandbox and policy were
  removed afterward.
- This separates the repeated `newPage` timeout from Chromium packaging and
  OpenShell enforcement. The remaining fault boundary is Prime's persistent
  IPython kernel / Playwright interaction; no corrective release is deployed.
- Snapshot: [v0165](versions/v0165.md)

## 2026-09-22 — v0164 — Confirm new-page timeout from a clean conversation

- A clean Qwen conversation reached `ipython`; the DEBUG-enabled, bounded
  browser probe still timed out at Playwright `BrowserContext.new_page()`.
- No BMC navigation occurred. Playwright's browser debug stream did not reach
  the task or Docker logs, limiting process-level attribution.
- Next engineering test: reproduce through OpenShell's own exec path or run
  browser automation in an isolated subprocess outside Prime's live kernel.
- Snapshot: [v0164](versions/v0164.md)

## 2026-09-22 — v0163 — Separate context rejection from browser timeout

- The Playwright DEBUG repeat failed before tool execution: Qwen received
  38,379 tokens from the resumed conversation, exceeding its 32,768-token
  context limit. No new browser evidence was produced.
- The next diagnostic run should use a new conversation to fit the context
  budget; the earlier `newPage` timeout remains the active browser finding.
- Snapshot: [v0163](versions/v0163.md)

## 2026-09-22 — v0162 — Pinpoint browser probe timeout

- A new Prime task used direct top-level `await` with a 15-second bound, did not
  navigate to the BMC, and still timed out in Playwright's
  `BrowserContext.new_page()` after browser/context creation succeeded.
- This rules out nested `asyncio.run()` as the sole cause; no crash, OOM, or
  policy denial was logged. A Playwright DEBUG-enabled repeat is the next
  discriminating test.
- Snapshot: [v0162](versions/v0162.md)

## 2026-09-22 — v0161 — Isolate the live Prime browser hang

- Compared three stalled browser attempts: each stopped at the `ipython`
  browser context entry rather than BMC navigation. The current Playwright
  driver exists without a Chromium child.
- Captured the hung kernel stack waiting in nested `asyncio.run()` and ruled
  out the immutable image, browser package, and basic OpenShell policy with
  successful in-sandbox standalone, forked-process, and fresh-IPython launches.
- A bounded top-level-`await` probe in a fresh Prime task remains necessary
  before attributing the fault specifically to event-loop nesting.
- Snapshot: [v0161](versions/v0161.md)

## 2026-09-22 — v0160 — Show complete live task output

- Diagnosed a task that reached `ipython` and then stopped emitting output; the
  “Starting Prime” screen was a stale UI indication, not its actual stage.
- Persisted every sanitized runtime line immediately, added owner-scoped live
  chunk reads and a complete download, and exposed both through the trace's
  right-click/visible output control.
- Added OpenShell startup stages, silence duration, duplicate-event
  coalescing, and a transcript-error fallback that retains the prompt and trace.
- Published and deployed v0.5.28 at `561af55` after the existing task reached
  its 30-minute timeout; all 113 dashboard and four managed-skill tests passed.
  Verified API/UI/runner file identity, active services, owner-scoped access,
  and retrieval of the retained task log.
- Decision: [ADR-0095](decisions/0095-retain-complete-safe-live-task-output.md).
- Snapshot: [v0160](versions/v0160.md)

## 2026-09-20 — v0159 — Make the BMC browser work in enforced OpenShell

- Reproduced the reported crashpad failure inside a policy-enforced OpenShell
  sandbox; ordinary Docker had hidden the read-only-home constraint.
- Added private ephemeral Chromium HOME/config/cache state below writable
  `/tmp` with cleanup on successful or failed browser exit.
- Disabled unnecessary GPU and zygote subprocesses after real-sandbox tests
  showed OpenShell correctly blocked them.
- Verified the final skill through its public `BMCBrowser` interface inside an
  actual network-operations sandbox using production mounts and policy.
- A v0.5.26 activation check caught checkout ACL modes entering Docker image
  identity; v0.5.27 normalizes all temporary context modes and supersedes it.
- Published and deployed v0.5.27 at `b43ecc6`; all 113 tests passed, all six
  installed image IDs match, and the final OpenShell browser test succeeded.
- Decision: [ADR-0094](decisions/0094-run-headless-chromium-within-openshell-process-limits.md).
- Snapshot: [v0159](versions/v0159.md)

## 2026-09-20 — v0158 — Keep managed skills lazy and make them kernel-runnable

- Embedded the three reviewed managed Python adapters in the immutable Prime
  kernel used by all six OpenShell profiles.
- Kept instruction discovery lazy through compact routing metadata and delayed
  full `SKILL.md` reads until selection.
- Confined Playwright to `network-operations` and changed the browser adapter to
  import it only when a browser context opens.
- Re-pinned the six reproducible image IDs. Imports passed in every candidate;
  the network image also launched the system Chromium successfully.
- A v0.5.24 activation check caught generated bytecode entering the image
  context; v0.5.25 excludes it before normalization and supersedes that release.
- Published and deployed v0.5.25 at `e38e7ba`; all 113 release tests passed.
  Verified exact live image IDs, Prime's own managed-module kernel check,
  network-only Playwright, a real Chromium launch, active services, and HTTPS.
- Decision: [ADR-0093](decisions/0093-embed-lazy-managed-skills-in-prime-kernel.md).
- Snapshot: [v0158](versions/v0158.md)

## 2026-09-20 — v0157 — Install the NVIDIA catalog and working BMC skills

- Pinned and installed all 366 official NVIDIA skills as a protected global,
  lazy-loaded catalog rather than adding every description to every prompt.
- Converted the Prime-created headless browser and IPMI/Redfish helpers into
  working Prime Python skill packages with runtime-only credentials and explicit
  confirmation gates for power mutations.
- Added an atomic, recoverable installer and made the BMC packages part of the
  normal OpenShell installation path.
- Published and deployed v0.5.23 at `9752e2d`; all 112 release tests passed.
- Verified zero Prime loader diagnostics, catalog search and read, Python
  imports, real system-Chromium launch, active services, and healthy HTTPS.
- Removed the last live workspace Qwen 3.6 routing instruction in favor of
  Qwen 3.8 Flash-Next.
- Decision: [ADR-0092](decisions/0092-use-a-lazy-pinned-nvidia-skill-catalog.md).
- Snapshot: [v0157](versions/v0157.md)

## 2026-09-20 — v0156 — Govern user-requested skills and administrator-managed tools

- Added user skill requests with source, permission, dependency, and scope data.
- Added administrator approval, denial, enable/disable, recoverable removal,
  profile-tool inventory, and system-image escalation states.
- Added reviewed project skill selection and project-context integration.
- Preserved non-root OpenShell execution: approval runs no package manager and
  installs no operating-system package in a task.
- Published and deployed v0.5.21, then published and deployed superseding
  v0.5.22 with administrator source-archive download before approval. Validation
  passed with 109 tests; services are active and installed/latest versions match.
- Decision: [ADR-0091](decisions/0091-govern-skills-through-scoped-requests.md).
- Snapshot: [v0156](versions/v0156.md)

## 2026-09-18 — v0155 — Deploy and verify the skill/tool repair

- Published and deployed v0.5.20.
- Verified persistent skill migration/linking, package managers and persistent
  paths, Chromium/ipmitool, exact release tag, services, gateway, and HTTPS.
- The general validator stopped only at the existing 15% free-memory gate with
  both models resident; targeted runtime checks passed.
- Snapshot: [v0155](versions/v0155.md)

## 2026-09-18 — v0154 — Verify protected volume paths through runner boundary

- Corrected the volume provisioner's existence check for mode-0700
  prime-runner gateway paths to use sudo without broadening ACLs.
- Prepared v0.5.20 as the supported replacement release.
- Snapshot: [v0154](versions/v0154.md)

## 2026-09-18 — v0153 — Provision gateway directories before volumes

- Removed the installer's assumption that runtime-generated per-user gateway
  directories already exist.
- Added explicit restricted, internet, LAN, and full gateway directory creation
  with the runner identity before Docker volume provisioning.
- Prepared v0.5.19 as the supported replacement release.
- Snapshot: [v0153](versions/v0153.md)

## 2026-09-18 — v0152 — Normalize image build modes and timestamps

- Traced the final clean-checkout image mismatch to mode 0775 versus 0755 on
  the copied entrypoint under the Spark's group-writable checkout umask.
- Normalized both timestamps and build-relevant file modes while retaining the
  exact approved image-ID gate.
- Prepared v0.5.18 as the supported replacement release.
- Snapshot: [v0152](versions/v0152.md)

## 2026-09-18 — v0151 — Make exact image verification deterministic

- Confirmed identical image source built from different clean paths produces
  different Docker IDs because build metadata includes source timestamps.
- Normalized a temporary copy of the reviewed build context before builds.
- Preserved the pre-recorded exact image-ID equality security gate.
- Prepared v0.5.17 as the supported replacement release.
- Snapshot: [v0151](versions/v0151.md)

## 2026-09-18 — v0150 — Correct idempotent OpenShell package installation

- Found that v0.5.15 used an ARM64 package filename not present in NVIDIA's
  official v0.0.116 assets; deployment stopped safely at the 404.
- Corrected the asset to `openshell_0.0.116-1_arm64.deb` and verified its
  published checksum matches the existing pin.
- Made the installer skip package download/reinstallation when OpenShell 0.0.116
  is already installed.
- Prepared replacement release v0.5.16; v0.5.15 is superseded for fresh installs.
- Snapshot: [v0150](versions/v0150.md)

## 2026-09-18 — v0149 — Repair OpenShell skill and dependency installation

- Added a persistent skill registry with recoverable migration from the
  workspace compatibility path.
- Added writable persistent uv, pip, npm, and Playwright locations plus a
  project virtual-environment path.
- Added pip to every task profile and Chromium/ipmitool to network-operations.
- Fixed the installer to select `Containerfile` explicitly.
- Rebuilt all six ARM64 task images on the Spark and pinned their immutable IDs.
- Updated the GitHub README, runtime guides, installer, and v0.5.15 notes.
- Validation: `scripts/validate-release.sh` passed with 104 tests.
- Decision: [ADR-0090](decisions/0090-use-persistent-user-tooling-with-immutable-system-images.md).
- Snapshot: [v0149](versions/v0149.md)

## 2026-09-18 — v0148 — Diagnose skill and tool installation failures

- Verified from live task logs that skill files can be created, but a generated
  skill was written into the workspace rather than Prime's persistent registry.
- Confirmed the approved task image includes `uv` and `npm` but not `pip`.
- Confirmed runtime system-package installation is blocked by the intended
  non-root, read-only `/usr` OpenShell boundary.
- Identified `uv`'s default `/home/prime/.cache/uv` location as outside the
  current writable policy.
- No runtime policy, image, or service was changed during diagnosis.
- Snapshot: [v0148](versions/v0148.md)

## 2026-09-17 — v0147 — Make WebUI logins durable and long-lived

- Replaced the 30-minute idle and 12-hour absolute login limits with a 30-day
  idle window and 180-day absolute lifetime.
- Added an owner-only durable session store so valid logins survive auth-service
  restarts and WebUI updates.
- Throttled session activity writes to five-minute intervals.
- Preserved logout, password-change, administrator-revocation, account-state,
  and expiry invalidation behavior.
- Updated the WebUI updater to restart the authentication service when auth code
  changes.
- Prepared v0.5.14.
- Validation: `scripts/validate-release.sh` passed with 104 tests.
- Published and deployed v0.5.14 after explicit approval of the 30-day idle and
  180-day absolute lifetimes. Verified the exact tag, active authentication,
  dashboard, and task-broker services, installed defaults, and HTTPS health.
  The first post-upgrade login will create the durable mode-0600 store.
- Decision: [ADR-0089](decisions/0089-use-durable-long-lived-web-sessions.md).
- Snapshot: [v0147](versions/v0147.md)

## 2026-09-16 — v0146 — Add live telemetry sparklines

- Replaced plain top-of-sidebar statistic values with compact SVG sparklines
  and large translucent current-value watermarks.
- Added hover and keyboard-focus expansion for a larger live graph.
- Increased the telemetry refresh cadence to one second and retained 60 samples
  only in browser memory.
- Prepared the v0.5.13 release.
- Validation: `scripts/validate-release.sh` passed with 102 tests.
- Published and deployed v0.5.13. Verified the exact tag, active dashboard and
  broker services, HTTPS health, all seven rendered cards, rolling one-second
  history labels, and expanded focused-card presentation in the live browser.
- Snapshot: [v0146](versions/v0146.md)

## 2026-09-16 — v0145 — Add scoped persistent security approval

- Added **Always allow for this chat/project** beside the existing per-task
  security confirmation mode.
- Persisted the setting through project defaults and independent conversation
  overrides, including promoted conversations.
- Required the full owner-scoped saved policy to match before repeated
  execution, private-network, automatic-proposal, or local-file confirmations
  can be suppressed.
- Kept the first task of a new standalone chat explicitly confirmed before its
  policy is saved.
- Prepared the v0.5.12 release and updated portable install references.
- Validation: `scripts/validate-release.sh` passed with 101 tests.
- Published v0.5.12 and deployed it to the Spark. Verified the exact tag, active
  dashboard API and runner broker, HTTPS 200 response, and installed UI asset.
- Decision: [ADR-0088](decisions/0088-scope-persistent-security-approval.md).
- Snapshot: [v0145](versions/v0145.md)

## 2026-09-15 — v0144 — Document deployed Spark switches in the GitHub README

- Added a GitHub README section that explicitly lists the deployed DGX Spark
  parameters for Nemotron 3.5 Lightning, Qwen 3.8 Flash-Next, and OpenShell.
- Included concrete model images/checkpoints, listeners, context/KV settings,
  speculation settings, memory limits, container/server switches, task limits,
  filesystem policy, Docker volumes, and workspace paths.
- Validation: `scripts/validate-release.sh` passed with 97 tests.
- Snapshot: [v0144](versions/v0144.md)

## 2026-09-15 — v0143 — Apply recursive ACLs to migrated home task workspaces

- Live verification after v0.5.10 showed the Docker bind volume had moved to
  `~/prime-agent/tasks/dbyte`, but migrated child directories could retain
  restrictive permissions.
- Updated install and volume provisioning to apply recursive `rwX` ACLs for the
  WebUI owner and `prime-web`, plus default ACLs on directories for future task
  outputs.
- Prepared `v0.5.11` release notes.
- Validation: `scripts/validate-release.sh` passed with 97 tests.
- Snapshot: [v0143](versions/v0143.md)

## 2026-09-15 — v0142 — Fix the home workspace volume migration helper

- Found during live deployment that the v0.5.9 volume provisioning helper exited
  when an existing Docker volume already pointed at the expected path because a
  bare `return` inherited the failed comparison status.
- Changed that path to `return 0` so already-correct volumes are treated as
  success.
- Prepared `v0.5.10` release notes while retaining the v0141 workspace design.
- Validation: `scripts/validate-release.sh` passed with 97 tests.
- Snapshot: [v0142](versions/v0142.md)

## 2026-09-15 — v0141 — Move OpenShell task workspaces into the host home tree

- Moved the OpenShell task workspace backing `/project` from
  `/var/lib/prime-runner/users/USER/workspace` to
  `~/prime-agent/tasks/USER/`.
- Kept protected Prime sessions, credentials, project-source staging, and
  metadata under `/var/lib/prime-runner/users/USER/prime`.
- Updated install and WebUI update paths to create the home-backed task root,
  apply runner/WebUI ACLs, migrate legacy workspace files, refresh Docker bind
  volumes, and restart the broker with the new service boundary.
- Preserved the policy boundary: arbitrary `/home` paths remain rejected by the
  local-path picker; only the controlled task workspace is mounted.
- Prepared `v0.5.9` release notes.
- Validation: `scripts/validate-release.sh` passed with 97 tests.
- Decision: [ADR-0087](decisions/0087-store-openshell-task-workspaces-under-host-home.md).
- Snapshot: [v0141](versions/v0141.md)

## 2026-09-14 — v0140 — Isolate OpenShell resumes with per-task Prime daemon sockets

- Diagnosed the latest `OpenShell task runtime exited` failure as Prime refusing
  to resume a conversation registered to a failed stale worker from an earlier
  OpenShell sandbox.
- Added a per-task sandbox-local Prime daemon socket to WebUI OpenShell launches
  so stale default daemon worker state cannot block later resumes.
- Confirmed the failed task's submitted prompt, `resume`, was preserved in saved
  task metadata.
- Wrote final task status back into saved metadata for existing-conversation
  tasks, preventing stale saved `running` rows after a failure or completion.
- Prepared `v0.5.8` release notes for the OpenShell resume repair.
- Validation: `scripts/validate-release.sh` passed with 91 tests.
- Decision: [ADR-0086](decisions/0086-use-per-task-prime-daemon-sockets-in-openshell.md).
- Snapshot: [v0140](versions/v0140.md)

## 2026-09-14 — v0139 — Move model-aware task progress into the conversation stream

- Replaced detailed live status beneath the active chat title with a
  model-aware, collapsible task trace rendered inside the conversation stream.
- Added actor-prefixed progress rows for the active route, including
  `prime-nemotron`, `prime-codex`, and `prime-qwen`.
- Kept traces expanded while tasks run, then collapsed after a result or failure
  so the workspace stays uncluttered while remaining reviewable.
- Preserved privacy by rendering reasoning as safe status only, not private
  chain-of-thought.
- Prepared `v0.5.7` release notes for the task-trace UX update.
- Validation: `scripts/validate-release.sh` passed with 90 tests.
- Decision: [ADR-0085](decisions/0085-render-safe-model-task-traces-in-conversation.md).
- Snapshot: [v0139](versions/v0139.md)

## 2026-09-14 — v0138 — Preserve prompts from failed pre-transcript tasks

- Confirmed the specific `f9b0a7a1d26b40bf88429c0b8a58d8d4` rootless-worded
  failure log contains only the runner import crash and `broker_exit`; the
  submitted prompt was not persisted before Prime started, so it cannot be
  recovered exactly from server-side records.
- Added accepted-prompt persistence to the WebUI task record as soon as
  `/api/tasks/start` accepts a request.
- Added automatic recovered conversations for failed, stopped, or timed-out
  tasks that end before Prime creates a session; the recovered chat includes
  the submitted user prompt and the runtime failure notice.
- Kept the submitted prompt visible in the browser after a failed task even if
  a recovery conversation row has not appeared yet.
- Preserved project, files, routing, model, effort, and task-policy metadata on
  recovered failed-task conversations.
- Prepared `v0.5.6` release notes for failed-prompt recovery.
- Validation: `scripts/validate-release.sh` passed with 89 tests.
- Snapshot: [v0138](versions/v0138.md)

## 2026-09-14 — v0137 — Repair OpenShell WebUI task startup and cleanup

- Fixed the live **Starting Prime** failure by installing the full privileged
  OpenShell runner helper set to `/usr/local/lib/prime-runner` during WebUI
  updates, not only the launcher in `/usr/local/libexec`.
- Added an OpenShell FIFO relay for Prime RPC input because OpenShell 0.0.116
  waits for CLI stdin EOF before starting `sandbox exec`.
- Changed the broker to terminate the per-task launcher when the dashboard
  client disconnects after `agent_end`, allowing the launcher to delete the
  completed sandbox.
- Updated Admin status to check `prime-model-gateway` and
  `prime-runner-broker` as system services and moved stale per-user OpenShell
  gateway/broker unit files into a recovery folder during installation.
- Updated user-facing runtime failure text from retired rootless terminology to
  OpenShell terminology and prepared `v0.5.5` release notes.
- Validation: `scripts/validate-release.sh` passed with 87 tests. Live Spark
  validation completed a real dashboard API canary with `canary-ok` and no
  remaining OpenShell sandboxes.
- Decision: [ADR-0084](decisions/0084-relay-prime-rpc-through-openshell-fifo.md).
- Snapshot: [v0137](versions/v0137.md)

## 2026-09-14 — v0136 — Install runner launcher from WebUI updates

- Extended `deploy/spark/update/update-webui.sh` so future WebUI updates install
  `runner_launch.py` into `/usr/local/libexec/prime-runner-launch`.
- Added updater regression coverage for the privileged runner launcher install.
- Bumped release metadata, installer version, clone/upgrade instructions, and
  release validation to `v0.5.4`.
- Added `docs/releases/v0.5.4.md`; the runtime/model stack remains
  OpenShell + Nemotron 3.5 Lightning + Qwen 3.8 Flash-Next.
- Validation: `scripts/validate-release.sh` passed with 81 tests.
- Snapshot: [v0136](versions/v0136.md)

## 2026-09-14 — v0135 — Fix Prime task startup and Nemotron co-residency

- Fixed the OpenShell runner launch path so `sandbox create` receives
  `/dev/null` for stdin and cannot consume the browser's initial Prime RPC
  `get_state` and prompt messages before `sandbox exec` starts Prime.
- Cleared a stale stuck task and stale OpenShell sandboxes from the Spark.
- Lowered the live Nemotron 3.5 Lightning `GPU_MEMORY_UTILIZATION` from `0.48`
  to `0.38` because vLLM was requesting 58.4 GiB while only 49.4 GiB was free
  with Qwen 3.8 resident.
- Verified Nemotron started healthy and a WebUI-launcher canary progressed past
  **Starting Prime**, completed, and returned `canary-ok`.
- Updated the shipped Nemotron template/default and prepared `v0.5.3` release
  notes for the startup fix.
- Validation: `scripts/validate-release.sh` passed with 80 tests.
- Snapshot: [v0135](versions/v0135.md)

## 2026-09-14 — v0134 — Prepare v0.5.2 updater-helper patch release

- Fixed `deploy/spark/update/update-webui.sh` so WebUI updates copy the shared
  OpenShell task helper into the live dashboard directory before restarting the
  API.
- Added updater regression coverage for the helper copy.
- Bumped release metadata, installer version, clone/upgrade instructions, and
  release validation to `v0.5.2`.
- Added `docs/releases/v0.5.2.md`; the runtime/model stack remains
  OpenShell + Nemotron 3.5 Lightning + Qwen 3.8 Flash-Next.
- Validation: `scripts/validate-release.sh` passed with 78 tests.
- Snapshot: [v0134](versions/v0134.md)

## 2026-09-14 — v0133 — Prepare v0.5.1 project-action patch release

- Bumped the release metadata, installer version, clone/upgrade instructions,
  and release validation from `v0.5.0` to `v0.5.1`.
- Added `docs/releases/v0.5.1.md` documenting the visible sidebar `...` button,
  active-chat project button, right-click preservation, and static-update-only
  upgrade path.
- The patch release carries the same OpenShell, Nemotron 3.5 Lightning, and
  Qwen 3.8 Flash-Next runtime/model state as v0.5.0.
- Validation: `scripts/validate-release.sh` passed with 77 tests.
- Snapshot: [v0133](versions/v0133.md)

## 2026-09-14 — v0132 — Expose visible chat project actions

- Added a boxed `...` action button beside every conversation in the sidebar so
  project promotion, project moves, and other chat actions are discoverable
  without right-clicking.
- Added an active-chat header button that reads **Add to project** for
  unprojected chats and **Move project** for chats already inside a project.
- Kept the existing right-click menu as a secondary shortcut and hid **Remove
  from project** when a chat is not currently in a project.
- Added static UI regression coverage so the visible project action path remains
  present.
- Validation: `scripts/validate-release.sh` passed with 77 tests.
- Decision: [ADR-0083](decisions/0083-expose-visible-chat-project-actions.md).
- Snapshot: [v0132](versions/v0132.md)

## 2026-09-14 — v0131 — Prepare OpenShell-only v0.5.0 release source

- Removed the superseded task-runtime source, activation/rollback scripts,
  dashboard fallback, and runtime-specific tests from the release tree.
- Removed the retired Qwen service files from the release tree and updated
  shipped Prime routing instructions to `spark-qwen/qwen3.8-flash-next`.
- Made `deploy/spark/openshell/install.sh` self-contained: it now provisions the
  `prime-runner` identity, protected state, model gateway, runner broker,
  dashboard OpenShell drop-in, owner-state migration, OpenShell gateway, Docker
  volumes, and digest-checked images.
- Added reproduction docs for OpenShell, Nemotron 3.5 Lightning, and Qwen 3.8
  Flash-Next; updated the root README, Spark README, security guide, sample
  screenshot, and release validation for `v0.5.0`.
- `scripts/validate-release.sh` passed with 76 tests after replacing the old
  runtime tests with OpenShell/shared-helper coverage.
- Decision: [ADR-0082](decisions/0082-publish-openshell-only-v050.md).
- Snapshot: [v0131](versions/v0131.md)

## 2026-09-14 — v0130 — Remove local backups and retired model rollbacks

- Permanently cleared Prime/Spark recovery bundles under `/var/backups`,
  `/home/dbyte/backups`, and `/var/lib/prime-runner/recovery`, plus stale
  application backup-folder contents and standalone stale `.bak`/`.old` copies.
- Removed the inactive rootless-Podman image/container store, rejected and older
  Qwen 3.8 comparison builds, unused model revisions, and the unused Nemotron 3
  Super cache.
- Removed Qwen 3.6 completely from the live Spark: service, runtime directory,
  stopped container, cache, and checkpoint.
- Retained the active Nemotron/DSpark revisions, production Qwen 3.8 image and
  model, current OpenShell runtime, durable Prime data, and code/test snapshot
  fixtures that are not rollback stores.
- Reclaimed 122,164,404,224 bytes. Post-cleanup checks found 511 GB used and
  3.0 TB available; both local models, the Prime API, model gateway, runner
  broker, and dashboard remained healthy.
- Local recovery is intentionally unavailable; current source/reacquisition is
  now the recovery path.
- Decision: [ADR-0081](decisions/0081-remove-local-backups-and-retired-model-rollbacks.md).
- Snapshot: [v0130](versions/v0130.md)

## 2026-09-14 — v0129 — Add project promotion, OpenShell updates, and collapsible controls

- Added an **Add to project** conversation flow. Existing conversations can be
  promoted into a new project with their saved controls as project defaults, or
  added to an existing project while preserving that project's defaults.
- Promoted conversations carry related uploaded assets by using saved
  conversation file IDs, prior project sources, and exact upload paths in the
  visible transcript. Stale deleted upload references are skipped.
- Added OpenShell to Settings software updates. The updater downloads only the
  official NVIDIA OpenShell stable ARM64 package, verifies the published checksum
  file, refuses to run while sandboxes exist, restarts `openshell-gateway`,
  validates owner and runner access, and records the API version.
- Broke Settings and Admin into remembered collapsible groups and made Projects
  and Chats collapsible in the sidebar.
- Validation: release validation passed all 81 tests; JavaScript and shell
  syntax checks passed; deployed API/static/update hashes matched; live Spark
  services were active; unauthenticated API returned 401; no OpenShell sandbox
  IDs remained; live browser inspection confirmed sidebar, Settings, Admin, and
  OpenShell update behavior. Recovery bundle:
  `/var/lib/prime-runner/recovery/project-promote-openshell-collapse-20260914T032916Z`.
- Decisions: [ADR-0079](decisions/0079-promote-conversations-into-projects.md)
  and [ADR-0080](decisions/0080-update-openshell-from-checked-stable-releases.md).
- Snapshot: [v0129](versions/v0129.md)

## 2026-09-13 — v0128 — Layer project defaults under persistent chat controls

- Moved sandbox image, agent tools, egress, policy-proposal, and local-path
  controls out of the message composer into a persistent toolbar directly below
  the conversation header.
- Added the same controls to Project settings. A new chat in a project receives
  a copied project policy; subsequent chat changes persist independently, so
  later project edits do not rewrite existing chats.
- Retained task-by-task confirmations for execution, private networking,
  automatic policy proposals, and Spark-local paths. Persistence remembers the
  preference but does not silently expand authority.
- Validation: 78 tests and release validation passed; Python and JavaScript
  syntax checks passed; deployed hashes matched; API and WebUI services were
  active; the unauthenticated state endpoint returned 401; no OpenShell
  sandboxes remained; live browser inspection confirmed toolbar placement and
  project-default fields. Recovery bundle:
  `/var/lib/prime-runner/recovery/projects-policy-webui-20260914T031200Z`.
- Decision: [ADR-0078](decisions/0078-layer-project-defaults-under-conversation-overrides.md).
- Snapshot: [v0128](versions/v0128.md)

## 2026-09-13 — v0127 — Add native-style Prime projects

- Added an owner-isolated Projects section above Chats with create, edit, pin,
  select, and confirmed delete flows plus icon/color customization.
- Added shared project instructions and up to 40 uploaded sources. Project
  tasks receive the context automatically while injected context stays out of
  the visible user transcript.
- Added move-to-project and remove-from-project conversation actions. New chats
  started from a selected project inherit membership; deleting a project keeps
  its chats and returns them to Chats.
- Copied project sources into each owner's mounted Prime state at task start and
  made that subtree read-only in OpenShell. Provisioned the live dbyte source
  root with the existing WebUI ACL boundary.
- Validation: 77 tests, release validation, exact deployed/source hashes, active
  API/auth/WebUI/runner services, unauthenticated API 401, and live browser
  inspection of the sidebar and project settings. Recovery bundles:
  `/var/lib/prime-runner/recovery/projects-webui-20260914T025500Z` and
  `/var/lib/prime-runner/recovery/projects-sources-20260914T025900Z`.
- Snapshot: [v0127](versions/v0127.md)

## 2026-09-13 — v0126 — Move production Prime tasks into OpenShell

- Installed the official ARM64 NVIDIA OpenShell 0.0.116 package after verifying
  its published SHA-256, activated a loopback mTLS Docker gateway, and disabled
  telemetry. Docker 29.2.1 is supported; Podman 4.9.3 is retained only for
  rollback because current OpenShell requires Podman 5.x.
- Built and pinned six Prime 0.8.0 OpenShell images, added `nftables`, enforced
  hard Landlock with empty direct-network policy, and bridged existing per-user
  state through pre-provisioned bind-backed Docker volumes. The external
  credential/model/network broker remains the ownership and egress boundary.
  Approved shared files/directories use read-only volume subpaths so Ubuntu's
  gateway confinement does not invalidate the UI's static-policy control.
- Cut the production broker over to ephemeral OpenShell sandboxes and updated
  the WebUI to display sandbox image, agent tools, egress channel, manual/clean-
  proof auto proposal modes, runtime/version/driver, static-policy lifecycle,
  and default-deny networking. Internet, LAN/VPN, and Full are now distinct
  broker policies.
- Enabled OpenShell's policy-advisor proposal surface at gateway settings
  revision 1. Manual remains default; administrator-selected auto mode retains
  upstream's empty-prover-delta and no-security-note gates.
- Hard-isolation, production Nemotron, and production Qwen 3.8 canaries passed;
  both task sandboxes cleaned up, both model services remained healthy, and the
  API reports OpenShell 0.0.116. OpenShell exec explicitly preserves Prime's
  pre-provisioned kernel path and places IPython state under the writable Prime
  state mount, so approved tools remain offline-capable. All 71 release tests
  passed and the settled host retained 20.01% available memory, above the 15%
  gate. Recovery bundle
  `/var/lib/prime-runner/recovery/openshell-20260914T020818Z` and the inactive
  Podman runner remain available.
- Decision: [ADR-0076](decisions/0076-run-prime-tasks-inside-openshell.md).
- Snapshot: [v0126](versions/v0126.md).

## 2026-09-13 — v0125 — Reject the latest llama.cpp Qwen candidate

- Built isolated image `local/llama-qwen38-mtp:9bc0988b` by combining current
  upstream master `ad6c6683`, the latest Qwen Flash-Next MTP PR head
  `d1a92352`, and direct-read PR head `c6a9e5c9`.
- The candidate raised the ordinary deterministic/prose/coding mean by only
  1.3% (36.45 to 36.91 token/s), while decode fell 2.0-3.3% at 2K, 8K, and 24K
  prompt depths and a 140-tool request fell 2.4% (32.14 to 31.36 token/s).
  Warm prefill was effectively unchanged.
- Restored production image `560abb66`. Both inference services are active, the
  deployed validator passed, and 21.07% memory remained available against the
  15% floor. The candidate image and clean source branch remain available for
  future comparison.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0125](versions/v0125.md).

## 2026-09-13 — v0124 — Reject Qwen MTP confidence thresholds

- Added an explicit `SPEC_DRAFT_P_MIN` service setting and tested values 0.0,
  0.1, 0.2, and 0.3 with N=2 across repeated 600-token deterministic, prose,
  and coding requests.
- The reverse-order zero control averaged 36.45 token/s. Threshold 0.1 did not
  trigger gating and was behaviorally identical; 0.2 averaged 36.35 token/s;
  and 0.3 regressed to 32.52 token/s. Higher acceptance did not produce higher
  end-to-end throughput.
- Restored the explicit zero cutoff. Qwen and Nemotron remain active, the
  deployed validator passed, and 20.33% memory remained available against the
  15% floor.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0124](versions/v0124.md).

## 2026-09-13 — v0123 — Select MTP confidence gating as the next Qwen test

- Verified that the active llama.cpp MTP build defaults
  `--spec-draft-p-min` to `0.0`, so confidence-based draft early-stop is
  currently disabled.
- Selected a bounded N=2 threshold matrix as the next experiment. It will use
  identical deterministic, prose, and coding prompts and retain the current
  setting unless representative throughput improves without a quality or
  memory regression.
- Kept KV capacity and the live runtime unchanged; a larger cache increases
  context or concurrency capacity, not short single-stream tokens per second.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0123](versions/v0123.md).

## 2026-09-13 — v0122 — Retain two-token Qwen MTP after a three-token A/B

- Temporarily increased Qwen's shared-Q8 MTP draft limit from two to three and
  tested identical 600-token deterministic and temperature-0.7 prose requests.
- Three drafts improved the warm deterministic request from 38.52 to 39.85
  token/s (3.5%) but reduced warm prose from 33.91 to 31.63 token/s (6.7%).
  Acceptance fell from 70.32% to 62.63% and from 53.10% to 41.27%, respectively.
- Restored and verified the two-token production profile. Both model services
  are active, Qwen is healthy, the deployed validator passed, and 21.41% system
  memory remained available against the 15% floor.
- Increasing KV capacity was rejected as a throughput lever: it expands context
  or concurrency capacity but does not make two-token MTP decode faster.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0122](versions/v0122.md).

## 2026-09-13 — v0121 — Enable Qwen 3.8 shared-Q8 MTP

- Built and deployed `local/llama-qwen38-mtp:560abb66` from pinned combined
  MTP/direct-read commit `560abb6616eea7b8c0fc76259bc08142df5c2e1b` for CUDA
  13.0.2 and SM 121.
- Added the exact 2,786,568,256-byte shared-Q8 MTP head and enabled two-token
  target-verified speculative decoding while retaining direct PLE reads, 32K
  context, Q8 KV, vision, and single-slot serving.
- The like-for-like deterministic benchmark improved from 23.08 to 42.08
  request-level token/s (82.3%) at 100% draft acceptance. Technical prose reached
  30.57 token/s at 63.258% acceptance.
- Settled dual-model operation retained 25.77 GB available (19.73%), above the
  15% gate. The Qwen process allocated 66,757 MiB and Nemotron 25,863 MiB.
- Validation passed text, vision, tools, exact Prime Qwen/Nemotron routes,
  Docker and systemd health, loopback bindings, the deployed validator, shell
  syntax, diff hygiene, and all 71 dashboard tests.
- The non-MTP configuration is checksummed at
  `/home/dbyte/backups/qwen38-mtp-20260913` for rollback.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0121](versions/v0121.md).

## 2026-09-13 — v0120 — Lower the memory headroom gate to 15%

- Changed the deployed validation target from 20% to 15% of usable memory,
  approximately 18.3 GiB on this Spark.
- Kept the threshold explicit in the validator and synchronized the operating,
  security, model-stack, dashboard, and Qwen 3.8 decision records.
- Validation: shell syntax, the complete 71-test dashboard suite, both direct
  model endpoints, exact Prime Qwen and Nemotron routes, Docker/service state,
  private bindings, and the deployed validator passed.
- No model, cache, context, inference, or routing setting changed.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0120](versions/v0120.md).

## 2026-09-13 — v0119 — Identify Qwen 3.8 throughput levers

- Repeated the 600-token Qwen test at 23.08 request-level token/s; llama.cpp
  reported 23.38 model-eval token/s and 528.82 token/s on a 1,503-token prefill.
- Measured 84-94% GB10 SM utilization, P0 state, and approximately 2.50-2.52 GHz
  clocks during decode. Together with the previously measured 0.73 MiB/s direct
  reads, this identifies compute rather than NVMe paging as the decode limit.
- Selected shared-Q8 MTP with two draft tokens as the next controlled A/B test.
  Published 1.3-1.7x low-concurrency gains imply approximately 30-39 token/s
  from this baseline, subject to acceptance and the narrow memory gate.
- Recorded shared-Q4 MTP, larger prefill batches, n-gram speculation, lower main
  quantization, and Qwen3.8-27B as secondary tradeoffs. No live setting changed.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0119](versions/v0119.md).

## 2026-09-13 — v0118 — Deploy co-resident Qwen 3.8 Flash Next

- Replaced the enabled Qwen 3.6 service with Qwen3.8-Flash-Next UD-IQ4_XS plus
  its F16 vision projector, served by a commit-pinned CUDA llama.cpp image.
- Enabled direct, on-demand NVMe reads for the PLE table, bounded Qwen to 32,768
  context with Q8 KV, and reduced Nemotron's explicit KV reserve from 12 GiB to
  4 GiB while retaining its 81,920-token context.
- Updated Prime, rootless task catalogs, routing, dashboard status/restart
  controls, and the persisted enabled-model setting. Qwen 3.6 is disabled but
  retained as the rollback target.
- Validation passed for both health endpoints, loopback exposure, Qwen text,
  vision and tool calling, Nemotron text, exact Prime routes, all 71 dashboard
  tests, and the complete deployed validation script.
- Under warm dual-model operation after the final restart, Qwen allocated
  63,617 MiB and Nemotron 25,863 MiB; Linux retained 31.22 GB available (23.89%).
  A 600-token Qwen run
  measured 23.08 token/s, 0.385 major faults/s, and 0.73 MiB/s direct reads.
  A 10-second idle sample showed no swap-in or swap-out.
- Protected rollback files and checksums are at
  `/home/dbyte/backups/qwen38-migration-20260913` on the Spark.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0118](versions/v0118.md).

## 2026-09-13 — v0117 — Separate Nemotron weights from engine allocation

- Corrected the co-residency budget: Nemotron's live 34 GiB includes a 12 GiB KV
  reservation, DSpark, and runtime; compact published GGUFs are roughly 19-25 GB.
- Added compact-GGUF and reduced-cache Nemotron profiles to the proposed
  Flash-Next IQ1 co-residency comparison.
- Retained measured total-process budgeting, output-quality validation, and the
  production memory gate because “4-bit” names do not identify a single size or
  fidelity level.
- No live service changed.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0117](versions/v0117.md).

## 2026-09-13 — v0116 — Distinguish Unsloth IQ1 from NVFP4 Flash-Next

- Corrected the Flash-Next capacity analysis to separate the official NVFP4
  deployment from Unsloth's 72.5-74.5 GB IQ1 GGUFs.
- Recognized Unsloth IQ1 plus Nemotron as a valid constrained co-residency
  experiment, while retaining the 20% production headroom gate.
- Defined the initial safeguards: stop Qwen 3.6, reduce Nemotron's 12 GiB KV
  reservation, bound Qwen context, begin without MTP, and measure memory, swap,
  faults, performance, and quantization quality before increasing capacity.
- No live runtime configuration changed.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0116](versions/v0116.md).

## 2026-09-13 — v0115 — Research Qwen 3.8 Spark upgrade lanes

- Identified Qwen3.8-Flash-Next's 47.7 GiB PLE/n-gram table as the component that
  can be memory-mapped from NVMe; this is file-backed table lookup, not generic
  model swap.
- Verified SGLang's file-backed PLE backend was merged and includes random-access
  advice, prefill hints, and mapped-RSS trimming for unified-memory GB10 systems.
- Measured the unchanged live Spark at 121 GiB usable memory, 40 GiB available,
  about 34.0 GiB allocated to Nemotron and 30.8 GiB to Qwen 3.6, with 3.1 TiB
  free NVMe.
- Selected Qwen3.8-27B NVFP4 plus DFlash2 as the production co-resident candidate.
  Flash-Next remains a mutually exclusive benchmark lane because its 76-79 GiB
  resident core cannot preserve the current 20% headroom gate beside Nemotron.
- No service, model, route, swap setting, or runtime configuration was changed.
- Decision: [ADR-0075](decisions/0075-select-qwen38-upgrade-lanes.md).
- Snapshot: [v0115](versions/v0115.md).

## 2026-09-13 — v0114 — Publish all current WebUI changes as v0.4.0

- Bumped portable install and manual-update documentation to `v0.4.0`.
- Passed the complete release validator, including all 71 dashboard tests.
- Pushed `main`, created and pushed annotated tag `v0.4.0`, and published `.4.0`
  as the latest private GitHub release.
- Verified remote `main` and the peeled release tag both resolve to
  `89cabf864a41f66b73ac4891f57cac2b156136ba`.
- Retired superseded release/tag `v0.3.1` after verifying `.4.0`, preserving the
  one-current-release policy. Local architecture artifacts remain excluded.
- Snapshot: [v0114](versions/v0114.md).

## 2026-09-03 — v0113 — Add the deep implementation topology and pseudocode guide

- Expanded the editable architecture deck from three to five slides with a
  cluster-and-namespace implementation topology and a phase 0–7 build sequence.
- Made Kubernetes, RAG, OpenTelemetry, and OAuth/mTLS MCP interfaces explicit
  across management, workload, data/observability, and Linux-management planes.
- Added a 12-page pseudocode guide covering configuration, ownership, every
  rollout phase and exit gate, OpenShell policy, read-first Uyuni MCP enablement,
  runtime remediation, approval objects, GitOps promotion, acceptance tests,
  recovery, and go-live criteria.
- Preserved Multi-Linux Manager as fleet change authority, with direct SLES 16
  MCP limited to a named-host, read-focused technology-preview exception.
- Rendered and visually inspected every slide and document page; passed slide
  overflow, template-plan, template-fidelity, DOCX accessibility, heading, and
  exact table-geometry checks. Confirmed a source block on all five slides.
- Decision: [ADR-0074](decisions/0074-implement-through-gated-multi-plane-gitops.md).
- Snapshot: [v0113](versions/v0113.md).

## 2026-09-03 — v0112 — Expand the enterprise Linux AI architecture

- Preserved the original overview and expanded the editable PowerPoint to three
  slides: operating model, detailed platform stack, and closed-loop agent
  troubleshooting.
- Added the major SUSE AI Factory with NVIDIA management, workload, data,
  inference, GPU-orchestration, model-routing, safety, vector/search, security,
  observability, and Linux-fleet components.
- Represented the requested functional library as NVIDIA NeMo Agent Toolkit
  functions and function groups, and retained Nemotron 3.5 Lightning plus Qwen
  3.8 behind NIM and Switchyard routing.
- Kept SUSE Multi-Linux Manager as the production fleet authority and the SLES
  16 direct-host MCP route as a narrow technology-preview exception.
- Rendered and visually inspected every final slide, confirmed sources in all
  speaker notes, passed the overflow test, and passed template-plan and
  template-fidelity validation.
- Decision: [ADR-0073](decisions/0073-separate-ai-management-workload-data-and-fleet-authority.md).
- Snapshot: [v0112](versions/v0112.md).

## 2026-09-03 — v0111 — Add enterprise Linux agent architecture slide

- Added an editable one-slide PowerPoint architecture combining OpenShell,
  Hermes Agent, Nemotron 3.5 Lightning, Qwen 3.8, and SUSE Multi-Linux Manager.
- Made SUSE Multi-Linux Manager the authoritative fleet path and separated the
  SLES 16 direct-host MCP troubleshooting route as a technology preview.
- Set the operating policy to read-only discovery by default, with explicit
  human approval, bounded targets, verification, and rollback for write actions.
- Verified the slide by rendering the final PPTX and passing the presentation
  overflow test; no runtime or managed system was changed.
- Decision: [ADR-0072](decisions/0072-fleet-first-mcp-with-gated-host-diagnostics.md).
- Snapshot: [v0111](versions/v0111.md).

## 2026-09-01 — v0110 — Confirm browser-independent task execution

- Verified that closing the WebUI sends no task lifecycle request and that
  `/auth/logout` revokes only the browser authentication session and cookies.
- Confirmed neither path invokes `/api/tasks/stop`, terminates the Prime process,
  or revokes an already-authorized running task.
- Distinguished normal close/sign-out from an administrative API service restart,
  which can still interrupt the service-owned control process.
- Snapshot: [v0110](versions/v0110.md).

## 2026-09-01 — v0109 — Keep sidebar conversations during active tasks

- Reproduced the disappearing sidebar while a live rootless task caused Prime's
  parent ACL mask to become `---`.
- Prevented inaccessible empty catalogs from overwriting good memory, persisted
  the catalog across API restarts, and removed cached-row session-file stats.
- Allowed metadata-authorized conversation settings to save without touching a
  temporarily protected session file.
- Added three regressions; all 71 tests and release validation pass.
- Deployed through commit `7032a48`, performed the approved API restarts, and
  proved a fresh reader returns 10 sidebar rows while traversal is denied.
- Decision: [ADR-0071](decisions/0071-persist-sidebar-catalog-across-task-locks.md).
- Snapshot: [v0109](versions/v0109.md).

## 2026-09-01 — v0108 — Correct stale kernel error and invalid local path

- Proved the newest affected task never started a container: its saved
  `/home/byte/work` path was unavailable on the Spark, while the visible kernel
  text was an older assistant response.
- Backed up metadata and removed only that unusable path, retaining the
  conversation's Development, execution, and Internet settings.
- Removed `/home` from selectable roots while the broker masks it and added
  immediate policy rejection plus a focused regression test.
- Added a dialogue-level failed-task notice so a pre-response failure cannot
  leave an older answer looking current.
- Passed all 68 tests, release validation, exact production-kernel verification,
  and deployed commit `7db3c0c`.
- Decision: [ADR-0070](decisions/0070-use-explicit-spark-sharing-roots.md).
- Snapshot: [v0108](versions/v0108.md).

## 2026-09-01 — v0107 — Preserve conversation access after rejected paths

- Confirmed all 17 prior session files remained intact; the WebUI lost access
  because a failed directory-enabled launch left parent ACL masks at `---`.
- Restored the intended traverse-only ACL without modifying conversation data.
- Moved gateway validation, local-path validation, argv construction, and
  process startup inside the runner's unconditional ACL-restoration boundary.
- Added a regression test, passed all 67 tests and release validation, deployed
  commit `53e481e`, and proved a live rejected path leaves the mask at `--x`.
- Decision: [ADR-0069](decisions/0069-restore-acls-after-all-launch-failures.md).
- Snapshot: [v0107](versions/v0107.md).

## 2026-08-31 — v0106 — Pre-provision the Prime IPython runtime

- Traced the reported `uv` failure to Prime's first-use Python 3.11 bootstrap,
  which required Internet before any IPython or bash cell could execute.
- Installed checksum-pinned `uv` for all newly built profiles and built an
  immutable Python 3.11 kernel containing IPython, Prime's bundled runtime,
  state support, and all default Python packages.
- Verified the entire runtime with networking disabled, then atomically promoted
  Development digest `9f4ba779…bb648`; retained the previous manifest for rollback.
- Increased release coverage to 66 tests and passed release validation.
- During diagnosis, observed a credential printed into agent conversation output;
  its value is intentionally not recorded and revocation was recommended.
- Decision: [ADR-0068](decisions/0068-preprovision-prime-kernel-runtime.md).
- Snapshot: [v0106](versions/v0106.md).

## 2026-08-31 — v0105 — Restore home isolation after mount verification

- Tested an actual rootless Podman bind mount with `prime-local-access` as both
  a supplementary group and the process's effective primary group; both failed
  during Podman's source `statfs` with `permission denied`.
- Reversed the temporary `/home` service-mask removal and restored
  `InaccessiblePaths=/home /root` so the unsuccessful group experiment does not
  leave the broker with broader host visibility.
- Retained the dedicated group and non-recursive boundary ACL for future use;
  home selections remain fail-closed pending a different sharing design.
- Snapshot: [v0105](versions/v0105.md).

## 2026-08-31 — v0104 — Activate group-governed home path mounts

- After explicit owner approval, removed `/home` from the broker's
  `InaccessiblePaths` while retaining the `/root` mask.
- Kept `prime-local-access` as the only local-data group, its membership limited
  to `prime-runner`, and the `/home/dbyte` boundary ACL at `r-x`.
- Preserved descendant filesystem permissions, runner-side canonical/sensitive
  path validation, per-task confirmation, and read-only task bind mounts.
- Snapshot: [v0104](versions/v0104.md).

## 2026-08-31 — v0103 — Isolate Podman home access in a dedicated group

- Created `prime-local-access`, added only `prime-runner`, and granted the group
  the `r-x` home-boundary ACL required by rootless Podman mount preparation.
- Removed the direct named-user ACL and kept local-data access separate from the
  broader `prime-web` service group.
- Preserved descendant ownership/modes/ACLs and read-only container mounts; the
  boundary grant reveals top-level names but grants no new descendant writes.
- Updated the rootless installer to reproduce and migrate the group/ACL setup.
- Added the dedicated group explicitly to the hardened broker service while
  retaining its `/home /root` mask. The group/ACL migration is complete, but
  `/home/dbyte` mounts remain fail-closed until the conflicting `/home` service
  mask is explicitly approved for removal.
- Decision: [ADR-0067](decisions/0067-dedicated-local-access-group.md).
- Snapshot: [v0103](versions/v0103.md).

## 2026-08-31 — v0102 — Add uv to the development tool profile

- Added ARM64 `uv` and `uvx` 0.12.8 to development containers using the official
  immutable release archive and a pinned SHA-256 checksum.
- Documented that Execution controls Prime tool availability and Internet-capable
  Network access is additionally required for dependency downloads.
- Limited the package-manager addition to the Development profile to keep the
  general, CAD, finance, network-operations, and review images minimal.
- Built and verified `uv 0.12.8 (aarch64-unknown-linux-gnu)` in a disposable
  network-disabled container, then atomically promoted development digest
  `sha256:2540ccca…bbf66`; the prior manifest is retained under `/var/backups`.
- Decision: [ADR-0066](decisions/0066-pin-uv-in-development-profile.md).
- Snapshot: [v0102](versions/v0102.md).

## 2026-08-31 — v0101 — Add guarded conversation-local path access

- Added a **Files & directories** conversation control alongside Profile,
  Execution, and Network, with up to eight newline-separated Spark-local paths.
- Persisted selected paths per conversation while requiring explicit read-only
  access confirmation for every task.
- Limited the feature to power users and administrators; canonicalized sources
  at the rootless runner boundary, restricted roots, rejected sensitive state and
  non-file objects, and mounted inputs read-only under `/project-files`.
- Added only traverse ACL access for the dedicated runner on the installer
  account's home boundary; descendant read permissions are not broadened.
- Added authorization and container-boundary regression coverage; all 65 tests
  and release validation pass.
- Decision: [ADR-0065](decisions/0065-guard-conversation-local-paths.md).
- Snapshot: [v0101](versions/v0101.md).

## 2026-08-31 — v0100 — Add guarded data-driven routing administration

- Replaced hard-coded request matching with priority-ordered literal routing
  rules stored atomically outside the repository.
- Added an admin-only visual workflow to list, add, edit, enable/disable, delete,
  and reset rules; destructive delete/reset actions require exact server-checked
  confirmation values.
- Restricted targets to configured models, bounded names/priorities/phrases and
  rule counts, used literal matching instead of custom regex, retained CSRF and
  Origin enforcement, and audit events without prompt contents.
- Seeded editable explicit Nemotron, Codex/ChatGPT, and Qwen rules; Codex
  architecture requests target `openai-codex/gpt-5.6-sol`, and existing Qwen
  visual/CAD/finance/engineering behavior remains an editable rule.
- Preserved pre-change API/UI files, deployed exact reviewed hashes, verified the
  live five-rule API and both Admin list/editor visuals, and passed 61 tests plus
  release validation.
- Decision: [ADR-0064](decisions/0064-use-guarded-data-driven-routing.md).
- Snapshot: [v0100](versions/v0100.md).

## 2026-08-31 — v0099 — Verify why Codex usage remains zero

- Confirmed ChatGPT subscription configuration and 13 enabled
  `openai-codex` models without inspecting credentials.
- Aggregated provider/model/usage metadata only across 17 production
  conversations: none contains an `openai-codex` assistant message.
- Confirmed the 24 `openai/gpt-5.4` records all ended with `stopReason=error`
  and explicit zero token/cost fields.
- Established that prompt text assigning Codex an architect role did not launch
  a Codex child agent; the missing usage is an orchestration issue, not a Usage
  aggregation defect. No synthetic tokens were added.
- Snapshot: [v0099](versions/v0099.md).

## 2026-08-31 — v0098 — Persist policy controls per conversation

- Added owner-scoped conversation metadata for Profile, Execution, and Network.
- New chats retain their initial selections once Prime assigns the conversation
  ID; saved chats persist manual changes immediately and restore them on reopen.
- Kept preferences separate from authorization so `Ask for each task` and LAN or
  full-network confirmation gates remain enforced on subsequent messages.
- Added role validation and three regression tests covering metadata storage,
  catalog retrieval, and initial new-chat persistence.
- Deployed matching API/UI sources after preserving pre-change copies; the API
  is active and healthy, and all 58 tests plus release validation pass.
- Snapshot: [v0098](versions/v0098.md).

## 2026-08-31 — v0097 — Keep accepted prompts cleared

- Reproduced a completed task whose prompt text remained in the composer and
  correlated it with a failed post-start conversation refresh in browser logs.
- Separated task-start acceptance from best-effort message refreshes so a
  transient refresh error cannot reclassify an accepted task as unsent or
  restore its prompt text.
- Retained prompt restoration for genuine start and steering-delivery failures,
  without overwriting any newer text the user may already have entered.
- Deployed the script to the Spark and verified its served SHA-256 matches the
  reviewed source. JavaScript syntax, 55 tests, and release validation pass.
- Snapshot: [v0097](versions/v0097.md).

## 2026-08-31 — v0096 — Restore the Advanced Console under scoped CSP

- Traced the white Advanced Console iframe to the site-wide CSP blocking ttyd
  1.7.4's embedded JavaScript and CSS.
- Added `unsafe-inline` only for scripts/styles under the authenticated
  `/terminal/` location and repeated every other server security header to avoid
  Nginx header-inheritance loss.
- Left the main WebUI CSP, terminal authentication, private listener, and exact
  WebSocket origin gate unchanged.
- Preserved the previous active Nginx site as
  `/etc/nginx/sites-available/prime-agent.conf.pre-terminal-csp`.
- Validation passes 55 tests, release validation, `nginx -t`, active-service
  checks, and served-header comparison proving only `/terminal/` is relaxed.
- Snapshot: [v0096](versions/v0096.md).

## 2026-08-31 — v0095 — Show the full sanitized runtime log live

- Added a console-style Full live log to every owner-scoped Background Activity
  task and feed it every backend line before event parsing.
- Retained up to 5,000 lines or 2 MiB per task and automatically follows new
  output in the UI.
- Recursively redacts credentials and replaces content in thinking/reasoning
  parts plus nested delta/end events with `[PRIVATE_REASONING]`.
- Applied the same sanitizer to newly written downloadable task logs.
- Validation passes 55 tests, syntax checks, live API health, and a production
  canary proving nested reasoning deltas are replaced by privacy markers.
- Historical log rewriting remains pending explicit owner approval.
- Snapshot: [v0095](versions/v0095.md).

## 2026-08-31 — v0094 — Restore Internet-profile inference and observable task failures

- Traced the stalled budget-app request to proxy-aware container traffic sending
  the internal model bridge through the outbound policy proxy; all model retries
  failed while the API incorrectly reported completion.
- Added an explicit loopback no-proxy policy at container launch and in the image
  entrypoint for future builds.
- Added owner-scoped live runtime events, safe reasoning-state indicators,
  retry/tool/error visibility, redacted console output, and downloadable redacted
  completion logs without exposing private chain-of-thought.
- Made model errors fail visibly instead of leaving a pending conversation in a
  false `Finishing response` state.
- Validation passes 54 automated tests, syntax checks, live API health, and a
  successful Internet-profile Nemotron canary.
- Snapshot: [v0094](versions/v0094.md).

## 2026-08-30 — v0093 — Repair chat start after stale runner ACL

- Traced the browser's undefined `task.id` error to an API `PermissionError`
  reading the isolated session directory after an interrupted runner left ACL
  masks ineffective on ancestor directories.
- Made pre/post-task session snapshots tolerate temporary access loss and made
  the launcher handle termination while still completing ACL restoration.
- Made the browser reject non-JSON or malformed task-start responses with a
  useful error instead of dereferencing an undefined task.
- Preserved broker `PrivateTmp` isolation while disabling Podman's implicit
  copy-up tmpfs mounts and supplying explicit hardened no-copy-up `/tmp` and
  `/run` mounts.
- Validation passes 52 automated tests plus Python/JavaScript syntax checks.
- Snapshot: [v0093](versions/v0093.md).

## 2026-08-27 — v0092 — Lower connector openings and narrow the case

- Lowered only the USB-C and both micro-HDMI openings by 2 mm, from Z=10.9 mm
  to Z=8.9 mm.
- Reduced internal width from 60 mm to 59 mm and external width from 66.4 mm to
  65.4 mm; the 90 mm internal and 96.4 mm external lengths are unchanged.
- Reduced the wall-integrated receiver radius to preserve 1.05 mm rounded-HAT
  clearance in the narrower cavity; assembled lid/base overlap remains 0.0 mm3.
- Kept the Pi plane, power opening, network openings, and vents fixed at their
  v0091 positions.
- Regenerated watertight meshes with all wall-path probes at 0.0 mm3.
- Passed warning-free, support-free X2D/PETG slicing with no filament changes;
  estimated plate time is 2 h 27 m 14 s.
- Added ADR-0061 and immutable snapshot [v0092](versions/v0092.md).

## 2026-08-27 — v0091 — Raise only the Pi plane and switch opening

- Raised the Pi mounting plane 2 mm from Z=2.8 mm to Z=4.8 mm.
- Raised the native power-button/LED opening and exact actuator 2 mm from
  Z=10.2 mm to Z=12.2 mm.
- Kept USB-C/micro-HDMI at Z=10.9 mm, network openings at Z=14.4 mm, upper vents
  at Z=31 mm, and the 90 x 60 mm cavity unchanged.
- Regenerated watertight parts with 0.0 mm3 lid/base overlap, 1.06 mm HAT
  clearance, and 0.0 mm3 obstruction in all wall-path probes.
- Passed warning-free, support-free X2D/PETG slicing with no filament changes;
  estimated plate time is 2 h 27 m 40 s.
- Added ADR-0060 and immutable snapshot [v0091](versions/v0091.md).

## 2026-08-27 — v0090 — Use the confirmed 90 x 60 mm cavity

- Replaced photo-estimated plan dimensions with the owner's confirmed 90 mm
  internal length and 60 mm internal width; exterior is 96.4 x 66.4 mm.
- Lowered the Pi mounting plane 2.6 mm from the first print, leaving a printable
  0.4 mm pad, and independently raised all connector/control openings 3 mm.
- Set USB-C/micro-HDMI centers to Z=10.9 mm, network centers to Z=14.4 mm, and
  the power-button/LED center to Z=10.2 mm.
- Tightened wall-integrated lid receivers while retaining 1.06 mm rounded-HAT
  clearance and 0.0 mm3 assembled lid/base overlap.
- Raised upper wall vents to preserve material above the network bays and made
  any slicer warning a validation failure.
- Regenerated three watertight parts; all wall-opening probes report 0.0 mm3.
- Passed warning-free X2D/PETG slicing without supports or filament changes;
  estimated plate time is 2 h 26 m 47 s.
- Added ADR-0059 and immutable snapshot [v0090](versions/v0090.md).

## 2026-08-27 — v0089 — Tighten the case and lower the Pi

- Used first-print photos showing excess plan clearance and a small vertical
  network-port mismatch as physical-fit evidence.
- Reduced the exterior from 103.6 x 74.6 mm to 98.1 x 68.6 mm, leaving 3.75 mm
  per HAT end and 3.25 mm per HAT side inside the cavity.
- Lowered the Pi support plane 0.6 mm while retaining the network openings at
  Z=11.4 mm.
- Slimmed and moved the corner receivers into recessed wall pockets; rounded-HAT
  clearance is 1.43 mm and assembled lid/base overlap remains 0.0 mm3.
- All wall-path probes remain clear and all three meshes remain watertight.
- Passed X2D/PETG slicing with no supports, warnings, or filament changes;
  estimated plate time is 2 h 32 m 22 s.
- Added ADR-0058 and immutable snapshot [v0089](versions/v0089.md).

## 2026-08-26 — v0088 — Correct dedicated WebUI password instructions

- Removed ambiguous system-account language from first-use documentation.
- Documented the masked `prime-web-password` workflow, non-root requirement,
  auth-service restart, protected credential path, and explicit PAM/Linux-
  password exclusion.
- Added release-validation assertions protecting the authentication guidance.
- Snapshot: [v0088](versions/v0088.md).

## 2026-08-26 — v0087 — Open and verify every side-wall penetration

- Corrected the root cause of closed upper vents: wall cutters were centered on
  the exterior surface and left an approximately 0.8 mm inner membrane.
- Centered the vent, connector, Ethernet/USB, and shared button/LED cutters on
  the 2.8 mm wall midplanes so every opening passes through the shell.
- Added generation-failing obstruction probes for both upper-wall vent axes,
  USB-C, an Ethernet/USB bay, and the button/LED path; all report 0.0 mm3.
- Regenerated three watertight parts; lid/base overlap remains 0.0 mm3 and HAT
  clearance remains 1.51 mm.
- Passed X2D/PETG slicing with no supports, warnings, or filament changes;
  estimated plate time is 2 h 42 m 27 s.
- Added ADR-0057 and immutable snapshot [v0087](versions/v0087.md).

## 2026-08-26 — v0086 — Add through-holes and exterior countersinks

- Kept all four M3 lid holes and all four M2.5 floor mounts open through their
  respective parts.
- Replaced cylindrical exterior counterbores with true conical countersinks:
  6.4 x 1.5 mm for M3 and 5.5 x 1.3 mm for M2.5 flat-head screws.
- Kept internal recessed lid-receiver pilots blind to prevent bottom protrusion.
- Regenerated watertight meshes; lid/base overlap remains 0.0 mm3 and HAT
  clearance remains 1.51 mm.
- Passed X2D/PETG slicing with no supports, warnings, or filament changes;
  estimated plate time is 2 h 42 m 34 s.
- Added ADR-0056 and immutable snapshot [v0086](versions/v0086.md).

## 2026-08-26 — v0085 — Correct and prove enclosure assembly

- Confirmed that the prior base receivers and lid collars prevented the lid from
  seating, and that receiver/HAT clearance was not conservatively proven.
- Increased the cavity to 98 x 69 mm and recessed the receivers 4.45 mm below the
  rim, leaving 0.25 mm below the reduced lid guides.
- Added generation-failing assembled lid/base intersection and full rectangular
  HAT keepout checks; results are 0.0 mm3 overlap and 1.51 mm minimum clearance.
- Changed lid hardware to M3 x 12 mm for about 5 mm of receiver engagement.
- Replaced the approximated actuator with the exact SHA-verified supplied
  PowerButton v14 mesh and its matching 9 x 4 mm opening/inside-flange assembly.
- Regenerated watertight STLs and passed the X2D/PETG slice with no supports,
  warnings, or filament changes; estimated plate time is 2 h 42 m 34 s.
- Added ADR-0055 and immutable snapshot [v0085](versions/v0085.md).

## 2026-08-26 — v0084 — Publish deployment-focused v0.3.1

- Added a concise upstream repository-scope note, updated release metadata to
  v0.3.1, and retained only current release notes.
- Validated, committed, tagged, and published `.3.1`, then removed `.3` and tag
  `v0.3.0` after the replacement was confirmed.
- Runtime behavior and local production-only files remain unchanged.
- Snapshot: [v0084](versions/v0084.md).

## 2026-08-26 — v0083 — Retain only the current upstream release tag

- Removed GitHub releases `.1` and `.2` and their `v0.1.0` and `v0.2.0` tags.
- Retained current release `.3` and tag `v0.3.0`; branch history was not rewritten.
- Snapshot: [v0083](versions/v0083.md).

## 2026-08-26 — v0082 — Separate production-local memory from upstream

- Preserved the local wiki, Pi 5 CAD work, Prime policy/evaluation refinements,
  and saved security-review skill while removing them from Git tracking.
- Added ignore rules preventing those production-local assets from being
  republished and replaced upstream README links with standalone deployment and
  security documentation.
- No Spark runtime or installed production file was changed. Git history and
  release `v0.3.0` were intentionally not rewritten.
- Snapshot: [v0082](versions/v0082.md).

## 2026-08-26 — v0081 — Activate production rootless task isolation

- Created and verified root-only pre-activation recovery bundle
  `/var/backups/prime-rootless-v0081-20260826T161217-0500` and added automatic
  preinstall backup plus conversation-preserving rollback tooling.
- Provisioned dedicated `prime-runner`, subordinate mappings, persistent model
  gateway and peer-authenticated task broker, per-user state/workspaces, and six
  digest-pinned profile images.
- Kept the WebUI API fully sandboxed. Confined rootless Podman's approved
  `newuidmap`/`newgidmap` exception to the broker with only `CAP_SETUID` and
  `CAP_SETGID` in its bounding set and no ambient capabilities.
- Activated restricted, public-Internet, LAN/VPN, and confirmed full-network
  policy with rootless read-only, capability-free, bounded task containers.
- Hardened global/per-user Codex credential fallback, file validation, serialized
  OAuth refresh, and upstream-401 recovery; credentials never enter containers.
- Corrected initial-prompt/steering startup ordering, stopped-task status, ACL
  mask restoration, recoverable per-user trash ownership behavior, temporary
  active-task catalog permission changes, and nonzero broker-exit reporting.
- Validation passed 51 automated tests, Nemotron/Qwen/Codex canaries, persistence,
  steering, stop, resume, temporary second-account isolation, live resource and
  mount inspection, all network modes, zero-orphan cleanup, and rollback dry run.
- Added [ADR-0054](decisions/0054-activate-peer-authenticated-rootless-runtime.md)
  and immutable snapshot [v0081](versions/v0081.md). Release tag `v0.3.0` is the
  intended source rollback point after publication.

## 2026-08-26 — v0080 — Publish portable WebUI release 0.2.0

- Added a repository-root README with a synthetic screenshot, complete first-use
  and operating guidance, and explicit Ubuntu/Debian, RHEL-family, and
  SLES/openSUSE installation alternatives.
- Added a non-root installer that detects the distribution family, installs only
  production host-mode prerequisites, provisions pinned Prime Agent 0.8.0,
  private TLS, Nginx, dedicated WebUI authentication, hardened user services,
  and verifies the local health and authentication boundary.
- Kept firewall modification and rootless execution opt-in. Documented the
  optional Podman prerequisites and every remaining activation gate rather than
  implying that package installation provides isolation.
- Made WebUI origins, repository location, and initial administrator portable;
  made the release updater work from main or a detached tagged checkout and run
  the full suite before installation.
- Added a release validation script and validated all 39 Python tests, shell and
  JavaScript syntax, required release contents, and the screenshot artifact.
- Added [ADR-0053](decisions/0053-portable-versioned-installation.md) and
  immutable snapshot [v0080](versions/v0080.md). Rollback is checkout/reinstall
  of `v0.1.0`; the staged container feature remains off.

## 2026-08-26 — v0079 — Stage policy-controlled rootless task containers

- Created and verified the root-only pre-change bundle
  `/var/backups/prime-containers-v0079-20260826T145311-0500` with 38 checksums.
- Installed Podman 4.9.3, uidmap, slirp4netns, fuse-overlayfs, and supporting
  rootless runtime packages on the Spark; existing WebUI/model services remained
  active and unchanged.
- Added server-enforced roles, execution/network confirmations, profiles, and
  resource ceilings, plus matching composer controls and activity visibility.
- Added a fail-closed Podman argv builder and tests for read-only roots, dropped
  capabilities, no-new-privileges, per-user paths, hard limits, no host network,
  and Prime `--no-tools` enforcement when execution is denied.
- Bounded RPC event reads, removed pipe writes from the global task lock, added
  initial-prompt failure cleanup and command acknowledgement, and stopped an
  auxiliary RPC rejection from poisoning an otherwise healthy task.
- Built and ran the general ARM64 candidate image from the official checksum-
  pinned Prime 0.8.0 artifact. The image digest is recorded in Current State.
- Discovered that `prime-agent@0.8.0` is not published on the public npm registry;
  replaced the tracked updater's npm-registry lookup with the official versioned
  artifact plus its published SHA256SUMS verification. This updater change is not
  deployed yet. The production task path remains v0078 pending gateway, service-
  identity, data-migration, profile-image, and end-to-end validation.
- The local suite passes 39 tests and JavaScript syntax validation. Added
  [ADR-0052](decisions/0052-rootless-per-task-execution.md) and immutable
  snapshot [v0079](versions/v0079.md).
- Deployed the host-compatible policy/API/UI and corrected updater, restarted the
  auth/API services with no active child task, verified both active, checked the
  telemetry endpoint, confirmed unauthenticated HTTPS API access remains 401,
  and confirmed the container feature flag is absent.

## 2026-08-26 — v0078 — Verify live RPC steering end to end

- Deployed commit `4a66709`; the deployed suite passed all 30 tests and installed
  API/static files matched the repository.
- Live browser validation confirmed immediate optimistic echo, safe lifecycle and
  IPython progress in the dialogue, visible steering delivery, and no alert or
  console attachment.
- Prime completed the in-flight tool call, consumed `/steer` at the next turn
  boundary, and changed a requested two-sentence result into the requested
  one-sentence final answer.
- Added immutable verification snapshot [v0078](versions/v0078.md). Runtime
  recovery remains the pre-v0077 bundle documented in v0077.

## 2026-08-26 — v0077 — Use Prime RPC for interactive running tasks

- Live validation proved that one-shot JSON/print sessions publish valid saved
  session IDs but are not addressable by Prime's external `send` command while
  running.
- Changed WebUI task transport to Prime's documented persistent RPC mode. Initial
  prompts, steering, follow-ups, and aborts now share the task's private stdin;
  responses and safe task events stream over stdout.
- Restored `/follow-up` because RPC exposes native `follow_up`, and changed Stop
  to native `abort`. Internal response maps and end-state flags are excluded from
  browser task snapshots and remain bounded.
- Added [ADR-0051](decisions/0051-use-prime-rpc-for-interactive-webui-tasks.md),
  immutable snapshot [v0077](versions/v0077.md), and root-only pre-change recovery
  at `/var/backups/prime-rpc-v0077-20260826T140000-0500`.

## 2026-08-26 — v0076 — Correct Prime 0.8 steering invocation

- Live browser validation found that Prime 0.8.0's generated `send --help` still
  advertises removed `--steer` and `--follow-up` flags; its installed parser
  rejects both flags.
- Changed steering to the parser-verified `send <agent> --message <text>` form.
  Prime 0.8 delivers sends to a busy agent as steering.
- Removed the unsupported follow-up choice rather than presenting a control that
  cannot be honored reliably by the installed release. Message, `/steer`, and
  `/stop` remain available.
- Added [ADR-0050](decisions/0050-use-parser-verified-prime-steering.md), immutable
  snapshot [v0076](versions/v0076.md), and root-only pre-fix recovery at
  `/var/backups/prime-steering-v0076-20260826T135500-0500`.

## 2026-08-26 — v0075 — Echo new messages and add live steering

- Added immediate optimistic rendering of a submitted user message, including
  visible sending/received/failure state, so a new conversation no longer appears
  empty while Prime starts.
- Replaced completion-only stdout collection with bounded incremental processing
  of Prime's supported JSON event stream. The dialogue shows safe lifecycle/tool
  events, elapsed time, and available draft response text while excluding hidden
  reasoning. Raw progress/log retention is bounded.
- Added owner-scoped `/steer` and `/follow-up` delivery through Prime 0.8.0's
  supported `send` command, plus `/stop` and ordinary Message choices in the
  composer. Controls become available only after a valid active agent ID arrives.
- Added regression coverage for safe event projection and owner-scoped steering;
  the local suite now contains 30 tests.
- Added [ADR-0049](decisions/0049-live-dialogue-and-supported-steering.md),
  immutable snapshot [v0075](versions/v0075.md), and planned root-only pre-change
  recovery at `/var/backups/prime-live-dialogue-v0075-20260826T134500-0500`.

## 2026-08-26 — v0074 — Prevent invalid single-user trust downgrades

- The bounded third forward test correctly rejected argv injection, CSP, and
  guarded-import/listener false positives, demonstrating that v0073's semantic
  guardrails changed behavior as intended.
- It still downgraded local privileged-backend access and shared execution identity
  to informational by assuming a single-user system despite distinct WebUI users
  and user-influenced local agents/terminals.
- The skill now rejects `single-user`/`trusted-localhost` assumptions when the
  product exposes distinct accounts or lets less-trusted users launch local code,
  jobs, plugins, terminals, or agents. Such workloads are explicitly part of the
  attacker model.
- Added generic safeguards against treating side-effect-free GETs as CSRF data
  exfiltration without cross-origin response access, or assuming an unimplemented
  HTTP method falls through to another method handler.
- The final tools-disabled regression was capped at 500 words and correctly
  identified both direct loopback identity/role forgery by user-influenced local
  processes and failed cross-account isolation under shared agent/terminal OS
  identity. It supplied concrete paths and did not repeat the prior semantic
  false positives.
- Added immutable snapshot [v0074](versions/v0074.md).

## 2026-08-26 — v0073 — Add semantic false-positive guardrails

- Used Prime's JSON event stream to verify the second forward test actually ran
  `spark-qwen/qwen3.6-35b-a3b` at high effort with tools disabled; this confirmed
  the earlier Anthropic/minimal text was invented rather than runtime metadata.
- The test surfaced the header-trust area but misattributed it to external client
  header injection rather than direct local backend reachability, and still
  produced false positives around double-submit CSRF, argument arrays plus `--`,
  CSP `'self'`, and importing a listener behind an entrypoint guard.
- Added generic platform-semantic rejection rules for those patterns. Gateway
  bypass and shared execution identity must now each become an explicit finding
  or evidence-based negative result. Reports must prioritize distinct material
  results rather than manufacture an item for every checklist branch.
- Added immutable snapshot [v0073](versions/v0073.md).

## 2026-08-26 — v0072 — Refine the generic security skill from forward testing

- Forward-tested the new skill against the same WebUI source with all tools
  disabled. It no longer repeated the earlier CSP and Origin-forwarding false
  positives and added capability-driven negative results, subprocess sandboxing,
  and resource-lifecycle analysis.
- The test still missed the direct local gateway-bypass attack and did not connect
  shared OS execution identity to failed tenant isolation. It also invented
  provider/model/effort metadata instead of respecting the invocation.
- Added mandatory generic gates for direct reachability of privileged backends,
  forgery of gateway assertions by sibling/local workloads, and comparison of
  application identities with actual process/filesystem/credential/tool/terminal
  isolation. Runtime metadata must now come from trusted execution metadata or be
  reported as unknown.
- Added immutable snapshot [v0072](versions/v0072.md).

## 2026-08-26 — v0071 — Add a generic capability-driven security-review skill

- Added a technology-neutral Prime skill that inventories capabilities before
  activating relevant web, authentication, memory/resource, filesystem/storage,
  subprocess/plugin/agent, network/IPC, cryptography, concurrency, dependency,
  update, and deployment review modules.
- Required concrete attack paths, compensating-control checks, evidence and
  confidence, important negative results, and explicit separation of confirmed
  vulnerabilities from validation needs, reliability defects, defense in depth,
  and accepted trust assumptions.
- Added lifecycle-aware memory guidance for manual, managed, pooled, FFI, GPU,
  and sensitive buffers without incorrectly demanding manual deallocation or
  unverifiable zeroization from garbage-collected abstractions.
- Recorded the two material trust-boundary discoveries from the preceding
  report-only comparison without changing the WebUI: spoofable loopback proxy
  identity headers and shared-user execution/console isolation.
- Added [ADR-0048](decisions/0048-capability-driven-security-review-skill.md) and
  immutable snapshot [v0071](versions/v0071.md).

## 2026-08-25 — v0070 — Make both component updaters release-aware

- Published the first Prime WebUI GitHub release with display title `.1`, valid
  tag `v0.1.0`, and target commit `5d9fd3a`.
- Added an admin-only release-status endpoint and automatic checks whenever
  Settings is entered for both Prime Agent and Prime WebUI. Installed/latest
  versions remain visible, and available updates receive prominent amber notices.
- Changed both one-shot updaters to install only validated published releases:
  the exact npm version matching Prime Agent's official tag and the exact commit
  resolved from the private WebUI release tag. Unreleased `main` is no longer an
  update target.
- Restyled Settings into the same grouped card hierarchy as Admin while retaining
  provider configuration, model defaults, account controls, and update history.
- Added numeric semantic-version regression coverage; all 28 local tests plus
  Python, JavaScript, shell, whitespace, and credential-pattern checks pass.
- Deployed commit `a0d82b4`; all 28 deployed tests and four core service checks
  passed. Live authenticated browser inspection confirmed the grouped Settings
  layout and automatic release results: Agent 0.8.0 equals v0.8.0, while the
  unreleased WebUI commit is correctly treated as containing `.1` and up to date.
- Added [ADR-0047](decisions/0047-release-aware-updates.md), immutable snapshot
  [v0070](versions/v0070.md), and root-only pre-change recovery bundle
  `/var/backups/prime-releases-v0070-20260825T204000-0500`.

## 2026-08-25 — v0069 — Add secure provider configuration workflow

- Replaced the full-width configured-provider search with a compact filter and
  **Add provider** action.
- Added a searchable modal catalog based on the providers documented by installed
  Prime 0.8.0: built-in API keys, subscription login, Azure OpenAI, Amazon
  Bedrock, Cloudflare, Vertex AI, and custom OpenAI-compatible endpoints.
- Added admin-only, CSRF-protected configuration endpoints. Secrets are stored
  atomically in Prime's mode-0600 auth/settings files, are never returned, logged,
  or recorded in the wiki, and are cleared from modal fields after use.
- Preserved existing OAuth/auth and local model configuration during updates;
  added tests for write-only keys and custom-model merge behavior.
- Allowed outbound networking for loopback-bound API child tasks so configured
  cloud providers can actually run. Added ADR-0046 and immutable snapshot
  [v0069](versions/v0069.md). All 27 local tests and syntax checks pass.
- Created root-only checksummed pre-change recovery at
  `/var/backups/prime-providers-v0069-20260825T203000-0500`.
- After explicit approval of the outbound-network tradeoff, deployed commit
  `bf1d662`; all 27 deployed tests and four service checks passed, and the live
  unit reports no IP egress deny/allow filter.
- Live desktop inspection verified the compact Settings controls, all 34 catalog
  rows, subscription/configured badges, and a masked provider-specific API-key
  form. The dialog was closed without submission and byte comparison confirmed
  that credentials/model configuration were unchanged.

## 2026-08-25 — v0068 — Refine Admin layout and active rename

- Visually inspected the live Admin tab and corrected concatenated labels,
  collapsed retention copy, cramped user actions, and ambiguous status text.
- Grouped System, Maintenance, and WebUI users into scannable sections; added
  health/role/state badges, a two-column user-action grid, and disabled controls
  that the backend intentionally refuses for the current/initial admin.
- Added a Rename action to the active conversation header. It appears only for a
  saved conversation and refreshes both the active title and sidebar.
- All 25 local tests and JavaScript syntax/whitespace checks pass. Added immutable
  snapshot [v0068](versions/v0068.md).
- Deployed commit `89d3a24`; all 25 deployed tests and four service checks passed.
  Live desktop inspection verified the full Admin/user-card layout and the Rename
  control on a saved active conversation.
- Visual transcript inspection disclosed a separate plaintext credential embedded
  in a historical user script/output. No secret was copied into the wiki; source
  removal, transcript redaction, and credential rotation remain pending approval.

## 2026-08-25 — v0067 — Complete recoverable user-data cleanup

- Extended per-user cleanup to persisted task ownership/logs and owned usage
  ledger records, including records created before an API restart.
- Cache deletion now revokes the affected user's sessions; account enable/disable
  and role changes are separate Admin actions.
- Replaced visible password prompts with masked, validation-enforced password
  dialogs for account creation and resets.
- All 25 local tests and JavaScript syntax checks pass. Updated ADR-0045 and added
  immutable snapshot [v0067](versions/v0067.md).
- Deployed commit `84bd189`; all 25 deployed tests passed, Nginx validation
  passed, Auth/API and both model services are active, negative login returns
  401, and live Auth/API/UI hashes match the repository.

## 2026-08-25 — v0066 — Add isolated user administration

- Added local admin/user accounts with add, role/state change, password reset,
  session revocation, recoverable server-cache deletion, and account deletion.
- Propagated broker-verified identity/role through Nginx and enforced ownership
  for chats, files, tasks/logs, usage, metadata, and all mutations. Existing data
  belongs to `dbyte`; new data records explicit ownership.
- Preserved scrypt and atomic mode-0600 credentials with version-1 migration,
  protected the initial/last admin, and made deletion recoverable.
- All 24 local tests and Python/JavaScript/shell syntax and whitespace checks pass.
  Added ADR-0045 and immutable snapshot [v0066](versions/v0066.md).

## 2026-08-25 — v0065 — Resolve conversation identifier mismatches

- Confirmed 9 of 30 Spark transcripts use a filename ID different from their
  internal Prime session ID, causing false not-found errors from sidebar deletion.
- Added strict bounded resolution of either alias for deletion, opening, and
  export; recovery keeps the true filename and active-work checks protect both.
- Added mismatch deletion and active-alias regressions. All 21 local tests and
  syntax/whitespace checks pass. Preserved a checksummed root-only rollback bundle,
  updated ADR-0029, and added immutable snapshot [v0065](versions/v0065.md).
- The GitHub HEAD updater deployed v0065 successfully. All 22 visible Spark rows,
  including nine mismatches, resolved without deleting user conversations; 18
  applicable deployed tests and all dashboard/model services passed.

## 2026-08-25 — v0064 — Add guarded software updates

- Added confirmed Settings actions and status for updating Prime Agent through
  its bundled Node/npm runtime and updating WebUI from private GitHub `main` HEAD.
- Kept the dashboard network-confined; it starts only two named, locked one-shot
  units. WebUI update requires the exact remote, clean tree, and fast-forward,
  validates Python, redeploys tracked files, and restarts the API.
- Fixed the Archived checkbox/label and conversation row overflow at narrow
  sidebar widths.
- All 19 local tests and Python/JavaScript/shell syntax checks pass. Added
  ADR-0044 and immutable snapshot [v0064](versions/v0064.md); release discovery
  and version comparison remain explicitly planned.
- Exercised both the WebUI one-shot directly and the real dashboard update API;
  both reached private GitHub HEAD, redeployed, restarted cleanly, and reported
  success. Sixteen applicable deployed tests pass. Prime Agent update was not run.
- Added atomic owner-only update result records after systemd proved it discards
  completed one-shot timestamps during unit reload. The deployed WebUI record
  reports success; the untouched Prime updater correctly reports never run.

## 2026-08-25 — v0063 — Add a resizable sidebar

- Added a draggable desktop divider with a 260–700 px/65%-viewport envelope,
  browser-local persistence, and double-click reset to 370 px.
- Added accessible separator semantics and Left/Right/Home/End keyboard control;
  retained the existing divider-free stacked mobile layout.
- All 17 local tests, JavaScript syntax, whitespace checks, installed markers,
  dashboard health, and private HTTPS behavior pass. Preserved a checksummed
  root-only rollback bundle and added immutable snapshot
  [v0063](versions/v0063.md).

## 2026-08-25 — v0062 — Repair Chats deletion

- Diagnosed the delete conflict from the dashboard audit: Prime labels persisted
  idle conversations `lifecycle: live`, and the guard incorrectly treated that
  as active execution.
- Changed protection to actual activity signals while retaining strict IDs,
  double-check-before-move, private timestamped recovery storage, and auditing.
- Made individual failures visible; bulk deletion continues safely and reports
  failed chats. Deleting the currently viewed chat clears the main view.
- All 17 local and 14 applicable deployed tests pass. The deployed guard found
  zero actually active conversations among 30 persisted files without deleting
  any. Preserved a checksummed root-only rollback bundle, updated ADR-0029, and
  added immutable snapshot [v0062](versions/v0062.md).

## 2026-08-25 — v0061 — Restore provider-grouped Usage roll-ups

- Replaced the native UI's regressed flat Usage model list with collapsible
  groups for every configured provider, including OpenAI and OpenAI Codex.
- Provider summaries roll up tokens and recorded spend for Today and Last 30
  days; expansion exposes individual models and remains stable across refreshes.
- JavaScript syntax, 14 local tests, whitespace checks, deployed asset markers,
  service health, and private HTTPS authentication behavior pass. Preserved a
  checksummed root-only rollback bundle and added immutable snapshot
  [v0061](versions/v0061.md). ADR-0020 remains the governing decision.

## 2026-08-25 — v0060 — Make routing and active effort observable

- Added an active-conversation header showing provider/model, editable effort,
  route, and context; the selected effort applies to and persists with the next
  task in that conversation.
- Added deterministic Qwen specialist routing for visual/document, 3D/CAD,
  finance/trading, and deep-review prompts, with explicit model overrides,
  visible disabled-Qwen fallback, and preservation of manually selected defaults.
- Strengthened Prime policy to require an actual Qwen child for specialist
  subtasks in mixed Nemotron work and prohibit unperformed delegation claims.
- Added four routing regressions; all 14 dashboard/auth/security tests, Python
  compilation, JavaScript syntax, and whitespace checks pass locally. Eleven
  deployed Python tests, service/model health, HTTPS boundary, installed assets,
  and on-host route probes pass; 41.1 GB (31.5%) RAM remained available.
- Preserved the prior API/UI/policy and web root in a checksummed root-only
  rollback bundle; added ADR-0043 and immutable snapshot
  [v0060](versions/v0060.md).

## 2026-08-25 — v0059 — Remove Hermes completely from active service

- Disabled and removed Hermes WebUI and gateway services, the 22 GB runtime/data
  tree, launcher, Hermes model/package caches, and identified Hermes-named
  project/setup paths.
- Removed disabled legacy SGLang/TRT-LLM units and their configuration, plus the
  unused 25.5 GB SGLang image. About 44 GB of filesystem use was reclaimed.
- Verified no active Hermes service, process, listener, container/image, cache,
  or installation path remains; port 8787 is closed. Prime, its WebUI, and both
  vLLM endpoints remain healthy.
- Preserved the previously created root-only WebUI recovery copy and historical
  baseline/wiki records; added immutable snapshot [v0059](versions/v0059.md).

## 2026-08-25 — v0058 — Inventory running browser interfaces

- Enumerated live TCP listeners, system/user services, containers, Nginx routes,
  HTTP responses, page titles, and process command lines.
- Verified Prime is the only LAN/VPN-reachable WebUI. Hermes, NVIDIA DGX
  Dashboard, and CUPS are separate loopback-only interfaces; ttyd is an
  authenticated embedded Prime component.
- Distinguished the auth/dashboard/vLLM APIs and Prime kernel-worker ports from
  browser interfaces; added immutable snapshot [v0058](versions/v0058.md).

## 2026-08-25 — v0057 — Validate the dedicated WebUI credential

- The owner created the separate WebUI password through the no-echo interactive
  tool; automation did not handle the password or inspect the one-way record.
- Verified the credential record is mode 0600 inside a mode-0700 owner directory,
  the broker reports it configured, and the owner's browser login returned 200.
- Confirmed the auth broker and Nginx are healthy and no source is currently
  banned; added immutable snapshot [v0057](versions/v0057.md).

## 2026-08-25 — v0056 — Replace PAM with dedicated local WebUI authentication

- Retired PAM and the Linux account password from the WebUI after systemd's
  intentional no-new-privileges confinement prevented Ubuntu's set-group helper
  from reading the account record.
- Added a dedicated password tool that prompts without echo, enforces 12–1024
  UTF-8 bytes, derives a salted scrypt record, and atomically stores it mode 0600
  outside the repository.
- Updated the loopback broker to validate the strict credential record, serialize
  memory-hard derivation, compare in constant time, and fail closed with 503 until
  initial setup. Existing session, CSRF, rate-limit, and Fail2ban controls remain.
- Preserved the pre-v0056 files under
  `/var/backups/prime-local-auth-v0056-20260825T170500-0500`; six tests, Python
  compilation, service/listener checks, Nginx validation, and unconfigured-state
  checks pass.
- Added ADR-0042 and immutable snapshot [v0056](versions/v0056.md).

## 2026-08-25 — v0055 — Recover altered authentication stack

- Diagnosed Nginx 502 responses as a failed authentication helper: its reviewed
  broker had been replaced by an obsolete dashboard server that collided on port
  8765 and contained a non-empty-password authentication bypass.
- Found Prime-specific PAM drift adding `nullok` and an obsolete recreated Nginx
  PAM policy; verified that system-wide common PAM files were unchanged.
- Preserved all altered files and checksums in root-only recovery directory
  `/var/backups/prime-auth-recovery-20260825T165500-0500`, restored the reviewed
  broker and PAM policy, and removed the backed-up obsolete policy.
- Validated loopback-only auth on 8764, invalid-password rejection, login redirect
  and page responses, Nginx syntax, empty ban list, both model health endpoints,
  and byte-for-byte agreement for audited WebUI/security artifacts.
- Added immutable snapshot [v0055](versions/v0055.md).

## 2026-08-25 — v0054 — Correct static asset deployment

- Diagnosed a rendered but nonfunctional login form: its JavaScript/CSS URLs used
  `/assets/`, while deployment had placed the files in the web root.
- Installed all login/native UI JavaScript and CSS under
  `/var/www/prime-agent/assets/`; login assets now return 200 and Nginx validates.
- Added a tracked static installer to preserve the HTML/root and asset/subfolder
  mapping; added immutable snapshot [v0054](versions/v0054.md).

## 2026-08-25 — v0053 — Restrict bans to real login failures

- Diagnosed the apparently offline WebUI as a Fail2ban false positive: the stale
  v0051 page generated repeated expired-session API 401 responses and the owner's
  `172.16.253.114` client entered the nftables ban set.
- Narrowed the filter to 401 responses from `POST /auth/login` only; retained the
  15-failure/10-minute/one-hour reactive policy and added no CIDR policy.
- Validated the filter, restarted Fail2ban, removed the stale ban, confirmed an
  empty ban set, and verified HTTPS from the client returns the login response.
- Added ADR-0041 and immutable snapshot [v0053](versions/v0053.md).

## 2026-08-25 — v0052 — Native session-authenticated Prime WebUI

- Replaced Nginx PAM Basic Auth with a loopback PAM session broker, 30-minute
  idle/12-hour absolute sessions, logout, CSRF, and Origin enforcement; removed
  `www-data` from `shadow`.
- Issued a private-CA server certificate with Spark IP/hostname SANs and exposed
  only its public CA for client installation.
- Replaced terminal-first chat with native Prime JSON tasks, four-task admission,
  process-group stop, 30-minute timeout, safe Markdown/message polling, parallel
  activity, redacted logs, and a native-request ledger. Kept ttyd as Advanced.
- Added search, rename, pin, archive/restore, fork, export, recoverable delete,
  and bulk archive/delete conversation management.
- Added file metadata/selection/previews/deletion/retention and unsafe archive
  traversal/link rejection; added service/storage/task administration and guarded
  restarts.
- A live Nemotron native task completed in 2.3 seconds, persisted its conversation,
  and recorded 6,268 tokens. Seven tests and the complete Spark validation pass.
- Created root-only rollback bundle
  `/var/backups/prime-webui-v0052-20260825T153014-0500`; added ADR-0040 and
  immutable snapshot [v0052](versions/v0052.md).

## 2026-08-25 — v0051 — Harden Prime without CIDR firewall changes

- Created a checksummed, root-only pre-hardening recovery bundle at
  `/var/backups/prime-security-20260825T151200-0500`.
- Restricted PAM to `prime-web`, added Nginx throttling/security headers and
  fail2ban, and retained existing Nginx source rules without adding UFW or a new
  CIDR firewall policy.
- Disabled the default HTTP site, NFS export, NFS/rpcbind services, and wildcard
  Hermes listener; verified all internal Prime services are loopback-only.
- Bounded API concurrency and request types; corrected upload quota/deletion
  races, validation, malformed-session parsing, audit logging, and model IDs.
- Added compatible systemd confinement and local security regression checks. An
  initially incompatible ttyd address-family restriction caused a wildcard bind;
  it was removed and the restored loopback bind was verified.
- Backed up and redacted one transcript containing two credential-shaped OpenAI
  key occurrences; no matching active/trash session files remain. External key
  revocation is still required if that key is active.
- Installed all 19 pending security updates. Application tests, service checks,
  listener checks, headers, fail2ban, NFS shutdown, and the dual-model validation
  gate passed.
- Added [security posture](SECURITY.md), ADR-0039, and immutable snapshot
  [v0051](versions/v0051.md).

## 2026-08-24 — v0050 — Adapt supplied v14 controls and cooling

- Inspected the supplied lower, upper, button, and spacer STL reference meshes.
- Rebuilt the actuator around the reference 10.6 x 8.3 x 5.6 mm envelope and put
  the adjacent LED window through the button face.
- Removed the microSD access cutout at the owner's request.
- Replaced the former vent fields with long floor slots, a honeycomb lid, and
  narrow vertical exhausts around all four upper walls.
- Retained the iUniker-specific case envelope, hardware stack, port bays,
  fasteners, and PETG clearances.
- Regenerated all outputs and passed the installed X2D/PETG slice check with no
  supports, warnings, or filament changes; estimated plate time is 2 h 41 m 9 s.
- Added ADR-0038 and immutable snapshot [v0050](versions/v0050.md).

## 2026-08-24 — v0049 — Correct the Pi 5 native-control end

- Applied the owner's correction that the native button is on the short microSD
  end, near the USB-C corner, rather than near the middle of the connector side.
- Moved the captive actuator opening to that end and added a 2.9 mm sight hole
  for the immediately adjacent bi-colour status LED.
- Exposed the button Y, LED Y, and common Z positions as fit parameters and added
  them to the generated validation report.
- Regenerated the STL, GLB, PNG, and validation outputs.
- Passed the installed X2D/PETG slice check with no supports, warnings, or
  filament changes; estimated three-part plate time is 2 h 29 m 48 s.
- Added ADR-0037 and immutable snapshot [v0049](versions/v0049.md).

## 2026-08-24 — v0048 — Encode photographed INV001 stack assumptions

- Reviewed owner-supplied photographs of the installed iUniker INV001 HAT and
  brass spacer.
- Retained the 85 x 56.5 mm plan envelope and existing compact shell; the photos
  support rather than contradict those dimensions.
- Replaced the opaque vertical allowance with an explicit nominal 16 mm spacer,
  1.6 mm HAT PCB, and 7.4 mm topside component/wiring/air allowance.
- Added the stack values, 8 mm rim air gap, and photographic evidence limitation
  to generated validation output and case documentation.
- Regenerated all outputs and passed the installed X2D/PETG slice check with no
  supports, warnings, or filament changes; estimated plate time is 2 h 29 m 45 s.
- Added ADR-0036 and immutable snapshot [v0048](versions/v0048.md).

## 2026-08-24 — v0047 — Correct INV001 length and compact the case

- Applied the owner's confirmation that the INV001 is the same 85 mm length as
  Raspberry Pi 5 instead of the earlier conservative 90 mm assumption.
- Reduced the internal length from 102 to 95 mm and the external length from 107.6
  to 100.6 mm while retaining connector clearance and ventilation.
- Moved the lid towers outward to clear the now-centered Pi/HAT corners and nearby
  mounting standoffs.
- Regenerated all outputs; the three STLs remain one-body, watertight, winding-
  consistent, and positive-volume.
- Passed the complete X2D/PETG slice again with no supports, changes, or warnings;
  the compact plate estimate is 2 h 29 m 46 s.
- Added ADR-0035 and snapshot [v0047](versions/v0047.md).

## 2026-08-24 — v0046 — Tune the Pi enclosure for X2D PETG Basic

- Tuned walls, sliding clearance, and M3 pilots for a stock 0.4 mm X2D nozzle and
  Bambu PETG Basic.
- Split the 54 mm USB/Ethernet opening into three connector bays, preserving ribs
  and limiting the longest wall bridge to less than 17 mm for support-free PETG.
- Added an X2D-specific Bambu Studio setup, plate orientation, fit-coupon, and
  post-processing guide using the built-in material preset.
- Regenerated the STL, GLB, PNG, and validation outputs; all three printable parts
  remain single-body, watertight, winding-consistent, and positive-volume.
- Resolved Bambu's bundled profile inheritance and passed an actual Bambu Studio
  02.08.02.61 slice with the X2D/PETG profiles, left/main nozzle only, no support,
  no warnings, and no retained printer G-code.
- Added ADR-0034 and snapshot [v0046](versions/v0046.md).

## 2026-08-24 — v0045 — Add vented Pi 5 + iUniker NVMe case

- Added a parametric Raspberry Pi 5 enclosure for the iUniker INV001 M.2 HAT+
  with dense bottom, lid, and rear airflow paths.
- Added primary connector openings, recessed M2.5 stack mounts, an M3-secured lid,
  and a no-wiring printed actuator for the Pi 5 native power button.
- Exported base, lid, and button STLs plus colored GLB and PNG previews.
- Verified all three printable meshes are single-body, watertight,
  winding-consistent, and positive-volume.
- Documented the conservative unpublished-HAT envelope and required physical fit
  check before final printing; added ADR-0033 and snapshot [v0045](versions/v0045.md).

## 2026-08-24 — v0044 — Private dashboard file uploads

- Added a paperclip/file picker and drag-and-drop tray above the conversation.
- Streamed uploads into private mode-0700 storage with mode-0600 files, safe
  stored names, random prefixes, SHA-256, a 100 MiB per-file cap, and 2 GiB quota.
- Added **Copy path** for explicit use in prompts; uploading sends no attach,
  resume, or agent message and cannot interrupt a running task.
- Preserved PAM, private-network ACLs, origin checks, and loopback API binding.
- Validated a live upload's size, checksum, and permissions; rejected an invalid
  origin, confirmed the PAM challenge and loaded Nginx streaming configuration,
  removed the test file, and passed the full Prime gate.
- Added ADR-0032 and snapshot [v0044](versions/v0044.md).

## 2026-08-24 — v0043 — Raise Nemotron context with 20% RAM reserve

- Raised Nemotron's served and advertised context from 65,536 to 81,920 tokens.
- Kept the FP8 KV cache fixed at 12 GiB and maximum concurrency at two, avoiding
  an intentional increase in reserved model memory.
- Set a 20%-of-usable-RAM acceptance floor (about 24.3 GiB available).
- Updated the validation gate to enforce that percentage dynamically; warm
  verification reported 39.1 GiB available (32.15%) and passed both models.
- Added ADR-0031 and snapshot [v0043](versions/v0043.md).

## 2026-08-24 — v0042 — Reboot-safe dashboard startup

- Verified that `prime-web.service` and `prime-dashboard-api.service` restarted
  correctly after reboot, while Nginx failed its explicit LAN-address bind test.
- Added a bounded, fail-closed address wait before Nginx configuration validation.
- Preserved the existing loopback/private listeners, TLS, PAM, and source ACL.
- Added ADR-0030 and reviewable deployment source for the helper and drop-in.
- Snapshot: [v0042](versions/v0042.md)

## 2026-08-24 — v0041 — Correct per-row delete targeting

- Replaced position-based conversation lookup with a full session ID stored on
  each rendered row.
- Updated both right-click deletion and ordinary row selection to resolve directly
  through the clicked row's ID, so the third row targets the third conversation.
- Validation: JavaScript syntax and deployed-code assertions passed; dashboard and
  terminal services plus full Spark validation passed. No conversation was deleted.
- Rollback: restore the v0040 dashboard JavaScript.
- Snapshot: [v0041](versions/v0041.md)

## 2026-08-24 — v0040 — Add recoverable conversation deletion

- Added a custom right-click conversation menu with **Delete conversation** and an
  explicit confirmation prompt.
- Added an origin-protected API action that accepts only strict session IDs,
  rejects every live conversation, and atomically moves inactive JSONL transcripts
  to private mode-0700 recovery storage instead of unlinking them.
- Preserved historical Usage accounting by reading active and trashed transcripts;
  deleted rows disappear from the Conversations catalog only.
- Validation: Python/JavaScript checks passed; the live API rejected a traversal-
  style ID with HTTP 400, the 40-row catalog remained intact, UI assets deployed,
  and full Spark validation passed. No real conversation was deleted in testing.
- Rollback: restore v0039 API/HTML/JavaScript and remove `conversation-menu.css`.
  Previously moved transcripts remain recoverable in session trash.
- Snapshot: [v0040](versions/v0040.md)

## 2026-08-24 — v0039 — Hide attach artifacts from Conversations

- Identified eight saved sessions whose sanitized first-user topic was exactly
  `attach`, created by earlier attachment behavior.
- Filtered those artifacts at the API layer before applying the 40-row limit, so
  genuine older conversations replace them. No session history was deleted.
- Validation: the deployed API returned 40 conversations and zero exact `attach`
  topics; dashboard service and full Spark validation passed.
- Rollback: restore the v0038 dashboard API; retained JSONL artifacts will reappear.
- Snapshot: [v0039](versions/v0039.md)

## 2026-08-24 — v0038 — Clarify minimized overlay control

- Changed the overlay header control from a static minus to a state-aware symbol:
  minus while expanded and plus while minimized.
- Synchronized its tooltip, accessible label, and `aria-expanded` value.
- Validation: JavaScript syntax and deployed-code checks passed; dashboard/terminal
  services and full Spark validation passed.
- Rollback: restore the v0037 dashboard JavaScript.
- Snapshot: [v0038](versions/v0038.md)

## 2026-08-24 — v0037 — Separate explicit attachment from UI behavior

- Corrected v0036's over-broad policy: session attachment remains available, but
  the dashboard UI contains no attach command, URL, control, or iframe.
- Restored launcher attachment behind an exact `--attach ID --explicit` form with
  strict ID syntax and existing-session validation. Stale two-argument attach URLs
  fail with exit 64 and cannot fall through to start Prime.
- Removed the reconnecting stale client PID 3149324 after installing the guard;
  only the main terminal client PID 3113237 persisted.
- Validation: deployed JavaScript contains no attach behavior; stale-form rejection
  and one-client persistence passed; both services and full Spark validation passed.
- Rollback: restore v0036 launcher only to disable explicit browser attachment;
  retain the v0037 event-only dashboard JavaScript.
- Snapshot: [v0037](versions/v0037.md)

## 2026-08-24 — v0036 — Retire browser session attachment

- Removed the extra ttyd attachment client identified as PID 3111439 while
  preserving the original main terminal client PID 3111303 and daemon worker.
- Retired the overlay live-console control and removed its deployed stylesheet.
- Changed `prime-web-launch` to reject every `--attach` request with exit 64 and
  no Prime launch, including protection against stale cached browser JavaScript.
- Validation: only the original ttyd client remained; attach rejection passed;
  ttyd and dashboard services stayed active; full Spark validation passed. ttyd
  was deliberately not restarted so the running job was not interrupted.
- Rollback is not recommended while work is active. To restore later, redeploy
  v0035 wrapper/HTML/activity/live-console assets after confirming attach safety.
- Snapshot: [v0036](versions/v0036.md)

## 2026-08-24 — v0035 — Move Stop task to the conversation window

- Removed the Stop task control from both activity-overlay views.
- Added a running-task bar above the main terminal with the guarded Stop task
  action; it follows an active sidebar selection and offers a selector for parallel
  running conversations.
- Preserved confirmation, active-ID validation, conversation retention, and
  single-agent Prime stop semantics.
- Validation: JavaScript and asset checks passed; deployed HTML contains the sole
  visible Stop task button in the main workspace; full Spark validation passed.
- Rollback: restore v0034 HTML/JavaScript/CSS and remove
  `conversation-control.css`.
- Snapshot: [v0035](versions/v0035.md)

## 2026-08-24 — v0034 — Move overlay and add provider switches

- Moved the activity overlay's default position from bottom-right to top-right,
  including a top inset on narrow screens; dragging and resizing remain available.
- Rebuilt Parameters' model menu from live configured models and added a searchable
  provider list with enable/disable switches backed by Prime `enabledModels`.
- Guarded against disabling the selected default provider and against empty,
  unknown, or unconfigured provider submissions. Enabling a provider activates all
  models currently discovered for it; changes apply to new tasks after Save.
- Validation: local allowlist/default-provider tests passed; the live API found four
  configured providers and preserved the existing three enabled providers through
  a no-change save; deployed layout checks and full Spark validation passed.
- Rollback: restore v0033 API/HTML/JavaScript/activity CSS and remove
  `provider-settings.css`.
- Snapshot: [v0034](versions/v0034.md)

## 2026-08-24 — v0033 — Add per-task stop control

- Added a confirmation-gated **Stop task** button to the event and live-console
  views for every active task.
- Added an origin-protected API action that validates a strict, currently active
  session ID and invokes Prime's native single-agent stop command. Saved
  conversation history remains intact; other workers and the supervisor continue.
- Validation: local command-construction/inactive-ID tests passed; the deployed API
  rejected a malformed target with HTTP 400; dashboard service and Spark model
  validation passed. No live task was interrupted during validation.
- Rollback: restore v0032 API, JavaScript, and `live-console.css` assets.
- Snapshot: [v0033](versions/v0033.md)

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
