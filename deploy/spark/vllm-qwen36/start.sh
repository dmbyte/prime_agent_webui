#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "${script_dir}/vllm.env"
set +a
: "${HF_TOKEN:?HF_TOKEN is required in vllm.env}"

image="${IMAGE:-vllm/vllm-openai:v0.27.1-aarch64-cu129-ubuntu2404}"
container="${CONTAINER_NAME:-vllm-qwen36}"
port="${PORT:-30001}"

until docker info >/dev/null 2>&1; do sleep 2; done
docker rm -f "${container}" >/dev/null 2>&1 || true

exec docker run -d --restart unless-stopped \
  --name "${container}" --gpus all --shm-size 24g --ipc=host \
  --memory="${DOCKER_MEMORY_LIMIT:-52g}" --memory-swap="${DOCKER_MEMORY_SWAP:-64g}" \
  --oom-score-adj 600 -p "127.0.0.1:${port}:${port}" \
  -v "${HOME}/.cache/huggingface:/root/.cache/huggingface" -e HF_TOKEN="${HF_TOKEN}" \
  "${image}" "${MODEL_CKPT:-nvidia/Qwen3.6-35B-A3B-NVFP4}" \
  --host 0.0.0.0 --port "${port}" --trust-remote-code --moe-backend marlin \
  --kv-cache-dtype fp8 --enable-prefix-caching --enable-chunked-prefill --async-scheduling \
  --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-auto-tool-choice \
  --max-model-len "${MAX_MODEL_LEN:-65536}" --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.38}" \
  --kv-cache-memory-bytes "${KV_CACHE_MEMORY_BYTES:-8G}" --max-num-seqs "${MAX_NUM_SEQS:-2}" \
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS:-8192}" \
  --served-model-name "${SERVED_MODEL_NAME:-qwen3.6-35b-a3b}"
