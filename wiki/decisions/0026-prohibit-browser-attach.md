# ADR-0026: Prohibit browser session attachment

Date: 2026-08-24
Status: superseded by [ADR-0027](0027-explicit-not-automatic-attach.md)
Supersedes: [ADR-0022](0022-read-only-live-console.md)

## Context

The overlay's second ttyd TUI attached to a running Prime session and interfered
with the job despite being visually read-only. Two ttyd children were confirmed:
the original main client and the later attachment client.

## Decision

Remove the later attachment client without stopping the daemon-managed worker.
Retire the live-console UI, keep the sanitized event feed, and make the browser
launcher reject every `--attach` request before it can invoke Prime. Retain a CSS
compatibility guard so old cached dashboard JavaScript cannot expose the control.

## Consequences

The browser has one interactive Prime TUI, eliminating competing attachment
clients. The overlay no longer provides raw console fidelity but remains safe for
task monitoring. Direct command-line attachment is not changed by this dashboard
policy; only browser launcher attachment is prohibited.

## Rollback

Do not restore browser attachment until its multi-client behavior is proven safe
against a disposable task. If later approved, supersede this ADR and redeploy the
v0035 launcher and live-console assets.
