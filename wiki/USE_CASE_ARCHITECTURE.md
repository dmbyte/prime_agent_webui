# Personal Agent Use-Case Architecture

Status: orchestration/model foundation commissioned; domain tools pending; no live trading authorized  
Last researched: 2026-08-23

Core agent: Prime Agent. Hermes may be added as a replaceable messaging gateway,
but domain state, permissions, evaluations, and improvement history remain in
Prime/project-controlled storage.

## Capability tiers

| Tier | Model | Use |
|---|---|---|
| Fast local | Nemotron 3.5 Lightning NVFP4 + DSpark | Conversation, schedules, summaries, routine tools, triage |
| Deep/multimodal local | Qwen3.6-35B-A3B-NVFP4 | Images, spatial/manufacturing reasoning, documents/charts, finance, code |
| Frontier API | GPT-5.6 Sol via Responses API | Ambiguous design, independent financial critique, difficult debugging |

Use GPT-5.6 Terra only if evaluation shows it passes a defined escalation class
at lower cost. Official OpenAI documentation currently recommends Sol for complex
professional work; current frontier models accept images, and the Responses API
supports function tools, web/file search, computer use, and MCP.

## 3D-print design workflow

The agent should produce parametric CAD rather than attempt to emit STL triangles
directly from natural language:

1. Collect envelope, interfaces, tolerances, material, printer, nozzle, layer
   height, loads, orientation, and finish requirements.
2. Qwen inspects sketches, photos, drawings, failures, and slicer screenshots.
3. Generate a parameterized model in CadQuery or OpenSCAD; use FreeCAD where a
   richer solid-model workflow is required.
4. Run deterministic checks for manifold mesh, wall thickness, clearances,
   overhangs, bounding box, volume, and interference.
5. Slice with a pinned profile and inspect time, material, supports, and warnings.
6. Render multiple views and have Qwen review them against requirements.
7. Escalate ambiguous assemblies, complex load paths, or stubborn failure
   analysis to GPT-5.6 Sol with images and exact constraints.
8. Require human approval before production export or starting a print.

Models propose geometry; CAD kernels, validators, slicers, measurements, and
physical test coupons provide truth.

## Portfolio evaluation workflow

1. Ingest positions, lots, cash, benchmarks, objectives, horizon, tax constraints,
   and risk limits from authoritative sources.
2. Fetch timestamped market and fundamental data from licensed APIs. Model
   knowledge is never treated as current market data.
3. Calculate exposure, concentration, factor/sector allocation, drawdown,
   volatility, correlation, liquidity, income, fees, and scenarios in deterministic
   code with versioned formulas.
4. Nemotron produces routine briefs; Qwen reviews filings, charts, and scenarios.
5. GPT-5.6 Sol supplies an independent adversarial thesis for unusual or complex
   cases, not an unreviewed final recommendation.
6. Every report states timestamps, sources, assumptions, missing data, and whether
   values are observed, calculated, or inferred.

## Day-trading research and execution boundary

The initial system is **paper-trading only**. Promotion to live trading requires
a separate decision after replay, backtest, forward paper tests, and failure
drills.

Models may summarize evidence, propose hypotheses, generate strategy code/tests,
analyze feature feeds, and produce candidate orders for review. Models may not
possess broker credentials, call unrestricted order endpoints, change limits,
self-approve orders, or trade on stale or unverified data.

A separate non-LLM risk gateway must enforce instrument allowlists, market hours,
data freshness, maximum order/notional/position, daily loss, exposure, slippage,
duplicate-order idempotency, rate limits, kill switch, audit log, and manual
approval. It alone constructs and submits a final broker order. Read-only market
and portfolio tools remain separate from write-capable broker tools.

Never expose a live broker-order tool directly to Prime, Hermes, or a model. Place
approval and deterministic risk enforcement outside every agent framework.

## Profiles and scheduled work

- `design`: CAD, printers, materials, dimensions; no finance tools.
- `portfolio`: read-only holdings and market data; no order tools.
- `trading-research`: feeds, backtests, and paper broker only.
- `general`: personal memory, schedules, messaging; minimal tools by default.

Scheduled jobs may refresh data, run screens, create reports, monitor paper
positions, and deliver alerts. They must not execute live orders.

## Frontier escalation packet

Send only the goal, constraints, relevant images/files, deterministic results,
source timestamps, local conclusion, and specific uncertainty. Exclude broker
credentials, unrelated personal memory, and unrestricted tools. Require a
structured answer with evidence, counterarguments, confidence, and unresolved
items.

## Continual-improvement policy

Prime may propose harness memories, prompts, skill descriptions, and subagent
specifications. Improvement is not defined as “the agent changed itself.” A
change is promoted only when it:

1. is attributable to a recorded failure or repeated workflow;
2. is small, inspectable, and reversible;
3. passes the relevant frozen regression tasks;
4. does not broaden tools, credentials, financial permissions, or autonomy;
5. is captured in Prime's refinement history and this project wiki.

Use a two-speed loop: session-local experiments may adapt quickly, while durable
promotion occurs on a scheduled review cadence. Never let live trading outcomes
alone train or promote behavior; regime changes and selection bias make short-run
profit a dangerous objective.

## Sources

- Qwen, [Qwen3.6-35B-A3B announcement](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
- NVIDIA, [Qwen3.6-35B-A3B NVFP4](https://huggingface.co/nvidia/Qwen3.6-35B-A3B-NVFP4)
- vLLM, [verified Qwen3.6 DGX Spark recipe](https://github.com/vllm-project/recipes/blob/main/models/Qwen/Qwen3.6-35B-A3B.yaml)
- Nous Research, [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- Nous Research, [Hermes cron and delegation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-hermes-agent.md)
- OpenAI, [current API models](https://developers.openai.com/api/docs/models)
- OpenAI, [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
