# Security Posture

Last verified: 2026-08-25

## Access boundary

Prime is served by Nginx with private-CA TLS and session authentication on
`172.16.253.231:8443` and loopback.
The existing private-source Nginx rules remain. The owner explicitly excluded a
new CIDR firewall policy, so UFW remains inactive and no host allowlist was
introduced. Router and perimeter port forwarding must remain disabled.

Only SSH (22) and Prime HTTPS (8443) listen beyond loopback. ttyd (7681), the
local session broker (8764), dashboard API (8765), Nemotron (30000), and Qwen (30001)
are loopback-only. The default HTTP site and port 80 are disabled. The former
NFS home export, NFS server, and rpcbind listeners are disabled.

## Authentication and abuse controls

The WebUI does not use PAM or the Linux account password. A loopback-only Python
broker verifies the dedicated `dbyte` WebUI password against an owner-only salted-
scrypt record and issues random Secure, HttpOnly, SameSite=Strict sessions with
30-minute idle and 12-hour absolute limits. The credential loader rejects links,
wrong ownership, permissive modes, malformed data, and unexpected KDF parameters.
Nginx delays failed authentication, limits requests and
connections, and emits security headers. Fail2ban monitors only 401 responses to
`POST /auth/login` and, after 15 failures in 10 minutes, bans the source for one
hour via nftables. Expired-session 401 responses from background API polling are
excluded. This reactive rule does not define or narrow trusted CIDRs.

Nginx and the broker have no `shadow` access. The broker runs as `dbyte` under
filesystem, network, syscall, and process confinement. Password hashing is
serialized to bound memory use, uses scrypt N=32768/r=8/p=1 with a random 16-byte
salt, and compares the result in constant time.

The server certificate is signed by a dedicated private CA with SANs for the
Spark IP, hostname, localhost, and loopback. Clients must install the downloadable
`/prime-webui-ca.crt` once. The CA private key is root-only on the Spark.

## Application protections

- The API has bounded sizes and content types, socket timeouts, a 16-request
  concurrency gate, restrictive filesystem access, and structured security logs.
- Upload quota checking and writing are serialized, stored names are bounded by
  UTF-8 byte length, files are mode 0600, and paths remain private.
- Conversation deletion is recoverable, serialized, and rechecks that a session
  is inactive immediately before its atomic move.
- Malformed JSONL records are skipped individually instead of hiding an entire
  conversation. Provider/model identifiers preserve model path separators.
- The API no longer reads the OpenAI environment file to determine configuration
  state; the service supplies a non-secret flag and cannot read the key path.
- The repository includes Python regression tests; JavaScript, shell syntax, and
  credential-pattern checks were run before commit. Continuous integration is
  not enabled because the current GitHub credential lacks workflow scope.
- Native tasks have four-task admission, separate process groups, explicit stop,
  30-minute limits, credential-redacted logs, and a dedicated usage ledger.
- Provider configuration is administrator-only and CSRF/Origin checked. API keys
  are accepted only in bounded JSON, atomically stored mode 0600 in Prime's auth
  store, never returned or audit-logged, and cleared from the modal after use.
  Non-key cloud fields use a separate mode-0600 settings file. Existing OAuth
  entries and local model definitions are preserved during updates.
- Release status is administrator-only. Repository identities are fixed in the
  server and updater code; returned tags and URLs must match strict formats, and
  release commits are resolved through GitHub before use. Browser input cannot
  select a repository, package, tag, or shell command. Updaters install exact
  validated releases rather than an unconstrained branch or npm `latest` alias.
  Deployed validation confirmed both release sources, all 28 regression tests,
  and active authentication, API, and model services without invoking an update.
- The owner explicitly approved removing the dashboard service's loopback-only
  egress filter for provider access. Its listener remains loopback-only; live
  validation showed empty `IPAddressDeny`/`IPAddressAllow` values and active
  authentication/API/model services.
- Upload archives reject traversal and links. Active-content previews are blocked;
  allowed PDF/text frames are sandboxed. Retention requires explicit confirmation.

## Confirmed review gaps

- The loopback dashboard API treats `X-Prime-User` and `X-Prime-Role` as trusted
  proxy assertions but does not authenticate Nginx itself. Local processes can
  bypass Nginx and forge those headers; a read-only request using fabricated
  administrator headers returned HTTP 200 from `/api/admin` on 2026-08-26.
- Per-user ownership enforcement exists in the WebUI APIs, but native Prime tasks
  and the writable Advanced console execute as shared OS account `dbyte` with a
  common home and agent environment. Nginx requires a valid session for the
  console but does not require the admin role. These execution paths are not a
  tenant boundary, so all enabled WebUI users must currently be mutually trusted.
- The review was explicitly report-only. No security control was changed. The
  recommended direction is authenticated/permissioned backend IPC, admin-only
  console access, and per-user process/storage/credential sandboxing.

## Credential-history remediation

One conversation file contained two credential-shaped OpenAI key occurrences.
Before redaction, the original was copied into the root-only recovery bundle.
Both were replaced with `[REDACTED_OPENAI_API_KEY]`; a follow-up scan found zero
matching active or trashed session files. If the key is active, it must still be
revoked or rotated in the OpenAI account.

The v0068 visual check found a different plaintext service credential embedded
in a historical user-authored script and consequently rendered in that user's
private transcript. Its value is intentionally omitted here. Rotation at the
service provider, removal from the source script, and redaction of the owned
transcript remain pending explicit authorization; WebUI ownership isolation does
not make a credential safe once it has been written into user-visible content.

## Package state and validation

On 2026-08-25, all 19 available security updates were applied (OpenSSL, FFmpeg,
OpenJDK 8, Vim, and dependencies), and fail2ban was installed. Validation passed:

- both local models healthy and private with at least 20% memory headroom;
- all Prime/dashboard/Nginx/fail2ban/model services active;
- no NFS export or rpcbind/NFS listener;
- unauthenticated HTTPS redirects to the login form and the broker returns 401;
- seven upload/path/quota/archive tests plus JavaScript and shell checks pass;
- no remaining upgradable package was reported.

During hardening, `RestrictAddressFamilies` prevented ttyd from resolving the
loopback interface and caused a wildcard bind. It was removed from ttyd only,
the service restarted, and `127.0.0.1:7681` was verified. The API retains its
compatible address-family restriction.

Later on 2026-08-25, an unreviewed replacement of the authentication broker and
Prime-specific PAM policy caused Nginx 502 responses and introduced a non-empty-
password bypass plus `nullok`. The altered files were preserved, the reviewed
repository versions were restored, and the obsolete Nginx PAM policy was removed.
Invalid credentials now return 401, the broker listens only on loopback, and the
audited live security artifacts match their tracked hashes.

PAM was retired from the WebUI in v0056 after its user-service confinement proved
incompatible with Ubuntu's set-group password helper. A dedicated local password
keeps the broker unprivileged and fully confined without granting any process
access to Linux password hashes. The PAM-free broker fails closed with 503 until
the owner creates the initial credential interactively.

The owner subsequently created the credential interactively. Its file is mode
0600 under a mode-0700 owner directory, `/auth/status` reports it configured,
and the owner's browser login returned 200. No password or credential-record
contents were handled during validation; no Fail2ban source is currently banned.

Hermes Agent and WebUI were later removed completely from the active system:
gateway/WebUI services, runtime/data, launchers, two disabled legacy model units,
the 25.5 GB SGLang image, Hermes model/package caches, and identified Hermes-
named project/setup paths. Port 8787 is closed and no active Hermes service,
process, image, listener, cache, or installation path remains. Prime and both
commissioned vLLM endpoints remained healthy. The root-only WebUI recovery copy
and older baseline/history records remain protected rollback evidence.

## Recovery

Pre-hardening files and checksums are stored root-only at:

`/var/backups/prime-security-20260825T151200-0500`

The immediate pre-v0052 WebUI configuration is stored root-only at:

`/var/backups/prime-webui-v0052-20260825T153014-0500`

The authentication files found altered during v0055 are stored root-only with a
checksum manifest at:

`/var/backups/prime-auth-recovery-20260825T165500-0500`

The immediate pre-v0056 PAM broker, unit, policy, and login page are stored
root-only with checksums at:

`/var/backups/prime-local-auth-v0056-20260825T170500-0500`

Prefer restoring only the affected file or service. Restoring the NFS export,
default Nginx site, wildcard Hermes listener, or unredacted transcript would
reintroduce known vulnerabilities and must be an explicit rollback.
