# ADR-0005: Use Prime as the continually improving core

- Status: accepted for prototype; evaluation gates required
- Date: 2026-08-23
- Supersedes: ADR-0004 framework choice only
- Superseded by: none

## Context

The desired outcome is maximum long-run capability across multiple domains, not
minimum setup effort. Prime and Hermes both retain memory/skills, but Prime's
programmable RLM environment, exact child-model selection, persistent agents, and
reviewable Continual Harness provide a stronger experimental and orchestration
foundation. Hermes provides a broader ready-made personal-assistant surface.

## Decision

Use Prime Agent as the core. Nemotron remains the fast parent, Qwen3.6 the local
multimodal specialist, and GPT-5.6 Sol the gated frontier specialist. Continual
Harness changes require frozen evaluations and reviewed promotion. Add Hermes
only as a replaceable messaging/gateway layer if its channels are needed.

## Alternatives considered

Hermes as the core would reduce integration work and provide messaging, memory,
cron, and MCP features sooner. It was not selected because convenience is not the
primary objective and its session/delegation topology offers less precise control
over heterogeneous specialist children.

## Consequences

The project must build or integrate more personal-assistant surface area. In
return, model routing, context decomposition, durable refinement, and evaluation
remain under a more programmable core. “Self-improvement” adds regression and
permission-expansion risk, so promotion is deliberately conservative.

## Validation

Run frozen cross-domain task suites before and after every durable harness change.
Track task success, human correction, tool safety, latency, cost, memory, and
regressions. A change that improves one domain while weakening safety or another
domain is not automatically promoted.

## Reversal conditions

Use Hermes as core if integration burden stalls useful operation, Prime's
refinements do not produce measured gains, or Hermes matches performance while
materially improving reliability and safety.
