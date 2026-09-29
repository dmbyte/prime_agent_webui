# ADR-0108: Show RAM amounts on the expanded memory graph

Date: 2026-09-29
Status: accepted

## Context

The Spark sidebar's memory graph shows a percentage but not the quantities
behind it. The operator asked for both free and used RAM. The compact telemetry
cards are narrow, and the operator confirmed that showing the amounts only
when hovering over the memory graph is acceptable.

## Decision

Keep the compact card's percentage and graph. On hover or keyboard focus, show
used and free RAM under the percentage. Reuse the API's existing
`memoryUsedBytes` and `memoryTotalBytes` fields and one-second poll. Calculate
the displayed free amount as total minus used, which equals the API's Linux
`MemAvailable` reading. Explain that “free” includes reclaimable cache.

## Consequences

- The figures are consistent with the percentage and the operational headroom
  checks; they are not raw `MemFree` or per-process GPU memory.
- A keyboard user can access the same details via focus.
- No additional backend probe, request, or model allocation is needed.

## Rollback

Restore the prior dashboard JavaScript and telemetry-card CSS; the API remains
compatible because its telemetry shape did not change.
