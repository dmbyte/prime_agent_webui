# ADR-0003: Prototype with Prime Agent

- Status: superseded
- Date: 2026-08-23
- Supersedes: none
- Superseded by: ADR-0004

## Context

The two local vLLM models need an agent scaffold that preserves long-running
work, tools, context, and durable learning while routing coding tasks from the
fast Nemotron parent to the stronger Qwen specialist.

## Decision

Prototype with Prime Agent. Configure Nemotron as the parent and select Qwen
explicitly for RLM children. Keep routing rules and harness refinements reviewed,
versioned, and reversible.

## Alternatives considered

Hermes Agent offers stronger personal memory, messaging integrations, scheduling,
and omnichannel operation. A custom router offers more control. Prime is selected
because exact per-child model choice and long-running coding/research primitives
best match the current goal without building an agent runtime from scratch.

## Consequences

The project can test the two-model architecture quickly and retain an escape hatch
to Hermes or a custom runtime. Prime-generated code runs with user permissions and
is not inherently sandboxed, so external isolation and strict tool controls are
mandatory for untrusted work.

## Validation

Run the comparative task, routing, compatibility, memory, safety, and failure
tests in `wiki/AGENT_FRAMEWORK.md` before production promotion.

## Reversal conditions

Switch if Prime cannot reliably call both local models, its prompt/tool protocol
does not fit the checkpoints, orchestration overhead erases quality gains, or
messaging/personal-automation needs become the primary product requirement.
