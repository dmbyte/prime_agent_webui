# ADR-0007: Use an SSH-tunneled Prime browser interface

- Status: accepted
- Date: 2026-08-23

## Decision

Provide browser access with ttyd 1.7.4 running as `dbyte`, bound only to
127.0.0.1:7681, and reached through SSH local forwarding. Enable WebSocket
origin checking, cap clients at two, and launch only the `prime-dgx` workspace.

## Rationale and consequences

Prime 0.8.0 provides terminal and ACP interfaces but no official browser UI.
Because Prime can execute commands and edit files as `dbyte`, a directly exposed
unauthenticated terminal would be an unacceptable authority bypass. The SSH
tunnel reuses the user's existing key authentication and encryption without
creating or storing another password or certificate. The consequence is that a
tunnel command must remain running while the browser is in use.

## Alternatives

A LAN-facing web terminal with basic authentication was rejected because it
would add a password and send HTTP without TLS. A reverse proxy with TLS and
identity-aware authentication remains a future option if direct URL access is
important. ACP editor clients remain suitable for native-editor integration.

## Rollback

Disable and stop `prime-web.service`. Terminal access through `prime-dgx` and
both model services remain unchanged.
