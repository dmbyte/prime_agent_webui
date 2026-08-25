# ADR-0043: Route specialist WebUI tasks to Qwen deterministically

Date: 2026-08-25
Status: accepted

## Context

Prime's operating policy asked Nemotron to delegate specialist work to Qwen,
but that instruction was advisory. A verified session showed Nemotron handling
an explicitly requested Qwen review itself. The WebUI launcher always passed the
configured default provider/model and did not expose the actual route or effort.

## Decision

When Nemotron is the selected default, the native WebUI launcher routes clear
image/document, 3D/CAD/manufacturing, portfolio/trading, and deep-review prompts
directly to Qwen. Explicit Qwen or Nemotron requests override automatic routing.
If Qwen is disabled, the task falls back visibly to the selected default. A
manually selected non-Nemotron default remains authoritative.

The rule is deterministic and local rather than a model-based classifier, so it
adds no inference call, cost, or routing nondeterminism. Each task and conversation
records its model, effort, routing mode/reason, and context metadata. Mixed tasks
that stay on Nemotron must actually invoke a Qwen child for specialist subtasks;
the agent may not claim delegation without performing it.

The active conversation header shows the current model, editable effort, route,
and context. Effort changes apply to the next message in that conversation and
are persisted when the task starts; Settings continues to define new-conversation
defaults.

## Consequences

Qwen now receives the work for which it was provisioned without depending on
Nemotron voluntarily following a soft instruction. Lexical routing will not infer
every ambiguous task, so explicit model requests remain supported and the policy
can be extended with reviewed regression tests.
