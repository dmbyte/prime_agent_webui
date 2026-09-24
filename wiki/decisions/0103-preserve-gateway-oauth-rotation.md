# ADR-0103: Preserve the gateway's rotated OAuth credential

Date: 2026-09-24
Status: accepted

## Context

The isolated model gateway and the host Prime installation initially receive
the same Codex OAuth record. OpenAI refresh tokens rotate and are single-use.
The gateway correctly persists its replacement after refresh, but repeated
OpenShell activation unconditionally copied the older host file over that newer
gateway file. The next request then received `refresh_token_reused` and the
gateway reduced the failure to an opaque HTTP 502.

The same incident showed that a `/qwen` prefix could lose to a higher-priority
phrase rule when later prompt text mentioned Codex.

## Decision

- Treat the gateway credential as independently rotating state.
- During installation, copy the host credential only when its expiry is
  strictly greater than the gateway credential's expiry.
- Convert known refresh-token reuse into a sanitized, actionable sign-in error;
  log only the safe error category and never tokens or upstream payloads.
- Resolve explicit slash-model directives before data-driven phrase rules. If
  several directives appear, the first directive in the message wins.

## Consequences

- Routine WebUI/OpenShell updates cannot roll back a working OAuth refresh token.
- A genuinely expired or revoked credential still needs one interactive
  `/login`; the system cannot recreate user authorization itself.
- Task activity now distinguishes a Codex sign-in failure from model or proxy
  health failures.
- Explicit local-model fallback behaves predictably even when the request
  discusses another model.

## Rollback

Restore v0.5.39. This is not recommended because activation can reintroduce a
consumed refresh token and slash fallbacks can be overridden by prompt prose.
