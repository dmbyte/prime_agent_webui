# OpenShell runtime

The DGX Spark release runs WebUI tasks inside NVIDIA OpenShell sandboxes through
the local Docker driver. OpenShell replaces the earlier task-container runtime
for production use.

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
10. Installs the reviewed `bmc-headless-browser` and `ipmi-redfish-bmc` Prime
    packages. The follow-on skill command pins and installs the complete NVIDIA
    catalog plus its lazy Prime router.

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
role-authorized `network-operations` profile and LAN policy for an actual BMC
task. The small Python adapters are preinstalled in Prime's immutable kernel so
Prime can invoke them reliably, but they are imported only when selected.
Playwright is installed only in `network-operations` and starts only when the
headless browser context is opened.

The WebUI's **Security prompts** control can persist **Always allow** at a chat
or project scope. The dashboard API accepts quiet execution/network/file
confirmation only when the full task policy exactly matches an owner-scoped
saved policy. This does not broaden role permissions or weaken the sandbox;
changing access settings changes the policy and invalidates the previous match.

## Verify

```bash
openshell --gateway spark-local status
sudo -u prime-runner env HOME=/var/lib/prime-runner openshell --gateway spark-local status
systemctl status prime-model-gateway prime-runner-broker
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
