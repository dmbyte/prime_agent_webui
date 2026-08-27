# ADR-0054: Activate a peer-authenticated rootless task runtime

- Status: accepted
- Date: 2026-08-26
- Supersedes: the staged-only portion of ADR-0052 and ADR-0053

## Context

WebUI ownership metadata could not isolate Prime processes, host credentials, or
workspaces while all tasks ran as `dbyte`. The staged Podman design still needed
a safe identity handoff, credential/model access without secret mounts, immutable
images, per-user migration, network enforcement, and a proven rollback.

Direct API-to-sudo execution conflicted with the API's no-new-privileges sandbox.
A filesystem Unix socket also conflicted with systemd mount-namespace hardening.
Rootless Podman legitimately requires the setuid `newuidmap`/`newgidmap` helpers.

## Decision

Run every Prime task in a fresh rootless container owned by dedicated system user
`prime-runner`. The API communicates over an abstract Unix socket with a broker
that verifies kernel peer credentials and `prime-web` membership, validates a
bounded request, and resolves only digest-pinned profile images.

Keep `NoNewPrivileges=yes` and `RestrictSUIDSGID=yes` on the API. Confine the
required exception to the broker: disable those two controls, bound available
capabilities to `CAP_SETUID` and `CAP_SETGID`, grant no ambient capabilities,
hide `/home` and `/root`, and restrict address families. Containers independently
drop all capabilities, set no-new-privileges, use read-only roots, and receive
hard CPU/memory/PID/open-file/tmp/runtime limits.

Use per-user mode-0700 state/workspaces. Mount only the selected user's Prime
state, workspace, and gateway mode. Keep real credentials in the gateway;
per-user mode-0600 credentials override a global fallback. Use no direct network
for restricted/Internet/LAN modes, address-filtered proxies for Internet/LAN,
and rootless slirp only for explicitly confirmed full mode.

Create a root-only checksum recovery bundle before installation. Activation is
non-destructive to newer container conversations. Rollback preserves new
conversations, restores the pre-rootless API/unit, disables broker/gateway, and
retains isolated data/images for forward recovery.

## Consequences

- Ordinary WebUI tasks have process, storage, credential, mount, and network
  isolation instead of sharing `dbyte`.
- Rootless UID mapping creates a narrow, documented broker exception; it is not
  inherited by the API or task containers.
- Full-network mode remains intentionally powerful and requires role plus
  task-specific confirmation.
- The Advanced console remains a shared host shell and must be treated as an
  administrative compatibility path, not a tenant boundary.
- Image rebuilds must update and validate the protected digest manifest before
  use; release/install tests cover all rootless artifacts.

## Validation

Nemotron, Qwen, and Codex canaries; live persistence, steering, stop, and resume;
temporary second-account isolation; live container inspection; all four network
modes; 49 automated tests; checksum verification; and rollback `--check` passed.
