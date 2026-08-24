# Project Wiki

This file-based wiki is the durable memory for the project. It records both the
verified current state and enough history to understand or reverse changes.

## Start here

- [Current state](CURRENT_STATE.md) — authoritative, concise description of the
  project as it exists now.
- [Change log](CHANGELOG.md) — chronological record of tweaks and optimizations.
- [Operating guide](OPERATING_GUIDE.md) — how to keep this wiki accurate.
- [Recommended agent stack](AGENT_STACK.md) — Spark-optimized model roles,
  inference architecture, sizing, and validation plan.
- [Agent framework analysis](AGENT_FRAMEWORK.md) — Prime Agent versus Hermes and
  the selected orchestration scaffold.
- [Use-case architecture](USE_CASE_ARCHITECTURE.md) — 3D design, portfolio,
  trading safeguards, and frontier escalation.
- [Spark pre-change baseline](SPARK_BASELINE.md) — verified hardware, software,
  services, exposure, and rollback artifact.
- [Prime deployment](PRIME_DEPLOYMENT.md) — deployed services, operation,
  validation, and rollback.
- [Prime dashboard](PRIME_DASHBOARD.md) — sidebar controls, token accounting,
  provider spend, security, and data semantics.
- [Decision records](decisions/README.md) — durable rationale and tradeoffs.
- [Version snapshots](versions/README.md) — immutable historical states and
  restoration guidance.

## Status

- Current wiki version: `v0034`
- Last verified: 2026-08-24
- Project phase: conversation-first monitored Prime dashboard backed up to private GitHub

## Truth and precedence

`CURRENT_STATE.md` describes the latest verified state. Version snapshots are
historical and immutable. The implementation is tested evidence, but unexplained
implementation/wiki drift is a defect: verify it, then update the current state
and history together.
