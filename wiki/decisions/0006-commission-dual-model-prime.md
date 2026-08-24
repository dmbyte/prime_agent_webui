# ADR-0006: Commission the dual-model Prime stack

- Status: accepted
- Date: 2026-08-23

## Decision

Run Prime Agent 0.8.0 with Nemotron 3.5 Lightning + DSpark as its default local
orchestrator and Qwen3.6-35B-A3B-NVFP4 as its exact-routed multimodal specialist.
Host them in separate vLLM 0.27.1 containers with explicit KV budgets and
loopback-only APIs. Require a 20 GiB available-memory floor and human-reviewed,
reversible continual improvements. Leave OpenAI escalation inactive until a
credential is supplied securely.

## Rationale and consequences

Separate servers preserve model-specific parsers, speculative decoding, and
memory controls. Concurrent validation demonstrated that the 12 GiB/8 GiB KV
budgets retain about 38 GiB available host memory after warm-up. Loopback binding
removes the prior unauthenticated LAN inference exposure. The tradeoff is only
two active sequences per model and a 65K context cap until longer soak tests
justify expansion. Hermes remains available as a future gateway, not authority.

## Rollback

Use the protected v0006 baseline and the procedure in `../PRIME_DEPLOYMENT.md`.
