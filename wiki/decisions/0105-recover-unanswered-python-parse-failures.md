# ADR-0105: Recover unanswered Python parse failures once

Date: 2026-09-28
Status: accepted

## Context

Prime submitted a tool argument to `ipython` in which a Python `if` statement
was followed by English prose and a numbered explanation. The cell raised
`SyntaxError` before it executed. Prime then emitted `agent_end` without a
final answer. The dashboard closed RPC input and classified `agent_end` as
success, leaving the user with an apparently completed but unanswered task.

## Decision

For a task with no finalized assistant answer, whose last tool failure is an
`ipython` `SyntaxError`, `IndentationError`, or `TabError`, queue one corrective
RPC prompt after `agent_end` in the same session. Keep input open for up to 30
seconds for Prime to start the correction. Never repeat the automatic attempt.
Require a finalized assistant answer for a successful ended task; otherwise
report failure and retain the submitted prompt and task log. Ask the managed
agent to use short, code-only Python cells and self-correct parse errors.

## Consequences

- A recoverable model-generated code typo no longer silently strands a task.
- A correction that is rejected, never starts, or ends unanswered is visible
  as failure instead of false success.
- Non-parse tool errors and tasks that already answered are not automatically
  rerun, avoiding duplicate side effects.

## Rollback

Restore v0.5.41. This removes automatic correction and restores the former
false-completion behavior for unanswered `agent_end` events.
