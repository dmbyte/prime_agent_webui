# ADR-0049: Stream safe task state and use supported Prime steering

Date: 2026-08-26
Status: superseded by [ADR-0050](0050-use-parser-verified-prime-steering.md)

## Context

New-chat submissions were invisible until Prime created and persisted a session,
leaving only a small Working label. The dashboard also collected Prime's process
output only after completion, so long tasks could not show dialogue-local progress
or accept steering from the user.

## Decision

Render submitted text optimistically before starting the API request and reconcile
it with the persisted transcript after Prime publishes a session ID. Incrementally
consume Prime's JSON event stream, retaining only bounded safe lifecycle/tool
events, usage, and draft assistant text. Do not expose reasoning content.

Capture Prime's running agent ID and use its supported `send --steer` and
`send --follow-up` commands. Accept messages only for the authenticated owner's
currently running task, validate mode/length/agent ID, use argument arrays, bound
the command timeout, and retain the existing explicit stop path. Present ordinary
Message, `/steer`, `/follow-up`, and `/stop` in the composer.

## Consequences

Users receive immediate acknowledgement and visible progress in the conversation
and can redirect or queue work without console attachment. Streaming parsing and
browser payloads are bounded, but event names remain coupled to Prime's documented
JSON protocol and require regression checks when Prime changes. Draft text may be
revised before the final persisted response.
