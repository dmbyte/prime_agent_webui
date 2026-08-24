# ADR-0012: Add a local settings and usage dashboard

- Status: accepted
- Date: 2026-08-23

## Decision

Serve a first-party static dashboard through Nginx/PAM, embed ttyd at
`/terminal/`, and run a minimal loopback Python API as `dbyte` for allowlisted
settings changes and read-only Prime session-usage aggregation.

## Rationale and consequences

ttyd alone cannot provide controls or accounting. Prime session JSONL already
contains provider/model token usage and computed cost, avoiding a divergent
meter. Settings apply to new sessions rather than mutating an active conversation.
The dashboard reports recorded Prime usage, not an authoritative provider invoice.

The API needs Prime settings/session access and therefore runs as `dbyte`;
systemd hardening limits system writes and privilege escalation. PAM, private
source ACLs, origin/header checks, strict allowlists, and atomic writes bound it.

## Validation and rollback

API health/state/settings, parameter precision, browser panels, accounting,
embedded terminal, services, ports, and the project gate passed. Rollback disables
the API and restores v0014 Nginx/ttyd configuration.
