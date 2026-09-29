# ADR-0107: Serve Nemotron at 256K within the fixed KV pool

Date: 2026-09-29
Status: accepted

## Context

The operator requested a 256K Nemotron context after a 65,536-token request
failed because 57,345 input tokens plus 8,192 reserved output tokens exceeded
the model limit. The live 2 GiB FP8 KV pool reported capacity for 275,587
tokens under the old 65K profile, above 262,144, but below two full-length
requests. Qwen remains
co-resident. A trial restart at 131,072 failed before loading weights because
its old 35% GPU startup target required 42.59 GiB while only about 39.8 GiB
was free. This is an admission check even with explicit KV allocation.

## Decision

Set `MAX_MODEL_LEN=262144` and both Prime model catalog context windows to
262,144. Keep `KV_CACHE_MEMORY_BYTES=2G`, FP8 KV, DSpark speculation, and
`MAX_NUM_SEQS=2`; the second slot benefits shorter concurrent work but cannot
host another full-length context. Lower `GPU_MEMORY_UTILIZATION` to `0.30` so
startup can pass with Qwen present. Do not enlarge the KV reserve merely to
permit two long requests under the Spark's narrow memory headroom.

## Consequences

- At 256K, vLLM recalculated the pool to 505,783 cache tokens, enough for one
  full-length request with 243,639 tokens left. Two full-length requests need
  524,288 and still do not fit. The reason for the changed reported token
  capacity has not been separately verified.
- Prompt and reserved completion tokens together must remain within 262,144;
  Prime's OpenShell catalog still reserves up to 8,192 output tokens.
- Long prefill and decoding can be slower and can monopolize the KV pool.
- Capacity measured at startup is a planning bound; a live long-prompt test
  and system memory check are necessary to validate operational behavior.

## Rollback

Restore `MAX_MODEL_LEN=65536` and both catalog context windows to 65,536, keep
the 30% startup target while Qwen is co-resident, restart Nemotron, and confirm
both model endpoints respond. Do not restore the 35% admission target without
first measuring at least 42.59 GiB free GPU memory.
