# ADR-0018: Load OpenAI key from a service environment file

Date: 2026-08-23  
Status: accepted

## Decision

Load `OPENAI_API_KEY` into `prime-web.service` from
`~/.config/prime-agent/openai.env`, owned by `dbyte` and mode 0600. Do not place
the key in Git, dashboard assets/responses, the wiki, or conversation text. Enable
`openai/gpt-5.4`, the installed Prime version's API-key-compatible OpenAI default.

## Consequences

New web-terminal Prime processes can authenticate to OpenAI. The dashboard can
select and account for GPT-5.4. Current requests remain blocked until the OpenAI
API account has credits. GPT-5.6 Sol requires the separate OpenAI Codex route.
