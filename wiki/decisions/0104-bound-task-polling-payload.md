# ADR-0104: Bound task polling log previews

Date: 2026-09-28
Status: accepted

## Context

The dashboard polls `/api/tasks` and loads `/api/state` to refresh conversation
and task information. `task_snapshot` copied each task's entire retained
`liveLog` into both responses. Each task could retain up to 2 MiB of redacted
runtime text in memory. Four completed tasks made both responses about 9 MB,
even though the activity panel displayed only one task at a time. The API
journal showed timed-out writes and reset connections during task polling.

## Decision

Keep the complete redacted log in its owner-scoped task log file and expose it
through the existing chunk and download endpoints. Include only the newest 32
entries and at most 32 KiB of log text per task in the frequently polled task
snapshot. Mark truncated previews in the response and label them accordingly
in the activity panel.

## Consequences

- Routine dashboard refreshes remain small even after long tasks.
- The activity panel still shows recent runtime detail, and Complete output
  retrieves all retained log data on demand.
- A single unusually large runtime event can begin mid-line in the preview;
  the complete log retains the original redacted event.

## Rollback

Restore v0.5.40. That restores full logs in every poll and can reproduce slow
or timed-out refreshes as task history grows.
