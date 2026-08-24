# Agent Framework Analysis

> Updated by v0005 and ADR-0005. Prime is the core reasoning/orchestration layer
> for long-run capability; Hermes is an optional outer messaging gateway.

Status: Prime Agent 0.8.0 commissioned; domain qualification remains  
Last researched: 2026-08-23

## Conclusion

Use **Prime Agent** for this DGX Spark project. Keep Nemotron 3.5 Lightning as the
parent/default model and spawn Qwen3.6-35B-A3B-NVFP4 as an exact-model RLM child
for multimodal, spatial, financial, implementation, debugging, or review work.

This is a better structural match than Hermes Agent because the objective is a
high-capability coding/research agent using two specialized local models—not
primarily a persistent personal assistant across chat applications.

## Comparison

| Criterion | Prime Agent | Hermes Agent |
|---|---|---|
| Local vLLM endpoints | Explicit custom OpenAI-compatible providers/models | Custom OpenAI-compatible endpoint supported |
| Two-model specialist routing | Exact model selector on each `rlm()` child | Main session is one model; delegation can use another model |
| Long-running coding/research | Core design: daemon sessions, goals, heartbeats, autonomous limits | Supported through persistent agent, gateway, cron, and delegation |
| Context strategy | RLM treats context as variables and delegates compact subproblems | Compression, session search, memory, skills, and model switching |
| Durable learning | Continual Harness with reviewable snapshots and rollback | Self-created/improving skills and agent-curated memory |
| Project fit | Strongest | Good, but optimized more broadly for personal-assistant workflows |
| Messaging and personal automation | Not the main strength | Strongest: multiple chat channels, scheduling, profiles |
| Security boundary | Explicitly not a sandbox; generated Python/commands run as the user | Command approval and container/remote terminal options are documented |

## Why Prime Agent wins here

### Exact heterogeneous subagents

Prime Agent's `rlm.run()` accepts an exact `provider/model` selector. This maps
directly onto two separately hosted vLLM endpoints:

- Parent: Nemotron for planning, tool selection, synthesis, and routine work.
- Child: Qwen Coder for difficult repository work and independent review.

The child gets a focused task packet rather than forcing a mid-session model
switch or copying the whole parent context. It also lets the parent run more than
one independent Qwen review when the workload justifies it. Because both models
share one Spark, default concurrency must remain low and measured; parallel child
support is not permission to saturate unified memory bandwidth.

### Long-task continuity

Daemon-backed sessions, persistent goals, heartbeats, schedules, background
children, automatic compaction, and bounded autonomous mode suit long coding and
research work. The persistent Python environment also makes programmatic
inspection, tool use, and subagent coordination first-class.

### Durable, reversible learning

Prime's Continual Harness can retain memories, prompts, skill descriptions, and
subagent specifications with refinement history and snapshots. That aligns with
this repository's immutable wiki snapshots, provided automatic refinements are
reviewed before becoming trusted project behavior.

## Where Hermes is better

Choose Hermes instead if the main product is an always-on personal or operations
assistant accessed through Telegram, Discord, Slack, WhatsApp, Signal, email, or
voice. Hermes has richer out-of-box messaging, cron delivery, user-oriented
memory, a large tool/skill surface, multiple terminal backends, and Mixture of
Agents.

Hermes can use the proposed model pair: set one as the main model and the other as
the delegation model, or configure both in a Mixture-of-Agents preset. However,
its current main conversation remains tied to one model; automatic context-aware
main-model routing was explicitly reported as not planned. Delegation still
works, but Prime exposes exact per-child model choice more naturally for this
project's controller/specialist topology.

## Why not start with a custom framework

A small bespoke router would provide maximum control, but it would require us to
build session persistence, tool execution, cancellation, compaction, child-agent
lifecycle, recovery, and observability before measuring model quality. Start on
Prime Agent, instrument it, and replace only the components that benchmarks show
are limiting.

## Prototype topology

1. Two vLLM servers run locally on separate loopback ports with conservative
   memory reservations.
2. Prime Agent defines each endpoint as a separate custom provider/model.
3. The main Prime session uses Nemotron.
4. Project instructions define deterministic escalation triggers.
5. Nemotron calls `rlm(..., model=<exact Qwen selector>)` with a compact task
   packet when escalation is needed.
6. Qwen returns a proposal or review; Nemotron reconciles it with requirements
   and owns the user-facing result.
7. Tool permissions and irreversible actions remain controlled outside the
   models.

Do not put both models behind a proxy that presents them as one opaque model in
the first prototype. Keeping their identities explicit improves routing tests,
telemetry, failure isolation, and reproducibility.

## Required qualification

- Confirm Prime Agent sends compatible system roles, reasoning fields, tool
  schemas, and streaming requests to both pinned vLLM endpoints.
- Test tool-call correctness separately for Nemotron parent and Qwen child.
- Measure end-to-end task completion, not merely tokens/second.
- Compare four modes on the same task suite: Nemotron only, Qwen only, routed
  Prime pair, and routed Hermes pair.
- Track child-call rate, routing precision, token/context transfer, wall time,
  peak unified memory, failures, and human corrections.
- Constrain autonomous turns, wall time, tool scope, and child concurrency.
- Run Prime in an external sandbox or restricted container/worktree for untrusted
  repositories; its own worker/kernel separation is not a security sandbox.
- Require review for every Continual Harness refinement before promotion to the
  durable project configuration or wiki.

Promote Prime only if the routed pair improves representative task completion
enough to justify orchestration overhead. If Hermes matches coding performance
and messaging/personal automation becomes important, switch the scaffold without
changing the vLLM model layer.

## Sources

- Prime Intellect, [Prime Agent repository and architecture](https://github.com/PrimeIntellect-ai/prime-agent)
- Prime Intellect, [custom local model configuration](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/models.md)
- Prime Intellect, [RLM runtime and exact child model selection](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/rlm-runtime.md)
- Nous Research, [Hermes Agent repository](https://github.com/NousResearch/hermes-agent)
- Nous Research, [Hermes local-model FAQ](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md)
- Nous Research, [Hermes Mixture of Agents](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mixture-of-agents.md)
- Nous Research, [Hermes model configuration](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuring-models.md)
