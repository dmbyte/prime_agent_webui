# ADR-0044: Use narrow one-shot services for software updates

Date: 2026-08-25
Status: accepted

## Context

The owner wants Settings controls to update Prime Agent and Prime WebUI. The
dashboard API is deliberately denied non-loopback networking and has a read-only
home, so granting it GitHub/npm access would weaken an important boundary.

## Decision

Keep the dashboard confined. It may start only two named user-systemd one-shot
services after an exact confirmation token and refuse duplicate runs. The Prime
service uses the existing bundled Node runtime and installs `prime-agent@latest`.
The WebUI service requires the known private GitHub remote, branch `main`, and a
clean worktree; fetches `origin/main`; permits only a fast-forward merge;
compiles the Python entry points; installs tracked source/static/update assets;
reloads user units; and restarts only the dashboard API.

For now, WebUI means current `origin/main` HEAD. A future version will replace
that policy with release discovery, installed-versus-release comparison, and an
explicit version choice.

## Consequences

The update jobs have network and home-write access, but the long-running WebUI
API does not. Updates are explicit, serialized by per-update locks, auditable,
and status-visible. Package or upstream incompatibility remains possible, so
pre-change root-only snapshots and repository history remain the recovery path.
Each updater atomically writes an owner-only result record so Settings can retain
never-run/running/success/failure truth across service reloads and reboots.
