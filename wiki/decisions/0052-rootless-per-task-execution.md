# ADR-0052: Isolate WebUI work in policy-controlled rootless task containers

Date: 2026-08-26
Status: accepted; staged implementation

## Context

Distinct WebUI accounts currently launch Prime and its tools as `dbyte`. A local
task can therefore reach other users' data and forge the loopback headers trusted
by the dashboard API. The owner approved ephemeral rootless containers, isolated
per-user persistence, gateway-held model/provider credentials, role-bounded
resources and networks, explicit execution approval, and a staged migration.

## Decision

Run each task in a fresh rootless Podman container under a dedicated service
identity. Containers are read-only except for a private user agent directory,
private workspace, and bounded temporary storage. Drop all capabilities, set
no-new-privileges, impose CPU/RAM/PID/open-file/runtime limits, never mount the
Podman socket or host credentials, and never use host networking or privileged
containers. Prime `--no-tools` enforces denied execution.

Normal users receive restricted or filtered-Internet modes. Power users and
administrators may also choose LAN/VPN or full network. Private/full access is
confirmed separately for every task. Full mode uses rootless user-mode networking;
restricted and filtered modes fail closed and will reach model/provider services
through an authenticated Unix-socket gateway. High-speed/raw scanning remains a
future narrow helper, not a reason to grant broad host capabilities.

User credentials override global provider credentials when configured. A failed
personal credential does not silently fall back to the global one. Provider and
local-model secrets remain in the gateway and are not mounted into task
containers. Each profile is a pinned image; administrative package overrides
build a candidate image and never modify the host.

## Consequences

The gateway, per-user migration, dedicated identities, remaining profile images,
and full end-to-end tests are activation gates. Until they pass, the deployment
continues using the verified host execution path. The candidate feature flag is
off by default. Rollback removes the candidate and Podman packages if desired,
then restores the v0079 pre-change bundle; no production data conversion has yet
occurred.

