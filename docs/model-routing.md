# Model routing and code ownership

## Mandatory code policy

Qwen 3.8 Flash-Next (`spark-qwen/qwen3.8-flash-next`) generates nontrivial code
in **all six profiles**: General, Development, CAD/3D, Finance, Network operations,
and Read-only review. Selecting a profile controls the sandbox, not code ownership.
Nemotron 3.5 Lightning is the orchestrator for conversation, planning, research
synthesis, and very simple inspection/delegation scripts.

Routing order is:

1. Coding requests, Development/Network operations tasks, and ongoing coding
   conversations go to Qwen. This overrides model directives and custom rules.
   If Qwen is disabled, the request fails with a clear explanation; there is no
   silent Nemotron implementation fallback.
2. Otherwise, the first explicit slash directive (`/nemotron`, `/qwen`,
   `/codex`, `/chatgpt`) selects its enabled target.
3. Otherwise, enabled phrase rules run in descending priority order. Rules with
   the `nemotron-default` scope run only when Nemotron is the selected default.
4. Otherwise, the configured default model handles the conversation.

The code detector covers code/coding/programming, scripts, Python, JavaScript,
TypeScript, IPython, SQL, Bash, PowerShell, implementation, refactoring, debugging,
automation, unit tests/test suites, fixing bugs/errors/failures/tests, and
building/creating/writing/developing an app, application, website, function,
plugin, tool, skill, or installer. It is conservative phrase matching, not a
semantic guarantee for every possible request.

Coding follow-ups such as “continue” or “do it” keep Qwen through saved
conversation metadata. Outside Development/Network operations, an explicit
non-code model request such as `/nemotron summarize the findings` exits that
coding route. A new conversation starts without another chat's coding-route flag.
Project instructions and policy are inherited normally; coding ownership is
global and does not have to be set separately for each project.

If a non-code task already running on Nemotron discovers implementation work,
the managed policy and per-task instructions require a real Qwen delegation:

```python
await rlm.spawn(
    "Implement the bounded task and run its checks; report evidence and blockers.",
    name="implementation",
    model="spark-qwen/qwen3.8-flash-next",
)
```

This is an IPython call, not a separate model tool name. Use a unique child name,
wait for the actual result, and verify it before reporting success. Nemotron must
not write the complex code first and merely ask Qwen to review it. Emerging-task
delegation is an agent instruction, **not a Python execution lock**.

## Default phrase rules

These are the reset/default rules. Administrators may have changed the live list.
Every match is case-insensitive with word boundaries. A disabled target produces
a visible fallback to the selected model for ordinary rules, but **not** for the
mandatory code policy above.

| Priority | Rule | Scope | Target | Trigger phrases |
|---|---|---|---|---|
| 1000 | Explicit Nemotron | Always | Nemotron | `use nemotron`, `route to nemotron`, `/nemotron` |
| 990 | Explicit Codex / ChatGPT | Always | `openai-codex/gpt-5.6-sol` | `use codex`, `ask codex`, `route to codex`, `delegate to codex`, `use chatgpt`, `ask chatgpt`, `/codex`, `/chatgpt` |
| 980 | Explicit Qwen | Always | Qwen | `use qwen`, `ask qwen`, `route to qwen`, `delegate to qwen`, `/qwen` |
| 700 | Codex architecture specialist | Nemotron default | `openai-codex/gpt-5.6-sol` | `software architecture`, `application architecture`, `system architecture`, `architecture recommendation`, `architect the`, `architecture plan` |
| 600 | Qwen visual, CAD, finance, and engineering specialist | Nemotron default | Qwen | `image`, `photo`, `screenshot`, `diagram`, `chart`, `graph`, `png`, `jpeg`, `webp`, `pdf`, `3d print`, `cad`, `stl`, `step`, `mesh`, `slicer`, `printability`, `portfolio`, `stock`, `equity`, `earnings`, `valuation`, `day trading`, `trade setup`, `technical analysis`, `options`, `code review`, `security review`, `independent review`, `second opinion`, `refactor`, `debug` |

The source of truth is `route_task()` / `default_routing_rules()` in
`deploy/spark/dashboard/api_v2.py`. The installable agent policy is
`deploy/spark/prime/AGENTS.managed.md`.

## Installation and administration

Install `deploy/spark/prime/models.json` and `settings.json` as described in the
[Spark recipe](../README.md#dgx-spark-openshell-and-local-models). Both local models
must be configured and Qwen enabled. Apply `deploy/spark/openshell/install.sh` to
refresh managed workspace instructions and immutable runtime images. It backs
up older managed policies; it does not overwrite unrelated custom policies.

Use **Admin → Routing rules** for the current phrase rules. The page explains
the higher-priority code policy. The conversation header shows the actual model;
the Route label's hover text explains the decision. Route changes do not enable
tools, widen network access, bypass confirmation, authorize BMC changes, or permit
live trading. Frontier architecture routes require their provider to be configured
and enabled; code implementation still belongs to Qwen.

Run `bash scripts/validate-release.sh` for routing and runtime regressions. The
installed `validate-prime-kvm-task.py` additionally checks a Qwen-driven synthetic
browser workflow through the real broker, OpenShell, IPython, and final response.
