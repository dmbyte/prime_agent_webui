# ADR-0022: Offer a read-only attached live console

Date: 2026-08-24
Status: accepted

## Context

The sanitized activity feed is safe and compact, but it cannot show the actual
Prime terminal state. The operator explicitly wants an option to follow the real
console while background tasks run.

## Decision

Offer a **Live console** control per active-task tab. Lazily attach ttyd to only
the selected Prime session, render it read-only inside the overlay, and retain a
control to return to the sanitized event feed. The launcher forwards only an
exact `--attach ID` request whose ID has a strict syntax and an existing session
file. All other browser arguments remain discarded.

## Consequences

The authenticated operator can see the highest-fidelity live task state, including
content deliberately excluded from the safe event API. That makes the existing
private LAN/VPN, TLS, and PAM boundary essential. Read-only presentation prevents
accidental input; intentional control remains available in the primary terminal.
Attaching only the selected task limits resource use and fits ttyd's two-client
limit.

## Rollback

Restore the v0031 launcher, dashboard JavaScript, and HTML, and remove
`live-console.css`. The sanitized background event feed remains available.
