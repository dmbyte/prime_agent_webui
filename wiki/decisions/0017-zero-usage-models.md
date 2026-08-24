# ADR-0017: Show intended models with operational status

Date: 2026-08-23  
Status: accepted

## Decision

Build Usage rows from the union of recorded activity and the configured/intended
model catalog. Display zero values for unused models. Mark intended models that
are not actually configured with `not configured` rather than implying readiness.

## Consequences

Qwen remains visible before its first call. The planned OpenAI GPT-5.6 Sol route
is visible but clearly non-operational. This separates zero activity from missing
configuration and avoids treating an agent's setup claim as verified state.
