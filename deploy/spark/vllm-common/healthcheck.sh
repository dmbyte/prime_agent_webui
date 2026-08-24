#!/usr/bin/env bash
set -euo pipefail

port="${1:?usage: healthcheck.sh PORT [TIMEOUT_SECONDS]}"
timeout_seconds="${2:-900}"
deadline=$((SECONDS + timeout_seconds))

while (( SECONDS < deadline )); do
  if curl --fail --silent --max-time 5 "http://127.0.0.1:${port}/v1/models" >/dev/null; then
    echo "vLLM on port ${port} is ready"
    exit 0
  fi
  sleep 5
done

echo "vLLM on port ${port} did not become ready within ${timeout_seconds}s" >&2
exit 1
