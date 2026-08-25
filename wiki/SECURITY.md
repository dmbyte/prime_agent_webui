# Security Posture

Last verified: 2026-08-25

## Access boundary

Prime is served by Nginx with private-CA TLS and session authentication on
`172.16.253.231:8443` and loopback.
The existing private-source Nginx rules remain. The owner explicitly excluded a
new CIDR firewall policy, so UFW remains inactive and no host allowlist was
introduced. Router and perimeter port forwarding must remain disabled.

Only SSH (22) and Prime HTTPS (8443) listen beyond loopback. ttyd (7681), the
PAM broker (8764), dashboard API (8765), Hermes WebUI (8787), Nemotron (30000), and Qwen (30001)
are loopback-only. The default HTTP site and port 80 are disabled. The former
NFS home export, NFS server, and rpcbind listeners are disabled.

## Authentication and abuse controls

PAM accepts only local accounts in the `prime-web` group; `dbyte` is the intended
interactive member. A loopback-only Python broker invokes Ubuntu PAM and issues
random Secure, HttpOnly, SameSite=Strict sessions with 30-minute idle and 12-hour
absolute limits. Nginx delays failed authentication, limits requests and
connections, and emits security headers. Fail2ban monitors only 401 responses to
`POST /auth/login` and, after 15 failures in 10 minutes, bans the source for one
hour via nftables. Expired-session 401 responses from background API polling are
excluded. This reactive rule does not define or narrow trusted CIDRs.

Nginx has been removed from `shadow`. The broker runs as `dbyte` and cannot read
password hashes; PAM delegates the comparison to Ubuntu's narrowly scoped
set-group `unix_chkpwd` helper.

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
- Upload archives reject traversal and links. Active-content previews are blocked;
  allowed PDF/text frames are sandboxed. Retention requires explicit confirmation.

## Credential-history remediation

One conversation file contained two credential-shaped OpenAI key occurrences.
Before redaction, the original was copied into the root-only recovery bundle.
Both were replaced with `[REDACTED_OPENAI_API_KEY]`; a follow-up scan found zero
matching active or trashed session files. If the key is active, it must still be
revoked or rotated in the OpenAI account.

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

## Recovery

Pre-hardening files and checksums are stored root-only at:

`/var/backups/prime-security-20260825T151200-0500`

The immediate pre-v0052 WebUI configuration is stored root-only at:

`/var/backups/prime-webui-v0052-20260825T153014-0500`

Prefer restoring only the affected file or service. Restoring the NFS export,
default Nginx site, wildcard Hermes listener, or unredacted transcript would
reintroduce known vulnerabilities and must be an explicit rollback.
