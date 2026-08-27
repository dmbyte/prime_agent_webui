#!/usr/bin/env bash
set -euo pipefail

mode=${1:---check}
bundle=${2:-}
[[ $mode == --check || $mode == --apply ]] || { echo "Usage: $0 [--check|--apply] [recovery-bundle]" >&2; exit 2; }
[[ -n $bundle ]] || { echo "An explicit recovery-bundle path is required." >&2; exit 2; }
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
sudo test -d "$bundle"
sudo test -f "$bundle/state.tgz"
sudo test -f "$bundle/SHA256SUMS"
sudo env --chdir="$bundle" sha256sum -c SHA256SUMS

runner_uid=$(id -u prime-runner)
active=$(cd /tmp && sudo -u prime-runner env HOME=/var/lib/prime-runner XDG_RUNTIME_DIR="/run/user/${runner_uid}" podman ps -q | wc -l)
[[ $active -eq 0 ]] || { echo "Stop all active Prime tasks before rollback." >&2; exit 1; }

if [[ $mode == --check ]]; then
  echo "ROLLBACK_CHECK_OK bundle=$bundle active_containers=0"
  exit 0
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
current="/var/backups/prime-rootless-rollback-current-${stamp}"
sudo install -d -o root -g root -m 0700 "$current"
sudo cp -a "$HOME/prime-dgx-dashboard/api.py" "$HOME/prime-dgx-dashboard/api_v2.py" "$HOME/prime-dgx-dashboard/container_runner.py" "$current/"
if [[ -f $HOME/.config/systemd/user/prime-dashboard-api.service.d/rootless.conf ]]; then
  sudo cp -a "$HOME/.config/systemd/user/prime-dashboard-api.service.d/rootless.conf" "$current/"
fi

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
owner=$USER
sudo tar -xzf "$bundle/state.tgz" -C "$temporary" \
  "home/$owner/prime-dgx-dashboard/api.py" \
  "home/$owner/prime-dgx-dashboard/api_v2.py" \
  "home/$owner/prime-dgx-dashboard/container_runner.py" \
  "home/$owner/.config/systemd/user/prime-dashboard-api.service"
sudo chown -R "$USER:$(id -gn)" "$temporary/home/$owner"

# Preserve conversations created after activation before switching execution back.
sudo rsync -a "/var/lib/prime-runner/users/${USER}/prime/agent/sessions/" "$HOME/.prime/agent/sessions/"
sudo chown -R "$USER:$(id -gn)" "$HOME/.prime/agent/sessions"
install -m 0644 "$temporary/home/$owner/prime-dgx-dashboard/api.py" "$HOME/prime-dgx-dashboard/api.py"
install -m 0644 "$temporary/home/$owner/prime-dgx-dashboard/api_v2.py" "$HOME/prime-dgx-dashboard/api_v2.py"
install -m 0644 "$temporary/home/$owner/prime-dgx-dashboard/container_runner.py" "$HOME/prime-dgx-dashboard/container_runner.py"
install -m 0644 "$temporary/home/$owner/.config/systemd/user/prime-dashboard-api.service" "$HOME/.config/systemd/user/prime-dashboard-api.service"
rm -f "$HOME/.config/systemd/user/prime-dashboard-api.service.d/rootless.conf"
systemctl --user daemon-reload
systemctl --user restart prime-dashboard-api.service
sudo systemctl disable --now prime-runner-broker.service prime-model-gateway.service
systemctl --user is-active --quiet prime-dashboard-api.service
curl -ksS -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/api/state | grep -qx 401
echo "ROLLBACK_APPLY_OK current_backup=$current"
