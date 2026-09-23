#!/usr/bin/env bash
set -euo pipefail

test "${EUID}" -ne 0 || { echo "Run as the Docker/WebUI owner, not root." >&2; exit 2; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
version=0.0.116
deb_sha256=d39e93477e8a160012fc199ae1d08ddea15a2e76ba700dcf7c485593a9bd6e1b
asset="openshell_${version}-1_arm64.deb"
asset_url="https://github.com/NVIDIA/OpenShell/releases/download/v${version}/${asset}"
staging=$(mktemp -d)
build_context=$(mktemp -d)
trap 'rm -rf "$staging" "$build_context"' EXIT

for command in docker jq setfacl rsync curl; do
  command -v "$command" >/dev/null || { echo "Missing OpenShell prerequisite: $command" >&2; exit 1; }
done
test "$(dpkg --print-architecture)" = arm64 || { echo "This pinned OpenShell package is for ARM64." >&2; exit 1; }
docker_major=$(docker version --format '{{.Server.Version}}' | cut -d. -f1)
test "$docker_major" -ge 28 || { echo "OpenShell requires Docker 28 or newer." >&2; exit 1; }

if ! getent group prime-web >/dev/null; then sudo groupadd --system prime-web; fi
if ! id prime-runner >/dev/null 2>&1; then sudo useradd --system --create-home --home-dir /var/lib/prime-runner --shell /usr/sbin/nologin prime-runner; fi
sudo usermod -a -G prime-web "$USER"
sudo usermod -a -G prime-web prime-runner
sudo usermod -g prime-runner prime-runner
runner_uid=$(id -u prime-runner)
runner_gid=$(id -g prime-runner)
sudo loginctl enable-linger prime-runner
sudo systemctl restart "user@${runner_uid}.service"

sudo install -d -o prime-runner -g prime-runner -m 0700 /var/lib/prime-runner/credentials/global /var/lib/prime-runner/credentials/users /var/lib/prime-runner/users /var/lib/prime-runner/gateway /var/lib/prime-runner/openshell-policies
for mode in restricted internet lan full; do
  sudo install -d -o prime-runner -g prime-runner -m 0700 "/var/lib/prime-runner/gateway/${USER}/${mode}"
done
sudo chown prime-runner:prime-runner /var/lib/prime-runner /var/lib/prime-runner/users
sudo chmod 0700 /var/lib/prime-runner /var/lib/prime-runner/users
sudo setfacl -m "u:${USER}:--x,g:prime-web:--x,m::--x" /var/lib/prime-runner /var/lib/prime-runner/users

workspace_root="${PRIME_RUNNER_WORKSPACE_ROOT:-${HOME}/prime-agent/tasks}"
install -d -m 0770 "${HOME}/prime-agent" "$workspace_root"
setfacl -m "u:prime-runner:rwx,g:prime-web:rwx,m::rwx,d:u:prime-runner:rwx,d:g:prime-web:rwx,d:m::rwx" "${HOME}/prime-agent" "$workspace_root"
owner_agent="/var/lib/prime-runner/users/${USER}/prime/agent"
owner_workspace="${workspace_root}/${USER}"
sudo install -d -o prime-runner -g prime-runner -m 0700 "$owner_agent" "$owner_workspace"
for name in sessions skills session-artifacts; do
  if [[ -d ${HOME}/.prime/agent/$name ]]; then
    sudo rsync -a "${HOME}/.prime/agent/$name/" "$owner_agent/$name/"
  fi
done
if [[ -d /var/lib/prime-runner/users/${USER}/workspace ]]; then
  sudo rsync -a "/var/lib/prime-runner/users/${USER}/workspace/" "$owner_workspace/"
fi
if [[ -d ${HOME}/prime-dgx-agent ]]; then
  sudo rsync -a --exclude uploads "${HOME}/prime-dgx-agent/" "$owner_workspace/"
fi
managed_policy="$repo/deploy/spark/prime/AGENTS.managed.md"
workspace_policy="$owner_workspace/AGENTS.md"
if ! sudo test -e "$workspace_policy"; then
  sudo install -o prime-runner -g prime-runner -m 0640 "$managed_policy" "$workspace_policy"
elif sudo grep -q '^# DGX Spark Prime Agent operating policy$' "$workspace_policy" && ! sudo cmp -s "$managed_policy" "$workspace_policy"; then
  policy_backup="${workspace_policy}.pre-prime-managed-$(date --utc +%Y%m%dT%H%M%SZ)"
  sudo cp -a "$workspace_policy" "$policy_backup"
  sudo install -o prime-runner -g prime-runner -m 0640 "$managed_policy" "$workspace_policy"
fi
sudo chown -R prime-runner:prime-runner "/var/lib/prime-runner/users/${USER}"
sudo chown -R prime-runner:prime-runner "$owner_workspace"
sudo setfacl -Rm "u:${USER}:rwX,g:prime-web:rwX,m::rwX,o::---" "$owner_workspace"
sudo find "$owner_workspace" -type d -exec setfacl -m "d:u:${USER}:rwx,d:g:prime-web:rwx,d:m::rwx,d:o::---" {} +
sudo setfacl -m "u:${USER}:--x,g:prime-web:--x,m::--x" "/var/lib/prime-runner/users/${USER}" "/var/lib/prime-runner/users/${USER}/prime" "$owner_agent"
sudo install -d -o prime-runner -g prime-runner -m 0770 \
  "$owner_agent/sessions" "$owner_agent/trash" "$owner_agent/project-sources" "$owner_agent/skills" \
  "/var/lib/prime-runner/users/${USER}/prime/cache/uv" \
  "/var/lib/prime-runner/users/${USER}/prime/cache/pip" \
  "/var/lib/prime-runner/users/${USER}/prime/cache/npm" \
  "/var/lib/prime-runner/users/${USER}/prime/tools/npm" \
  "/var/lib/prime-runner/users/${USER}/prime/tools/playwright"
sudo setfacl -Rm "u:${USER}:rwx,g:prime-web:rwx,m::rwx,o::---" "$owner_agent/sessions" "$owner_agent/trash" "$owner_agent/project-sources" "$owner_agent/skills"
sudo find "$owner_agent/sessions" "$owner_agent/trash" "$owner_agent/project-sources" "$owner_agent/skills" -type d -exec setfacl -m "d:u:${USER}:rwx,d:g:prime-web:rwx,d:m::rwx,d:o::---" {} +

# Install the reviewed BMC adapters on every OpenShell deployment. The larger
# pinned NVIDIA catalog remains an explicit follow-on download.
"$repo/deploy/spark/prime/install-skills.sh" --bundled-only

sudo install -d -o root -g root -m 0755 /usr/local/lib/prime-runner /usr/local/libexec
sudo install -o root -g root -m 0644 "$repo/deploy/spark/container/task_common.py" "$repo/deploy/spark/container/model_gateway.py" "$repo/deploy/spark/container/openshell_runner.py" /usr/local/lib/prime-runner/
install -m 0644 "$repo/deploy/spark/container/task_common.py" "${HOME}/prime-dgx-dashboard/task_common.py"
sudo install -o root -g root -m 0755 "$repo/deploy/spark/container/runner_launch.py" /usr/local/libexec/prime-runner-launch
sudo install -o root -g root -m 0755 "$repo/deploy/spark/container/runner_client.py" /usr/local/libexec/prime-runner-client
sudo install -o root -g root -m 0644 "$repo/deploy/spark/container/runner_broker.py" /usr/local/lib/prime-runner/runner_broker.py
sudo install -o root -g root -m 0644 "$repo/deploy/spark/systemd/prime-model-gateway.service" /etc/systemd/system/
broker_unit=$(mktemp)
sed -e "s/@RUNNER_UID@/${runner_uid}/g" -e "s/@WEB_OWNER@/${USER}/g" "$repo/deploy/spark/systemd/prime-runner-broker.service" >"$broker_unit"
sudo install -o root -g root -m 0644 "$broker_unit" /etc/systemd/system/prime-runner-broker.service
rm -f "$broker_unit"
if [[ -f $HOME/.prime/agent/auth.json ]]; then
  sudo install -o prime-runner -g prime-runner -m 0600 "$HOME/.prime/agent/auth.json" /var/lib/prime-runner/credentials/global/auth.json
else
  echo "No global ChatGPT/Codex credential found; local models remain available." >&2
fi
stale_unit_backup=""
for stale_unit in prime-model-gateway.service prime-runner-broker.service; do
  stale_path="${HOME}/.config/systemd/user/${stale_unit}"
  if [[ -f "$stale_path" ]]; then
    if [[ -z "$stale_unit_backup" ]]; then
      stale_unit_backup="${HOME}/.prime/agent/recovery/stale-openshell-user-units-$(date --utc +%Y%m%dT%H%M%SZ)"
      install -d -m 0700 "$stale_unit_backup"
    fi
    mv "$stale_path" "$stale_unit_backup/"
  fi
done
systemctl --user daemon-reload
sudo systemctl daemon-reload
sudo systemctl enable prime-model-gateway.service
sudo systemctl restart prime-model-gateway.service
sudo systemctl enable --now prime-runner-broker.service

install -d -m 0755 "${HOME}/.config/systemd/user/prime-dashboard-api.service.d"
install -m 0644 /dev/stdin "${HOME}/.config/systemd/user/prime-dashboard-api.service.d/openshell.conf" <<EOF
[Service]
Environment=PRIME_TASK_RUNTIME=openshell
Environment=PRIME_OPENSHELL_VERSION=${version}
Environment=PRIME_RUNNER_STORAGE=/var/lib/prime-runner/users
Environment=PRIME_RUNNER_WORKSPACE_ROOT=${workspace_root}
ReadWritePaths=/var/lib/prime-runner/users ${HOME}/prime-agent
EOF

installed_openshell=$(openshell --version 2>/dev/null | awk 'NR == 1 {print $2}' || true)
if [[ "$installed_openshell" != "$version" ]]; then
  curl -fL "$asset_url" -o "$staging/$asset"
  echo "$deb_sha256  $staging/$asset" | sha256sum --check --strict
  sudo apt-get install -y "$staging/$asset"
fi

install -d -m 0700 "$HOME/.config/openshell" "$HOME/.config/systemd/user/openshell-gateway.service.d"
install -m 0600 "$repo/deploy/spark/openshell/gateway.toml" "$HOME/.config/openshell/gateway.toml"
install -m 0600 /dev/stdin "$HOME/.config/systemd/user/openshell-gateway.service.d/10-spark.conf" <<'EOF'
[Service]
Environment=OPENSHELL_GATEWAY_CONFIG=%h/.config/openshell/gateway.toml
Environment=OPENSHELL_TELEMETRY_ENABLED=false
EOF
systemctl --user daemon-reload
systemctl --user enable --now openshell-gateway.service

if ! openshell gateway list | grep -q 'spark-local'; then
  openshell gateway add https://127.0.0.1:17670 --local --name spark-local
fi
openshell --gateway spark-local status
openshell --gateway spark-local settings set --global --key agent_policy_proposals_enabled --value true --yes

cp -a "$repo/deploy/spark/container/." "$build_context/"
install -d -m 0755 "$build_context/managed-skills"
for skill in bmc-headless-browser ipmi-redfish-bmc prime-nvidia-catalog; do
  cp -a "$repo/deploy/spark/prime/skills/$skill" "$build_context/managed-skills/"
done
# Test and import runs may leave generated bytecode in the checkout. It is not
# source and would otherwise make the supposedly reproducible image ID depend on
# which commands ran before installation.
find "$build_context" -depth \( -type d -name __pycache__ -o -type f \( -name '*.pyc' -o -name '*.pyo' \) \) -delete
find "$build_context" -exec touch -h -d '@0' {} +
find "$build_context" -type d -exec chmod 0755 {} +
find "$build_context" -type f -exec chmod 0644 {} +
chmod 0755 "$build_context/prime-container-entrypoint.sh"
for profile in general development cad finance network-operations review; do
  expected_image=$(jq -r --arg profile "$profile" '.[$profile].image' "$repo/deploy/spark/openshell/image-digests.json")
  expected_id=$(jq -r --arg profile "$profile" '.[$profile].imageId' "$repo/deploy/spark/openshell/image-digests.json")
  build_image="local/prime-openshell-${profile}:0.9.5-build"
  docker build --file "$build_context/Containerfile" \
    --build-arg "PROFILE=$profile" --build-arg "PRIME_UID=$runner_uid" \
    --build-arg "PRIME_GID=$runner_gid" -t "$build_image" "$build_context"
  actual_id=$(docker image inspect "$build_image" --format '{{.Id}}')
  test "$actual_id" = "$expected_id" || {
    echo "OpenShell image review required for $profile: expected $expected_id, built $actual_id" >&2
    exit 1
  }
  docker tag "$build_image" "$expected_image"
done

sudo install -d -o prime-runner -g prime-runner -m 0700 /var/lib/prime-runner/.config/openshell
sudo cp -a "$HOME/.config/openshell/." /var/lib/prime-runner/.config/openshell/
sudo chown -R prime-runner:prime-runner /var/lib/prime-runner/.config/openshell
sudo find /var/lib/prime-runner/.config/openshell -type d -exec chmod 0700 {} +
sudo find /var/lib/prime-runner/.config/openshell -type f -exec chmod 0600 {} +

"$repo/deploy/spark/openshell/provision-volumes.sh"
sudo install -o prime-runner -g prime-runner -m 0400 "$repo/deploy/spark/openshell/image-digests.json" /var/lib/prime-runner/openshell-image-digests.json
sudo -u prime-runner env HOME=/var/lib/prime-runner openshell --gateway spark-local status
