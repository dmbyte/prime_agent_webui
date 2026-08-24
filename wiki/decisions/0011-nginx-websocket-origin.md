# ADR-0011: Enforce WebSocket origin at Nginx

- Status: accepted
- Date: 2026-08-23

## Decision

Validate `/ws` Origin headers in Nginx against the approved HTTPS LAN/loopback
hostnames and remove ttyd's `--check-origin` flag. Keep ttyd bound only to
127.0.0.1 so every network WebSocket must pass through Nginx's private-source,
TLS, PAM, and origin controls.

## Rationale

ttyd behind a reverse proxy sees its internal loopback host while the browser
sends the correct external HTTPS origin. Its check rejected all valid clients,
causing 502 responses and a continuous “press return to reconnect” loop. Nginx
sees both the external Origin and requested host and is therefore the correct
enforcement layer.

## Validation and rollback

Logs show an accepted `/ws`, one connected client, and a spawned Prime process.
The live browser exposed an active terminal input with no reconnect message.
Configuration and the complete acceptance gate pass. Rollback restores the old
unit/site but also restores the defect; use v0008 SSH-only access if functional
rollback is required.
