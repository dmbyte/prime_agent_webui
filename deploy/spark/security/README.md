# Spark security hardening

The reviewed deployment applies these host controls in addition to the tracked
WebUI configuration:

- A loopback-only broker verifies a dedicated salted-scrypt WebUI credential and
  issues secure expiring sessions; Nginx has no PAM or `shadow` access. The mode-
  0600 credential is outside the repository and is set interactively with
  `prime-web-password`.
- The distribution Nginx default site is disabled; no plaintext port 80 listener
  is permitted.
- Hermes Agent, its WebUI, gateway, legacy model services, caches, and active
  installation data are removed.
- The unused `/home/dbyte` NFS export is disabled, along with NFS server and
  rpcbind activation. The previous export configuration is retained only in the
  root-only rollback bundle.
- Fail2ban observes Prime endpoint 401 responses and applies temporary reactive
  source bans with nftables. This is not a CIDR allowlist firewall policy.
- Security updates are installed through Ubuntu's signed repositories.
- A root-only private CA signs the WebUI certificate. Only its public certificate
  is copied into the authenticated static site for client trust installation.

The rootless installer prints the path to its root-only rollback bundle. Verify
it with `deploy/spark/container/rollback-rootless.sh --check BUNDLE` before any
restore. Restore individual files from the bundle, reload systemd/Nginx as
appropriate, and verify listeners before re-enabling any network service.
