#!/usr/bin/env bash
set -euo pipefail
umask 0007
socat TCP-LISTEN:31000,bind=127.0.0.1,reuseaddr,fork UNIX-CONNECT:/run/prime-gateway/model.sock &
bridge_pid=$!
proxy_pid=""
if test -S /run/prime-gateway/network.sock; then
  socat TCP-LISTEN:31080,bind=127.0.0.1,reuseaddr,fork UNIX-CONNECT:/run/prime-gateway/network.sock &
  proxy_pid=$!
  export HTTP_PROXY=http://127.0.0.1:31080 HTTPS_PROXY=http://127.0.0.1:31080 ALL_PROXY=http://127.0.0.1:31080
  export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" all_proxy="$ALL_PROXY"
fi
trap 'kill "$bridge_pid" ${proxy_pid:-} 2>/dev/null || true' EXIT
for attempt in 1 2 3 4 5; do
  test -S /run/prime-gateway/model.sock && break
  sleep 0.1
done
exec /usr/bin/tini -- prime-agent "$@"
