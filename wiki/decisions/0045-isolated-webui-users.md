# ADR-0045: Isolate WebUI users and recoverably remove their server data

Date: 2026-08-25
Status: accepted

## Decision

Replace the single-account authentication model with local WebUI accounts having
`admin` or `user` roles. Preserve salted scrypt credentials, secure sessions,
CSRF, rate limits, and the isolated loopback broker. `dbyte` is the initial admin
and owns all pre-migration data. Nginx propagates only the broker-authenticated
username and role to the loopback API.

Chats, uploads, native tasks/logs, usage, and metadata are filtered and mutated by
owner. New assets record explicit ownership; legacy assets default to `dbyte`.
Admins may add users, change role/enabled state, reset passwords, revoke sessions,
delete user cache, or delete an account. Cache/account deletion moves owned server
data into private recovery storage instead of permanently unlinking it. The
initial `dbyte` admin cannot delete its own cache/account through the UI, and the
last enabled admin cannot be removed.

## Consequences

Users cannot browse or mutate each other's chats/files/tasks through the WebUI.
Admin identity management is security-sensitive and remains CSRF/session checked.
Password reset requires an administrator-supplied new password and revokes that
user's sessions immediately. Cache deletion includes persisted task ownership,
task logs, and owned usage-ledger records even after an API restart, and also
revokes active sessions. Recovery storage requires a separate deliberate purge
decision for permanent deletion. Isolation is enforced at the authenticated
WebUI/API ownership boundary; administrators and the shared host account remain
trusted infrastructure rather than mutually untrusted OS security domains.
