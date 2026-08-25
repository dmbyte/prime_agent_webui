# Spark security hardening

The reviewed deployment applies these host controls in addition to the tracked
WebUI configuration:

- `prime-web` is the only PAM group authorized for the Prime HTTPS interface.
- The distribution Nginx default site is disabled; no plaintext port 80 listener
  is permitted.
- Hermes WebUI is retained but its systemd override binds it to loopback only.
- The unused `/home/dbyte` NFS export is disabled, along with NFS server and
  rpcbind activation. The previous export configuration is retained only in the
  root-only rollback bundle.
- Fail2ban observes Prime endpoint 401 responses and applies temporary reactive
  source bans with nftables. This is not a CIDR allowlist firewall policy.
- Security updates are installed through Ubuntu's signed repositories.

The root-only rollback bundle created before deployment is documented in the
corresponding wiki version. Restore individual files from that bundle, reload
systemd/Nginx/PAM as appropriate, and verify listeners before re-enabling any
network service.
