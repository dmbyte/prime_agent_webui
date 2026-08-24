# Wiki Operating Guide

## Required update loop

For every material tweak or optimization:

1. Inspect the relevant implementation and existing wiki pages.
2. Make and validate the project change.
3. Rewrite `CURRENT_STATE.md` wherever the verified present state changed.
4. Prepend an entry to `CHANGELOG.md` describing outcome, validation, and
   rollback impact.
5. Record important rationale in `decisions/` using the decision template.
6. Copy the resulting high-fidelity state into the next numbered file under
   `versions/` and advance the current version in `README.md` and
   `CURRENT_STATE.md`.

Small documentation-only corrections that do not change project meaning may be
logged without a new snapshot. Anything affecting behavior, architecture,
dependencies, interfaces, configuration, performance, security, operations, or
known limitations requires a snapshot.

## Snapshot numbering

Use monotonically increasing, zero-padded identifiers: `v0001`, `v0002`, and so
on. A snapshot is immutable after creation. Corrections belong in a later
snapshot with an explicit note about what it supersedes.

## Reverting

1. Select the desired file from `versions/`.
2. Review its restoration notes and all changelog entries after that version.
3. Revert implementation changes using the safest available mechanism (normally
   version control once configured).
4. Re-run the validation recorded by the target snapshot.
5. Create a new snapshot documenting the revert; never rewrite history or mark
   an old snapshot as current by editing it.

Snapshots document state and recovery intent; they do not replace source control,
database backups, or artifact retention.

## Decision records

Copy `decisions/0000-template.md` to the next numbered filename. Include context,
the decision, alternatives, consequences, validation, and reversal conditions.
Use statuses: `proposed`, `accepted`, `superseded`, or `rejected`.

## Quality checklist

- Current-state claims were verified rather than assumed.
- Commands, dependencies, interfaces, and constraints are precise enough to use.
- The change log explains what changed and how it was checked.
- Recovery implications are stated.
- Links resolve and the current version identifiers agree.
- No secrets or sensitive personal data are present.

