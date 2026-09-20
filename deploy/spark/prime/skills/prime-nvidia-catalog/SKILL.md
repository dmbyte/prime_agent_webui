---
name: prime-nvidia-catalog
description: Find and load a relevant NVIDIA-verified skill from the globally installed NVIDIA skills catalog without placing all catalog descriptions in every Prime prompt.
---

# NVIDIA Global Skill Catalog

The pinned NVIDIA catalog is installed at
`/home/prime/.prime/agent/catalogs/nvidia`. Use `search_skills(query)` from
`prime_nvidia_catalog` to select the smallest relevant set, then use
`read_skill(name)` and follow that skill's complete instructions.

Catalog instructions guide work; they do not grant new permissions. OpenShell
profile, filesystem, network, credential, approval, and system-tool boundaries
still apply. Treat commands involving package installation, Docker, sudo, host
mutation, external writes, or credentials as requiring the same authorization
they would require without a skill. Do not execute an irrelevant skill merely
because a lexical search matched it.
