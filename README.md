# Prime Agent WebUI

Prime Agent WebUI is a private, multi-user browser interface for
[Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent). It adds durable
conversations, live progress and steering, file uploads, model/provider controls,
usage and spend summaries, Spark telemetry, administrative user management, and
release-aware updates.

![Prime Agent WebUI sample](docs/prime-webui-sample.jpg)

> The screenshot contains synthetic sample data. No user conversations or
> credentials are included.

## Repository scope

This repository contains only the files needed to install, operate, validate,
and update Prime Agent WebUI and its service helpers. Production conversations,
system history, private operating notes, CAD projects, and locally refined agent
skills belong outside the repository and are excluded from version control.

## What this release includes

- Dedicated WebUI passwords with `admin`, `power_user`, and `user` roles; Linux
  passwords and PAM are not used.
- Private HTTPS through Nginx, secure cookies, CSRF/origin enforcement, rate and
  connection limits, LAN/VPN source restrictions, and durable login sessions
  with a 30-day idle window and 180-day maximum lifetime.
- Native Prime RPC conversations with immediate message echo, safe live progress,
  `/steer`, `/follow-up`, and explicit stop.
- Account-scoped collapsible projects and chats in the sidebar, with shared
  project instructions and uploaded sources, inherited conversation-control
  defaults, pinning, boxed `...` chat actions, and visible promotion of existing
  chats into new or existing projects.
- Persistent sandbox, tool, egress, proposal, local-path, and security-prompt
  controls directly below the conversation header; saved chats retain their own
  overrides. **Always allow for this chat/project** suppresses repeated prompts
  only while the requested policy exactly matches that saved scope.
- Configured-provider discovery, write-only credential forms, model selection,
  effort control, and provider/model token and spend roll-ups.
- One-second CPU, GPU, memory, power, and temperature sparklines at the top of
  the sidebar, with large value watermarks and an expanded live hover view.
- Recoverable conversation deletion, isolated ownership metadata, uploads,
  activity logs, and administrative user lifecycle management.
- Production OpenShell per-task execution under a dedicated service identity,
  six immutable Docker profile images, isolated per-user storage, a
  credential/model gateway, four role-controlled network modes, and enforced
  resource limits.

## Supported systems

The WebUI and cloud/remote-model workflow supports current systemd-based members
of these families:

| Family | Examples | Package manager | Notes |
|---|---|---|---|
| Debian | Ubuntu 22.04/24.04, Debian 12 | `apt` | Primary and most-tested path. NVIDIA DGX Spark uses Ubuntu 24.04. |
| Red Hat | RHEL 9/10, Rocky, AlmaLinux, CentOS Stream, Fedora | `dnf`/`yum` | Enable the appropriate BaseOS/AppStream repositories. |
| SUSE | SLES 15, openSUSE Leap/Tumbleweed | `zypper` | The WebUI works; NVIDIA's DGX Spark local-model recipes are Ubuntu-specific. Package names can vary by service pack. |

Requirements: x86-64 or ARM64 Linux, systemd with user services, Python 3.10+,
Nginx, OpenSSL, curl, Git, sudo access during installation, and a private LAN or
VPN address. A local GPU is optional when cloud or remote OpenAI-compatible
providers are used.

## Quick installation

Clone the release and run the installer as the account that should own Prime:

```bash
git clone --branch v0.5.34 --depth 1 https://github.com/dmbyte/prime_agent_webui.git
cd prime_agent_webui
./install.sh --bind-address 192.168.1.50 --server-name prime.example.lan
```

For a private repository, authenticate Git or GitHub CLI before cloning. A
source archive can be used instead; preserve the repository directory layout.

Do **not** run `install.sh` as root. It asks for sudo only for OS packages,
private TLS, Nginx, and persistent user-service login. It then prompts for the
initial WebUI password; use at least 12 characters.

### Set the WebUI password

Prime WebUI does **not** authenticate with PAM, `/etc/shadow`, or a Linux account
password. The installer creates a separate salted password record and normally
runs the password tool automatically. The initial WebUI username defaults to the
name of the non-root account that ran the installer, but that name is only a
WebUI identifier—it does not enable system-account authentication.

If installation used `--skip-password`, or to rotate the password later, run
the installed tool as the WebUI owner without `sudo`:

```bash
~/.local/bin/prime-web-password
systemctl --user restart prime-auth.service
```

Enter and confirm a password of at least 12 characters at the masked prompts.
The tool stores only a salted scrypt record in
`~/.config/prime-agent/web-auth.json` with mode `0600`; it does not read or
change the Linux password. Then sign in at `https://ADDRESS:8443` using the
displayed WebUI username and the password you just set.

The installer deliberately does not modify the firewall. When it finishes, open
`https://ADDRESS:8443`, download `prime-webui-ca.crt`, and install that private CA
on each trusted client.

Useful options:

```text
--bind-address ADDRESS  Explicit private LAN/VPN address
--server-name NAME      Private DNS name for the certificate
--port PORT             HTTPS port; default 8443
--skip-packages         Packages are already installed
--skip-prime            Prime Agent is already installed
--skip-password         Set the password later with prime-web-password
```

## Distribution-specific preparation

The installer normally installs these automatically. Use the commands below when
you prefer to manage packages yourself, then add `--skip-packages`.

### Ubuntu and Debian

```bash
sudo apt-get update
sudo apt-get install -y nginx openssl python3 curl git
```

DGX Spark local Nemotron/Qwen hosting additionally requires NVIDIA's supported
Ubuntu image, driver/container stack, Docker, and the NVFP4 model artifacts. See
[the Spark deployment guide](deploy/spark/README.md); do not apply those GPU
steps to ordinary Ubuntu/Debian hosts.

### RHEL, Rocky, AlmaLinux, CentOS Stream, and Fedora

```bash
sudo dnf install -y nginx openssl python3 curl git policycoreutils-python-utils
```

On a minimal RHEL-compatible installation, enable the vendor-supported
BaseOS/AppStream repositories first.

When SELinux is enforcing, the installer enables `httpd_can_network_connect` so
Nginx can reach the loopback authentication and API services. This is not needed
on Debian-family systems.

### SLES and openSUSE

```bash
sudo zypper --non-interactive install nginx openssl python3 curl git
```

On SLES, enable the Server Applications and Containers modules appropriate to
your service pack. If a package uses a service-pack-specific name, install its
equivalent and use `--skip-packages`. DGX Spark's local NVFP4 recipes are not
supported on SLES; use cloud or a remote OpenAI-compatible inference endpoint.

### DGX Spark OpenShell and local models

The production Spark release runs Prime tasks inside NVIDIA OpenShell while
serving Nemotron 3.5 Lightning and Qwen 3.8 Flash-Next from loopback-only local
endpoints. Install the base WebUI first, then apply the Spark-specific model and
OpenShell pieces. On Ubuntu 24.04 DGX Spark systems, the extra host
prerequisites are Docker 28 or newer, `jq`, `acl`, and `rsync`.

Install Nemotron 3.5 Lightning on port 30000:

```bash
install -d ~/vllm-nemotron35
cp deploy/spark/vllm-nemotron35/vllm.env.template ~/vllm-nemotron35/vllm.env
cp deploy/spark/vllm-nemotron35/start.sh ~/vllm-nemotron35/start.sh
install -m 0644 deploy/spark/systemd/vllm-nemotron35.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vllm-nemotron35.service
curl -fsS http://127.0.0.1:30000/v1/models
```

If the model artifacts require Hugging Face access, add the token to
`~/vllm-nemotron35/vllm.env` before starting the service.

Install Qwen 3.8 Flash-Next on port 30001:

```bash
deploy/spark/llama-qwen38/build-image.sh
install -d ~/llama-qwen38
cp deploy/spark/llama-qwen38/llama.env.template ~/llama-qwen38/llama.env
cp deploy/spark/llama-qwen38/start.sh ~/llama-qwen38/start.sh
install -m 0644 deploy/spark/systemd/llama-qwen38.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llama-qwen38.service
curl -fsS http://127.0.0.1:30001/v1/models
```

Edit `~/llama-qwen38/llama.env` if the Qwen GGUF, multimodal projector, or MTP
draft files live outside the default model directory. Qwen 3.8 is the supported
Qwen runtime for this release.

Install the local model catalog and OpenShell integration:

```bash
install -m 0600 deploy/spark/prime/models.json ~/.prime/agent/models.json
install -m 0600 deploy/spark/prime/settings.json ~/.prime/agent/settings.json
deploy/spark/openshell/install.sh
deploy/spark/prime/install-skills.sh
systemctl --user restart prime-dashboard-api.service
deploy/spark/prime/validate.sh
```

The OpenShell installer uses the pinned ARM64 package, validates the published
checksum, provisions `prime-runner`, installs the model gateway and task broker,
copies existing owner state into protected runner storage, builds the approved
Docker runtime images, provisions per-user volumes, and restarts the local
gateway. It installs the reviewed BMC adapters; the following skill installer
pins the official NVIDIA catalog at commit
`fd9f1466ff8a39178e488981e8b5118709392949`. See the component guides for details:
[Nemotron](deploy/spark/vllm-nemotron35/README.md),
[Qwen 3.8](deploy/spark/llama-qwen38/README.md), and
[OpenShell](deploy/spark/openshell/README.md).

### Deployed DGX Spark configuration

The tracked Spark recipe is intentionally explicit. A default deployment uses
these concrete parameters unless you edit the copied files under your home
directory before starting the services.

#### Nemotron 3.5 Lightning service

Source files:
`deploy/spark/vllm-nemotron35/vllm.env.template`,
`deploy/spark/vllm-nemotron35/start.sh`, and
`deploy/spark/systemd/vllm-nemotron35.service`.

| Setting | Deployed value |
|---|---|
| Container image | `vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404` |
| Model | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` |
| DSpark draft model | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark` |
| Served name | `nemotron-3.5-lightning` |
| Listener | `127.0.0.1:30000` |
| Context cap | `MAX_MODEL_LEN=81920` |
| GPU memory target | `GPU_MEMORY_UTILIZATION=0.38` |
| Explicit KV cache | `KV_CACHE_MEMORY_BYTES=4G` |
| Parallel sequences | `MAX_NUM_SEQS=2` |
| Speculation | `SPEC_TOKENS=3`, `--spec-method dspark` |
| Container memory | `--memory=68g`, `--memory-swap=80g`, `--shm-size=24g` |

The vLLM command line includes:

```text
--moe-backend marlin
--kv-cache-dtype fp8
--enable-prefix-caching
--spec-method dspark
--spec-model nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark
--spec-tokens 3
--mamba-backend flashinfer
--mamba-cache-mode align
--reasoning-parser nemotron_v3
--tool-call-parser qwen3_coder
--enable-auto-tool-choice
--max-model-len 81920
--gpu-memory-utilization 0.38
--kv-cache-memory-bytes 4G
--max-num-seqs 2
--served-model-name nemotron-3.5-lightning
```

#### Qwen 3.8 Flash-Next service

Source files:
`deploy/spark/llama-qwen38/llama.env.template`,
`deploy/spark/llama-qwen38/start.sh`, and
`deploy/spark/systemd/llama-qwen38.service`.

| Setting | Deployed value |
|---|---|
| Container image | `local/llama-qwen38-mtp:560abb66` |
| Model directory | `/home/dbyte/models/qwen38-flash-next-ud-iq4-xs` |
| Main GGUF | `UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf` |
| Vision projector | `mmproj-F16.gguf` |
| MTP draft head | `MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` |
| Served name | `qwen3.8-flash-next` |
| Listener | `127.0.0.1:30001` |
| Context slot | `CONTEXT_SIZE=32768` |
| Parallel slots | `PARALLEL=1` |
| GPU layers | `GPU_LAYERS=999` and `SPEC_DRAFT_GPU_LAYERS=999` |
| KV cache | `CACHE_TYPE_K=q8_0`, `CACHE_TYPE_V=q8_0` |
| Batching | `BATCH_SIZE=2048`, `UBATCH_SIZE=512` |
| PLE loading | `--load-mode mmap`, `LAZY_MODE=on-direct` |
| Speculation | `SPEC_DRAFT_MAX_TOKENS=2`, `SPEC_DRAFT_P_MIN=0.0` |
| Container memory | `--memory=88g`, `--memory-swap=88g` |

The llama.cpp server command line includes:

```text
--model /models/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
--mmproj /models/mmproj-F16.gguf
--model-draft /models/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
--spec-type draft-mtp
--spec-draft-ngl 999
--spec-draft-n-max 2
--spec-draft-p-min 0.0
--alias qwen3.8-flash-next
--ctx-size 32768
--parallel 1
--gpu-layers 999
--flash-attn on
--cache-type-k q8_0
--cache-type-v q8_0
--batch-size 2048
--ubatch-size 512
--load-mode mmap
--lazy-mode on-direct
--reasoning auto
--reasoning-format deepseek
--metrics
```

#### OpenShell task runtime

Source files:
`deploy/spark/openshell/install.sh`,
`deploy/spark/openshell/provision-volumes.sh`,
`deploy/spark/container/openshell_runner.py`,
`deploy/spark/container/runner_launch.py`, and
`deploy/spark/systemd/prime-runner-broker.service`.

| Setting | Deployed value |
|---|---|
| OpenShell package | `0.0.116` ARM64 `.deb` with pinned SHA256 |
| Gateway name | `spark-local` |
| Task service identity | `prime-runner:prime-runner` |
| Supplementary groups | `prime-web`, `prime-local-access` |
| Dashboard runtime env | `PRIME_TASK_RUNTIME=openshell` |
| Runner state root | `/var/lib/prime-runner/users` |
| Task workspace root | `/home/WEB_OWNER/prime-agent/tasks` |
| Sandbox workdir | `/project` |
| Default task limits | `memoryGiB=8`, `cpus=4`, `runtimeMinutes=30` |
| Prime daemon socket | `/tmp/prime-daemon-<task-prefix>.sock` per task |
| Prime RPC FIFO | `/tmp/prime-rpc-<task-prefix>.fifo` per task |

If a task appears stuck, expand its in-chat task trace. It reports the last
OpenShell startup/tool stage and how many seconds have passed since runtime
output. Right-click the trace or choose **Complete output…** for the
owner-scoped, live-updating redacted log; use **Download** to retain a copy.
The output view refreshes every three seconds. Private reasoning and recognized
credentials are hidden; events above the 262 KiB runtime safety limit are not
retained. A silent tool call may still require waiting for the 30-minute task
limit or explicitly stopping that task.

Each OpenShell sandbox is created with these important switches:

```text
openshell --gateway spark-local sandbox create
  --name pt-<task-prefix>
  --from local/prime-openshell-<profile>:0.8.0-<digest>
  --policy /var/lib/prime-runner/openshell-policies/<task>.yaml
  --driver-config-json <pre-provisioned Docker volume mounts>
  --cpu <task cpus>
  --memory <task memory>Gi
  --approval-mode manual|auto
  --label prime.owner=<user>
  --label prime.profile=<profile>
  --label prime.network=<restricted|internet|lan|full>
  --label prime.task=<task-id>
  --detach
  --no-auto-providers
  --no-tty
  -- /bin/sleep infinity
```

Prime is then executed inside the sandbox with:

```text
timeout --signal=TERM --kill-after=15s <runtime>m
openshell --gateway spark-local sandbox exec
  --name pt-<task-prefix>
  --workdir /project
  --no-tty
  --env HOME=/home/prime
  --env NO_PROXY=127.0.0.1,localhost,::1
  --env no_proxy=127.0.0.1,localhost,::1
  --env TINI_SUBREAPER=1
  --env PATH=/home/prime/.prime/tools/npm/bin:/project/.venv/bin:/usr/local/bin:/usr/bin:/bin
  --env XDG_CACHE_HOME=/home/prime/.prime/cache
  --env UV_CACHE_DIR=/home/prime/.prime/cache/uv
  --env PIP_CACHE_DIR=/home/prime/.prime/cache/pip
  --env NPM_CONFIG_CACHE=/home/prime/.prime/cache/npm
  --env NPM_CONFIG_PREFIX=/home/prime/.prime/tools/npm
  --env PLAYWRIGHT_BROWSERS_PATH=/home/prime/.prime/tools/playwright
  --env PRIME_AGENT_KERNEL_PYTHON=/opt/prime-kernel/bin/python
  --env IPYTHONDIR=/home/prime/.prime/ipython
  -- /usr/local/bin/prime-container-entrypoint
     --cwd /project
     --mode rpc
     --daemon-socket /tmp/prime-daemon-<task-prefix>.sock
     --provider <selected provider>
     --model <selected model>
     --thinking <selected effort>
```

When execution mode is **Deny tools**, the runner also passes `--no-tools`.
Existing conversations add either `--resume SESSION_ID` or `--fork SESSION_ID`.

The default OpenShell filesystem policy makes these paths read-only:

```text
/usr
/lib
/proc
/etc
/opt/prime-kernel
/run/prime-gateway
/home/prime/.prime/agent/project-sources
/project-files/<approved-source>
```

and only these paths writable:

```text
/home/prime/.prime
/project
/tmp
/dev/null
/dev/urandom
/dev/random
/dev/shm
```

The device entries are granted when the sandbox is created. Chromium's TLS
runtime reads the kernel random devices and uses shared memory; because
OpenShell confinement is monotonic, adding these paths to an already-running
sandbox cannot repair a browser process that started without them.

The sandbox receives Docker bind volumes only through pre-provisioned local
volumes:

| Volume | Sandbox path | Mode |
|---|---|---|
| `prime-USER-prime` | `/home/prime/.prime` | read/write |
| `prime-USER-workspace` | `/project` | read/write |
| `prime-USER-gateway-MODE` | `/run/prime-gateway` | read-only |
| `prime-shared-mnt`, `prime-shared-media`, `prime-shared-srv`, `prime-shared-opt` | `/project-files/...` | read-only, explicitly approved paths only |

The local-path picker still rejects arbitrary `/home` paths. The controlled
`~/prime-agent/tasks/USER/` workspace is the only home-backed writeable task
mount in the default Spark recipe.

### Skills and additional tools

Installed skills live at `/home/prime/.prime/agent/skills` inside a task and in
the protected per-user Prime volume on the host. For compatibility with agents
that write beneath the work directory, `/project/.prime/agent/skills` is linked
to the same registry. Existing workspace-only skills are copied into the
registry and retained in a timestamped recovery directory during migration.

The WebUI provides a governed **Skills & tools** workflow:

1. A user opens **Settings → Skills & tools**, chooses **Request skill**, and
   uploads a ZIP containing exactly one `SKILL.md` at the archive root or inside
   one top-level directory. The request declares intended access, project
   dependencies, and any required system tools.
2. An administrator reviews the request under **Admin → Skills & tools**. The UI
   exposes the requesting account, scope, archive SHA-256, requested access,
   dependencies, and system tools before approval.
3. Approval safely validates and unpacks instruction skills into the requesting
   user's host-visible `~/prime-agent/tasks/USER/.prime/agent/skills/` registry.
   Existing same-name installs are moved to recovery storage. Approval never
   executes package managers or grants root.
4. An approved skill can be enabled for a project in **Project settings →
   Project skills**. New project chats receive that selection as shared context.
   Administrators can later disable, re-enable, deny, or recoverably remove it.

Requests for operating-system tools enter the `Sandbox image change required`
state. They must be added to a reviewed, rebuilt, digest-pinned OpenShell image;
the dashboard does not install them into a live task. Python/npm dependencies
remain explicit review data and are installed only through the normal
non-root project-environment workflow below.

The images include pip, uv, and npm. Use a persistent project environment for
additional Python packages:

```bash
uv venv /project/.venv
uv pip install --python /project/.venv/bin/python PACKAGE
```

Select **Internet** for tasks that must download packages. Caches and user-level
npm/Playwright content persist under `/home/prime/.prime`; `/usr` remains
read-only and tasks do not receive sudo. System binaries must be added to a
reviewed image profile. The `network-operations` profile includes Chromium and
ipmitool for browser-assisted BMC and IPMI work.

The supported Spark bundle includes Prime-native `bmc-headless-browser` and
`ipmi-redfish-bmc` packages. The browser adapter runs Playwright and the
profile's existing Chromium in a clean, per-browser subprocess so Prime's
persistent IPython event loop cannot retain Playwright connection state. The
private pipe bridge uses worker threads instead of IPython's asyncio subprocess
child watcher, keeping consecutive launches reliable after cancellation. Each
operation has a bounded timeout and captures worker diagnostics. Both adapters require explicit confirmation before any
power-changing action. Credentials are supplied only at runtime. Prime sees the
short skill metadata for routing, but imports these adapters only after a task
selects them. Playwright is present only in the `network-operations` image and
starts only when the BMC browser is opened.

`deploy/spark/prime/install-skills.sh` also validates and stores all 366 upstream
NVIDIA skills unchanged in protected global Prime state. Prime advertises one
`prime-nvidia-catalog` router and loads only a selected skill on demand;
directly advertising every entry would consume roughly 13,000 tokens before
each task. Catalog instructions do not override OpenShell access, role,
confirmation, or immutable-image boundaries. Re-running the installer is
recoverable. To use an already-reviewed checkout without another clone:

```bash
deploy/spark/prime/install-skills.sh --nvidia-source /path/to/NVIDIA-skills
```

## Firewall examples

Expose only the chosen HTTPS port to private LAN/VPN sources. Never expose the
backend ports 8764, 8765, 7681, 30000, or 30001.

Ubuntu with UFW:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 8443 proto tcp
```

RHEL/SLES with firewalld (adjust the source range):

```bash
sudo firewall-cmd --permanent --new-zone=prime-private
sudo firewall-cmd --permanent --zone=prime-private --add-source=192.168.0.0/16
sudo firewall-cmd --permanent --zone=prime-private --add-port=8443/tcp
sudo firewall-cmd --reload
```

The supplied Nginx configuration independently allows loopback, RFC1918, and
`100.64.0.0/10` sources and denies public source addresses.

## First use

1. Sign in with the WebUI username created during installation (initially the
   installer account's name) and the dedicated password set by
   `prime-web-password`. This is not PAM or Linux-password authentication.
2. Open **Settings → Add provider** to configure an API-key or custom
   OpenAI-compatible provider. Secrets are accepted write-only and are never
   returned to the browser.
3. Alternatively run `prime-agent`, enter `/login`, and configure a supported
   subscription provider such as ChatGPT/Codex.
4. Choose a model and effort level. Under **Security prompts**, keep **Ask each
   task** or choose **Always allow for this chat**. Project settings offer the
   equivalent project default; a new standalone chat asks once before saving it.
5. Administrators can add users and assign `user`, `power_user`, or `admin` from
   the Admin panel.

For a DGX Spark, use the tracked Nemotron and Qwen configurations under
`deploy/spark/`; both local endpoints must remain loopback-only.

## Operations

```bash
systemctl --user status prime-auth prime-dashboard-api
systemctl --user restart prime-auth prime-dashboard-api
journalctl --user -u prime-dashboard-api -f
systemctl status prime-model-gateway prime-runner-broker
prime-web-password
```

Nginx and certificate checks:

```bash
sudo nginx -t
sudo systemctl status nginx
curl -kI https://127.0.0.1:8443/login.html
```

Configuration and data live under:

- `~/prime-dgx-dashboard/` — installed WebUI application
- `~/prime-dgx-agent/` — legacy host-mode workspace and uploads
- `~/prime-agent/tasks/USER/` — host-visible OpenShell task workspace mounted
  as `/project`
- `~/.prime/agent/` — Prime sessions/settings and WebUI metadata
- `~/.config/prime-agent/web-auth.json` — mode-0600 password records
- `~/.config/prime-agent/web-sessions.json` — mode-0600 durable WebUI sessions
- `/var/lib/prime-runner/users/USER/` — isolated Prime state
- `/var/lib/prime-runner/credentials/` — protected global/per-user gateway credentials
- `/var/lib/prime-runner/image-digests.json` — approved immutable profile images
- `/var/www/prime-agent/` — static browser assets
- `/etc/nginx/prime-agent-{ca,tls}/` — private CA and server certificate

Back up the three user directories and the Nginx TLS/configuration before an
upgrade. Never commit credentials, provider settings, sessions, or TLS keys.

## Updating

Administrators can check and install published releases from Settings. Prime
Agent updates use the official versioned artifact and verify its published
SHA256SUMS entry. The WebUI updater resolves an immutable GitHub release tag.
OpenShell appears in the same section and updates only from NVIDIA's latest
stable ARM64 release with the published checksum file, while refusing to run if
OpenShell sandboxes still exist. In-app release checks require an authenticated
[GitHub CLI](https://cli.github.com/) installation because this repository is
private; core chat operation does not require `gh`.

For a manual upgrade:

```bash
git fetch --tags origin
git checkout v0.5.34
./install.sh --skip-packages --skip-prime --skip-password \
  --bind-address 192.168.1.50 --server-name prime.example.lan
```

## Security and limitations

Read the [security hardening guide](deploy/spark/security/README.md),
[OpenShell runtime-image guide](deploy/spark/container/README.md), and
[OpenShell operations guide](deploy/spark/openshell/README.md). In v0.5.14,
Prime tasks execute inside OpenShell sandboxes launched by the dedicated
`prime-runner` service identity, with protected per-user Prime state and a
host-visible task workspace under `~/prime-agent/tasks/USER/`. That workspace is
mounted as `/project` inside the sandbox; credentials, sessions, the Docker
socket, and arbitrary home-directory paths are not mounted. Each task also uses
its own sandbox-local Prime control socket so stale OpenShell worker records
cannot poison later resumes. The API retains no-new-privileges, the gateway is
loopback-only with mTLS, and full-network mode remains intentionally powerful
and limited to confirmed power-user/administrator tasks.

The **Always allow** setting is owner-scoped and stored with the chat or project,
not as a global bypass. The API honors it only when the sandbox image, execution
mode, network mode, policy-proposal mode, and local paths exactly match the saved
policy. Changing any of those controls requires the new policy to be saved in
that scope. Role restrictions, OpenShell isolation, resource limits, and the
read-only treatment of approved host paths remain enforced.

WebUI logins remain valid for up to 30 days without activity and 180 days total,
and survive `prime-auth.service` or WebUI updates through the private
mode-0600 session store. Explicit sign-out, password rotation, administrator
revocation, account disablement/deletion, idle expiry, and absolute expiry all
invalidate access. A v0.5.14 upgrade restarts the authentication service once,
so the first deployment may require one final sign-in before durable sessions
take effect.

This project provides research and workflow tooling, not investment advice or an
unattended live-trading system. Keep broker credentials and deterministic risk
controls outside model processes.

## Development and verification

```bash
python3 -m unittest discover -s deploy/spark/dashboard -p 'test*.py' -v
node --check deploy/spark/dashboard/app-v2.js
bash -n install.sh deploy/spark/update/update-prime-agent.sh \
  deploy/spark/update/update-webui.sh deploy/spark/update/update-openshell.sh
```

Run `./scripts/validate-release.sh` before publishing a change. Keep operational
history, private system notes, CAD projects, and specialized agent skills outside
the deployable WebUI repository.

## License

No license has been selected yet. Until one is added, the repository remains
all-rights-reserved by its owner.
