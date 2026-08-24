# ADR-0030: Wait for the private address before starting Nginx

Date: 2026-08-24
Status: accepted

## Context

After a Spark reboot, the Prime user services started successfully but Nginx
failed because its configuration binds `172.16.253.231:8443` before that address
was assigned. The distribution Nginx unit already ordered itself after
`network-online.target`, but neither available wait-online service was enabled,
so the target did not guarantee address readiness.

## Decision

Keep Nginx bound only to loopback and the explicit private LAN address. Add a
systemd drop-in that replaces Nginx's preflight sequence with a bounded 120-second
wait for exactly `172.16.253.231`, followed by the original configuration test.
The helper fails closed if the address never appears.

## Consequences

Normal boots tolerate delayed address assignment without broadening network
exposure. A missing or changed private address leaves Nginx failed after two
minutes rather than making the dashboard listen on every interface. A future LAN
address change must update both the Nginx site and the wait drop-in.

## Rollback

Remove `/etc/systemd/system/nginx.service.d/prime-address-wait.conf` and
`/usr/local/sbin/prime-wait-address`, reload systemd, and restart Nginx after the
LAN address is present. This restores the original boot race.
