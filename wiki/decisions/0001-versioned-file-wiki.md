# ADR-0001: Maintain a versioned file-based project wiki

- Status: accepted
- Date: 2026-08-23
- Supersedes: none
- Superseded by: none

## Context

The project needs durable, high-fidelity context that survives conversation
compaction. Each tweak and optimization must leave the current truth and its
history understandable, with a path back to an earlier state.

## Decision

Maintain Markdown documentation under `wiki/` with an authoritative current-state
page, chronological change log, decision records, and immutable numbered state
snapshots. A root `AGENTS.md` makes updating this record part of every project
change.

## Alternatives considered

- Conversation history alone: insufficiently durable under compaction.
- A single changelog: preserves events but not a high-fidelity current state.
- Git history alone: valuable for exact file recovery but weak at preserving
  intent, operational context, and verified conclusions.

## Consequences

Every material change carries a small documentation cost. In return, future work
can recover context quickly, distinguish current truth from history, and identify
the rationale and validation behind a state.

## Validation

For each material change, check that the version identifiers agree, the current
state matches verified implementation, and an immutable snapshot exists.

## Reversal conditions

Supersede this decision if a different durable knowledge system provides equal or
better local accessibility, version fidelity, recovery guidance, and automatic
inclusion in the project-change workflow.

