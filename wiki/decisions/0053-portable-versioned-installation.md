# ADR-0053: Ship a portable, versioned host-mode installer before container activation

Date: 2026-08-26
Status: accepted

## Context

The tracked deployment evolved on one DGX Spark and contained host-specific
paths, origins, and administration defaults. A new host needed a clear complete
installation path, while rootless task execution still lacks its credential
gateway, service identity, data migration, and end-to-end evidence.

## Decision

Release v0.2.0 with a non-root, distribution-aware installer for current
systemd-based Debian, Red Hat, and SUSE families. Parameterize the private bind
address, name, port, repository, allowed origins, and initial administrator.
Install the verified host-mode services, pinned Prime Agent version, private TLS,
and dedicated WebUI password; verify service health and the unauthenticated API
boundary. Do not modify a host firewall, install Podman as a production
dependency, or enable the container feature flag.

Publish a synthetic-data screenshot and OS-specific package/firewall guidance.
Validate required release contents, shell/JavaScript syntax, Python compilation,
and the complete dashboard test suite before release. Release updates must
resolve immutable tags and pass tests before replacing installed assets.

## Consequences

Fresh systems have one documented installation entry point without falsely
claiming production-grade tenant isolation. Rootless-preview packages and gates
are explicit and separable. The installer still requires systemd, Nginx, sudo
for host provisioning, and a trusted private LAN/VPN; GPU-local model recipes
remain DGX/Ubuntu-specific. Rollback selects the prior immutable tag and reruns
the installer after restoring the documented data/configuration backup.
