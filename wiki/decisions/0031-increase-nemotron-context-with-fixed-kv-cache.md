# ADR-0031: Increase Nemotron context with a fixed KV cache

Date: 2026-08-24
Status: accepted

## Context

The dual-model Spark normally reports just under 70% memory utilization. The
operator wants a modestly longer Nemotron context while preserving at least 20%
system RAM headroom. At measurement time Linux reported 38.7 GiB available out
of 121.7 GiB (31.8%). Nemotron's fixed 12 GiB FP8 KV cache reported capacity for
1,661,925 tokens, while its per-request limit was only 65,536 tokens.

## Decision

Raise only Nemotron's advertised and served context limit to 81,920 tokens. Keep
its KV cache fixed at 12 GiB, maximum concurrency at two, and all model/runtime
settings unchanged. Treat `MemAvailable`, not the dashboard's used percentage,
as the acceptance measurement because Linux reclaims filesystem cache.

## Consequences

Nemotron gains 25% more context without reserving additional model memory. Its
existing cache reported 1,884,160 tokens after restart—23 full 81,920-token
contexts—well
above the two-sequence limit. Long prompts still consume more compute time and
may reduce responsiveness. The configuration must retain at least 24.3 GiB
available—20% of the Spark's approximately 121.7 GiB usable RAM—after warm-up.

## Rollback

Restore `MAX_MODEL_LEN=65536` in the Nemotron environment and `contextWindow` to
65,536 in Prime's model registry, restart Nemotron, and validate both models.
