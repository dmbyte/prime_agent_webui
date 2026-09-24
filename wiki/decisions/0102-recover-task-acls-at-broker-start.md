# ADR-0102: Recover interrupted-task ACLs when the broker starts

Date: 2026-09-24
Status: accepted

## Context

Prime deliberately restricts access to its agent-state parent while an isolated
task is running, then the launcher restores the WebUI's named ACL in `finally`.
An abrupt host power loss bypassed that cleanup. After reboot, every service was
healthy and the transcripts still existed, but the protected agent directory's
ACL mask was `---`; the dashboard therefore showed an empty chat catalog.

The existing per-launch restoration protects ordinary errors and clean task
completion, but it cannot execute after loss of power or a kernel halt.

## Decision

Install a small, validated `prime-runner-recover` helper and run it as
`ExecStartPre` for the system task broker. Before the broker accepts work, the
helper restores:

- traversal-only ACLs on protected storage parents;
- recursive WebUI/group access and directory defaults on conversations, trash,
  project sources, and skills; and
- matching access on each user's host-visible task workspace.

The helper accepts only the configured WebUI owner and its exact
`/home/OWNER/prime-agent/tasks` root. It does not read transcript content or
change conversation ownership metadata.

## Consequences

- Rebooting after a power failure or forced shutdown repairs a task-interrupted
  ACL before the WebUI depends on the conversation tree.
- Clean launches retain their existing `finally` restoration, so recovery is
  both immediate and restart-safe.
- Broker startup now fails visibly if ACL recovery itself fails instead of
  starting with a silently empty chat catalog.

## Rollback

Remove the broker `ExecStartPre` line and uninstall
`/usr/local/libexec/prime-runner-recover`. Manual ACL repair would again be
required after an abrupt interruption.
