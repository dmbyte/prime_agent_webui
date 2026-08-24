# ADR-0004: Build a multimodal Hermes personal agent

- Status: superseded
- Date: 2026-08-23
- Supersedes: ADR-0002 and ADR-0003
- Superseded by: ADR-0005

## Context

The primary jobs are 3D-print design, portfolio evaluation, day-trading research,
personal automation, and occasional coding. Frontier OpenAI APIs may handle
difficult work. This favors multimodality, scheduling, memory, and controlled
tools over a coding-specialist topology.

## Decision

Use Hermes Agent with Nemotron 3.5 Lightning + DSpark as the fast local model,
NVIDIA Qwen3.6-35B-A3B-NVFP4 as the multimodal/deeper local model, and GPT-5.6
Sol through the OpenAI Responses API as a gated frontier tier. Financial analysis
is separated from execution by deterministic risk controls and human approval.

## Alternatives considered

Prime Agent plus Qwen3-Coder-Next remains stronger for a coding-dominant project.
Qwen3.5-122B-A10B NVFP4 offers more parameters but its 83.5 GB artifact leaves an
uncomfortably small dual-resident operating margin with Nemotron and tools.

## Consequences

The system gains vision/spatial reasoning, schedules, profiles, memory, messaging,
MCP connectivity, and frontier escalation while retaining coding. Trading needs
far stricter freshness, audit, testing, and permission boundaries.

## Validation

Follow `wiki/USE_CASE_ARCHITECTURE.md`. Begin with paper trading only.

## Reversal conditions

Reconsider if Qwen multimodal quality is inadequate, Hermes cannot support safe
boundaries, finance/trading is removed, or coding again dominates the workload.
