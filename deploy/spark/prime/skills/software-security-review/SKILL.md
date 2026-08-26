---
name: software-security-review
description: Perform evidence-based, technology-neutral security reviews of software projects. Use for requested security audits, threat reviews, vulnerability assessments, or secure-design reviews; discover capabilities first and apply only relevant checks.
---

# Software Security Review

Review the actual system, not an assumed framework. Default to read-only analysis.
Do not modify code, configuration, dependencies, services, or data unless the user
separately asks for remediation.

## Review method

1. Establish scope, deployment context, exposed interfaces, identities, assets,
   trust boundaries, and attacker capabilities. Treat proxies, workers, local
   services, subprocesses, plugins, agents, and administrators as separate trust
   zones until evidence shows otherwise.
2. Inventory project capabilities before auditing details. Read
   [references/capability-checklist.md](references/capability-checklist.md) and
   apply every module whose activation test is true. Record important modules as
   present, absent, or unknown so an absent feature does not generate findings.
3. Trace security properties end to end. A control at one layer is insufficient
   if another path bypasses it. Follow data and authority across process, host,
   container, proxy, queue, storage, and third-party boundaries.
   For every privileged backend behind a gateway, explicitly test whether a local
   process, sibling service, container, plugin, job, or agent can reach it without
   the gateway and forge the gateway's identity assertions. Loopback alone is not
   authentication.
   For every claimed tenant/user boundary, compare the application identity with
   the OS/process identity, filesystem view, credentials, tools, terminal, cache,
   and IPC access used by background work. A shared execution identity invalidates
   isolation unless an independently enforced sandbox preserves the boundary.
4. Validate behavior against code, configuration, tests, runtime evidence, or
   authoritative platform semantics. Never infer that a default header is
   dropped, a same-origin path is cross-origin, memory is leaked, or sanitization
   is absent without confirming the relevant runtime behavior.
5. For each candidate, construct the shortest concrete attack path: prerequisite,
   attacker-controlled input or authority, vulnerable operation, boundary crossed,
   and impact. If any link is unverified, label the item `Needs validation` rather
   than `Confirmed`.
6. Check compensating controls and alternate paths before assigning severity.
   Separate security vulnerabilities from reliability defects, functional bugs,
   policy choices, and defense-in-depth opportunities.

## Evidence and severity rules

Every confirmed finding must include:

- severity and confidence;
- affected component plus exact file/line or runtime evidence;
- attacker prerequisites and a reproducible attack path;
- the security property violated and realistic impact;
- existing controls and why they do not stop the path;
- a scoped remediation and a validation test.

Use `Critical` only for plausible compromise of highly sensitive assets or broad
control with practical prerequisites. Use `High` for serious confidentiality,
integrity, availability, authorization, or code-execution impact. Use `Medium`
for constrained exploitation or material tenant/resource impact. Use `Low` for
limited impact. Do not inflate severity because a bug is easy to describe.

Classify every item as one of:

- `Confirmed vulnerability`
- `Needs validation`
- `Reliability or correctness defect`
- `Defense in depth`
- `Accepted/design trust assumption`

## Output

Lead with the confirmed findings in descending severity. Then list needs-
validation items, reliability defects, and defense-in-depth suggestions. Include
an assessed-capabilities table before the findings, important negative results,
review limitations,
and a prioritized remediation order. State the provider, model, effort, tools,
and whether runtime validation was performed only from trusted invocation/runtime
metadata. If that metadata is unavailable, say `unknown`; never infer or invent it.

Do not count duplicated symptoms as separate vulnerabilities. Do not recommend
weakening a protection merely to restore functionality without first identifying
a safer correction.
