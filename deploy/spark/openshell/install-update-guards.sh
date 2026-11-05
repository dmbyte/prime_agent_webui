#!/usr/bin/env bash
# One-time migration for an existing Prime/OpenShell deployment, not a fresh install.
set -euo pipefail
[[ ${1:-} == --activate-while-idle && $EUID -ne 0 ]] || {
  echo 'Run as the WebUI owner with --activate-while-idle; briefly pauses web access.' >&2; exit 2;
}
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
idle() {
  python3 - <<'PY'
import json, os, pathlib, subprocess, urllib.request
home=pathlib.Path.home()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8765/api/health',timeout=15) as response: state=json.load(response)
if state.get('ok') is not True or type(state.get('activeTasks')) is not int or state['activeTasks'] != 0:
    raise SystemExit('Cannot verify idle tasks; do not activate maintenance guards. Upgrade the API first.')
result=subprocess.run(['openshell','--gateway','spark-local','sandbox','list','--all-workspaces','--ids'],capture_output=True,text=True,check=True)
if result.stdout.strip(): raise SystemExit('Sandboxes exist; do not activate maintenance guards.')
print('All users idle; no OpenShell sandboxes.')
PY
}
idle
backup=$(mktemp -d "${HOME}/.prime/agent/maintenance-guard-backup.XXXXXX")
sudo -n cp -a "${HOME}/prime-dgx-dashboard" "$backup/dashboard"
cp -a "${HOME}/prime-update" "$backup/updaters"
sudo -n cp -a /usr/local/lib/prime-runner "$backup/runner"
sudo -n cp -a /usr/local/libexec/prime-runner-launch "$backup/runner-launch"
systemctl is-active --quiet nginx || { echo 'Nginx is not active; inspect deployment before migration.' >&2; exit 1; }
trap 'sudo -n systemctl start nginx' EXIT
sudo -n systemctl stop nginx
idle
if ! sudo -n test -e /var/lib/prime-runner/openshell-maintenance.lock; then
  sudo -n install -o root -g root -m 0644 /dev/null /var/lib/prime-runner/openshell-maintenance.lock
fi
exec 8</var/lib/prime-runner/openshell-maintenance.lock
flock -n -x 8
for file in api_v2.py runtime_maintenance.py connection_native.py connection_browser.py; do
  install -m 0644 "$repo/deploy/spark/dashboard/$file" "${HOME}/prime-dgx-dashboard/$file"
done
sudo -n install -o root -g root -m 0644 "$repo/deploy/spark/dashboard/runtime_maintenance.py" /usr/local/lib/prime-runner/
for file in hosting_broker.py kvm_broker.py; do
  sudo -n install -o root -g root -m 0644 "$repo/deploy/spark/container/$file" /usr/local/lib/prime-runner/
done
sudo -n install -o root -g root -m 0755 "$repo/deploy/spark/container/runner_launch.py" /usr/local/libexec/prime-runner-launch
systemctl --user restart prime-dashboard-api
if systemctl --user is-active --quiet prime-connection-broker; then systemctl --user restart prime-connection-broker; fi
for service in prime-kvm-broker prime-hosting-broker; do
  if systemctl is-active --quiet "$service"; then sudo -n systemctl restart "$service"; fi
done
systemctl --user is-active --quiet prime-dashboard-api
install -m 0644 "$repo/deploy/spark/openshell/release.json" "${HOME}/prime-update/openshell-release.json"
install -m 0755 "$repo/deploy/spark/update/update-openshell.sh" "$repo/deploy/spark/update/verify-openshell.py" "${HOME}/prime-update/"
echo "Maintenance guards installed; protected backup: $backup"
