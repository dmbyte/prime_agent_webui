# ADR-0050: Use Prime's parser-verified busy-agent send for steering

Date: 2026-08-26
Status: accepted

## Context

Prime 0.8.0's generated help advertises `send --steer` and
`send --follow-up`, but live validation showed that the installed parser rejects
both flags. Its changelog and parser agree that ordinary agent messages now use
steering delivery, and `send <agent> --message <text>` reaches active-agent
lookup successfully.

## Decision

Deliver WebUI steering with `send <agent> --message <text> --json`. Continue to
validate the authenticated task owner, running state, agent ID, message size, and
argument-array execution. Do not offer follow-up until the installed Prime CLI
provides a parser-verified supported mechanism.

## Consequences

The WebUI offers only commands it can actually honor: Message, `/steer`, and
`/stop`. A future Prime release may restore or replace explicit delivery modes;
the updater review must verify behavior against the installed parser and a live
busy task rather than relying on help text alone.
