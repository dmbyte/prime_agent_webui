# Spark security hardening

The reviewed deployment applies these host controls in addition to the tracked
WebUI configuration:

- A loopback-only broker verifies a dedicated salted-scrypt WebUI credential and
  issues secure expiring sessions; Nginx has no PAM or `shadow` access. The mode-
  0600 credential is outside the repository and is set interactively with
  `prime-web-password`.
- The distribution Nginx default site is disabled; no plaintext port 80 listener
  is permitted.
- Hermes WebUI is retained but its systemd override binds it to loopback only.
- The unused `/home/dbyte` NFS export is disabled, along with NFS server and
  rpcbind activation. The previous export configuration is retained only in the
  root-only rollback bundle.
- Fail2ban observes Prime endpoint 401 responses and applies temporary reactive
  source bans with nftables. This is not a CIDR allowlist firewall policy.
- Security updates are installed through Ubuntu's signed repositories.
- A root-only private CA signs the WebUI certificate. Only its public certificate
  is copied into the authenticated static site for client trust installation.

The root-only rollback bundle created before deployment is documented in the
corresponding wiki version. Restore individual files from that bundle, reload
systemd/Nginx as appropriate, and verify listeners before re-enabling any
network service.
