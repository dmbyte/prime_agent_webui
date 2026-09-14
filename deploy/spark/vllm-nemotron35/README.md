# Nemotron 3.5 Lightning service

Nemotron 3.5 Lightning is the default local orchestration model for the DGX
Spark WebUI release. It is served by vLLM on `127.0.0.1:30000` and exposed to
Prime through the local model gateway as
`spark-nemotron/nemotron-3.5-lightning`.

## Install

Run these commands as the non-root WebUI owner on the DGX Spark:

```bash
install -d ~/vllm-nemotron35
cp deploy/spark/vllm-nemotron35/vllm.env.template ~/vllm-nemotron35/vllm.env
cp deploy/spark/vllm-nemotron35/start.sh ~/vllm-nemotron35/start.sh
install -m 0644 deploy/spark/systemd/vllm-nemotron35.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vllm-nemotron35.service
```

If the NVIDIA model repository requires authentication, add the Hugging Face
token to `~/vllm-nemotron35/vllm.env` before the first start. Do not commit that
token.

## Defaults

- Image: `vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404`
- Model checkpoint:
  `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`
- DSpark checkpoint:
  `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark`
- Served model name: `nemotron-3.5-lightning`
- Port: `30000`
- Maximum context: `81920`
- KV cache cap: `4G`
- Speculative draft tokens: `3`

## Verify

```bash
systemctl --user status vllm-nemotron35.service
curl -fsS http://127.0.0.1:30000/v1/models
```

The endpoint must remain loopback-only. Prime WebUI reaches it through the
model gateway, not directly from task sandboxes.
