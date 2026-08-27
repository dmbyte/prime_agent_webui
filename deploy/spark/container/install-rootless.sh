#!/usr/bin/env bash
set -euo pipefail
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
for command in podman newuidmap newgidmap slirp4netns fuse-overlayfs setfacl rsync curl; do
  command -v "$command" >/dev/null || { echo "Missing rootless prerequisite: $command" >&2; exit 1; }
done
recovery_bundle=$("$repo/deploy/spark/container/create-rootless-backup.sh")
echo "Pre-rootless recovery bundle: $recovery_bundle"
if ! getent group prime-web >/dev/null; then sudo groupadd --system prime-web; fi
if ! id prime-runner >/dev/null 2>&1; then sudo useradd --system --create-home --home-dir /var/lib/prime-runner --shell /usr/sbin/nologin prime-runner; fi
sudo usermod -a -G prime-web "$USER"
sudo usermod -a -G prime-web prime-runner
sudo usermod -g prime-runner prime-runner
grep -q '^prime-runner:' /etc/subuid || echo 'prime-runner:165536:65536' | sudo tee -a /etc/subuid >/dev/null
grep -q '^prime-runner:' /etc/subgid || echo 'prime-runner:165536:65536' | sudo tee -a /etc/subgid >/dev/null
runner_uid=$(id -u prime-runner)
sudo loginctl enable-linger prime-runner
sudo systemctl restart "user@${runner_uid}.service"
sudo install -d -o prime-runner -g prime-runner -m 0700 /var/lib/prime-runner/credentials/global /var/lib/prime-runner/credentials/users /var/lib/prime-runner/users /var/lib/prime-runner/gateway
sudo chown prime-runner:prime-runner /var/lib/prime-runner /var/lib/prime-runner/users
sudo chmod 0700 /var/lib/prime-runner /var/lib/prime-runner/users
sudo setfacl -m "u:${USER}:--x,g:prime-web:--x,m::--x" /var/lib/prime-runner /var/lib/prime-runner/users
sudo install -d -o root -g root -m 0755 /usr/local/lib/prime-runner /usr/local/libexec
sudo install -d -o prime-runner -g prime-runner -m 0700 /var/lib/prime-runner/build
sudo install -o prime-runner -g prime-runner -m 0644 "$repo/deploy/spark/container/Containerfile" /var/lib/prime-runner/build/Containerfile
sudo install -o prime-runner -g prime-runner -m 0755 "$repo/deploy/spark/container/prime-container-entrypoint.sh" /var/lib/prime-runner/build/prime-container-entrypoint.sh
sudo install -o root -g root -m 0644 "$repo/deploy/spark/dashboard/container_runner.py" "$repo/deploy/spark/container/model_gateway.py" /usr/local/lib/prime-runner/
sudo install -o root -g root -m 0755 "$repo/deploy/spark/container/runner_launch.py" /usr/local/libexec/prime-runner-launch
sudo install -o root -g root -m 0755 "$repo/deploy/spark/container/runner_client.py" /usr/local/libexec/prime-runner-client
sudo install -o root -g root -m 0644 "$repo/deploy/spark/container/runner_broker.py" /usr/local/lib/prime-runner/runner_broker.py
sudo install -o root -g root -m 0644 "$repo/deploy/spark/systemd/prime-model-gateway.service" /etc/systemd/system/
broker_unit=$(mktemp)
sed -e "s/@RUNNER_UID@/${runner_uid}/g" -e "s/@WEB_OWNER@/${USER}/g" "$repo/deploy/spark/systemd/prime-runner-broker.service" >"$broker_unit"
sudo install -o root -g root -m 0644 "$broker_unit" /etc/systemd/system/prime-runner-broker.service
rm -f "$broker_unit"
sudo rm -f /etc/sudoers.d/prime-runner
if [[ -f $HOME/.prime/agent/auth.json ]]; then
  sudo install -o prime-runner -g prime-runner -m 0600 "$HOME/.prime/agent/auth.json" /var/lib/prime-runner/credentials/global/auth.json
else
  echo "No global ChatGPT/Codex credential found; local models remain available." >&2
fi
sudo systemctl daemon-reload
sudo systemctl enable prime-model-gateway.service
sudo systemctl restart prime-model-gateway.service
sudo systemctl enable --now prime-runner-broker.service
for profile in general development cad finance network-operations review; do (cd /tmp && sudo -u prime-runner env HOME=/var/lib/prime-runner XDG_RUNTIME_DIR="/run/user/${runner_uid}" podman build --quiet --build-arg PROFILE="$profile" -t "localhost/prime-task-$profile:0.8.0" /var/lib/prime-runner/build); done
manifest=$(mktemp)
printf '{' >"$manifest"
separator=""
for profile in general development cad finance network-operations review; do
  digest=$(cd /tmp && sudo -u prime-runner env HOME=/var/lib/prime-runner XDG_RUNTIME_DIR="/run/user/${runner_uid}" podman image inspect "localhost/prime-task-$profile:0.8.0" --format '{{.Digest}}')
  [[ $digest =~ ^sha256:[a-f0-9]{64}$ ]]
  printf '%s"%s":"localhost/prime-task-%s:0.8.0@%s"' "$separator" "$profile" "$profile" "$digest" >>"$manifest"
  separator=,
done
printf '}\n' >>"$manifest"
sudo install -o prime-runner -g prime-runner -m 0400 "$manifest" /var/lib/prime-runner/image-digests.json
rm -f "$manifest"
sudo -u prime-runner python3 -m json.tool /var/lib/prime-runner/image-digests.json >/dev/null
