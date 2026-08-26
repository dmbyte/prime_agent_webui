# ADR-0047: Update Prime components from validated published releases

Date: 2026-08-25
Status: accepted

## Context

The initial Settings update controls tracked npm `latest` and the WebUI's
`origin/main`. Those moving targets did not show whether a release was available
and could promote unreleased development code. The owner wants both Prime Agent
and Prime WebUI to check for updates on Settings entry and make availability
obvious.

## Decision

Query the latest official `PrimeIntellect-ai/prime-agent` release and latest
private `dmbyte/prime_agent_webui` release through the GitHub CLI from an
admin-only API. Display installed and latest state for each component and show a
prominent notice when the installed state is behind.

Keep the narrow one-shot services from ADR-0044, but install only the validated
published target. Prime Agent maps a semantic GitHub tag to the identical npm
package version. Prime WebUI fetches the release tag, resolves its commit, and
permits only a clean fast-forward deployment. Fixed repository identities,
strict tag validation, and resolved commits prevent browser-controlled command
or repository selection.

## Consequences

Settings reports both update channels consistently, and unreleased WebUI commits
are not presented as updates. Publishing a release is now the promotion gate.
Private WebUI release discovery requires the Spark's existing authenticated
GitHub CLI session. If GitHub is unavailable, Settings reports that the check is
unavailable while preserving the explicitly confirmed updater and its status
history. Automated rollback and release promotion remain future work.
