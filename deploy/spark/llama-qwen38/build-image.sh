#!/usr/bin/env bash
set -euo pipefail

source_dir="${SOURCE_DIR:-${HOME}/src/llama.cpp-qwen38-mtp}"
revision="560abb6616eea7b8c0fc76259bc08142df5c2e1b"
image="local/llama-qwen38-mtp:560abb66"

test "$(git -C "${source_dir}" rev-parse HEAD)" = "${revision}"
test -z "$(git -C "${source_dir}" status --porcelain)"

exec docker build \
  --file "${source_dir}/.devops/cuda.Dockerfile" \
  --target server \
  --build-arg CUDA_VERSION=13.0.2 \
  --build-arg CUDA_DOCKER_ARCH=121 \
  --build-arg APP_REVISION="${revision}" \
  --tag "${image}" \
  "${source_dir}"
