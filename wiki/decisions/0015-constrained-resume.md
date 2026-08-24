# ADR-0015: Constrain browser conversation resumption

Date: 2026-08-23  
Status: accepted; supersedes ADR-0013's deferral of browser resumption

## Decision

Enable ttyd URL arguments only through the dedicated `prime-web-launch` wrapper.
The wrapper forwards exactly `--resume <id>` when the ID contains only the
approved characters, is 8–80 characters long, and names an existing Prime session
file. It ignores every other browser-supplied argument and starts plain `prime-dgx`.

## Rationale and consequences

This provides ChatGPT-style conversation navigation without exposing Prime's
general command-line interface through URLs. Authenticated users can resume any
conversation visible to the shared `dbyte` account, consistent with their existing
terminal authority. The terminal remains loopback-only behind Nginx/PAM/TLS.
