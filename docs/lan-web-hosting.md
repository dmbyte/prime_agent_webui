# LAN web hosting for Prime tasks and projects

The `lan-web-host` managed skill deploys a **separate OpenShell container** for
ISO/file hosting or a web application preview. It returns a URL using the
Spark's assigned LAN IPv4 address and a published host port—not a container IP,
loopback URL or `.openshell.localhost` name. Other computers that can route to
that LAN address can use it. This is not automatic public-Internet publishing.

## Use in Prime

Start a task with **LAN or Full network access and tools enabled**. Ask, for
example: “Use lan-web-host to publish this installer ISO for the BMC, and return
the direct ISO URL” or “Host this project's built web application on the LAN.”
The skill appears in the installed/project skills inventory. Existing tasks
started before the hosting upgrade need a new turn/task to receive its control
capability. A selected project supplies the service's default discovery scope.

The installed skill explains its dependency-free Python client. For an explicit
tool call inside the task:

```python
import sys
sys.path.insert(0, "/home/prime/.prime/agent/skills/lan-web-host/scripts")
from prime_web_host import WebHost
host = WebHost()
host.list()
service = host.static("install-media", "/project/hosted/install-media")
iso_url = host.file_url(service, "installer.iso")
```

First stage only the intended public files in the named directory. The host
location is `~/prime-agent/tasks/OWNER/hosted/install-media/` under the default
workspace. The tool does not copy multi-gigabyte ISOs into RAM or make a second
copy; the container mounts the selected directory read-only. Static serving
supports GET, HEAD, single byte ranges, suffix ranges, 206 and 416. It denies
directory listings, hidden path components, symlinks, traversal, and writes.
Use a **direct file URL** for virtual media; an empty root may return 404.

For a prebuilt app:

```python
service = host.app("preview", "/project/hosted/preview", ["node", "server.js"])
```

The command runs in `/site` and must listen on **127.0.0.1:8000**. The sandbox has
Python and Node from the pinned development image. Its minimal environment has
`HOST=127.0.0.1`, `PORT=8000`, and both `PRIME_HOST_URL` and `PUBLIC_URL` set to
the published LAN URL. Raw TCP forwarding carries HTTP and WebSockets. Build
and install dependencies in the task before publishing; app source is read-only,
`/tmp` is disposable scratch, and the hosting sandbox has no outbound egress,
model gateway, task-control socket or credentials. Frameworks needing a writable
cache must put it in `/tmp`. Configure framework host checks for the advertised
address. Apps control their own routes/authentication; static-server path
restrictions do not apply to application-defined routes.

## Sharing, lifetime and controls

- Default scope: **project** for project tasks, otherwise **task**. Related task
  processes can list/reuse their own services; later authorized tasks in the same
  project discover project services by name. Task-private services are not listed
  to other tasks. Names are unique within a caller's visible scope.
- A trusted launcher supplies owner/task/project claims in a short-lived
  capability. Callers cannot choose another identity in the request. Completing
  a task revokes its capability but **does not stop its hosted service**.
- Default lifetime **24 hours**; create/renew accepts **1–72 hours**. `renew(id,
  ttl_hours=48)` extends from now; `stop(id)` releases the container/port and
  keeps source files. `logs(id)` returns a bounded diagnostic tail, which may
  contain application output; redact sensitive text before sharing it.
- At most **four services per installed owner**, each **2 CPUs / 1 GiB maximum**.
  Static transfers use 256-KiB chunks and at most 32 concurrent HTTP connections.
  No GPUs are assigned. Each service uses one port from **18080–18111**.
- Broker state is persisted under `/var/lib/prime-runner/hosting/OWNER/`. On a
  broker/host restart, unexpired services are recreated on their recorded ports.
  There is downtime during recovery; downloads are not uninterrupted. An IP
  change or failed recovery is reported as failed rather than silently returning
  a different URL. Stop/recreate after resolving it. Failed services remain
  listed for diagnosis and consume a service slot until stopped/expired.
- Scope protects **discovery/control**, not the HTTP URL. The owner workspace is
  already shared across that owner's tasks; project scope is not a new filesystem
  isolation boundary. Publishing is intentional unauthenticated LAN access.

Do not put secrets/private data in a published directory or preview app. HTTP
traffic is unencrypted; LAN clients can access it without a WebUI login. Do not
forward these ports through an Internet router. Use a separately reviewed
authenticated/TLS deployment for sensitive or production services. Publishing
an ISO does not authorize BMC media insertion, boot changes or server resets.

## Installation and network configuration

The full `deploy/spark/openshell/install.sh` installs the broker, launcher
integration, admitted owner control volume and bundled skill. The WebUI updater
uses that installer. Upgrades refuse to continue while hosting services exist,
so an ISO download is not silently interrupted. Explicitly stop the services
before upgrading. Do not run the full installer while other Prime/KVM work is
active. `install-hosting.sh` is a component installer, not a replacement for the
full task launcher/API/skills upgrade.

The broker selects the default-route source address if it is an assigned RFC1918
IPv4 address on an active non-container interface; otherwise it uses the sole
eligible LAN address or fails with a configuration error. It binds to that exact
address, never wildcard, loopback, Docker bridge or a public address. For a
multi-NIC host, set an explicit **assigned LAN address**:

```ini
# sudo systemctl edit prime-hosting-broker.service
[Service]
Environment=PRIME_HOSTING_LAN_IP=192.168.1.50
```

Restart the broker after configuration changes; stop existing services first if
changing the address. A DHCP reservation is recommended. Permit TCP ports
18080–18111 **only from the intended client/BMC networks** in any host/VLAN
firewall. The installer does not widen firewall rules or configure NAT. A URL
working from the Spark does not prove a BMC on a different VLAN can reach it.

Underneath, the broker runs the equivalent of:

```text
openshell --gateway spark-local forward service ph-<id> \
  --target-port 8000 --local <Spark-LAN-IP>:<allocated-port>
```

The OpenShell gateway itself stays on loopback with mTLS. No Docker socket or
gateway credential is given to tasks or hosted applications. The broker uses
the already admitted owner workspace volume with a selected directory subpath,
and the existing pinned development image. Hosting needs no new image rebuild
on an otherwise up-to-date installation. Its standard-library client is installed
in the owner's mounted managed-skill directory, not baked into the immutable
image layers; this keeps the approved image IDs unchanged. See
[OpenShell sandbox service documentation](https://docs.nvidia.com/openshell/latest/sandboxes/manage-sandboxes.html).

## Administrator operations and verification

On the Spark, replace `OWNER` with the installed WebUI owner:

```bash
sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner OWNER list
sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner OWNER logs SERVICE_ID
sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner OWNER renew SERVICE_ID --hours 24
sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner OWNER stop SERVICE_ID
sudo journalctl -u prime-hosting-broker.service --no-pager -n 50
```

Use these controls rather than deleting `ph-` sandboxes behind the broker's back.
Admin controls are a host CLI in this version, not a new WebUI hosting panel.
Stopping a task-only service after its task finishes requires these admin
controls, or waiting for expiry. Project-scoped services can be managed by the
next authorized task in that project.

Tests (use synthetic fixtures, never a real BMC):

```bash
bash scripts/validate-release.sh
sudo -u prime-runner env HOME=/var/lib/prime-runner PRIME_WEB_OWNER="$USER" \
  python3 deploy/spark/prime/validate-hosting.py start
# On another LAN machine, use the two URLs printed above:
python3 scripts/validate-hosting-lan.py --static http://SPARK_IP:18080/ --app http://SPARK_IP:18081/
# Back on the Spark, stop ONLY the recorded fixtures:
sudo -u prime-runner env HOME=/var/lib/prime-runner PRIME_WEB_OWNER="$USER" \
  python3 deploy/spark/prime/validate-hosting.py finish
python3 deploy/spark/prime/validate-prime-hosting-task.py
```

The first fixture tests a sparse 5-GiB ISO, app URL environment, project isolation
and real task-container discovery; the remote check tests range/HEAD/path safety
and a WebSocket frame. Fixture source files and the model-driven diagnostic
conversation are retained; fixture containers/ports are stopped. The model-driven
test uses the actual production launcher and a task-private synthetic service.
Set `PRIME_HOSTING_TEST_IP` to the Spark LAN IP for that model-driven test when
it differs from this recipe's deployed address, `172.16.253.231`.
