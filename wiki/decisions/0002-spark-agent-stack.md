# ADR-0002: Use a routed Nemotron and Qwen agent stack on vLLM

- Status: superseded
- Date: 2026-08-23
- Supersedes: none
- Superseded by: ADR-0004

## Context

One DGX Spark must provide the most useful local agent capability with two models
resident, including Nemotron 3.5 Lightning with speculative decoding. The Spark
has 128 GB unified memory and Blackwell FP4 support, but memory capacity,
bandwidth, caches, and host workloads share that pool.

## Decision

Use Nemotron 3.5 Lightning 30B-A3B NVFP4 plus its DSpark NVFP4 drafter as the
orchestrator, and Qwen3-Coder-Next in a GB10-calibrated NVFP4 format as the coding
specialist. Serve them in separate, conservatively budgeted vLLM processes behind
a deterministic router. Begin with 131K and 65K context caps, respectively, and
roughly 30% plus 50% memory envelopes.

## Alternatives considered

TensorRT-LLM, SGLang, llama.cpp, a second 30B coder, and a larger general model
were considered. vLLM has the most direct published Nemotron DSpark-on-Spark path
and supports both model families. Qwen3-Coder-Next adds a stronger coding-agent
specialization while remaining plausible for concurrent NVFP4 residency.

## Consequences

The system gains fast general orchestration and a stronger independent coding
specialist with a shared API style. It also inherits multi-process memory
coordination, router complexity, and supply-chain/quality risk from the current
community Qwen NVFP4 artifact. Maximum advertised context cannot be assumed while
both models are resident.

## Validation

Follow the concurrent-load, quality, routing, latency, speculative-acceptance,
memory, and soak gates in `wiki/AGENT_STACK.md`. Pin versions and hashes only
after they pass on the actual Spark.

## Reversal conditions

Reconsider the engine or model if the pair cannot retain safe memory headroom,
NVFP4 quality loss is unacceptable, speculative decode does not improve the real
workload, or another measured stack materially improves agent task completion
within the same power and residency constraints.
