# ADR-0008: Add PAM authentication over private HTTPS

- Status: accepted
- Date: 2026-08-23

## Decision

Front the loopback ttyd service with Nginx on 127.0.0.1:8443, require PAM
authentication through the `prime-agent-nginx` policy, and encrypt credentials
with TLS. Keep both layers reachable only through SSH local forwarding. Use the
existing `dbyte` system account; never collect its password in project files or
automation.

## Rationale and consequences

This adds authentication at the web boundary while retaining SSH as a separate
network boundary. A self-signed certificate provides encryption immediately but
causes a browser trust warning. The accepted design does not add Nginx to the
`shadow` group and does not expose the command-capable terminal to the LAN.

An alternative design that granted the Nginx worker `shadow` membership and
listened on the LAN was rejected as an unnecessary privilege and blast-radius
increase. A trusted internal CA certificate or identity-aware reverse proxy can
replace the self-signed certificate later.

## Validation and rollback

Nginx configuration validation passed; the HTTPS route returns a PAM 401
challenge without credentials; Nginx, ttyd, both models, private bindings, and
the memory gate pass. Positive login remains a user-only test because the PAM
password was never shared. Roll back by removing the site and PAM policy,
reloading Nginx, and restoring the v0008 SSH-only access design if desired.
