# ADR-0027: Preserve explicit attachment but prohibit UI attachment

Date: 2026-08-24
Status: accepted
Supersedes: [ADR-0026](0026-prohibit-browser-attach.md)

## Context

ADR-0026 incorrectly disabled browser attachment as a capability when the actual
problem was the dashboard automatically issuing an attach request and maintaining
a second TUI. Cached old JavaScript also reconnected immediately when the original
two-argument launcher form was restored.

## Decision

Keep the activity UI strictly event-only and remove all attach-related JavaScript.
Preserve intentional session attachment through an exact launcher-only form:
`--attach ID --explicit`. Validate the ID syntax and session file before forwarding
Prime's native `attach ID`. Reject every other attach-shaped request with exit 64
so stale cached UI cannot attach or fall through to a new conversation.

## Consequences

The dashboard never sends an attach command to the session or LLM. An operator can
still deliberately attach by constructing the explicit launcher request. The
extra marker is a safety interlock rather than authentication; PAM/TLS/private-
network controls remain the access boundary. Cached two-argument URLs become inert.

## Rollback

Restore the v0036 launcher to disable explicit browser attachment, but retain the
event-only dashboard JavaScript. Do not restore automatic overlay attachment.
