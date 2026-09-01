# Rootless task containers

Prime WebUI runs every agent task in a new rootless Podman container owned by
the dedicated `prime-runner` system account. The browser API never invokes
Podman or `sudo`; it connects to a peer-authenticated abstract Unix socket. The
broker validates the request, selects an immutable profile digest, and streams
Prime's RPC channel through the socket.

## Profiles

- `general`, `finance`, and `review` contain Prime, Python, Git, curl, jq, and
  ripgrep.
- `development` adds native build tools, Python headers, and checksum-pinned
  ARM64 `uv`/`uvx` 0.12.8.
- `prime-local-access` is a dedicated supplementary group for the runner. Its
  `r-x` ACL on the installer account's home boundary satisfies Podman's mount
  preparation without coupling local data access to the WebUI service group.
- `cad` adds OpenSCAD.
- `network-operations` adds nmap, ping, DNS, and traceroute tools and is limited
  to power users and administrators.

Every task is rootless, read-only, capability-free, no-new-privileges, PID/CPU/
memory/open-file/runtime bounded, and receives only its owner's Prime state,
workspace, and selected gateway socket. Host credentials, other users' data,
the Podman socket, host networking, and privileged mode are never mounted or
enabled. Image references are resolved from the root-owned digest manifest at
`/var/lib/prime-runner/image-digests.json`.

## Network modes

- **Restricted** uses `--network none` and has no network proxy.
- **Internet** uses `--network none` plus a Unix-socket HTTP CONNECT proxy that
  rejects private, loopback, link-local, reserved, and metadata addresses.
- **LAN/VPN** uses the same proxy but permits private and public destinations;
  it still rejects loopback, link-local, reserved, and metadata addresses.
- **Full** uses rootless `slirp4netns` and requires a power-user/admin role,
  execution approval, a task-specific network confirmation, and policy limits.

Local Nemotron and Qwen endpoints and ChatGPT/Codex are reached through the
credential/model gateway. OAuth material remains mode 0600 outside containers.
A per-user credential file at
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

## Install and activate

Run the normal WebUI installer first. On the DGX Spark, confirm both loopback
model endpoints are healthy, install the distribution's Podman prerequisites,
then run as the WebUI owner:

```bash
./deploy/spark/container/install-rootless.sh
./deploy/spark/container/activate-rootless.sh
```

The first command provisions `prime-runner`, subordinate UID/GID ranges,
gateway/broker services, six pinned images, and the digest manifest. The second
copies existing data without deleting newer container data, installs the API
feature drop-in, and restarts the API. It refuses activation while an API child
task is active.

## Verify and roll back

```bash
systemctl status prime-model-gateway prime-runner-broker
systemctl --user status prime-dashboard-api
./deploy/spark/container/rollback-rootless.sh --check /var/backups/RECOVERY-BUNDLE
```

`--check` is non-mutating: it validates every recovery checksum and refuses to
proceed with active containers. `--apply` requires the recovery bundle argument,
creates a new backup of the current API, copies post-activation conversations
back to host storage, restores the pre-rootless API/unit, disables the gateway
and broker, and verifies the authenticated HTTPS boundary. It intentionally
retains isolated storage and images for forward recovery.
