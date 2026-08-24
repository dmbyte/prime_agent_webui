# DGX Spark Two-Model Agent Recommendation

> Historical selection analysis. v0007 and `PRIME_DEPLOYMENT.md` are the current
> implementation truth: Qwen3.6-35B-A3B NVFP4 replaced Qwen3-Coder-Next and
> Prime is the core. The Nemotron, vLLM, and precision analysis remains useful.

Status: superseded analysis; architecture commissioned in v0007  
Last researched: 2026-08-23

## Recommendation

Use a routed two-model agent:

1. **Fast orchestrator and general workhorse:**
   `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`, paired with
   `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark` for speculative
   decoding.
2. **Coding and verification specialist:** `Qwen/Qwen3-Coder-Next`, deployed as
   a GB10-calibrated NVFP4 compressed-tensors checkpoint. Bootstrap with
   `saricles/Qwen3-Coder-Next-NVFP4-GB10`, but promote it only after local
   acceptance tests; for production, prefer an internally reproduced NVFP4
   quantization calibrated on representative code and agent traces.
3. **Inference engine:** vLLM, as two separately budgeted server processes behind
   one lightweight router. Pin a tested container/image version rather than
   tracking `latest`.
4. **Agent scaffold:** Prime Agent, with Nemotron as the parent and Qwen selected
   explicitly for specialist RLM children. See `wiki/AGENT_FRAMEWORK.md`.

This pairing optimizes capability per active parameter: both are sparse MoE
models with about 3B active parameters per token, but their training emphases are
complementary. Nemotron is optimized for efficient, long-running agents and has
an NVIDIA-published Spark speculative path. Qwen3-Coder-Next is explicitly built
for coding agents, long-horizon tool use, and recovery from execution failures.

## Why these roles

### Nemotron 3.5 Lightning: controller and throughput tier

- 30B total / 3B active hybrid Mamba-2, attention, and MoE model.
- Official NVFP4 target and NVFP4 DSpark draft artifacts.
- Up to 1M validated context as a single-model deployment.
- NVIDIA specifically recommends DSpark on DGX Spark at low concurrency, with
  three speculative tokens.
- Built-in reasoning and tool-call parsers are documented for vLLM.
- Small resident footprint (published target repository is about 21.6 GB) leaves
  room for a stronger specialist and useful cache.

Route conversational work, task decomposition, retrieval synthesis, tool
selection, short edits, and result consolidation here. The router should keep a
request on Nemotron unless a specialist trigger fires.

### Qwen3-Coder-Next: coding and critic tier

- 79.7B total / roughly 3B active hybrid DeltaNet, attention, and MoE model.
- Official base model is designed for coding agents and has a 262K context.
- Its model card emphasizes long-horizon reasoning, complex tool use, and
  recovery from failed actions—the strongest complement to a fast general
  orchestrator.
- The proposed community NVFP4 GB10 artifact is 45.9 GB on disk and reports
  about 42.7 GiB model memory under its single-model benchmark.

Route multi-file implementation, hard debugging, architecture-sensitive code,
test repair, and code review here. For high-risk work, use Nemotron to plan,
Qwen to implement, then Nemotron to check requirements and Qwen to review the
diff. Do not have both generate every answer; serial escalation preserves memory
bandwidth and avoids doubling latency.

## Why vLLM

vLLM is the best common engine for this exact pair because NVIDIA publishes the
DGX Spark Nemotron + DSpark command for vLLM, NVFP4 compressed-tensors and FP8 KV
cache are supported, both model families expose vLLM recipes, and it provides an
OpenAI-compatible API for a model router. SGLang is a credible later benchmark,
but vLLM has the most direct validated recipe for the required Nemotron DSpark
configuration.

Run one server per model. This provides separate ports, context limits, cache
budgets, health checks, and restart domains. It also avoids assuming that one
vLLM engine instance dynamically serves unrelated architectures.

## Spark-specific precision nuance

Use NVIDIA **NVFP4 compressed-tensors checkpoints**, not generic GGUF Q4, AWQ,
GPTQ, bitsandbytes NF4, or AMD MXFP4, when optimizing the NVIDIA GB10 path.
NVFP4 uses FP4 values with scaling metadata and minimizes model traffic/storage.

However, checkpoint format and compute path are distinct. NVIDIA's current
Nemotron model card says that on DGX Spark the NVFP4 checkpoint uses a **W4A16
Marlin** compute path, and explicitly marks native FP4 tensor-core execution as
unavailable for that recipe. Therefore, do not claim 1-PFLOP FP4 peak behavior
for this workload. Benchmark delivered tokens/second and latency instead.

## Initial dual-resident memory plan

The Spark has 128 GB unified memory; GPU and CPU allocations compete for the
same pool. The two model weights consume roughly 64–70 GB before KV/state,
runtime workspaces, draft-model memory, the OS, and the agent process.

Commission conservatively:

| Component | Initial budget | Initial context cap |
|---|---:|---:|
| Nemotron target + DSpark + cache | about 30% (38 GB) | 131K |
| Qwen Coder + cache | about 50% (64 GB) | 65K |
| OS, router, tools, workspaces, margin | about 20% (26 GB) | n/a |

The percentages are starting envelopes, not promised working flags. vLLM's
memory-utilization value is process-local but calculated against device memory;
the sum of both reservations must remain safely below 1.0. Never launch the two
published single-model examples unchanged: 0.85 plus 0.90 overcommits memory.

If initialization fails, reduce context/cache first; do not spill hot model
weights to CPU because CPU and GPU share the same physical memory bandwidth on
Spark. If the actual workload rarely needs instant access to both models, an
on-demand specialist provides better cache headroom, but it adds model-load
latency and is not the default requested architecture.

## Nemotron serving profile

Carry forward NVIDIA's documented Spark settings:

- vLLM image version `v0.27.1` as the initial compatibility reference.
- `--moe-backend marlin`
- `--kv-cache-dtype fp8`
- prefix caching enabled
- DSpark checkpoint with three speculative tokens
- FlashInfer Mamba backend with aligned Mamba cache
- `nemotron_v3` reasoning parser
- `qwen3_coder` tool-call parser with automatic tool choice

Replace NVIDIA's single-model memory utilization of 0.85 with the measured
dual-resident budget. Do not hard-code a final percentage until both engines
load together and pass soak testing.

## Qwen serving profile

- Use NVFP4 compressed-tensors with Marlin on GB10.
- Use FP8 KV cache if the pinned vLLM/model combination passes quality tests.
- Start with a 65,536 token limit and prefix caching.
- Give this process the larger cache reservation because the model weights are
  about twice Nemotron's size and code tasks benefit from repository context.
- Validate the chat template and tool-call schema through the router; do not
  assume Nemotron's parser applies to Qwen.

The community checkpoint's published single-model setup uses experimental image
and environment choices. Reproduce it in the same pinned vLLM line selected for
Nemotron if possible. If one common image cannot serve both reliably, retain the
same vLLM API contract but pin two compatible images; engine uniformity matters
more than container uniformity.

## Router policy

Use deterministic heuristics before model-based routing:

- Default to Nemotron.
- Escalate to Qwen for multi-file code changes, failing tests, unfamiliar build
  systems, security-sensitive code, performance debugging, or explicit review.
- Send the specialist a compact task packet: objective, constraints, relevant
  files/diffs, test output, and open questions—not the entire conversation.
- Return Qwen's proposed work to Nemotron for requirement reconciliation.
- Require an independent Qwen review for destructive, authentication,
  authorization, cryptographic, migration, or deployment changes.
- The controller, not either model, owns tool permissions, timeouts, retries,
  loop limits, and the durable wiki update.

In the first prototype, implement this policy through Prime Agent's model-aware
`rlm()` child calls and project instructions. A separate routing service is not
required until evaluation shows that framework-level routing is insufficient.

## Acceptance gates before production

1. Both servers load concurrently after a cold boot without swap or OOM.
2. At least 20% unified-memory operational headroom remains under representative
   concurrent context, unless soak tests justify a smaller reserve.
3. Measure time-to-first-token, decode tokens/second, speculative acceptance,
   peak memory, and power/thermal stability for concurrency 1, 2, 4, and 8.
4. Compare Nemotron DSpark at 0 and 3 draft tokens; retain speculation only when
   it wins for the real request distribution.
5. Compare Qwen NVFP4 against its official BF16/FP8 reference on a small local
   suite for code correctness, tool JSON, instruction following, and long-context
   retrieval. Community calibration on general chat data is a quality risk.
6. Test router decisions, malformed tool calls, server death, retry loops,
   cancellation, and context overflow.
7. Pin model revisions, container digests, configs, and artifact hashes only
   after the gates pass.

## Alternatives considered

- **TensorRT-LLM:** potentially excellent on NVIDIA hardware, but the required
  Nemotron DSpark recipe and the second model's ready-to-use path are more direct
  in vLLM. Reconsider after the baseline is stable and only with measurements.
- **SGLang:** supports both families and speculative techniques, but does not
  displace vLLM's directly published Spark recipe for this target today. Include
  it in a later A/B test if latency is inadequate.
- **llama.cpp/Ollama:** convenient, but generic GGUF quantization and less direct
  use of the official NVFP4/DSpark serving path make them a poor optimization
  target for this architecture.
- **A larger dense or 100B+ model:** may improve some reasoning tasks but consumes
  too much unified-memory bandwidth/capacity to remain concurrently resident
  with useful cache and operational margin.
- **Qwen3-Coder 30B-A3B:** easier to fit and a sensible fallback, but offers less
  capability separation from 30B Nemotron than Qwen3-Coder-Next.

## Sources

- NVIDIA, [Nemotron 3.5 Lightning NVFP4 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4)
- NVIDIA, [DGX Spark hardware overview](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)
- Qwen, [Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- Community quantization candidate,
  [Qwen3-Coder-Next-NVFP4-GB10 model card](https://huggingface.co/saricles/Qwen3-Coder-Next-NVFP4-GB10)
- NVIDIA, [vLLM release notes](https://docs.nvidia.com/deeplearning/frameworks/pdf/vLLM-Release-Notes.pdf)
