# ADR-0029: Use recoverable conversation deletion

Date: 2026-08-24
Status: accepted

## Context

The operator needs to remove conversations from the sidebar through a familiar
right-click menu. Permanent unlinking would make an accidental choice difficult to
reverse and would erase the dashboard's only record of associated usage costs.

## Decision

Provide **Delete conversation** in a custom context menu. Require browser
confirmation, origin/header checks, a strict ID, an existing transcript, and proof
from Prime that the session is not live. Atomically move the JSONL file to a
private mode-0700 `session-trash` directory with a timestamped name. Continue
including that directory in Usage calculations but exclude it from Conversations.

## Consequences

Deletion is immediately reflected in the UI yet remains recoverable by moving the
timestamped file back to `sessions/` under its original `<id>.jsonl` name. Live or
idle-but-open daemon sessions cannot be deleted until closed. Storage is not
automatically reclaimed; a future purge policy requires a separate decision.

## Rollback

Restore v0039 API/HTML/JavaScript and remove `conversation-menu.css`. Any files
already in session trash remain private and recoverable.
