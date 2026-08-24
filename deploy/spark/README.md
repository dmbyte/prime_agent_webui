# DGX Spark deployment

This tree is the reviewable source for the Spark's Prime Agent and two local
vLLM services. Secrets are intentionally absent. Deployment copies the existing
Hugging Face token into mode-0600 environment files on the Spark.

The local APIs bind only to loopback: Nemotron on port 30000 and Qwen on 30001.
Prime's default model is `spark-nemotron/nemotron-3.5-lightning`; Qwen is an
explicit multimodal/deep specialist.

Launch the configured workspace with `prime-dgx`. Prime is pinned at the
installed version until an update is deliberately reviewed and validated.

`prime-web.service` provides a browser terminal on Spark loopback port 7681.
Nginx exposes it at `https://172.16.253.231:8443` with PAM authentication and
allows only private LAN/VPN source ranges. The initial TLS certificate is
self-signed. The ttyd backend remains loopback-only.
Nginx validates WebSocket origins against the approved HTTPS hostnames before
proxying; ttyd's backend-origin check is disabled because it cannot see through
the reverse proxy correctly.
