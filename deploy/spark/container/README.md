# OpenShell task runtime images

This directory contains the shared task image and broker helpers used by the DGX
Spark OpenShell runtime. Prime WebUI does not launch tasks directly. It sends a
bounded request to the local `prime-runner` broker, and the broker asks the
loopback-only OpenShell gateway to create an ephemeral Docker sandbox with the
approved image, filesystem policy, resource limits, and selected network mode.

## Profiles

- `general`, `finance`, and `review` contain Prime, Python, pip, Git, curl, jq,
  ripgrep, and checksum-pinned ARM64 `uv`/`uvx` 0.12.8.
- `development` adds native build tools and Python headers.
- `cad` adds OpenSCAD.
- `network-operations` adds Chromium, ipmitool, nmap, ping, DNS, and traceroute
  tools and is limited to power users and administrators.

Every task receives only its owner's protected Prime state, host-visible task
workspace, selected model gateway socket, and explicitly approved read-only
local sources. The task workspace appears as `/project` inside the sandbox and
is backed by `~/prime-agent/tasks/OWNER/` on the host. Host credentials, other
users' data, the Docker socket, host networking, and privileged mode are never
mounted into the sandbox. Image references are validated against
`/var/lib/prime-runner/openshell-image-digests.json`.

## Network modes

- **Restricted** has no direct network route and can reach local models only
  through the broker-provisioned model gateway.
- **Internet** uses the brokered HTTP CONNECT path and rejects private, loopback,
  link-local, reserved, and metadata addresses.
- **LAN/VPN** uses the same brokered path but permits private and public
  destinations; it still rejects loopback, link-local, reserved, and metadata
  addresses.
- **Full** is available only to power users and administrators after explicit
  task confirmation.

Local Nemotron and Qwen endpoints and ChatGPT/Codex are reached through the
credential/model gateway. OAuth material remains mode 0600 outside sandboxes. A
per-user credential file at
`/var/lib/prime-runner/credentials/users/USER/auth.json` overrides the global
fallback; otherwise the global credential is used. The gateway validates file
ownership, type, mode, and size, refuses symlinks, serializes refreshes, and
refreshes once on an upstream 401.

An administrator can provision a user's own Prime OAuth record without exposing
it in shell arguments:

```bash
chmod 600 /private/path/auth.json
./deploy/spark/container/install-user-codex-credential.sh WEBUI_USER /private/path/auth.json
```

The source must be owned by the invoking WebUI owner, mode 0600, a regular
non-symlink file, and contain a complete `openai-codex` record. The helper copies
it into that user's protected override directory. Run the same helper with
`WEBUI_USER --remove` to move the override into root-only recovery storage and
return the user to the global credential on the next request.

## Install and verify

Run the normal WebUI installer first, then install the Spark OpenShell runtime:

```bash
deploy/spark/openshell/install.sh
systemctl --user restart prime-dashboard-api.service
deploy/spark/prime/validate.sh
```

The OpenShell installer provisions `prime-runner`, protected per-user state,
the home-backed task workspace, the model gateway, the runner broker, the
dashboard API drop-in, OpenShell gateway configuration, Docker volumes, and the
six digest-checked task images. It also copies existing owner sessions into the
runner state tree and workspace files into `~/prime-agent/tasks/OWNER/` so
current conversations continue under OpenShell.

## Installing skills and task dependencies

Prime's persistent skill registry is
`/home/prime/.prime/agent/skills/NAME/SKILL.md`. The compatibility path
`/project/.prime/agent/skills` is linked to that registry when a task starts.
If an older task created a real directory at the compatibility path, the
entrypoint copies its contents into the registry and retains the original as a
timestamped `skills.workspace-backup-*` directory before creating the link.

Python dependencies belong in a project virtual environment, never in the
read-only system interpreter:

```bash
uv venv /project/.venv
uv pip install --python /project/.venv/bin/python PACKAGE
```

The runner prepends `/project/.venv/bin` to `PATH`. Python, uv, pip, npm, and
Playwright caches are persisted beneath `/home/prime/.prime/cache`; npm global
user tools go beneath `/home/prime/.prime/tools/npm`, and Playwright-downloaded
browsers go beneath `/home/prime/.prime/tools/playwright`. Downloads require an
**Internet** task network mode. Restricted tasks can use only packages already
present in the image, `/opt/prime-kernel`, a populated project virtual
environment, or the persistent user-tool directories.

System packages are never installed during a task. Add a required binary to the
appropriate reviewed profile in `Containerfile`, rebuild all affected images,
record their immutable IDs in `deploy/spark/openshell/image-digests.json`, and
deploy through the OpenShell installer. This preserves the non-root task and
read-only `/usr` boundary.
