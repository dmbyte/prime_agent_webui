# ADR-0042: Use a dedicated local WebUI password instead of PAM

- Status: accepted
- Date: 2026-08-25

## Context

The unprivileged broker's systemd confinement forces no-new-privileges, which
prevents Ubuntu's set-group `unix_chkpwd` helper from reading the Linux account
record. Removing all directives that imply this protection or running the broker
with elevated access would weaken isolation. The owner elected to retire PAM.

## Decision

Use a separate WebUI password stored only as a strict mode-0600 salted-scrypt
record outside the repository. Set it through an interactive, no-echo command.
Keep the broker unprivileged, loopback-only, read-only, network-restricted, and
session/CSRF protected. Do not reuse or inspect the Linux account password.

## Consequences

The WebUI password has an independent lifecycle and must be created once after
deployment or rotated with `prime-web-password`. The broker never needs `shadow`
or set-user/group execution. Loss of the WebUI password is recovered through SSH
key access by setting a new one; existing sessions remain until broker restart or
expiry.

## Rollback

The pre-v0056 PAM files are preserved at
`/var/backups/prime-local-auth-v0056-20260825T170500-0500`. Restoring PAM would
also require resolving its helper/confinement incompatibility and is not
recommended.
