# Project Working Agreement

## Project wiki

The durable source of project context is `wiki/`. Read `wiki/README.md` and
`wiki/CURRENT_STATE.md` before changing this project.

Every project tweak, optimization, configuration change, or material discovery
must update the wiki in the same change:

1. Update `wiki/CURRENT_STATE.md` to describe the best current truth.
2. Append a concise entry to `wiki/CHANGELOG.md`.
3. Add or update a decision record in `wiki/decisions/` when rationale or a
   tradeoff should survive the implementation.
4. Create the next immutable snapshot in `wiki/versions/` for a material change.
   Never edit an older snapshot; supersede it with a new one.
5. Update links in `wiki/README.md` when pages are added, renamed, or retired.

Do not record secrets, credentials, tokens, or personal data in the wiki.
If implementation and wiki disagree, investigate the implementation, then make
the wiki accurately describe the verified state rather than copying stale text.

