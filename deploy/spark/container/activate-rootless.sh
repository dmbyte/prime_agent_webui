#!/usr/bin/env bash
set -euo pipefail
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
api_pid=$(systemctl --user show prime-dashboard-api.service -p MainPID --value)
if [[ $api_pid =~ ^[1-9][0-9]*$ ]] && pgrep -P "$api_pid" >/dev/null; then
  echo "Active dashboard child tasks must finish before migration." >&2; exit 1
fi
target=/var/lib/prime-runner/users/${USER}/prime/agent
sudo install -d -o prime-runner -g prime-runner -m 0700 "$target"
for name in sessions skills session-artifacts; do
  if [[ -d ${HOME}/.prime/agent/$name ]]; then
    sudo rsync -a "${HOME}/.prime/agent/$name/" "$target/$name/"
  fi
done
sudo rsync -a --exclude uploads "${HOME}/prime-dgx-agent/" "/var/lib/prime-runner/users/${USER}/workspace/"
sudo chown -R prime-runner:prime-runner "/var/lib/prime-runner/users/${USER}"
sudo setfacl -m "u:${USER}:--x,g:prime-web:--x,m::--x" "/var/lib/prime-runner/users/${USER}" "/var/lib/prime-runner/users/${USER}/prime" "$target"
sudo setfacl -Rm "u:${USER}:rwx,g:prime-web:rwx,m::rwx,o::---" "$target/sessions"
sudo setfacl -Rdm "u:${USER}:rwx,g:prime-web:rwx,m::rwx,o::---" "$target/sessions"
sudo install -d -o prime-runner -g prime-runner -m 0770 "$target/trash"
sudo setfacl -m "u:${USER}:rwx,g:prime-web:rwx,m::rwx,o::---" "$target/trash"
sudo setfacl -dm "u:${USER}:rwx,g:prime-web:rwx,m::rwx,o::---" "$target/trash"
sudo find "$target/sessions" -type d -exec chmod 0770 {} +
sudo find "$target/sessions" -type f -exec chmod 0660 {} +
install -d -m 0755 "${HOME}/.config/systemd/user/prime-dashboard-api.service.d"
install -m 0644 "$repo/deploy/spark/container/prime-dashboard-rootless.conf" "${HOME}/.config/systemd/user/prime-dashboard-api.service.d/rootless.conf"
install -m 0644 "$repo/deploy/spark/dashboard/"*.py "${HOME}/prime-dgx-dashboard/"
systemctl --user daemon-reload
systemctl --user restart prime-dashboard-api.service
systemctl --user is-active --quiet prime-dashboard-api.service
