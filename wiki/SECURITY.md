# Security Posture

Last verified: 2026-08-25

## Access boundary

Prime is served by Nginx with TLS and PAM on `172.16.253.231:8443` and loopback.
The existing private-source Nginx rules remain. The owner explicitly excluded a
new CIDR firewall policy, so UFW remains inactive and no host allowlist was
introduced. Router and perimeter port forwarding must remain disabled.

Only SSH (22) and Prime HTTPS (8443) listen beyond loopback. ttyd (7681), the
dashboard API (8765), Hermes WebUI (8787), Nemotron (30000), and Qwen (30001)
are loopback-only. The default HTTP site and port 80 are disabled. The former
NFS home export, NFS server, and rpcbind listeners are disabled.

## Authentication and abuse controls

PAM accepts only local accounts in the `prime-web` group; `dbyte` is the intended
interactive member. Nginx delays failed authentication, limits requests and
connections, and emits security headers. Fail2ban monitors 401 responses and,
after 15 failures in 10 minutes, bans the source for one hour via nftables. This
reactive rule does not define or narrow trusted CIDRs.

The current PAM module still requires Nginx workers to read password hashes via
the `shadow` group. This is a material residual risk: compromise of Nginx could
enable offline password cracking. An isolated authentication broker is the
preferred future replacement.

The self-signed TLS certificate encrypts traffic but is not trusted until its CA
is installed on each client. A private CA or internal ACME issuer is recommended.

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
- HTTP 401 challenge includes all configured security headers;
- four upload/path/quota tests plus JavaScript and shell syntax checks pass;
- no remaining upgradable package was reported.

During hardening, `RestrictAddressFamilies` prevented ttyd from resolving the
loopback interface and caused a wildcard bind. It was removed from ttyd only,
the service restarted, and `127.0.0.1:7681` was verified. The API retains its
compatible address-family restriction.

## Recovery

Pre-hardening files and checksums are stored root-only at:

`/var/backups/prime-security-20260825T151200-0500`

Prefer restoring only the affected file or service. Restoring the NFS export,
default Nginx site, wildcard Hermes listener, or unredacted transcript would
reintroduce known vulnerabilities and must be an explicit rollback.
