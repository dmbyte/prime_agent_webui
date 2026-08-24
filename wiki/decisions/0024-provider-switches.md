# ADR-0024: Manage provider availability through Prime settings

Date: 2026-08-24
Status: accepted

## Context

The fixed three-option model selector did not expose authenticated providers such
as OpenAI-Codex and offered no convenient way to remove a provider from new work.
Prime already has a durable `enabledModels` setting.

## Decision

Build the Parameters provider list from configured local models, authenticated
Prime discovery, and the validated direct OpenAI route. Group by provider, add
search and one switch per provider, and translate enabled providers into every
currently configured model under those providers when saving `enabledModels`.
Populate the default selector from enabled models only. Reject empty or unknown
provider sets and require the selected default's provider to remain enabled.

## Consequences

Provider availability is real Prime configuration rather than a dashboard-only
filter. A provider switch is intentionally provider-wide: enabling OpenAI-Codex,
for example, enables all of its currently discovered models. Existing running
sessions are not rewritten; new terminal sessions use saved settings. Usage can
continue to report configured providers even when they are disabled for new work.

## Rollback

Restore the v0033 API, HTML, and JavaScript and remove `provider-settings.css`.
The last saved `enabledModels` value remains valid Prime configuration and can be
changed through Prime directly if necessary.
