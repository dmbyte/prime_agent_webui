#!/usr/bin/env bash
set -euo pipefail
test "${EUID}" -ne 0 || { echo "Run as the WebUI owner, not root." >&2; exit 2; }
user=${1:-}
source_file=${2:-}
[[ $user =~ ^[A-Za-z0-9_.-]{2,32}$ ]] || { echo "Invalid WebUI user." >&2; exit 2; }
target="/var/lib/prime-runner/credentials/users/${user}"
if [[ $source_file == --remove ]]; then
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    recovery="/var/backups/prime-user-credential-${user}-${stamp}"
    sudo test -f "$target/auth.json" || { echo "No personal credential is configured for $user." >&2; exit 1; }
    sudo install -d -o root -g root -m 0700 "$recovery"
    sudo mv "$target/auth.json" "$recovery/auth.json"
    sudo chown root:root "$recovery/auth.json"; sudo chmod 0600 "$recovery/auth.json"
    echo "Personal credential removed recoverably for $user; global fallback is active."
    exit 0
fi
[[ -f $source_file && ! -L $source_file ]] || { echo "Credential source must be a regular non-symlink file." >&2; exit 2; }
[[ $(stat -c '%u %a' "$source_file") == "${EUID} 600" ]] || { echo "Credential source must be owned by you and mode 0600." >&2; exit 2; }
python3 - "$source_file" <<'PY'
import json, sys
row = json.load(open(sys.argv[1])).get("openai-codex") or {}
if not all(row.get(key) for key in ("access", "refresh", "accountId", "expires")):
    raise SystemExit("Credential source lacks a complete openai-codex record.")
PY
sudo install -d -o prime-runner -g prime-runner -m 0700 "$target"
sudo install -o prime-runner -g prime-runner -m 0600 "$source_file" "$target/auth.json"
echo "Personal Codex credential installed for $user. The gateway will use it immediately."
