# ADR-0032: Store dashboard uploads privately without implicit agent messages

Date: 2026-08-24
Status: accepted

## Context

The browser interface needs to accept local files for CAD, portfolio, document,
image, and coding work. Earlier implicit terminal/session commands disrupted
running work, so an upload must not silently steer an agent or masquerade as a
conversation attachment command.

## Decision

Add a paperclip and drag-and-drop tray above the terminal. Stream each file over
the existing PAM-authenticated, private HTTPS endpoint into
`~/prime-dgx-agent/uploads/YYYY-MM-DD/`. Directories use mode 0700 and files mode
0600. Limit each file to 100 MiB and the whole upload tree to 2 GiB. Generate a
random stored-name prefix, reduce the supplied name to a safe basename, compute
SHA-256 while streaming, and return the exact local path. The operator explicitly
copies that path into the intended Prime prompt.

## Consequences

Prime can read uploaded files through ordinary filesystem tools, including files
used by either local model or a frontier child. Uploads never automatically send,
attach, resume, or interrupt a task. Stored files persist until intentionally
cleaned up; no delete or retention policy is added in this change. Uploaded
content is untrusted data and must never be executed merely because it was
uploaded.

## Rollback

Restore the v0043 dashboard, API, and Nginx site. Existing private upload files
remain on disk and can be retained or removed separately after review.
