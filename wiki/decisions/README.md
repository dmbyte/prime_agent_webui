# Decision Records

Decision records preserve why consequential choices were made. They are append-
only historical evidence: when a decision changes, mark the old record
`superseded` and link to a new record.

- [Template](0000-template.md)
- [ADR-0001: Maintain a versioned file-based project wiki](0001-versioned-file-wiki.md)
- [ADR-0002: Use a routed Nemotron and Qwen agent stack on vLLM](0002-spark-agent-stack.md)
- [ADR-0003: Prototype with Prime Agent](0003-prime-agent-framework.md)
- [ADR-0004: Build a multimodal Hermes personal agent](0004-multimodal-personal-agent.md)
- [ADR-0005: Use Prime as the continually improving core](0005-prime-core-hermes-gateway.md)
- [ADR-0006: Commission the dual-model Prime stack](0006-commission-dual-model-prime.md)
- [ADR-0007: Use an SSH-tunneled Prime browser interface](0007-private-prime-browser.md)
- [ADR-0008: Add PAM authentication over private HTTPS](0008-pam-authenticated-browser.md)
- [ADR-0009: Permit authenticated browser access from private networks](0009-private-network-browser.md)
- [ADR-0010: Permit Nginx to retrieve PAM account information](0010-nginx-shadow-for-pam.md)
- [ADR-0011: Enforce WebSocket origin at Nginx](0011-nginx-websocket-origin.md)
- [ADR-0012: Add a local settings and usage dashboard](0012-dashboard-usage-settings.md)
- [ADR-0013: Use metadata-only sessions and read-only telemetry](0013-session-monitor.md)
- [ADR-0014: Display sanitized conversation topics](0014-conversation-topics.md)
- [ADR-0015: Constrain browser conversation resumption](0015-constrained-resume.md)
- [ADR-0016: Combine model token and spend reporting](0016-combined-usage.md)
- [ADR-0017: Show intended models with operational status](0017-zero-usage-models.md)
- [ADR-0018: Load OpenAI key from a service environment file](0018-openai-env-key.md)
