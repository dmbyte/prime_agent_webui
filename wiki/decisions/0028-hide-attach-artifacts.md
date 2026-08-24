# ADR-0028: Hide attachment-command session artifacts

Date: 2026-08-24
Status: accepted

## Context

Earlier UI attachment attempts created saved Prime sessions whose first user topic
is exactly `attach`. They are operational artifacts, not user conversations, and
occupied visible slots in the 40-row Conversations list.

## Decision

Exclude sessions whose sanitized first-user topic is exactly, case-insensitively,
`attach`. Apply the filter before limiting results to 40. Retain every underlying
JSONL file and make no change to usage accounting or explicit attachment support.

## Consequences

The conversation list contains user topics rather than attachment commands, while
history remains recoverable and auditable. A genuine conversation whose entire
first message is only the word `attach` will also be hidden; this narrow collision
is accepted because that exact input is the identified command artifact signature.

## Rollback

Restore the v0038 dashboard API. The retained artifacts will become visible again.
