# ADR-0048: Teach Prime capability-driven software security review

Date: 2026-08-26
Status: accepted

## Context

A read-only Prime review of Prime WebUI produced several useful observations but
ranked incorrect CSP and proxy-header assumptions above material local and
multi-user trust-boundary failures. A project-specific checklist would overfit
that incident and transfer poorly to other software.

## Decision

Add a generic `software-security-review` skill. It first discovers system
capabilities and trust boundaries, then applies only relevant conditional modules
for web/API, authentication, memory/resources, storage, commands/plugins/agents,
network/IPC, cryptography, concurrency, dependencies, updates, deployment, and
specialized domains.

Require every confirmed vulnerability to have a concrete evidence-backed attack
path, prerequisites, impact, compensating-control analysis, confidence, scoped
remediation, and a validation test. Require important negative results and keep
confirmed vulnerabilities separate from needs-validation items, reliability
defects, defense-in-depth opportunities, and accepted trust assumptions.

## Consequences

The skill can transfer across languages and architectures without applying every
check indiscriminately. The larger conditional checklist is loaded only for an
actual security review. Review quality still depends on model capability, source
coverage, deployment evidence, and appropriate specialist knowledge; therefore
the skill improves discipline but does not certify software as secure.
