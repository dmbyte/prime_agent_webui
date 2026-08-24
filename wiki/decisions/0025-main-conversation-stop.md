# ADR-0025: Locate task interruption in the main conversation

Date: 2026-08-24
Status: accepted
Supersedes: [ADR-0023](0023-single-task-stop.md) for control placement

## Context

Task monitoring belongs in the activity overlay, but the operator expects the
action that interrupts work to live with the primary conversation rather than in
a monitoring surface.

## Decision

Remove visible stop controls from both overlay modes. Show a running-task control
bar above the primary terminal whenever work is active. Follow the selected
sidebar conversation if it is active; otherwise show an explicit selector so
parallel tasks are never stopped ambiguously. Keep the existing confirmation and
server-side stop protections.

## Consequences

The overlay is observation-focused, while the main conversation is the control
surface. The selector is necessary because a newly created ttyd conversation does
not expose its eventual Prime session ID directly to the parent page and multiple
workers may run simultaneously. Stopping still preserves session history and
targets only one active worker.

## Rollback

Restore v0034 dashboard HTML, JavaScript, and live-console CSS, and remove
`conversation-control.css`.
