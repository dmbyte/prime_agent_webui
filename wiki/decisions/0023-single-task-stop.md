# ADR-0023: Stop only explicitly selected active tasks

Date: 2026-08-24
Status: accepted

## Context

The activity overlay can observe running tasks but could not interrupt a task that
was unnecessary, mistaken, or consuming resources. Prime supports stopping one
agent independently of its supervisor and other workers.

## Decision

Add **Stop task** to both representations of the selected active task. Require
browser confirmation, the existing same-origin dashboard header, a strict session
ID, and server-side proof that the ID is currently active. Invoke only
`prime-agent stop <id>`, clear the activity cache after success, and return no
command output or session content to the browser.

## Consequences

The operator gains a narrow kill control without global shutdown. A stopped
worker's saved conversation remains available. There is an unavoidable race if a
task finishes between validation and the stop call; the API reports that as a
non-success rather than broadening the target. PAM-authenticated dashboard users
can intentionally interrupt work, so account access remains privileged.

## Rollback

Restore the v0032 dashboard API, JavaScript, and live-console stylesheet. Prime's
command-line stop operation remains available outside the dashboard.
