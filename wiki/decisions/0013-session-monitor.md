# ADR-0013: Use metadata-only sessions and read-only telemetry

Date: 2026-08-23  
Status: superseded in part by [ADR-0014](0014-conversation-topics.md) and [ADR-0015](0015-constrained-resume.md); telemetry remains active

## Decision

Make Sessions the dashboard's default view and return only timestamp, model,
opaque session ID, and file size. Never return prompt, first-message, summary, or
message content. Add read-only host telemetry from procfs, sysfs, and `nvidia-smi`.
Keep ttyd's executable and arguments fixed; do not enable URL arguments.

## Rationale

The requested overview is useful without exposing conversation contents. A
plaintext credential discovered in existing session history makes content
minimization essential. URL-controlled ttyd arguments would broaden the browser
interface into process-argument control. Saved-session resume is therefore
deferred until a dedicated server-side mechanism can accept only verified session
IDs and a fixed resume action.

## Consequences

Users can inspect recent session activity and start a fresh embedded terminal,
but cannot yet resume a listed session from the sidebar. Telemetry is observational
and explicitly displays unavailable values when a sensor cannot be read.
