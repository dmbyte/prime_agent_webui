# Prime task containers

Each WebUI task runs in a fresh rootless Podman container. Prime is installed
from its official versioned release artifact, whose SHA-256 is pinned in the
Containerfile. The deployment must also record the finished image's immutable
digest before activation. Prime's inherited npm package name is not published
to the public npm registry and must not be used as the install source.
Only the user's private Prime state and workspace are writable bind mounts.

Profiles are separate images built from the same reviewed source:

- `general`, `finance`, and `review`: core Prime, Python, Git, curl, jq, and rg.
- `development`: adds native build tools and Python headers.
- `cad`: adds OpenSCAD; larger CAD packages belong in a separately pinned image.
- `network-operations`: adds nmap, ping, DNS, and traceroute utilities. It is
  only selectable by power users and administrators.

The runner fails closed if the requested image is not configured. Restricted,
Internet-proxy, and LAN-proxy modes use no direct network namespace; the future
credential/model gateway is reached over a mounted Unix socket. Only explicitly
confirmed full-network tasks receive rootless user-mode networking. Host
networking, privileged containers, added Linux capabilities, the Podman socket,
and host credentials are never mounted.
