#!/usr/bin/env bash
set -euo pipefail
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
runner_uid=$(id -u prime-runner)
workspace_root="${PRIME_RUNNER_WORKSPACE_ROOT:-${HOME}/prime-agent/tasks}"
# Do not silently restart active ISO downloads during an upgrade.
if sudo test -S "/var/lib/prime-runner/hosting/${USER}/admin.sock"; then
  current=$(sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner "$USER" list)
  if ! jq -e '.ok == true and (.result.services | length) == 0' >/dev/null <<<"$current"; then
    echo "Hosting services exist. Stop them explicitly before upgrading hosting." >&2
    exit 75
  fi
fi
sudo install -d -o prime-runner -g prime-runner -m 0700 /var/lib/prime-runner/hosting /var/lib/prime-runner/hosting-capabilities /var/lib/prime-runner/hosting-access "/var/lib/prime-runner/hosting-access/${USER}"
volume="prime-${USER}-hosting"
device="/var/lib/prime-runner/hosting-access/${USER}"
if docker volume inspect "$volume" >/dev/null 2>&1; then
  test "$(docker volume inspect "$volume" --format '{{ index .Options "device" }}')" = "$device" || { echo "Unexpected hosting volume source" >&2; exit 1; }
  docker volume inspect "$volume" | jq -e '.[0].Labels == {"openshell.ai/sandbox-attachable":"true","openshell.ai/sandbox-attachable-workspace":"default"}' >/dev/null || { echo "Unexpected hosting volume admission labels" >&2; exit 1; }
else
  docker volume create --driver local --opt type=none --opt o=bind --opt "device=$device" \
    --label openshell.ai/sandbox-attachable=true --label openshell.ai/sandbox-attachable-workspace=default "$volume" >/dev/null
fi
sudo install -o root -g root -m 0644 "$repo"/deploy/spark/container/hosting_{auth,broker,server,admin}.py /usr/local/lib/prime-runner/
unit=$(mktemp)
trap 'rm -f "$unit"' EXIT
sed -e "s/@RUNNER_UID@/${runner_uid}/g" -e "s/@WEB_OWNER@/${USER}/g" "$repo/deploy/spark/systemd/prime-hosting-broker.service" >"$unit"
printf '\n[Service]\nEnvironment="PRIME_RUNNER_WORKSPACE_ROOT=%s"\n' "$workspace_root" >>"$unit"
sudo install -o root -g root -m 0644 "$unit" /etc/systemd/system/prime-hosting-broker.service
sudo systemctl daemon-reload
sudo systemctl enable prime-hosting-broker.service
sudo systemctl restart prime-hosting-broker.service
for attempt in {1..15}; do
  if sudo test -S "/var/lib/prime-runner/hosting/${USER}/admin.sock"; then
    sudo -u prime-runner python3 /usr/local/lib/prime-runner/hosting_admin.py --owner "$USER" list >/dev/null
    echo "LAN hosting broker installed and responding."
    exit 0
  fi
  sleep 1
done
echo "Hosting broker did not become ready; inspect journalctl -u prime-hosting-broker for address/configuration errors." >&2
exit 1
