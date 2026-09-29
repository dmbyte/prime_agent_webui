# ADR-0106: Preserve Prime's post-compaction continuation

Date: 2026-09-28
Status: accepted

## Context

Two resumed Nemotron tasks ended after a successful `ipython` call with no
final answer. Prime's installed agent loop explicitly stops a turn when
threshold compaction is needed, emits `agent_end`, then compacts and schedules
continuation. One affected runtime log shows a second `compaction_start` after
`agent_end`. The dashboard treated that intermediate end as terminal and
closed its RPC input immediately. Its `select` plus buffered `readline` pair
could also leave already-arrived events unseen until more output arrived.

## Decision

Treat `agent_end` as a possibly intermediate turn boundary. Keep RPC input
open for a short settle period and for any observed compaction. After
`compaction_end`, allow Prime a bounded interval to emit a new `agent_start`.
Read events from the stdout descriptor without text-buffer read-ahead. If a
successful tool turn still has no finalized answer after settling, queue at
most one prompt in the same session that asks for a result without repeating
completed actions. Retain ADR-0105's one-attempt Python parse correction and
visible failure on an unanswered terminal task.

## Consequences

- Long-context tasks can resume naturally after automatic compaction.
- A truly stranded tool turn gets one bounded chance to provide the answer.
- Completed tool actions are not intentionally rerun by the recovery prompt;
  the agent still controls its response, so an administrator should review
  consequential actions in the preserved task log.
- Final task closure is delayed briefly to distinguish a terminal end from a
  compaction handoff.

## Rollback

Restore v0.5.42. This restores immediate input closure at `agent_end` and can
reproduce failed long-context continuations.
