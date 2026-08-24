# ADR-0016: Combine model token and spend reporting

Date: 2026-08-23  
Status: accepted; supersedes the separate Tokenomics and API Spend presentation

## Decision

Present one Usage table keyed by exact provider/model. Each row shows tokens and
recorded cost for Today and Last 30 days. Today is the Spark's local calendar day
beginning at midnight; Last 30 days is a rolling 30-day window.

## Consequences

Token volume and monetary cost are directly comparable without changing screens.
Local model rows show zero recorded API spend. The figures remain Prime-recorded
usage rather than provider invoices and exclude activity outside Prime.
