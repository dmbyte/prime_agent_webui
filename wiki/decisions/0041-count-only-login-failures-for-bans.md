# ADR-0041: Count only actual login failures for reactive bans

- Status: accepted
- Date: 2026-08-25

## Context

After v0052 invalidated the former browser authentication state, the stale v0051
page continued polling API endpoints. Fifteen ordinary session-expiry 401
responses caused Fail2ban to block the owner's client `172.16.253.114`, making
the WebUI appear offline even though Nginx and all backend services were healthy.

## Decision

Match only HTTP 401 responses from `POST /auth/login`. Keep the existing threshold
of 15 failures in 10 minutes and one-hour nftables ban. Do not count 401 responses
from authenticated API, asset, or terminal routes.

## Consequences

Stale or expired UI polling cannot ban a legitimate client. Repeated invalid PAM
password attempts retain reactive blocking. No CIDR firewall policy is added.

## Validation and rollback

The Fail2ban configuration test passed, the stale client ban was removed, the
nftables set became empty, and HTTPS returned the expected 302 login response
from the previously blocked client. Restore the v0052 filter only if deliberately
accepting false-positive bans from expired sessions.
