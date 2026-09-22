#!/usr/bin/env bash
set -euo pipefail
umask 0007

# The mounted Prime state is the durable home for skills, tool caches, and
# user-level runtimes. Keep the project-visible compatibility path connected to
# that registry so agent-authored skills cannot silently land in workspace-only
# storage. A pre-existing workspace skill directory is copied, then retained as
# a timestamped recovery directory rather than deleted.
prime_state=/home/prime/.prime
skill_registry="$prime_state/agent/skills"
legacy_skills=/project/.prime/agent/skills
install -d -m 0700 "$skill_registry" "$prime_state/cache/uv" "$prime_state/cache/pip" \
  "$prime_state/cache/npm" "$prime_state/tools/npm" "$prime_state/tools/playwright"
if test -d "$legacy_skills" && ! test -L "$legacy_skills"; then
  cp -a "$legacy_skills/." "$skill_registry/"
  legacy_backup="${legacy_skills}.workspace-backup-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$legacy_skills" "$legacy_backup"
  ln -s "$skill_registry" "$legacy_skills"
elif ! test -e "$legacy_skills"; then
  install -d -m 0700 "$(dirname "$legacy_skills")"
  ln -s "$skill_registry" "$legacy_skills"
fi

socat TCP-LISTEN:31000,bind=127.0.0.1,reuseaddr,fork UNIX-CONNECT:/run/prime-gateway/model.sock &
bridge_pid=$!
proxy_pid=""
bmc_broker_pid=""
if test -S /run/prime-gateway/network.sock; then
  socat TCP-LISTEN:31080,bind=127.0.0.1,reuseaddr,fork UNIX-CONNECT:/run/prime-gateway/network.sock &
  proxy_pid=$!
  export HTTP_PROXY=http://127.0.0.1:31080 HTTPS_PROXY=http://127.0.0.1:31080 ALL_PROXY=http://127.0.0.1:31080
  export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" all_proxy="$ALL_PROXY"
  # Keep the local model bridge out of the policy proxy. Proxy-aware clients
  # otherwise send 127.0.0.1 through a proxy that correctly rejects loopback.
  export NO_PROXY="127.0.0.1,localhost,::1" no_proxy="127.0.0.1,localhost,::1"
fi
if command -v chromium >/dev/null 2>&1; then
  bmc_socket=/tmp/prime-bmc-browser.sock
  bmc_log=/tmp/prime-bmc-browser.log
  rm -f "$bmc_socket"
  : >"$bmc_log"
  chmod 0600 "$bmc_log"
  /opt/prime-kernel/bin/python -m bmc_headless_browser --daemon "$bmc_socket" \
    </dev/null >>"$bmc_log" 2>&1 &
  bmc_broker_pid=$!
  export BMC_BROWSER_BROKER="$bmc_socket"
  export BMC_BROWSER_LOG="$bmc_log"
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    test -S "$bmc_socket" && break
    kill -0 "$bmc_broker_pid" 2>/dev/null || {
      echo "BMC browser broker failed to start" >&2
      exit 1
    }
    sleep 0.1
  done
  test -S "$bmc_socket" || {
    echo "BMC browser broker did not become ready" >&2
    exit 1
  }
fi
trap 'kill "$bridge_pid" ${proxy_pid:-} ${bmc_broker_pid:-} 2>/dev/null || true' EXIT
for attempt in 1 2 3 4 5; do
  test -S /run/prime-gateway/model.sock && break
  sleep 0.1
done
exec /usr/bin/tini -- prime-agent "$@"
