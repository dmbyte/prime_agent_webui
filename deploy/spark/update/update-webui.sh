#!/usr/bin/env bash
set -euo pipefail

status_dir="${HOME}/.prime/agent/update-status"
status_file="$status_dir/webui.json"
write_status() {
  local result=$1 exit_code=$2 temporary
  install -d -m 0700 "$status_dir"
  temporary=$(mktemp "$status_dir/.webui.XXXXXX")
  printf '{"ran":true,"result":"%s","exitCode":%d,"updatedAt":"%s"}\n' "$result" "$exit_code" "$(date --utc +%FT%TZ)" >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$status_file"
}
finish() { local code=$?; if (( code == 0 )); then write_status success 0; else write_status failed "$code"; fi; }
trap finish EXIT
write_status running 0

exec 9>"${HOME}/.prime/agent/webui-update.lock"
flock -n 9 || { echo "Another WebUI update is already running." >&2; exit 75; }

repo="${HOME}/prime_agent_webui"
live="${HOME}/prime-dgx-dashboard"
source_dir="$repo/deploy/spark/dashboard"
test "$(git -C "$repo" branch --show-current)" = main
test -z "$(git -C "$repo" status --porcelain)"
test "$(git -C "$repo" remote get-url origin)" = "https://github.com/dmbyte/prime_agent_webui.git"

echo "Fetching private origin/main..."
GIT_TERMINAL_PROMPT=0 git -C "$repo" fetch origin main
git -C "$repo" merge --ff-only FETCH_HEAD

python3 -m py_compile "$source_dir/api.py" "$source_dir/api_v2.py" "$source_dir/auth.py"
install -d -m 0755 "$live"
install -m 0644 "$source_dir"/*.py "$source_dir"/*.js "$source_dir"/*.css "$source_dir"/*.html "$live"/
install -m 0755 "$source_dir/install-static.sh" "$live/install-static.sh"

install -d -m 0755 "${HOME}/prime-update" "${HOME}/.config/systemd/user"
install -m 0755 "$repo/deploy/spark/update/update-prime-agent.sh" "$repo/deploy/spark/update/update-webui.sh" "${HOME}/prime-update/"
install -m 0644 "$repo/deploy/spark/systemd/prime-update-agent.service" "$repo/deploy/spark/systemd/prime-update-webui.service" "${HOME}/.config/systemd/user/"
install -m 0644 "$repo/deploy/spark/systemd/prime-dashboard-api.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload

"$live/install-static.sh" "$live"
systemctl --user restart prime-dashboard-api.service
echo "Prime WebUI now matches $(git -C "$repo" rev-parse --short HEAD)."
