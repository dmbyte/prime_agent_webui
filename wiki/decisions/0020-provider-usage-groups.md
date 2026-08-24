# ADR-0020: Group configured usage by provider

Date: 2026-08-24  
Status: accepted

## Decision

Render only models marked configured by the current catalog. Show a direct row for
single-model providers. For multi-model providers, show a collapsed provider row
whose Today and Last 30 days values sum every child model, with expandable model
detail.

## Consequences

The default Usage view stays compact even when an authenticated provider exposes
many models. Roll-ups provide immediate provider totals, while expansion preserves
model-level accounting. Historical usage from a removed configuration is retained
in session records but hidden from this current-configuration view.
