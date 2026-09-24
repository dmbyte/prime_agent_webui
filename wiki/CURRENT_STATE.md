# Current State

Last verified: 2026-09-24
Wiki version: `v0174`

## Project summary

The Spark now runs Prime Agent as the local orchestration core with two
concurrently resident NVFP4 models. The operating policy covers 3D-print design,
portfolio evaluation, paper-trading research, and supporting code. The repository
now also contains its first generated, kernel-validated 3D-print design: a vented
case for Raspberry Pi 5 with the iUniker INV001 NVMe HAT+.

## Repository state

- The v0.5.39 recovery fix addresses a power failure during an OpenShell task
  that left the protected Prime agent
  directory with an ACL mask of `---`. The preserved 58 protected transcripts
  and 35 legacy transcripts remained on disk, but the WebUI could not traverse
  the protected tree and showed no chats. Restoring the ACL made the live API
  return 40 owner-visible chats and 2 projects. The system broker now runs
  `prime-runner-recover` before every start to restore traversal and managed
  writable-tree ACLs after an interrupted task. Durable WebUI sessions remain
  intentional, so a valid saved browser session does not prompt for login after
  a reboot.

- The v0.5.38 canary follow-up fixes a false `task broker exited` result. The
  launcher had a daemon thread blocked in `sys.stdin.buffer.readline()` when
  Prime ended; Python finalization failed to acquire that buffered-reader lock
  and aborted with signal 6. Control forwarding now uses unbuffered `os.read`,
  and regression tests prohibit the old call. Repeated OpenShell activation
  also copies legacy workspaces with `--ignore-existing`, so stale migration
  sources cannot overwrite the current task workspace or managed policy. A
  deployed shutdown canary acknowledged state and abort, removed its sandbox,
  and emitted neither the fatal runtime error nor a broker-exit event.

- A post-deployment v0.5.36 canary proved the custom immutable kernel still
  omitted Prime's bundled Python skill packages: `agent_message` existed in the
  namespace only as `_PrimeAgentUnavailableSkill`, and direct import failed.
  v0.5.37 installs and import-verifies all eleven bundled Python-backed skills
  during image construction, then repins all six image IDs. This completes the
  repair at the runtime layer rather than relying only on prompt compliance.

- The v0.5.36 runtime-alignment fix upgrades all six WebUI/OpenShell task
  images from Prime 0.8.0 to 0.9.5, matching the already-updated host. It pins
  the official 0.9.5 artifact checksum and new exact image IDs. The managed
  task policy now uses `await rlm.spawn(...,
  model="spark-qwen/qwen3.8-flash-next")`, warns that omitting `model` inherits
  Nemotron, and requires `agent_message.send` to execute inside `ipython`
  rather than as a model tool call. Install/update refreshes only policies with
  the managed heading, preserving a timestamped backup; unrelated custom
  policies remain untouched. This repairs the observed `Tool
  agent_message.send not found` failure and the unintended Nemotron child.

- The v0.5.35 model profile expands Qwen 3.8 from 32,768 to 98,304 tokens and
  changes both K and V cache from Q8 to Q4. Nemotron is rebalanced to 65,536
  context, a 2 GiB FP8 KV reserve, and a 0.35 startup memory ceiling. Prime's
  host and OpenShell catalogs advertise the matching 65,536/98,304 limits.
  The live Spark accepted an exact 78,000-token Qwen prompt, recovered
  `LANTERN-4827` from a 77,034-token prompt, and kept both endpoints healthy.
  Warm short-context Qwen decode reached 44.76 model-eval token/s; at 78K it
  measured 29.56 token/s. The stressed co-resident state retained
  20,171,890,688 bytes (15.44%) available memory. ADR-0098 records the narrow
  headroom and required one-slot/automatic-compaction constraints.

- v0.5.34 is published and deployed with all six exact OpenShell image IDs. A
  final genuine Prime task on the installed network-operations image became
  browser-ready in 0.46 seconds, navigated read-only to the actual BMC with
  HTTP 200, closed, and completed without error. The v0.5.34 updater makes
  future in-app WebUI updates run the identity-verifying OpenShell
  installer when OpenShell and Docker are installed, preventing UI/runner
  updates from reporting success while older profile images remain active. A
  live already-current updater run rebuilt and verified all six IDs before
  reporting success; dashboard, authentication, gateway, runner, and model
  services are active, and no diagnostic sandboxes remain.

- The v0.5.33 release candidate fixes the real Prime/OpenShell BMC browser
  failure at both proven boundaries. New sandboxes receive `/dev/urandom`,
  `/dev/random`, and `/dev/shm` access at creation, allowing Chromium NSS/TLS
  initialization under monotonic Landlock confinement. The network-operations
  entrypoint starts a private mode-0600 browser broker before Prime so workers
  inherit the approved recipe egress bridge and remain independent of Prime's
  persistent kernel. A genuine WebUI API task opened three browser sessions in
  0.46–0.48 seconds and navigated read-only to the actual BMC with HTTP 200.
  Six normalized ARM64 candidate images are pinned by exact ID. ADR-0097
  supersedes ADR-0096.

- The BMC browser fix is published and deployed as v0.5.30 at `ea2a323`.
  v0.5.29's activation was safely rejected before image installation because
  its manifest came from an overly broad pre-release context; v0.5.30 uses the
  installer's exact three-package context and supersedes it. All six production
  image IDs match. Dashboard, authentication, OpenShell gateway, runner broker,
  and model gateway services are active. A final genuine Prime task using the
  installed network-operations image completed browser enter, page creation,
  and close in 21.8 seconds. No BMC was contacted. Diagnostic sandboxes,
  candidate images, temporary trees/manifests, and profiler files were removed.


- A controlled browser startup through the *actual OpenShell sandbox create +
  exec path*, using the approved network-operations image, production volumes,
  and task-style limits, successfully reached `BMCBrowser.__aenter__` and
  created a page in under two seconds. The ephemeral diagnostic sandbox and
  policy file were removed. Together with two bounded Prime failures at
  `BrowserContext.new_page()`, this localizes the fault to Playwright's
  interaction with Prime's persistent IPython kernel, not Chromium packaging,
  OpenShell policy, BMC networking, or nested `asyncio.run()` alone. The exact
  internal kernel/driver deadlock remains unproven. A supported fix should run
  browser automation in a dedicated subprocess or repair the Prime kernel
  integration, with per-step timeouts and captured stderr; no fix is deployed.


- The same 20-second Playwright DEBUG probe succeeded in reaching `ipython`
  from a new, short Qwen conversation, but again timed out at
  `BrowserContext.new_page()` before BMC navigation. Its debug stream was not
  forwarded into the task log or Docker logs, so no browser-process diagnostic
  beyond the Python traceback was obtained. The task completed and its
  OpenShell sandbox was removed. Repeated bounded Prime probes establish the
  `newPage` wait; standalone `docker exec` launches are not a conclusive
  OpenShell-policy equivalent. A subprocess-backed browser adapter or an
  OpenShell-exec reproduction is the next engineering test, not another blind
  30-minute task retry.


- The Playwright DEBUG repeat did not execute the browser probe: the resumed
  long conversation routed to `spark-qwen/qwen3.8-flash-next`, and the model
  gateway rejected its 38,379-token request against the 32,768-token context
  window. The task failed before any `ipython` call; this is a context-budget
  issue separate from the confirmed `BrowserContext.new_page()` timeout.
  Repeat the bounded debug probe in a new conversation to avoid inherited
  history. The submitted prompt remains in the task metadata.


- A fresh Prime task ran the bounded direct-`await` browser probe in the
  `network-operations` profile. It printed “entering browser” and then
  returned a 15-second `TimeoutError`. The traceback pinpoints the wait to
  `BMCBrowser.__aenter__` at `BrowserContext.new_page()` (Playwright channel
  request `newPage`). Browser launch and context creation had already returned.
  No BMC navigation or credentials were used. This disproves the narrower
  hypothesis that nested `asyncio.run()` alone caused the hang. No Chromium
  crash, OOM, or policy-denial message appeared in the retained task and kernel
  logs. Renderer/new-page startup under Prime's live kernel remains the
  unresolved boundary; a follow-up with Playwright browser debug logging is
  needed. Direct `docker exec` reproductions are informative but may not enforce
  the same OpenShell process path as Prime's task launcher.


- Live diagnosis of the repeated BMC browser attempt (2026-09-22): three
  attempts reached `ipython` and emitted no browser-ready message or tool
  result. In the newest attempt the Playwright Node driver started, but no
  Chromium process appeared; a read-only kernel stack snapshot showed the
  cell waiting inside nested `asyncio.run()`. The same immutable browser adapter
  launched Chromium successfully in the *same live sandbox* from standalone
  Python, from a fresh IPython kernel using direct top-level `await`, from that
  kernel using `nest_asyncio` plus `asyncio.run`, and from a forked Python
  process. Thus the image/browser/policy are sound; the unresolved failure is
  specific to Prime's live persistent IPython execution state. The next
  discriminating test is a fresh Prime task using top-level `await` directly
  with a bounded browser-startup timeout and stage markers, without BMC login.
  Do not present the event-loop hypothesis as confirmed until that test runs.


- Live task diagnostics now retain each sanitized runtime line in a private
  mode-0600 log as it arrives. The chat trace shows startup stages and how long
  the runtime has been silent; right-click or **Complete output…** opens the
  full owner-scoped log while running, refreshed every three seconds. A missing
  transcript no longer hides the submitted prompt or task trace. The reported
  task reached `ipython` within seconds and then emitted no more output for at
  least 18 minutes, explaining the apparent “Starting Prime” stall. The task
  reached its 30-minute limit without another tool result. v0.5.28 is published
  at `561af55` and deployed on Spark after the task timed out. All 113
  dashboard tests, four managed-skill tests, and JavaScript syntax validation
  pass. Dashboard, auth, and broker services are active; installed API, browser
  asset, and runner launcher match the release; the historical task log is
  owner-readable through the new chunk API and denied to another user.


- v0.5.27 corrects the BMC browser under OpenShell's enforced runtime, not only
  conventional Docker. Each invocation receives private ephemeral HOME/XDG
  state under writable `/tmp`, preventing Debian Chromium crashpad startup from
  touching the read-only image home. Headless Chromium also disables its GPU
  and zygote subprocesses, which OpenShell's process restrictions block. The
  final adapter successfully launched, navigated, and read a page inside an
  actual policy-enforced sandbox with the production volumes.
  The temporary image context also normalizes source modes, preventing the
  host checkout's group-write ACLs from changing reviewed image IDs.
  v0.5.27 is published and deployed at `b43ecc6`. All 113 release tests pass,
  all six installed image IDs match the manifest, and a fresh final-image
  OpenShell browser test returned `OpenShell-release-ok`.

- v0.5.25 preserves lazy skill selection while making the managed Python
  adapters usable by Prime's supported immutable kernel. All six OpenShell
  images contain the small BMC and NVIDIA-router modules; full instructions are
  read only after routing selects a skill. Playwright exists only in the
  `network-operations` image and is imported and started only when a BMC browser
  context opens. Reproducible image IDs are pinned for all profiles. Imports
  passed in all six candidates, and the network profile launched its real
  system Chromium successfully. Generated Python bytecode is excluded from the
  normalized context so prior test/import runs cannot alter image IDs.
  v0.5.25 is published and deployed at commit `e38e7ba`; the full 113-test
  release suite passes. The installed manifest matches the release, every live
  image matches its pinned ID, Prime's own kernel check accepts all three
  managed modules, and all WebUI/OpenShell services are active.

- v0.5.23 adds a reproducible protected global skill installation. The official
  NVIDIA skills repository is pinned at commit
  `fd9f1466ff8a39178e488981e8b5118709392949`; all 366 skill trees are validated
  and stored unchanged under Prime's protected catalog path. A single
  `prime-nvidia-catalog` Python skill searches and reads a selected entry on
  demand, avoiding roughly 12,800 catalog-description tokens in every task.
  The Prime-created `bmc-headless-browser` and `ipmi-redfish-bmc` tools are now
  proper Prime Python skills. The browser uses the immutable
  network-operations Chromium; Redfish discovers standard resources; IPMI uses
  `ipmitool` without putting its password on the command line; and all power
  mutations require explicit code-level confirmation. Previous managed content
  is retained in recovery. v0.5.23 is published and deployed at commit
  `9752e2d`. The catalog manifest reports 366 entries at the pinned commit;
  Prime discovers the three managed packages as Python skills with zero loader
  diagnostics; package installation, catalog search, imports, and a real
  headless Chromium launch passed. The dashboard, authentication, OpenShell,
  task broker, and model gateway services are active. The final stale Qwen 3.6
  workspace instruction was replaced with `spark-qwen/qwen3.8-flash-next`.

- v0.5.22 adds governed skill and tool management to the WebUI. Users submit a
  personal or project-scoped ZIP plus declared access, dependencies, and system
  tools; administrators review source hashes and declarations before approval.
  Approved instruction skills are bounded, traversal-safe extractions into the
  user's host-visible persistent workspace registry. Existing installs and
  removals use recovery storage. Project settings select enabled reviewed skills
  and inject their registry locations into project context. Dependency commands
  are not run during approval, and system-tool requests require an immutable
  sandbox image change. The Admin page also inventories shipped profile tools.
  Administrators can download the submitted source archive for review before
  approval. The full dashboard suite passes 109 tests. v0.5.22 is published and
  deployed at commit `7b22ab5`; the updater succeeded, both WebUI services are
  active, and release status reports the installed version as current.

- The OpenShell skill/tool installation repair is prepared for v0.5.15. Skills
  persist in `/home/prime/.prime/agent/skills`; the common
  `/project/.prime/agent/skills` path is linked to that registry, and existing
  workspace-only skills are copied before their original directory is retained
  as a timestamped recovery backup. Every profile now contains pip, uv, and
  npm; their caches and user-level tool content live below the existing writable
  per-user Prime volume. `/project/.venv/bin` is on task `PATH`, providing a
  supported persistent project-dependency workflow. The guarded
  network-operations profile also contains Chromium and ipmitool. Tasks remain
  non-root and `/usr` remains read-only. The OpenShell installer now selects the
  tracked `Containerfile` explicitly and all six rebuilt ARM64 image IDs are
  pinned in the manifest. The replacement v0.5.16 installer uses NVIDIA's
  actual `openshell_0.0.116-1_arm64.deb` asset name and skips the download when
  the pinned OpenShell version is already installed. The final v0.5.17 installer
  normalizes a temporary copy of the reviewed build context before rebuilding,
  preserving exact approved image-ID verification across clean checkouts;
  v0.5.15 through v0.5.18 are superseded by v0.5.19, which also normalizes the
  executable mode affected by the Spark checkout's group-writable umask and
  explicitly provisions every per-user gateway directory before volume setup.
  v0.5.20 also checks protected mode-0700 runner paths through sudo rather than
  falsely treating the WebUI owner's expected lack of traversal as absence.
  v0.5.20 was published and deployed. Targeted live verification confirmed the
  exact tag, active dashboard/broker/gateway services, healthy HTTPS, persistent
  skill migration/linking, pip/uv/npm, writable persistent cache/tool paths,
  and Chromium/ipmitool in network-operations. The broad validator reached its
  existing 15% free-memory gate while both models were resident; all runtime-
  specific checks passed separately.

- The production-local `wiki/`, `cad/`, repository/Prime agent instructions,
  evaluation refinements, and saved Prime skills remain on this workstation but
  are ignored and no longer tracked by the upstream WebUI repository. The Spark
  runtime and its installed copies are unchanged. Published tag `v0.3.0` retains
  the earlier snapshot; current `main` removes these paths without rewriting
  history.
- GitHub publication is being advanced to `v0.5.14`. The v0.5.14 source tree
  removes the superseded task-runtime source and the retired Qwen local service,
  adds reproduction docs for OpenShell, Nemotron 3.5 Lightning, and Qwen 3.8
  Flash-Next, includes the architecture artifacts under `docs/architecture/`,
  patches the Projects UX so existing chats expose visible project actions, and
  fixes the OpenShell task launcher so sandbox creation cannot consume the
  initial Prime RPC stdin intended for the task exec. The WebUI updater now also
  installs the privileged launcher, runner client, broker, model gateway, and
  helper modules so future updates carry the full OpenShell runtime boundary.
  Prime RPC input is relayed into a sandbox FIFO because OpenShell 0.0.116 waits
  for CLI stdin EOF before starting `sandbox exec`; the broker terminates the
  per-task launcher when the dashboard client disconnects so completed tasks
  clean up their OpenShell sandboxes. Accepted prompts are persisted in the
  WebUI task record immediately, and failed/stopped/timed-out tasks that end
  before Prime creates a session are recovered as normal conversations with the
  submitted prompt and runtime failure notice. Live task progress no longer
  updates the chat-title subtitle; it renders as a model-aware, collapsible task
  trace inside the conversation stream, using labels such as `prime-nemotron`,
  `prime-codex`, and `prime-qwen` while keeping private chain-of-thought
  redacted as safe status text.
  After a live `OpenShell task runtime exited` resume failure, the OpenShell
  runner now starts Prime with a per-task sandbox-local daemon socket instead of
  Prime's default daemon socket path. This avoids stale failed-worker records
  from earlier ephemeral OpenShell sandboxes blocking later conversation
  resumes. The failed task's submitted `resume` prompt was present in saved task
  metadata, and final task status is now mirrored back into saved metadata for
  tasks attached to existing conversations.
  OpenShell task workspaces are now separated from protected Prime state:
  `/project` inside each task maps to `~/prime-agent/tasks/USER/` on the host,
  while sessions, credentials, and internal Prime metadata remain under
  `/var/lib/prime-runner/users/USER/prime`. The installer and WebUI updater
  create the home-backed task root, apply runner/WebUI ACLs, migrate legacy
  workspace files, refresh Docker bind volumes, and restart the broker service
  with the updated boundary. The v0.5.10 volume helper explicitly returns
  success when an existing bind volume already points at the expected path. The
  v0.5.11 scripts apply recursive host-user ACLs to migrated task files so the
  home-backed workspace is actually browsable from the host. The local-path
  picker still rejects arbitrary `/home` paths.
  The GitHub README now explicitly lists the deployed Spark switches and
  parameters for Nemotron 3.5 Lightning, Qwen 3.8 Flash-Next, and OpenShell,
  including model images/checkpoints, listeners, context/KV settings,
  speculation settings, memory limits, sandbox creation/execution flags,
  filesystem policy, Docker volumes, and workspace paths.

- Workspace: `/Users/byte/Documents/Codex/dgx-spark`
- A five-slide, editable PowerPoint reference architecture now documents the
  proposed enterprise Linux and AI operating model. It preserves the fleet-first
  overview, detailed SUSE AI Factory with NVIDIA platform map, and closed-loop
  troubleshooting sequence, then adds a deep implementation topology and gated
  dependency-order build sequence. The topology separates management, AI
  workload, data/observability, and Linux-management planes and makes Kubernetes,
  RAG, OTLP, and OAuth/mTLS-protected MCP contracts explicit. It includes
  Rancher Prime, RKE2, AI Factory/Fleet, SUSE Security, OpenShell, Hermes, NeMo
  Agent Toolkit, Universal Proxy, Switchyard, NIM Operator/NIMCache/NIMService,
  Nemotron, Qwen through a validated vLLM or SUSE endpoint, embedding/rerank
  NIMs, Run:ai, GPU/Network Operators, Retriever, Qdrant/Milvus, OpenSearch,
  object storage, MLflow/Kubeflow, OpenTelemetry, SUSE Observability, Uyuni MCP,
  Multi-Linux Manager, execution channels, and the heterogeneous managed estate.
  Artifact: `docs/architecture/agentic-enterprise-linux-reference-architecture-v3.pptx`.
- A companion 12-page DOCX translates the topology into implementation
  pseudocode. It defines phases 0–7, exit gates, ownership, global configuration,
  OpenShell and MCP policies, read-first fleet enablement, incident remediation,
  approval objects, GitOps promotion, acceptance tests, rollback, go-live checks,
  and primary references. The implementation rule is security and telemetry
  before model or fleet write authority; SUSE Multi-Linux Manager remains the
  fleet authority and direct SLES 16 MCP remains an opt-in technology-preview
  exception. Artifact:
  `docs/architecture/enterprise-linux-ai-factory-implementation-pseudocode-v1.docx`.
- These are design artifacts only; no runtime service, model, cluster, or managed
  Linux system was changed.
- Version control: Git `main`, private GitHub repository
  `https://github.com/dmbyte/prime_agent_webui`, tracking `origin/main`
- Reviewable deployment source: `deploy/spark/`
- Portable entry points: repository-root `README.md` and `install.sh`; the
  installer detects Debian, Red Hat, and SUSE families, installs the host-mode
  prerequisites, installs pinned Prime Agent 0.9.5, provisions private TLS,
  Nginx, dedicated WebUI authentication, and hardened user services, then
  verifies telemetry and the unauthenticated 401 boundary. The Spark OpenShell
  installer is now self-contained for the supported DGX Spark runtime: it
  verifies the pinned upstream package, creates the dedicated runner/gateway
  services, installs the dashboard runtime drop-in, copies existing owner state,
  builds/validates the six Docker images, copies narrow runner mTLS material,
  provisions per-user volumes, and backs task work with
  `~/prime-agent/tasks/USER/`; none of the installers changes the firewall.
  Installation documentation now explicitly rejects PAM/Linux-password login,
  explains that the installer-account name is only the initial WebUI identifier,
  and documents the non-root `prime-web-password` plus `prime-auth.service`
  restart process for initial setup or rotation.
- Release validation: `scripts/validate-release.sh` checks required artifacts,
  shell and JavaScript syntax, Python compilation, and the full dashboard test
  suite. It passed 97 tests after removing the superseded runtime-specific source
  and tests, replacing them with OpenShell/shared-helper coverage, refreshing the
  docs for v0.5.12, adding static coverage for visible chat project actions,
  proving the WebUI updater copies the shared OpenShell task helper into the
  live dashboard directory before API restart, and covering the launcher stdin
  fix, FIFO relay, client-disconnect cleanup, system-service status checks, full
  privileged helper installation, stale user-unit migration, failed-prompt
  recovery, saved final task status for existing-conversation runs, per-task
  Prime daemon sockets for OpenShell resumes, the host-backed
  `~/prime-agent/tasks` workspace root, broker-unit refresh, Docker bind-volume
  reprovisioning, the co-resident Nemotron memory target, and the
  conversation-stream model-aware task trace, and scoped persistent security
  approval. The public-facing sample
  screenshot contains only synthetic data and names OpenShell plus Qwen 3.8.
- The message composer now distinguishes a successfully accepted task from a
  later conversation-refresh failure. Once `/api/tasks/start` returns a valid
  task identifier, the submitted prompt remains cleared and the task stays in
  its working state even if the immediate message refresh transiently fails;
  prompt restoration is reserved for a genuine task-start failure.
- WebUI authentication now uses durable mode-0600 session state under
  `~/.config/prime-agent/web-sessions.json`. The default idle window is 30 days
  and the absolute lifetime is 180 days, replacing the previous 30-minute idle
  and 12-hour absolute limits. Valid sessions survive authentication-service and
  WebUI restarts; activity persistence is throttled to five-minute intervals.
  Explicit logout, password rotation, administrator revocation, account
  disablement/deletion, and both expiry limits still revoke access. v0.5.14 is
  published and deployed; the Spark reports the exact tag, active auth/API/task
  broker services, the expected 30/180-day defaults, and healthy HTTPS. The
  durable store will be created mode 0600 by the next successful login.
- The seven top sidebar statistics now render one-second live sparklines for
  CPU, GPU, memory, power, and temperatures. Each compact card overlays its
  current value as a large translucent watermark, retains 60 browser-local
  samples, and expands on hover or keyboard focus for a larger live graph. No
  telemetry history is persisted server-side. v0.5.13 is deployed on the Spark;
  live browser inspection verified all seven cards, accumulating one-second
  histories, visible graph/value overlays, and the expanded focused-card view.
- The active conversation now displays live task progress as a collapsible trace
  card in the message stream rather than as detailed status beneath the chat
  title. While a task is running, the trace stays open and shows safe
  actor-prefixed progress lines derived from the runtime event feed, for example
  `prime-qwen: using tool`, `prime-codex: reasoning in progress`, or
  `prime-nemotron: drafting response` depending on the active model route. Once
  the task completes or fails, the trace collapses but remains available for
  review. Private reasoning content remains redacted; the UI only displays safe
  progress summaries.
- The Prime sidebar now has account-scoped projects modeled on the native
  ChatGPT/Codex project workflow. Projects group independent conversations and
  carry a name, icon, color, pin state, shared instructions, up to 40 shared
  uploaded sources, and default sandbox/tool/network/proposal/local-path
  controls. New chats started inside a selected project inherit a copy of its
  context and control defaults; after creation, conversation settings persist
  independently and later project edits do not rewrite them. Existing chats can
  be promoted into a new project or added to an existing project, including their
  related uploads and saved chat controls, from a visible boxed `...` button
  beside each sidebar chat or the active chat header's **Add to project** /
  **Move project** button. New projects inherit the promoted chat controls as
  defaults; existing projects keep their defaults while merging assets. Project
  deletion removes only the container and returns its chats to the unprojected
  Chats list.
  Source copies live in the authenticated owner's Prime state, are refreshed
  only when a project task starts, and are covered by a more-specific read-only
  OpenShell filesystem rule. Project context is sent to Prime but removed from
  the user-visible transcript. The deployment passed all 81 tests and live
  browser inspection of the sidebar, top conversation toolbar, Settings/Admin
  collapses, OpenShell update row, and project-promotion dialog presence.
- Sandbox image, execution, network, proposal-approval, and Spark-path selections
  now live in a toolbar directly below the conversation header rather than in
  the message composer. They are conversation-scoped: the first
  task in a new conversation records the selected values; reopening that chat
  restores them, and changes on a saved chat are persisted immediately. The
  toolbar and project defaults also include **Security prompts** with **Ask each
  task** and **Always allow for this chat/project**. Always-allow is owner-scoped
  and suppresses repeated execution, private-network, automatic-proposal, and
  local-path prompts only when the complete requested policy exactly matches
  the saved conversation or project policy. A new standalone chat receives
  normal confirmations on its first task before the choice is stored. Role
  limits, OpenShell policy construction, sandbox isolation, and resource limits
  remain enforced. v0.5.12 is deployed on the Spark; live verification found
  the tagged checkout, dashboard API, and runner broker healthy, HTTPS returning
  200, and the installed browser asset containing the new scoped control.
- The sidebar Projects and Chats lists, Settings sections, and Admin sections
  are collapsible and remember their open/closed state in the browser. Admin is
  grouped into System, Maintenance, Routing rules, and WebUI users; Settings is
  grouped into Model & context, Providers, Software updates, and Account.
- Settings now tracks OpenShell in the software update section alongside Prime
  Agent and the WebUI. The OpenShell updater uses the official
  `NVIDIA/OpenShell` latest stable release, accepts only the ARM64 `.deb`,
  verifies `openshell-checksums-sha256.txt`, refuses to run while sandboxes
  exist, restarts `openshell-gateway`, validates both owner and `prime-runner`
  access, records the installed API version, and restarts the dashboard API.
  Live verification found installed OpenShell `0.0.116` matching latest
  `v0.0.116`, so the update button was correctly disabled as up to date.
- Power users and administrators can now assign up to eight Spark-local files or
  directories to a conversation from a **Files & directories** control beside
  Profile, Execution, and Network. Paths persist as conversation preferences but
  require fresh confirmation for every task. The privileged runner canonicalizes
  each source, permits only `/mnt`, `/media`, `/srv`, and `/opt`, rejects
  special objects and credential/Prime-state directories, and exposes inputs
  read-only beneath `/project-files` through pre-provisioned OpenShell Docker
  volumes. `/home` remains intentionally excluded while the broker masks `/home`
  and `/root`; ordinary users retain isolated uploads and workspaces and cannot
  request host-path mounts.
- Spark-local inputs intentionally exclude `/home` while the hardened broker
  masks that tree. The affected app-development conversation had stored
  `/home/byte/work`, which is neither a Spark path nor accessible to the broker;
  its latest task therefore failed before a container started, leaving the prior
  kernel error as the newest visible assistant message. The metadata was backed
  up and that unusable path removed while preserving Development + Internet.
  Policy validation now rejects `/home` immediately, and the browser renders a
  failed-task notice directly in the dialogue instead of making an older answer
  appear current. Use a Spark-resident shared path under `/srv`, `/mnt`, `/media`,
  or `/opt`; paths on the Mac are not directly mountable by a remote Spark task.
- A rejected local-path launch can no longer hide conversation history. The
  runner now places gateway checks, path validation, OpenShell command
  construction, and sandbox startup inside the same unconditional
  ACL-restoration boundary. This
  corrects the observed case where a failed directory-enabled launch left the
  parent ACL mask at `---`, preventing the WebUI owner from traversing 17 intact
  session files. The intended traverse-only `--x` mask was restored without
  rewriting conversation data, and a live nonexistent-path regression proved it
  remains restored after pre-launch failure.
- Conversation listing now remains stable while Prime is actively protecting its
  state tree. An empty result during a running owner task no longer replaces the
  last known-good catalog, known conversation metadata can be updated without
  statting the temporarily inaccessible session file, and a mode-0600 catalog
  snapshot in WebUI metadata survives API restarts. Cached-row formatting also
  avoids per-session filesystem stats. A controlled fresh-process test with the
  parent ACL mask deliberately set to `---` returned all 10 current sidebar rows
  from the durable cache; the intended `--x` mask was then restored.
- Task execution is independent of the browser session lifecycle. Closing the
  tab/window sends no unload, beacon, abort, or stop request. WebUI sign-out only
  removes the authentication broker's session token and expires its cookies; it
  does not call `/api/tasks/stop`, signal Prime, or revoke an already-authorized
  task. Re-authenticating can observe a task still tracked by the running API.
  An administrative restart of `prime-dashboard-api.service` remains different:
  the current task-control process is a child of that service and may be
  interrupted by a service restart. Browser close/sign-out require no such
  restart and therefore continue execution.
- ChatGPT subscription access is configured and 13 `openai-codex` models are
  enabled, but the 17 inspected production conversations contain no
  `openai-codex` assistant messages, so the Usage tab correctly reports zero
  Codex tokens. The 24 observed `openai/gpt-5.4` records are failed API attempts
  with explicit zero usage. Prompt prose assigning an “architect” role to Codex
  did not itself launch a Codex child agent; routing/orchestration must be changed
  before Codex usage can be generated and counted.
- Request routing is now data-driven and admin-managed. The Admin tab lists
  priority-ordered rules with enable, edit, add, delete, and guarded reset
  actions. Rules use bounded literal trigger phrases, an `always` or
  `nemotron-default` scope, and a configured provider/model target; they are
  stored atomically in a mode-0600 JSON file and do not grant tool or network
  authority. Defaults add explicit Codex/ChatGPT routing plus a Codex architecture
  specialist targeting `openai-codex/gpt-5.6-sol`, while preserving editable
  explicit Nemotron/Qwen and Qwen specialist routes. These rules select the model
  for the whole incoming request; they do not yet spawn child agents.
- Parametric CAD source and generated parts:
  `cad/pi5-iuniker-inv001-case/`
- Target Spark: SSH verified as `dbyte@172.16.253.231`; passwordless sudo works
- Prime Agent: `0.9.5`, installed for `dbyte` on the host and pinned in every
  OpenShell task image; launcher `prime-dgx`
- NVIDIA OpenShell 0.0.116 is active for production WebUI tasks through its
  local Docker driver. The loopback-only gateway listens on `127.0.0.1:17670`
  with mTLS, and telemetry is disabled. The dedicated `prime-runner` identity
  (UID 995, private primary GID 982) holds a copied mode-0600 client
  registration but never receives the gateway's administrative state or Docker
  socket access. The source release no longer ships the former task
  runtime, activation scripts, rollback script, or tests. Production uses the
  already-supported Docker 29.2.1 through OpenShell.
  Persistent system services `prime-model-gateway` and `prime-runner-broker` are
  enabled and active. Six production image references are protected by a
  mode-0400 digest manifest: general `7197f494…ab5f2`, development
  `798bbce8…a359e`, CAD `ea0e0dc2…e023b`, finance `8c4f4cf7…6e39d`,
  network-operations `ce5fcfac…c89ea`, and review `133c75b4…63840`.
- The development profile includes checksum-pinned ARM64 `uv` and `uvx` 0.12.8
  in addition to native build tools and Python headers. Its production image now
  pre-provisions a system-Python 3.11 kernel environment with IPython, Prime's
  bundled version-matched Python runtime, state support, and Prime's default
  Python packages. `PRIME_AGENT_KERNEL_PYTHON` selects that immutable environment,
  so the built-in IPython tool works on first use with networking disabled instead
  of attempting an Internet-dependent bootstrap. The portable image definition
  applies the same kernel layer to every profile on a complete rebuild; the live
  Spark has promoted and pinned the Development image needed by the affected
  conversation. Tools are enabled through the conversation's Execution setting;
  downloading additional dependencies still requires an Internet-capable Network
  setting.
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
- The authenticated `/terminal/` location has a narrowly scoped CSP exception
  for ttyd 1.7.4's embedded JavaScript and CSS. All other security headers are
  repeated there because Nginx stops inheriting parent `add_header` directives
  when a location defines its own; the main WebUI retains its strict no-inline
  CSP. The `/terminal/ws` origin allowlist and authentication remain unchanged.
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
  Its modal catalogs every provider documented by installed Prime 0.9.5: API-key,
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

## Recovery state

- At owner direction on 2026-09-14, every retained Prime/Spark recovery bundle
  under `/var/backups`, `/home/dbyte/backups`, and
  `/var/lib/prime-runner/recovery` was permanently removed. Those directories
  are empty.
- The inactive superseded task-runtime containers, images, and storage were
  removed. The old Qwen 3.8 comparison sources/images and all retired Qwen
  runtime, service, container, cache, and checkpoint artifacts were also removed.
- The historical wiki snapshots remain immutable documentation, but their old
  recovery paths no longer exist. Current deployment files and upstream Git
  history may help reconstruct software; there is no verified on-Spark restore
  bundle for configuration, credentials, conversations, or earlier models.
- New installers may create new pre-change bundles in the future. Until that
  happens, operational rollback requires a fresh rebuild or redeployment from
  current source rather than restoration from local backup.

## Production OpenShell task sandboxes

- The repository contains a server-enforced policy for `user`, `power_user`, and
  `admin` roles; general, development, CAD, finance, network-operations, and
  review profiles; restricted, Internet, LAN/VPN, and full-network choices; and
  role-bounded CPU, RAM, runtime, PID, open-file, and temporary-storage limits.
- The deployed WebUI exposes OpenShell's effective sandbox image, agent-tool,
  egress-channel, and policy-proposal choices. Shell/code
  execution defaults to a per-task confirmation, can be allowed for one task or
  the authenticated login, or denied. Prime's native `--no-tools` is applied to
  denied tasks. LAN/VPN and full-network access require a separate
  task-specific confirmation and are limited to power users and administrators.
- The production runner creates a named ephemeral OpenShell sandbox per task
  from one of six immutable Prime 0.9.5 Docker images. OpenShell applies hard
  Landlock filesystem enforcement, a recreated static policy, CPU/RAM/PID/time
  bounds, and an empty direct-network policy. Restricted permits only the model
  socket; Internet permits public destinations; LAN/VPN permits private
  destinations; Full permits public and private destinations. Every permitted
  connection remains broker-mediated, and host loopback, link-local,
  multicast, unspecified, and reserved addresses remain blocked. Host
  networking, privileged mode, Docker socket mounts, and host credential mounts
  are prohibited.
- OpenShell's agent policy-advisor surface is enabled globally at settings
  revision 1. Manual review remains the effective default; only an administrator
  can choose per-sandbox `auto`, which upstream applies only when the prover
  delta is empty and the proposed rule has no security notes. Findings remain
  pending for human review.
- `PRIME_TASK_RUNTIME=openshell` is enabled in the API and runner-broker
  services. The hardened API retains `NoNewPrivileges=yes` and
  `RestrictSUIDSGID=yes`; it neither invokes sudo nor launches containers
  directly. It sends validated requests over an abstract Unix socket to
  `prime-runner-broker`, which authenticates the kernel peer UID against the
  `prime-web` group. The broker invokes only the validated OpenShell client and
  has no Docker-group membership. `/home` and `/root` remain inaccessible to the
  broker.
- Each WebUI account has its own mode-0700 Prime state and workspace. Only the
  selected owner's state/workspace and network-mode gateway socket are mounted.
  Pre-provisioned, bind-backed Docker volumes bridge these protected
  `/var/lib/prime-runner` directories into OpenShell without granting its
  user-scoped gateway access to that host tree. Direct bind paths failed under
  Ubuntu's `unprivileged_userns` AppArmor profile; named volumes passed the same
  upstream driver checks and preserve the existing inodes and ownership.
  Session/trash ACLs allow the trusted API to catalog and recoverably delete that
  owner's records without granting users cross-account access.
- The credential/model gateway owns mode-0600 ChatGPT/Codex OAuth material and
  proxies local Nemotron/Qwen over Unix sockets. A mode-0600 per-user auth file
  overrides the global fallback. It rejects symlinks, unsafe ownership/modes and
  oversized files, serializes refresh, refreshes by expiry and once on upstream
  401, and never mounts real credentials in a task.
- Current OpenShell validation passed hard Landlock ABI v8 in V2 mode, denied
  `/root`, `/var/lib/dpkg/status`, and direct outbound Internet, and preserved a
  writable test mount. The complete Prime RPC path then passed exact-response
  canaries through both `spark-nemotron/nemotron-3.5-lightning` and
  `spark-qwen/qwen3.8-flash-next`; each policy loaded at revision 1, each
  ephemeral sandbox was deleted, and no labeled task containers remained.
  A file-level `/srv` sharing canary used a read-only volume subpath; Prime's
  pre-provisioned IPython tool read it successfully and returned exactly
  `OPENSHELL_SUBPATH_OK` without Internet bootstrap.
  The production API reports OpenShell 0.0.116, Docker, recreated-per-task
  static policy, default-deny networking, and broker-channel egress.
  The API retains each user's last verified catalog while Prime temporarily
  protects its task-owned state tree, so active-task polling remains available;
  nonzero broker exits become a safe failed-task status. The final deployed
  restricted/no-tools production canaries returned exactly
  `PRODUCTION_OPENSHELL_OK` and `QWEN_OPENSHELL_OK`; the gateway, API, broker,
  both inference services, and all four per-user gateway modes were active.
  A later interrupted runner exposed a stale ACL mask on the owner's ancestor
  directories, causing task-start and monitor session scans to raise
  `PermissionError`; Nginx then returned non-JSON and the browser surfaced the
  secondary `body.task.id` error. The current fix makes session snapshots
  permission-tolerant, preserves launcher cleanup across SIGTERM so ACLs are
  restored, and rejects malformed/non-JSON task responses with a useful UI
  error. That historical runtime regression suite contained 52 tests; the
  current release suite also covers the OpenShell command/policy boundary and
  all three broker egress classes.
- The official Prime 0.9.5 release artifact is pinned by SHA-256
  `349f1682c7909550842f1b04a71ba95814341b136474ade736df93f8ec006876`.
  Prime's inherited package name is not published on npm; direct registry
  installation returns 404. The repository updater now uses the official
  versioned artifact and its published SHA256SUMS file; this corrected updater is
  installed on the Spark but has not been executed.
- The deployed API also bounds each RPC event at 256 KiB, cleans up a child and its
  task record if initial prompt delivery fails, writes stop/steering commands
  outside the global task lock, waits for Prime's explicit steering/follow-up
  acknowledgement, waits for initial-prompt acceptance before steering to avoid a
  startup race, labels user-aborted work `stopped`, and treats a rejected
  auxiliary RPC command separately from an initial-prompt failure.

## Deployed architecture

- Core framework: **Prime Agent 0.9.5**, selected for exact per-child model choice,
  persistent programmable RLM sessions, long-running work, schedules, skills,
  and a reviewable Continual Harness with snapshots and rollback.
- Default local tier: `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`
  plus its DSpark drafter, served as `nemotron-3.5-lightning` on loopback port
  30000. It uses Marlin, FP8 KV, 3 speculative tokens, 65,536 context, a 2 GiB
  KV cache, and at most two sequences.
- Multimodal/deep local tier: Unsloth Qwen3.8-Flash-Next UD-IQ4_XS, served as
  `qwen3.8-flash-next` on loopback port 30001 by a pinned CUDA llama.cpp image.
  It uses a single 98,304-token slot, Q4 K/V cache, F16 vision projector, and
  direct on-demand NVMe reads for the PLE table. A shared-Q8 MTP head drafts up
  to two tokens for verified speculative decoding. The retired Qwen runtime has
  been removed from the live Spark, including its service, container, cache, and
  checkpoint.
- Frontier API tier: OpenAI GPT-5.4 through the Responses API. A rotated key is
  loaded from a user-service environment file outside the repository;
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

- With a 77,034-token Qwen prompt still resident, both model endpoints healthy,
  and a completed Nemotron generation, Linux reported 20,171,890,688 of
  130,661,138,432 bytes available (15.44%). This passes the 15% gate by only
  0.44 percentage points. Nemotron's 2 GiB FP8 reserve provides 275,587 cache
  tokens, or 4.21 full 65,536-token requests, which remains above its two-
  sequence limit.
- Qwen accepted exactly 78,000 prompt tokens plus 16 output tokens. Its warm
  short-context 600-token run measured 44.76 model-eval token/s; after the 78K
  prompt it decoded at 29.56 token/s. Across the 32K and 78K context tests the
  Qwen process added only six major faults (about 0.042/s). A separate
  77,034-token recall test returned the exact early-context code
  `LANTERN-4827`, providing a targeted Q4 long-context quality check.

- Both endpoints passed simultaneous health, text generation, exact Prime
  routing, and private-binding tests; Qwen 3.8 also passed data-URL image,
  reasoning-control, and structured tool-call tests.
- With both models warm after the final restart, Qwen allocated 63,617 MiB and
  Nemotron 25,863 MiB. Linux reported 31,217,115,136 bytes available (23.89%),
  passing the current 15% gate.
  About 5.94 GB of swap remained occupied from loading, but a 10-second sample
  showed zero swap-in and swap-out activity.
- A 600-completion-token Qwen test measured 23.08 token/s, 0.385 major
  faults/s, and 0.73 MiB/s direct reads before MTP. This preserved baseline is
  the comparison point for the active speculative profile below.
- A repeated 600-token test measured 23.08 request-level token/s and 23.38
  model-eval token/s. During decode the GB10 reported 84-94% SM utilization,
  P0 state, and roughly 2.50-2.52 GHz clocks, so decode is compute-bound rather
  than NVMe-bound. A 1,503-token prompt evaluated at 528.82 token/s.
- With shared-Q8 MTP enabled, the same deterministic 600-token test measured
  42.08 request-level token/s and 43.27 model-eval token/s with 100% draft
  acceptance, an 82.3% improvement over the 23.08 token/s baseline. A
  temperature-0.7 technical-prose test measured 30.57 request-level token/s and
  31.08 model-eval token/s at 63.258% draft acceptance.
- A controlled two-versus-three-draft A/B used identical 600-token requests
  after fresh service starts. Three drafts improved the warm deterministic run
  from 38.52 to 39.85 request token/s (3.5%), but reduced the warm
  temperature-0.7 technical-prose run from 33.91 to 31.63 token/s (6.7%).
  Draft acceptance also fell from 70.32% to 62.63% on the deterministic test
  and from 53.10% to 41.27% on prose. The production default therefore remains
  two drafts; three is not a general throughput improvement.
- The N=2 confidence-cutoff matrix compared `p_min` 0.0, 0.1, 0.2, and 0.3 on
  repeat 600-token deterministic, prose, and coding requests. Reverse-order
  zero-control warm rates were 39.29, 33.58, and 36.48 token/s (36.45 mean).
  Threshold 0.1 produced the exact same draft/accept counts and outputs as zero,
  so its 36.60 mean was timing noise. Threshold 0.2 raised total acceptance from
  61.00% to 63.09% but returned a 36.35 mean; threshold 0.3 raised acceptance to
  64.41% while reducing the mean to 32.52 token/s. The active explicit setting
  remains `--spec-draft-p-min 0.0`. Increasing KV capacity remains excluded
  because it expands context or concurrency rather than accelerating short
  single-stream decode.
- A newer llama.cpp candidate combined upstream master `ad6c6683`, MTP PR
  `d1a92352`, and direct-read PR `c6a9e5c9` as local commit `9bc0988b` and image
  `local/llama-qwen38-mtp:9bc0988b`. It was not promoted. Its ordinary
  three-workload mean was 36.91 token/s versus 36.45 for production, but it was
  2.0-3.3% slower decoding at 2K, 8K, and 24K prompt depth and 2.4% slower on a
  140-tool request. Prefill was effectively unchanged after warm-up. The
  production `560abb66` image remains active; the rejected candidate and older
  non-MTP source/image were removed during v0130 cleanup.
- The settled tuned Qwen process allocated 66,757 MiB beside Nemotron's 25,863
  MiB. Linux retained 25,774,166,016 bytes available (19.73%), passing the 15%
  gate.
  A 10-second idle sample showed no swap-out and only intermittent tens of KiB/s
  swap-in rather than sustained pressure.
- After v0060 deployment, both model health endpoints, the dashboard service,
  authenticated HTTPS boundary, installed assets, and deterministic specialist
  routing passed. The Spark reported 41.1 GB available memory (31.5%).
- After the 81,920-token Nemotron warm-up and tests, Linux reported 39.1 GiB
  available memory (32.15%). The validation gate now requires at least 15% of
  usable RAM, about 18.3 GiB on this Spark.
- Both inference ports bind only to `127.0.0.1`.
- NVFP4 is the checkpoint format. Nemotron's published GB10 recipe uses W4A16
  Marlin rather than native FP4 tensor-core execution.

## Qwen 3.8 direct-read deployment

- Qwen3.8-Flash-Next UD-IQ4_XS became the supported local Qwen runtime on
  2026-09-13. The three GGUF
  shards total 93,682,584,224 bytes and the separate F16 vision projector is
  904,004,000 bytes. UD-IQ4_XS was selected over the 72.5-74.5 GB IQ1 options
  because Unsloth reports 89.554% rather than roughly 77-80% top-1 agreement.
- The active image is `local/llama-qwen38-mtp:560abb66`, digest
  `sha256:28ecdb03a5cf70d021c14eee32ebde5818079361ecc832c428321bf143b804e8`,
  built from combined MTP/direct-read commit
  `560abb6616eea7b8c0fc76259bc08142df5c2e1b` with CUDA 13.0.2 for SM 121.
- `--load-mode mmap --lazy-mode on-direct` leaves the large PLE/n-gram table on
  NVMe and issues explicit row reads as tokens are generated. This is bounded
  model-table access, not generic Linux swap. The service uses 98,304 context,
  one slot, Q4 KV, and an 88 GiB container memory ceiling with no extra swap.
- Nemotron's weight checkpoint is 20.08 GiB. Its warm allocation fell from about
  34.0 GiB to 25.9 GiB after reducing the explicit KV reserve from 12 GiB to
  2 GiB. Its 65,536-token maximum and two-sequence scheduler fit inside the
  measured 275,587-token cache capacity. The 0.35 utilization setting is a
  startup admission ceiling; the explicit 2 GiB value controls KV allocation.
- The retired Qwen runtime is fully removed from the live Spark. Its user unit,
  launcher/config directory, stopped container, cache, and checkpoint are absent.
- MTP is enabled with the 2,786,568,256-byte
  `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` head, all draft layers offloaded, and
  `--spec-draft-n-max 2`. The main model verifies every accepted draft, so the
  optimization does not replace target-model sampling.
- The previous non-MTP image, comparison sources, and checksummed configuration
  backup were removed. The production shared-Q8 MTP head is the only retained
  Qwen 3.8 serving path.

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
  altered files were once preserved in a root-only recovery directory that was
  deleted during v0130 cleanup. The reviewed broker and PAM policy were restored,
  the obsolete policy was removed, and all audited
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

- The enclosure is a rounded two-piece shell measuring 96.4 x 65.4 x 42.4 mm,
  tuned for Bambu PETG Basic on an X2D with a stock 0.4 mm main nozzle.
- It provides long bottom intakes, a honeycomb lid exhaust, vertical exhaust
  slots around all four upper walls, all primary Pi 5 port openings except
  microSD, recessed M2.5 board mounting, and four M3 lid screws.
- All side-wall cutters are centered on the wall midplanes and fully cross the
  3.2 mm shell. Generation-failing clear-path probes report 0.0 mm3 obstruction
  for both upper-wall vent directions, USB-C, an Ethernet/USB bay, and the shared
  power-button/LED opening.
- Its 3.2 mm walls equal eight nominal nozzle widths, the lid has 0.35 mm sliding
  clearance per side, and the M3 pilots are 2.7 mm. Separate Ethernet/USB bays
  replace the former long opening, keeping the largest wall bridge below 17 mm.
- Recessed lid receivers end 4.45 mm below the rim with a 0.25 mm axial gap below
  the lid guides. Automated assembled mesh intersection is 0.0 mm3. M3 x 12 mm
  screws provide engagement through the corrected lid/guide stack.
- Owner-confirmed fit dimensions, followed by a 1 mm side-to-side reduction, set
  the cavity to exactly 90 x 59 mm, leaving 2.5 mm per HAT end and 1.25 mm per
  HAT side. The Pi support plane is at
  Z=4.8 mm, 2 mm above v0090 and 0.6 mm below the first print.
  USB-C/micro-HDMI openings are centered at Z=8.9 mm; network openings remain at
  Z=14.4 mm. The button/LED opening remains at Z=12.2 mm. Wall-integrated
  receivers retain 1.05 mm clearance from
  the photo-confirmed 3 mm rounded HAT corners.
- Lid fasteners use 3.4 mm through-holes with 6.4 mm exterior conical
  countersinks. Floor board mounts use 2.9 mm through-holes with 5.5 mm exterior
  conical countersinks. Both accept flat-head screws; internal receiver pilots
  remain blind.
- A separate captive printed plunger operates the Pi 5 native power button without
  wiring an additional switch. It passes through the short end near the USB-C
  corner and is the exact SHA-verified supplied PowerButton v14 mesh, transformed
  into print orientation. Its broad flange stays inside the case while its narrow
  end passes outward through the 9 x 4 mm opening. The end has no microSD cutout
  at the owner's request. Control position remains a physical-fit parameter.
- Base, lid, and button STLs each validate as a single watertight,
  winding-consistent positive-volume body. A colored exploded GLB and PNG preview
  are generated with the parts.
- The owner confirmed that this INV001 board has the same 85 mm length as the Pi
  5. The model uses an 85 x 56.5 mm plan envelope inside a 90 x 59 mm cavity.
  Its receivers clear the photo-confirmed 3 mm rounded/cut PCB corners by at
  least 1.05 mm. Owner-supplied
  photos support the standard Pi mounting pattern and a
  nominal 16 mm brass HAT spacer; because the caliper display was off, the value
  remains a nominal assumption rather than an exact measurement. The explicit
  stack envelope leaves 8.6 mm of air below the base rim. Board width, exact stacked
  height, and native-button alignment still require physical measurement before a
  final-material print.
- The X2D guide uses the left/main hotend, built-in Bambu PETG Basic preset, 0.20
  mm Standard process as its starting point, four walls, 25% gyroid, five top and
  bottom layers, and no supports or active chamber heat.
- Bambu Studio 02.08.02.61 successfully sliced the compact three-part plate with
  resolved factory X2D/PETG profiles: left/main nozzle only, zero support features,
  zero filament changes, no warnings, and an estimated 2 h 27 m 14 s print time.
  Temporary G-code was discarded; the retained JSON report records the settings.
- Slice validation now treats any Bambu warning as a failure. Raising the upper
  wall vents to Z=31 mm preserves a printable wall band above the raised network
  openings and eliminated the intermediate floating-region warning.

## Operations

- Launch Prime with `prime-dgx`; Nemotron is the default and Qwen is available
  as `spark-qwen/qwen3.8-flash-next` for exact child routing.
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
  Agent updater downloads the official versioned release artifact and verifies
  its entry in the published SHA256SUMS file before installation. The
  WebUI updater resolves and fast-forwards to the private repository's release
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
- Internet/LAN task containers explicitly bypass their outbound policy proxy for
  the internal `127.0.0.1` model-gateway bridge. A production Internet-profile
  Nemotron canary returned `INTERNET_MODEL_FIXED` after this repair.
- Background Activity is owner-scoped and now shows live response drafts, tools,
  retries, safe reasoning-state indicators, redacted runtime output, and model
  errors. Raw private chain-of-thought is intentionally never returned to the
  browser. Model errors mark the task failed rather than falsely completed.
- Background Activity also lists every received runtime line in a continuously
  refreshed console, up to 5,000 lines or 2 MiB per task. Structured progress
  remains above it. Credentials are redacted recursively, and all reasoning
  payload variants—including nested delta/end fields—are replaced with
  `[PRIVATE_REASONING]`. The same sanitizer now protects newly persisted logs.
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
  restarts, retention, and the private-CA download. The dashboard/auth/terminal,
  OpenShell gateway, Nemotron, and Qwen services are checked as user services;
  `prime-model-gateway` and `prime-runner-broker` are checked as system services
  because OpenShell runs those persistent broker processes under `prime-runner`.

## Known gaps

- Historical downloadable task logs created before v0095 have not yet been
  rewritten with the recursive sanitizer; migrating them requires explicit owner
  approval because it changes existing production records.

- A read-only comparative review found that the loopback dashboard API trusts
  Nginx-supplied identity/role headers without authenticating the proxy. A local
  process can forge them; a non-mutating live request with fabricated admin
  headers returned 200 from `/api/admin`.
- Native Prime tasks, storage, and gateway credentials are now account-isolated
  OpenShell workloads. The optional Advanced console remains a shared `dbyte`
  host shell and therefore must remain limited to trusted administrative use; it
  is not equivalent to a task container.

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
- Existing Spark configuration is documented, but no protected local snapshot
  or off-device disk backup is currently recorded.
- Prime's local routing policy and infrastructure gate are implemented. The
  frozen domain prompt suite and OpenAI credential/route remain incomplete.
- The first CAD generator and X2D/PETG slice validation are implemented, but the
  iUniker case has not yet been physically printed and fit-tested. Market-data,
  portfolio, paper-broker, and risk-gateway tools remain undefined.
- No financial strategy has been specified or validated.
- Local application security regression checks are included. GitHub Actions and
  automated release promotion/rollback remain undefined.
