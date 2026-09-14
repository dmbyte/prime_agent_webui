# DGX Spark deployment

This tree is the reviewable source for the Spark's Prime Agent and two local
inference services. Secrets are intentionally absent. Nemotron uses vLLM;
Qwen uses a pinned llama.cpp direct-read build.

The local APIs bind only to loopback: Nemotron on port 30000 and Qwen on 30001.
Prime's default model is `spark-nemotron/nemotron-3.5-lightning`; the
`spark-qwen/qwen3.8-flash-next` UD-IQ4_XS service is the explicit
multimodal/deep specialist. Qwen's PLE table is read directly from NVMe on
demand. A shared-Q8 MTP head drafts two tokens at a time for faster
single-stream decode. Its confidence cutoff remains disabled after thresholds
through 0.3 failed to improve representative throughput.

## Production install sequence

Start from a clean checkout of the tagged release on the DGX Spark owner
account.

1. Run the repository-root installer to install the WebUI, private TLS, Nginx,
   local authentication, and user services.
2. Install Nemotron 3.5 Lightning from
   `deploy/spark/vllm-nemotron35/README.md` and confirm
   `http://127.0.0.1:30000/v1/models` responds.
3. Install Qwen 3.8 Flash-Next from `deploy/spark/llama-qwen38/README.md` and
   confirm `http://127.0.0.1:30001/v1/models` responds. Qwen 3.8 is the only
   shipped Qwen local runtime for this release.
4. Copy `deploy/spark/prime/models.json` and
   `deploy/spark/prime/settings.json` into `~/.prime/agent/` so the WebUI and
   Prime default to Nemotron while exposing Qwen 3.8 as the specialist route.
5. Install OpenShell with `deploy/spark/openshell/install.sh`. The installer
   validates the pinned upstream package, provisions `prime-runner`, installs
   the model gateway and task broker, builds the six approved Docker images,
   provisions per-user volumes, and verifies `prime-runner` gateway access.
6. Restart `prime-dashboard-api.service` and run `deploy/spark/prime/validate.sh`.

The expected steady state is:

- `prime-dashboard-api`, `prime-web`, `prime-model-gateway`,
  `prime-runner-broker`, and `openshell-gateway` active.
- `vllm-nemotron35` active on `127.0.0.1:30000`.
- `llama-qwen38` active on `127.0.0.1:30001`.
- Browser access only through authenticated HTTPS on the private LAN/VPN
  address.

Launch the configured workspace with `prime-dgx`. Prime is pinned at the
installed version until an update is deliberately reviewed and validated.

WebUI tasks run as ephemeral NVIDIA OpenShell sandboxes through the local Docker
driver. The deployment pins OpenShell `0.0.116`, applies hard Landlock
enforcement, starts with an empty direct-network policy, and carries the chosen
egress through the existing per-user Unix-socket broker. Prime state, workspace,
and gateway directories are exposed through pre-provisioned local-driver Docker
volumes; approved local files/directories use read-only subpaths of four
pre-provisioned sharing-root volumes. Install or refresh
the upstream runtime with `deploy/spark/openshell/install.sh`; that script
creates the Prime runner, protected per-user storage, model gateway, broker, and
OpenShell image set.

The authenticated sidebar also supports collapsible owner-scoped Projects and
Chats sections. A project groups independent Prime conversations and supplies
shared instructions plus selected uploaded sources and default
sandbox/tool/network/proposal/local-path controls. New project chats copy those
defaults and can then override them independently. Existing conversations can be
promoted into a new project, or added to an existing project while preserving
that project's defaults, from either the boxed `...` button beside each sidebar
chat or the chat header's **Add to project** / **Move project** button.
Conversation controls remain visible below the chat header and persist for the
whole chat. Source copies are refreshed lazily
beneath the owner's mounted Prime state and are read-only under the OpenShell
filesystem policy. Deleting a project detaches its conversations instead of
deleting them.

Install dashboard static files with
`deploy/spark/dashboard/install-static.sh`. HTML belongs in the web root while
JavaScript and CSS belong in `/var/www/prime-agent/assets/`; placing assets in
the web root leaves the login page visible but nonfunctional.

`prime-web.service` provides a browser terminal on Spark loopback port 7681.
Nginx exposes it at `https://172.16.253.231:8443` with session authentication
and allows only private LAN/VPN source ranges. The session broker validates a
dedicated WebUI password against a mode-0600 salted scrypt record; it does not
use PAM or the Linux account password. The portable installer installs
`set_web_password.py` as `~/.local/bin/prime-web-password`. Run that command
interactively as the non-root WebUI owner, then restart
`prime-auth.service`; never run the password tool with `sudo`. The account name
is used only as the initial WebUI username, not as a system-authentication source.
The ttyd backend remains loopback-only.
Nginx validates WebSocket origins against the approved HTTPS hostnames before
proxying; ttyd's backend-origin check is disabled because it cannot see through
the reverse proxy correctly.

`nginx-prime-address-wait.conf` replaces Nginx's preflight sequence so it waits
up to 120 seconds for the private LAN address before validating its explicit
binds. Install it as `/etc/systemd/system/nginx.service.d/prime-address-wait.conf`
and install `prime-wait-address` as `/usr/local/sbin/prime-wait-address`.
