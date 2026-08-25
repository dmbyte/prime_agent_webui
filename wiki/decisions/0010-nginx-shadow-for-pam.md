# ADR-0010: Permit Nginx to retrieve PAM account information

- Status: superseded by ADR-0040
- Date: 2026-08-23

## Decision

Add the Nginx worker account `www-data` to supplementary group `shadow` so the
installed Nginx PAM module can validate the `dbyte` system account. Restart Nginx
and verify every worker inherits GID 42.

## Rationale and consequences

Observed authentication attempts failed with `Authentication service cannot
retrieve authentication info`; `unix_chkpwd` reported the requested user unknown.
Ubuntu's privilege boundary prevented the unprivileged web worker from retrieving
the account verifier. The user explicitly approved the conventional group fix
after being informed that a compromised Nginx process could read password hashes
and attempt offline cracking.

The interface remains TLS-encrypted, PAM-protected, private-source restricted,
and backed by loopback-only ttyd. This change fixes account retrieval but does
not replace strong passwords, timely security updates, or future migration to
client certificates/identity-aware authentication.

## Validation and rollback

`id www-data` reports groups 33 and 42; inspected Nginx workers report the same.
Nginx syntax and the project acceptance gate pass. Positive password validation
is user-only and remains to be reconfirmed. Roll back with
`sudo gpasswd -d www-data shadow`, restart Nginx, and choose another authentication
mechanism.
