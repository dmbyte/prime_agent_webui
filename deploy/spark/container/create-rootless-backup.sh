#!/usr/bin/env bash
set -euo pipefail
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }

stamp=$(date +%Y%m%dT%H%M%S%z)
bundle="/var/backups/prime-rootless-preinstall-${stamp}"
sudo install -d -o root -g root -m 0700 "$bundle"
sudo install -o root -g root -m 0600 /dev/null "$bundle/warnings.txt"

paths=()
for path in \
  "$HOME/.config/systemd/user" \
  "$HOME/.config/prime-agent" \
  "$HOME/.prime/agent" \
  "$HOME/prime-dgx-dashboard" \
  "$HOME/prime-dgx-agent" \
  /etc/nginx /var/www/prime-agent; do
  if sudo test -e "$path"; then
    paths+=("${path#/}")
  else
    echo "Absent before migration: $path" | sudo tee -a "$bundle/warnings.txt" >/dev/null
  fi
done
sudo tar -C / -czf "$bundle/state.tgz" "${paths[@]}"
systemctl --user list-unit-files | sudo tee "$bundle/user-units.txt" >/dev/null
sudo ss -lntup | sudo tee "$bundle/listeners.txt" >/dev/null
sudo sh -c "nft list ruleset > \"$bundle/nft.txt\" 2>&1 || true"
if command -v podman >/dev/null; then
  podman images --digests --no-trunc | sudo tee "$bundle/podman-images.txt" >/dev/null
else
  echo "Podman was not installed." | sudo tee "$bundle/podman-images.txt" >/dev/null
fi
sudo sh -c "cd \"$bundle\" && sha256sum state.tgz warnings.txt user-units.txt listeners.txt nft.txt podman-images.txt > SHA256SUMS"
sudo find "$bundle" -maxdepth 1 -type f -exec chmod 0600 {} +
echo "$bundle"
