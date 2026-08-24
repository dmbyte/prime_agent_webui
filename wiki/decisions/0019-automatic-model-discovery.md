# ADR-0019: Discover authenticated models automatically

Date: 2026-08-24  
Status: accepted; supersedes manual intended-model catalog maintenance

## Decision

Use Prime's installed `model list` as the source for authenticated available
models. Cache successful output for 60 seconds, parse both stdout and stderr,
union it with custom/planned and recorded models, and retain the previous cache if
discovery fails.

## Consequences

New providers and models appear in Usage after authentication without dashboard
code edits. Discovery adds a bounded subprocess approximately once per minute.
Every available model appears, including models with zero usage, so the list can
be longer than a hand-curated shortlist.
