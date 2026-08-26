# ADR-0046: Configure providers through a write-only admin workflow

Date: 2026-08-25
Status: accepted

## Decision

Expose Prime 0.8.0's installed provider catalog through an administrator-only
Settings modal. Use provider-specific forms for API keys and cloud metadata,
Prime's existing interactive `/login` for subscription OAuth, and a constrained
form for custom OpenAI-compatible endpoints.

Store API keys in Prime's existing mode-0600 `auth.json`; store additional cloud
environment values in a separate atomic mode-0600 settings file. Never return
secret values or include them in audit logs, UI state, repository files, or the
wiki. Preserve existing OAuth credentials and model definitions when updating.

Remove the dashboard API unit's loopback-only egress filter while retaining its
loopback listener, authenticated Nginx boundary, admin/CSRF/Origin authorization,
filesystem confinement, and other systemd hardening. Native Prime child tasks
need outbound connections for configured cloud providers to function.

## Consequences

Provider credentials are shared trusted Spark infrastructure; ordinary WebUI
users may use enabled providers but cannot view or configure their credentials.
Compromise of the dashboard service has a larger network egress surface than
before, although it still cannot accept a direct LAN connection or return stored
secrets through its provider API. Subscription login remains in Prime's own
interactive flow rather than reimplementing OAuth in the WebUI.
