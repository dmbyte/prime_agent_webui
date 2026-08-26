# ADR-0051: Use Prime RPC for interactive WebUI tasks

Date: 2026-08-26
Status: accepted

## Context

One-shot JSON/print mode streams progress well but exits after one prompt and is
not addressable by Prime's external agent-message daemon while running. A live
test showed that its session event identifies saved conversation state, not a
daemon-managed messaging target. Prime documents RPC mode specifically for
custom interactive UIs and exposes prompt, steer, follow-up, and abort commands.

## Decision

Launch native WebUI work in persistent RPC mode with piped stdin/stdout. Send the
initial prompt through RPC, process safe output events incrementally, and accept
owner-scoped `steer`, `follow_up`, and `abort` commands only while that exact task
still owns an open input channel. Close the channel after the final `agent_end` so
the subprocess exits and normal ledger/session reconciliation completes.

## Consequences

The conversation UI can genuinely redirect, queue, and stop running work without
attaching to a terminal or relying on daemon visibility. The API now owns a
bidirectional subprocess channel, so writes are serialized under the task lock,
RPC response bookkeeping is bounded and server-only, and upgrades must regression
test Prime's RPC event/command contract.
