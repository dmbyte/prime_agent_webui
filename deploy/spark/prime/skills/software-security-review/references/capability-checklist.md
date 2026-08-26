# Capability-driven security checklist

Use the activation test for each module. Apply only relevant branches, but revisit
the inventory when one component reveals another capability.

## Baseline for every project

- Identify languages, runtimes, build system, deployment units, privilege levels,
  writable locations, secrets, sensitive data, dependencies, update paths, and
  security-relevant tests.
- Map external and local entry points, callers, data stores, subprocesses, network
  peers, administrative paths, and recovery mechanisms.
- Check untrusted-input flow, boundary validation, error handling, concurrency,
  resource limits, logging/redaction, defaults, and fail-open/fail-closed behavior.
- Compare documentation, tests, configuration, and deployed behavior. Mark unknown
  deployment assumptions instead of converting them into findings.

## Web interface or HTTP API

Activation: routes, controllers, HTTP listeners, browser assets, reverse proxies,
WebSockets, webhooks, or API schemas exist.

- Map public, authenticated, administrator, internal, health, static, upload,
  download, redirect, WebSocket, and proxy routes.
- Check method authorization, object-level authorization, tenant ownership,
  request-size/time/concurrency limits, parsing ambiguities, duplicate headers,
  content types, cache behavior, error disclosure, rate limiting, and abuse cost.
- Check injection and rendering by context: HTML/DOM, script, CSS, URL, header,
  template, command, query, path, log, and serialization.
- For browser sessions, evaluate TLS, cookie attributes, CSRF, CORS, Origin/Host,
  CSP, clickjacking, MIME sniffing, referrer leakage, redirects, service workers,
  postMessage, frames, and WebSocket origin/authentication.
- Trace proxy behavior using documented defaults and effective configuration.
  Determine whether clients can bypass the proxy or spoof trusted identity headers.
- For uploads/downloads, check canonical paths, symlinks, quotas, archive bombs,
  decompression, active content, metadata ownership, retention, and range/streaming.

## Authentication, sessions, or accounts

Activation: login, tokens, API keys, cookies, OAuth/OIDC/SAML, passwords, roles,
service identities, or account administration exist.

- Trace enrollment, authentication, recovery, rotation, revocation, logout,
  disable/delete, session expiry, and authorization refresh.
- Check credential storage and comparison, enumeration, brute-force controls,
  replay, fixation, token audience/scope/issuer, key rotation, clock handling,
  default accounts, and last-administrator safeguards.
- Test authorization server-side at function and object boundaries; UI hiding is
  not enforcement. Check horizontal, vertical, cross-tenant, confused-deputy,
  delegation, impersonation, and local-bypass paths.
- Determine which identities share an OS user, process, credential store, cache,
  agent/tool environment, terminal, or backup. Do not claim tenant isolation if a
  shared execution context can read or modify another tenant's assets.

## Memory, buffers, or resource ownership

Activation: manual allocation, unsafe/native code, FFI, binary parsing, shared
memory, GPU buffers, large/untrusted allocations, caches, pools, streams, or
sensitive values in memory exist.

- Determine the ownership and lifetime model: manual, RAII, garbage collected,
  reference counted, arena/pool, device-managed, or cross-language.
- For native/unsafe paths, check bounds and integer arithmetic, allocation failure,
  initialization, lifetime, aliasing, use-after-free, double free, invalid free,
  leaks, races, type confusion, and exception/error cleanup.
- For managed runtimes, check unbounded retention, attacker-controlled allocation,
  cache eviction, stream buffering, task/thread leaks, object resurrection, FFI
  boundaries, and memory-pressure failure behavior.
- For secrets, minimize copies and lifetime; avoid immutable intermediates where
  practical; zeroize before release only when the runtime and storage make that
  meaningful. Do not demand manual deallocation or zeroization from a garbage-
  collected abstraction that cannot guarantee it; document the residual instead.
- For GPU/shared/direct-memory buffers, check initialization, reuse, tenant
  separation, synchronization, pinning, cleanup on cancellation/failure, and
  whether prior contents can cross requests or processes.
- Check CPU, memory, disk, descriptors, threads, processes, connections, GPU
  memory, tokens, and paid API consumption for quotas, backpressure, cancellation,
  timeouts, cleanup, and denial-of-service amplification.

## Filesystem, storage, or databases

Activation: files, object stores, databases, caches, queues, backups, logs, or
user-selected paths exist.

- Check canonicalization, traversal, symlinks/hardlinks, races, permissions,
  ownership, temporary files, atomicity, locking, partial failure, durability,
  quotas, encryption, deletion semantics, recovery copies, and backup exposure.
- Check query construction, parameterization, row/object authorization, tenant
  keys, migrations, transaction boundaries, stale indexes, retention, exports,
  replication, and consistency after interruption.
- Treat metadata and primary content as one authorization unit. Validate that
  fallback ownership cannot reveal orphaned or legacy data.

## Commands, subprocesses, plugins, or agents

Activation: shells, process spawning, job runners, interpreters, templates,
plugins, extensions, notebooks, terminals, CI jobs, or AI/tool agents exist.

- Trace every argument, environment variable, working directory, executable,
  search path, inherited descriptor, credential, and writable location.
- Prefer argument arrays and allowlists; check shell expansion, option injection,
  PATH/library hijacking, unsafe interpreters, signal/process-group cleanup,
  timeout behavior, output limits, and child privilege.
- Treat an agent prompt as attacker-controlled input when users can influence it.
  Evaluate tool permissions, filesystem/network reach, secret inheritance,
  approval boundaries, prompt injection, cross-user state, and whether local
  services trust requests the child can forge.
- Verify plugins and hooks cannot silently expand authority or bypass the primary
  authentication/authorization path.

## Network clients, servers, IPC, or distributed systems

Activation: sockets, RPC, message buses, service discovery, cloud APIs, peer-to-
peer protocols, local ports, Unix sockets, or callbacks exist.

- Inventory bind addresses, firewall/proxy boundaries, peer identity, encryption,
  certificate and hostname validation, protocol negotiation, DNS/proxy behavior,
  retries, replay, request signing, and downgrade paths.
- Include local attackers and sibling processes. Loopback is exposure reduction,
  not authentication. Prefer authenticated IPC or permissioned Unix sockets for
  privileged local services.
- Check SSRF, rebinding, redirect handling, metadata endpoints, egress controls,
  parsing differentials, desynchronization, queue poisoning, idempotency, and
  distributed authorization consistency.

## Cryptography or sensitive data

Activation: encryption, hashing, signing, random tokens, certificates, password
storage, key derivation, protected personal/financial/health data, or secrets exist.

- Use established constructions and libraries. Check algorithm/mode, parameters,
  nonce uniqueness, entropy, key separation, comparison, rotation, revocation,
  certificate validation, downgrade resistance, and failure behavior.
- Map secret creation, input, storage, environment inheritance, use, logs, crash
  artifacts, backups, UI responses, process memory, and deletion. Redaction is not
  revocation; encryption at rest is not authorization.

## Concurrency, asynchronous work, or lifecycle operations

Activation: threads, async tasks, queues, workers, signals, scheduled jobs,
parallel requests, migrations, bulk operations, or multi-step deletion exist.

- Check shared-state synchronization, lock coverage/order, TOCTOU, cancellation,
  retries, duplicate delivery, idempotency, partial commits, stale authorization,
  shutdown/restart recovery, and orphan cleanup.
- Distinguish exploitable races from integrity/reliability defects. State what an
  attacker must control to win the race and what security boundary would break.

## Dependencies, builds, updates, or deployment

Activation: third-party packages, containers, CI/CD, installers, auto-updaters,
release channels, generated artifacts, or infrastructure configuration exist.

- Check provenance, pinned versions/integrity, signatures/attestations, lockfiles,
  dependency confusion, build scripts, untrusted contributions, artifact identity,
  rollback, secret exposure, and separation of build/update/runtime authority.
- Verify an updater binds the intended repository, release, resolved artifact,
  and installed result. Identify moving references and unsigned trust as explicit
  supply-chain assumptions rather than automatic vulnerabilities.
- Review service/container sandboxing, filesystem and network permissions,
  capabilities, users, writable paths, environment files, restart behavior, and
  whether deployment configuration matches the analyzed source.

## Domain-specific activation prompts

When present, add focused checks for mobile/desktop IPC and deep links; embedded
and hardware safety; parsers and file formats; serialization; ML model loading and
prompt/tool boundaries; payment and financial authorization; privacy/consent;
real-time/media processing; and safety-critical control. State which specialist
standard or expertise is still needed when the review cannot cover it reliably.

## Negative-result discipline

Record important checks that passed, especially when they eliminate common false
positives. Do not report absent controls that are inapplicable to the discovered
architecture. Do not convert theoretical compromise of an already-trusted
administrator or writable configuration owner into a new vulnerability unless it
crosses an additional boundary.
