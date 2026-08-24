# ADR-0014: Display sanitized conversation topics

Date: 2026-08-23  
Status: accepted; supersedes ADR-0013's metadata-only topic restriction

## Decision

After explicit user approval, display a shortened topic derived from each
conversation's first user message to authenticated LAN/VPN dashboard users. Show
the latest message timestamp on the second line. Normalize whitespace, cap the
topic at 96 characters, replace credential-like topics with a fixed sensitive
label, and render with `textContent`.

## Consequences

The list is meaningfully recognizable, but authorized dashboard users can now see
short excerpts of initial user messages. Pattern detection reduces accidental
credential display but cannot guarantee removal of every sensitive value. Full
prompts, summaries, and assistant messages remain excluded.
