# ADR-0040: Use a native session-authenticated Prime WebUI

- Status: accepted
- Date: 2026-08-25

## Context

The ttyd-first UI made conversation control dependent on terminal state, while
Nginx PAM Basic Auth required Nginx to read password hashes. The owner requested
session authentication, trusted TLS support, isolated tasks, native chat, richer
files/activity/usage/admin, and full conversation management.

## Decision

Use a loopback-only PAM broker to issue secure, expiring sessions and remove
Nginx from `shadow`. Serve a native chat client backed by structured Prime CLI
tasks with bounded concurrency, process groups, timeouts, message polling, and an
append-only task ledger. Retain ttyd only as an authenticated advanced console.
Add private-CA TLS, safe file preview/archive/retention controls, administration,
and expanded conversation metadata/actions. Do not add a CIDR firewall policy.

## Consequences

Nginx cannot read password hashes and browser credentials are no longer replayed
on every request. Normal chat no longer manipulates terminal sessions. The auth
broker's sessions are intentionally invalidated on service restart. Each client
must install the private CA, and the owner must perform positive password-entry
validation because automation never receives the password.

## Rollback

Restore individual files from
`/var/backups/prime-webui-v0052-20260825T153014-0500`, restore the prior
certificate if needed, and re-run the listener and model gate. Re-enabling the
old Nginx PAM module would also require knowingly restoring `www-data` shadow
access and is not recommended.
