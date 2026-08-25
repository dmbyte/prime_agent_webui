# ADR-0039: Harden Prime without adding a CIDR firewall policy

Status: accepted

Date: 2026-08-25

## Context

The review found unnecessary listeners and NFS exposure, weak PAM scope, missing
abuse controls and headers, application races, unbounded request concurrency,
pending security updates, and a credential-shaped value in conversation history.
The owner requested all security remediations except CIDR firewall policy.

## Decision

Harden the application, PAM, Nginx, systemd services, package state, credential
history, and exposed services. Disable NFS/rpcbind and bind internal services to
loopback. Add reactive fail2ban blocking. Preserve the existing Nginx private-
source rules, but do not activate UFW or introduce a new host CIDR allowlist.

## Consequences

The remotely reachable surface is reduced to SSH and authenticated Prime HTTPS,
and common application/authentication attacks have bounded impact. Network
admission still depends on Nginx rules and the owner's perimeter configuration.
PAM's Nginx `shadow` access and the self-signed certificate remain material
residual risks requiring architectural/client-trust changes.

## Rollback

Use `/var/backups/prime-security-20260825T151200-0500` to restore individual
pre-hardening files. Do not restore the unredacted transcript or unnecessary
network services unless knowingly accepting the previous exposure.
