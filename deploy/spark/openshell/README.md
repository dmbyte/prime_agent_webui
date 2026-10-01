# OpenShell runtime

The DGX Spark release runs WebUI tasks inside NVIDIA OpenShell sandboxes through
the local Docker driver. OpenShell replaces the earlier task-container runtime
for production use.

The reviewed package is NVIDIA OpenShell `0.1.2-1` for ARM64, with SHA256
`14838b811b54148060da99fd2aabe78f05c777002c0a8fc39b106e0de0ddd796`.
The loopback `spark-local` gateway uses schema v2, Docker, mTLS, a 256-process
per-sandbox cap, and disabled telemetry. It enables caller driver config only
with resource admission enabled; Prime's pre-provisioned bind-backed Docker
volumes carry `openshell.ai/sandbox-attachable=true` and
`openshell.ai/sandbox-attachable-workspace=default`. The host paths themselves
are not removed when an unlabeled Docker volume definition is recreated.

## Prerequisites

Run on Ubuntu 24.04 ARM64 DGX Spark as the non-root WebUI/Docker owner.

- Docker 28 or newer with GPU support.
- `jq`, `acl`, `rsync`, `curl`, `sudo`, and user systemd services.
- Healthy local model services on `127.0.0.1:30000` and `127.0.0.1:30001`.
- No active OpenShell sandboxes during install or update.

## Install

```bash
deploy/spark/openshell/install.sh
deploy/spark/prime/install-skills.sh
systemctl --user restart prime-dashboard-api.service
deploy/spark/prime/validate.sh
```

The installer:

1. Verifies the pinned OpenShell ARM64 package and checksum.
2. Creates the dedicated `prime-runner` identity and protected state tree.
3. Installs the model gateway and runner broker.
4. Copies existing owner sessions, skills, and artifacts into
   `/var/lib/prime-runner/users/OWNER/`, while copying existing workspace files
   into `~/prime-agent/tasks/OWNER/`.
5. Installs a dashboard API drop-in that selects `PRIME_TASK_RUNTIME=openshell`.
6. Configures the loopback `spark-local` OpenShell gateway and disables
   telemetry.
7. Builds and verifies the six approved Docker task images.
8. Creates the Docker volumes that expose per-user Prime state, the
   host-visible task workspace, model gateway sockets, and approved shared
   source roots.
9. Prepares persistent skill, package-cache, npm-tool, and Playwright-browser
   directories inside each user's protected Prime-state volume.
10. Installs the reviewed `bmc-headless-browser`, `bmc-html5-kvm`, and
    `ipmi-redfish-bmc` Prime
    packages. The network-operations image includes `ipmitool` and `pyte` for
    the SOL adapter, but direct IPMI/SOL UDP is not transported by the deployed
    HTTP(S) gateway, even in Full mode; the client now fails fast rather than
    reporting a misleading profile denial. Use Redfish or KVM. The browser package
    remains for bounded BMC web-page work. The separate KVM skill uses an
    owner-scoped broker and dedicated OpenShell sandbox so its browser can
    persist across Prime tasks, up to eight hours or 45 idle minutes. It does
    not mount virtual media or survive broker/host restarts. The follow-on
    skill command pins and installs the complete NVIDIA catalog plus its lazy
    Prime router.

The image packages `gateway_relay.py` at `/usr/local/lib/prime-gateway-relay.py`.
The entrypoint starts `model` (127.0.0.1:31000 → model.sock) and, when available,
`network` (127.0.0.1:31080 → network.sock). The KVM worker uses the same network
relay. Each listener has a 64-connection bound, 30-second socket I/O timeout,
30-minute idle limit, and retries rejected/cancelled accepts without relaxing
policy. Validate task startup, Redfish, browser/IPython, and denied egress with
`deploy/spark/prime/validate-task-gateway.py` as `prime-runner`, setting
`HOME=/var/lib/prime-runner` and `PRIME_WEB_OWNER` to the configured owner.
It uses a local fixture, not a BMC; set `PRIME_KVM_TEST_HOST` for another Spark IP.
For the complete model-driven path, run `deploy/spark/prime/validate-prime-kvm-task.py`
as the WebUI owner. It uses the production routing policy (Qwen for this task)
through the actual task broker and IPython,
requires fixture-side evidence of a login and exactly one console key, and rejects
unexpected tool errors or a missing final report. `--nemotron` and `--qwen`
force a comparison without changing application routing. This creates a synthetic Prime
conversation; it never targets a real BMC. Unit/browser-only tests do not replace
this model-driven test.

The installed `AGENTS.managed.md` and per-task runtime context assign all
nontrivial code generation to Qwen across all profiles. The WebUI additionally
routes recognized coding requests and Development/Network operations tasks
directly to Qwen, retaining coding routes on follow-ups. Qwen must be enabled;
there is no silent Nemotron implementation fallback. Existing managed workspace
policies are backed up and refreshed by installation/provisioning; custom
workspace policies are not overwritten. Unexpected code subtasks in a Nemotron
conversation rely on the agent following the explicit Qwen delegation policy,
not on an executable-code enforcement hook.

Inside a task sandbox, `/project` maps to `~/prime-agent/tasks/OWNER/` on the
host. Prime state remains protected under `/var/lib/prime-runner/users/OWNER/`.
The local-path picker still rejects arbitrary `/home` paths; the home-backed
task workspace is the controlled exception created by the installer.

Task images provide pip, uv, and npm, but tasks remain non-root and `/usr`
remains read-only. Install Python dependencies into `/project/.venv`; npm user
tools, package caches, downloaded browser engines, and registered skills persist
under `/home/prime/.prime`. Package downloads require the task's **Internet**
network mode. The `network-operations` profile includes reviewed Chromium and
ipmitool binaries for BMC work without runtime system-package installation.

`deploy/spark/prime/install-skills.sh` clones the official NVIDIA skills
repository at commit `fd9f1466ff8a39178e488981e8b5118709392949`, validates all
366 skills and their size/path bounds, and installs the unchanged upstream tree
under `/home/prime/.prime/agent/catalogs/nvidia`. Only the small
`prime-nvidia-catalog` router is advertised in every Prime prompt; it searches
and reads a selected upstream skill on demand. This keeps the catalog globally
available without adding roughly 13,000 description tokens to every task.
Re-running the command moves prior managed packages and catalog content to
timestamped recovery storage. Use
`--nvidia-source /path/to/reviewed/checkout` for an offline checkout at the same
pinned commit.

The BMC browser uses `/usr/bin/chromium` from the immutable profile and does not
run `apt` or download a Playwright browser. Both BMC packages require runtime
credentials, never store them, and require an explicit `confirm=True` gate for
power-changing actions. Their presence does not grant LAN access: select the
role-authorized `network-operations` profile and LAN/VPN or Full policy for an actual BMC
task. For those combinations the runner mounts the owner's LAN gateway read-only
at `/run/prime-kvm` and sets `PRIME_KVM_SOCKET=/run/prime-kvm/kvm.sock` so the
KVM control channel remains available with Full egress. Its separate browser
worker still uses LAN egress. Restricted/Internet tasks receive no such mount.
The small Python adapters are preinstalled in Prime's immutable kernel so
Prime can invoke them reliably, but they are imported only when selected.
Playwright is installed only in `network-operations` and starts only when the
headless browser context is opened. The adapter isolates Playwright and
Chromium in a clean worker subprocess, communicates over a thread-backed private
standard-I/O bridge that remains reliable across repeated launches in Prime's
persistent IPython loop, bounds every operation, and captures worker errors. Chromium receives a
private ephemeral HOME/XDG directory under `/tmp` and runs without GPU or
zygote subprocesses so it remains compatible with OpenShell's read-only home
and process isolation.

The WebUI's **Security prompts** control can persist **Always allow** at a chat
or project scope. The dashboard API accepts quiet execution/network/file
confirmation only when the full task policy exactly matches an owner-scoped
saved policy. This does not broaden role permissions or weaken the sandbox;
changing access settings changes the policy and invalidates the previous match.

## Verify

```bash
openshell --gateway spark-local status
sudo -u prime-runner env HOME=/var/lib/prime-runner openshell --gateway spark-local status
systemctl status prime-model-gateway prime-runner-broker prime-kvm-broker
systemctl --user status openshell-gateway prime-dashboard-api
deploy/spark/prime/validate.sh
```

The gateway must listen only on loopback with mTLS. The installer copies the
reviewed image context to a temporary directory, normalizes its timestamps and
file modes, and requires every locally built image ID to match
`deploy/spark/openshell/image-digests.json`. A mismatch remains a review gate,
not an automatic upgrade.

## Updates

Administrators can update OpenShell from Settings. The updater checks the latest
stable `NVIDIA/OpenShell` release, accepts only the ARM64 `.deb`, verifies the
published checksum file, refuses to run while sandboxes exist, restarts the
gateway, validates owner and `prime-runner` access, records the installed
version, and restarts the dashboard API.

### Migrating an existing 0.0.x installation

NVIDIA does not support an in-place local 0.0.x-to-0.1.x package upgrade. The
ordinary Settings updater refuses that boundary; use a reviewed maintenance
window. On the Spark migrated on 2026-09-30, we:

1. Confirmed zero sandboxes and configured OpenShell providers, and archived
   the exact old ARM64 package, its checksum, gateway configuration, Docker
   volume definitions, TLS/encryption state, and a SQLite `.backup` in a
   mode-0700 recovery directory. Do not copy only a live SQLite database file.
2. Stopped the gateway, moved its 0.0.x state into the recovery directory,
   installed the preflighted schema-v2 `gateway.toml`, removed only the
   `openshell` package, and installed the reviewed 0.1.2 package. We did not
   remove Prime sessions, host workspaces, or model state.
3. Started the gateway, replaced the old `spark-local` *client registration*
   so its saved mTLS CA matched the newly generated gateway CA, copied that
   registration to `prime-runner`, and restored the global policy setting.
   `openshell gateway remove spark-local` affects only client metadata, not
   the running gateway.
4. Ran `provision-volumes.sh` to recreate only unlabeled Docker *definitions*
   with workspace-`default` admission labels. It verifies the original host
   path and refuses unexpected labels or a volume still attached to a
   container; backing directories and their contents remain in place.
5. Verified owner and runner status, then created/executed/deleted a restricted
   Prime task sandbox and a separate HTML5 KVM/Chromium sandbox. Both passed
   without contacting a BMC. Finally, the updater recorded 0.1.2 as current.

For rollback, stop the gateway, restore the archived 0.0.116 package, schema-v1
config, state directory, and both client registrations, then start the old
gateway. Keep the recovery directory private because it contains mTLS keys
and gateway encryption material. Never run `apt autoremove` as part of this
migration; it may target unrelated kernel and NVIDIA packages.
