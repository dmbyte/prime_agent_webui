# Wiki and Project Change Log

Entries are newest first. Each material entry links to an immutable state
snapshot. Use ISO dates and describe outcomes, validation, and rollback impact.

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
