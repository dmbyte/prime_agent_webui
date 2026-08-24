# ADR-0009: Permit authenticated browser access from private networks

- Status: accepted
- Date: 2026-08-23

## Decision

Listen for the PAM-authenticated HTTPS interface on 172.16.253.231:8443 as well
as loopback. Allow only loopback, RFC1918 source ranges, and 100.64.0.0/10 for
private VPN overlays; deny every other source. Keep ttyd on loopback and prohibit
public router/firewall forwarding.

## Rationale and consequences

LAN and routed VPN clients can now use Prime without maintaining individual SSH
tunnels, while PAM and TLS remain mandatory. Binding to the specific LAN address
avoids Docker and unspecified interfaces. The broad private-range allowlist meets
the requirement for all LAN/VPN clients but means any reachable private client
can attempt PAM authentication; password quality and monitoring therefore remain
important. VPNs using other source ranges require a reviewed ACL addition.

The certificate was rotated to cover localhost, spark-c562, 127.0.0.1, and
172.16.253.231. The v0009 certificate and key were archived root-only on the
Spark before rotation.

## Validation and rollback

Nginx syntax and service reload passed. Both the Spark and a LAN Mac reached the
LAN endpoint and received HTTP 401 without credentials. The complete acceptance
gate passed. Roll back by restoring the v0009 Nginx site and archived certificate,
then reloading Nginx.
