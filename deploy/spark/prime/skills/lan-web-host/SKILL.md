---
name: lan-web-host
description: Deploy and share a LAN-accessible container web server for ISO/BMC virtual media, public task files, or a web application preview. Discover and manage existing task/project hosting services.
---

# LAN web hosting

Use the managed hosting tool when asked to make files or an app reachable by
other machines. Requires a task with LAN or Full network access and tools enabled.
Do not launch `http.server` in the ephemeral task and return its container IP.

In an IPython cell, load the installed standard-library client:

```python
import sys
sys.path.insert(0, "/home/prime/.prime/agent/skills/lan-web-host/scripts")
from prime_web_host import WebHost
host = WebHost()
host.list()  # discover services from this task and its project first
```

Stage **only material the user intends to publish** in a dedicated directory
under `/project/hosted/`, for example `/project/hosted/install-media` or
`/project/hosted/demo-public`. Never publish a whole workspace, credentials,
private configuration or chat logs. All non-hidden regular files in a static
publish directory are readable by LAN clients without login. No directory
listing, dotfiles or symlinks are served. A direct ISO URL needs no cookies.

```python
service = host.static("install-media", "/project/hosted/install-media")
iso_url = host.file_url(service, "installer.iso")
print(iso_url)  # actual Spark LAN address, not 127.0.0.1 or a Docker IP
```

This supports HEAD and single HTTP byte ranges (206/416) for virtual media and
resumable downloads, without loading an ISO into RAM. Use an actual file URL for
BMC media, not the service root. Verify the file exists and report its size.
Mounting/rebooting a BMC is a separate user-authorized operation; hosting alone
does not authorize it. The returned URL is reachable from the Spark's LAN;
cross-VLAN routing/firewall access must be verified from the intended client.

For an application, prebuild/install its dependencies within its dedicated
published directory, then run an argument array (not a shell string):

```python
service = host.app("demo", "/project/hosted/demo", ["node", "server.js"])
```

The app must listen on `127.0.0.1:8000`. It receives `HOST`, `PORT`,
`PRIME_HOST_URL` and `PUBLIC_URL` (the real LAN URL), and has Python/Node available.
Its source is read-only at `/site`; `/tmp` is writable but disposable. No model
keys, task gateway or outbound network access. Prepare dependencies in the task
before launching. Build outputs before publishing; development servers needing
to write alongside sources must be configured to use `/tmp`. Set a specific
allowed host to the returned IP when the framework requires one; don't disable
host checks globally. Raw TCP forwarding supports HTTP and WebSocket apps.
The app is responsible for authentication and which of its own routes are public.
Do not use this HTTP preview service for secrets or production Internet hosting.

Default scope is `project` in a project, otherwise `task`. Other authorized tasks
in that project can discover/reuse the service with `host.list()` and its name.
Pass `scope="task"` for a task-only registry entry. These are discovery/control
scopes, **not access controls on the public HTTP URL**. Services intentionally
outlive the agent task, default 24 hours, renewable up to 72 hours from now:

```python
host.renew(service["id"], ttl_hours=48)
host.logs(service["id"])  # bounded diagnostics; redact secrets before reporting
host.stop(service["id"])  # releases port/container; original files are retained
```

Maximum four services per owner, each two CPUs/1 GiB RAM. A failed service stays
listed for diagnosis; read logs and explicitly stop it before retrying. Do not
retry a failed launch repeatedly or stop somebody else's active hosting to free
capacity. Report the URL, scope, expiration and any unverified client reachability.
