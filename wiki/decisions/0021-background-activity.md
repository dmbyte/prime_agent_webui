# ADR-0021: Expose privacy-safe background activity

Date: 2026-08-24  
Status: accepted

## Decision

Poll Prime's sanitized lifecycle metadata every three seconds and expose working
tasks in a floating dashboard overlay. Represent parallel work as tabs. Show only
sanitized topic, model/status metadata, tool names, event type/timestamp, and token
counts. Never return full prompts, assistant/thinking text, tool inputs/results,
or status-summary content.

## Consequences

Users can follow autonomous and parallel work without occupying the main terminal.
The overlay is movable, resizable, and minimizable. The feed is intentionally less
detailed than raw session content to preserve the authenticated dashboard's least-
exposure posture. Prime CLI polling is cached for four seconds.
