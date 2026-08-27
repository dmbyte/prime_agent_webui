#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

required=(
  README.md
  install.sh
  docs/prime-webui-sample.jpg
  deploy/spark/dashboard/api.py
  deploy/spark/dashboard/api_v2.py
  deploy/spark/dashboard/app-v2.js
  deploy/spark/dashboard/auth.py
  deploy/spark/dashboard/index.html
  deploy/spark/nginx/prime-agent.conf
  deploy/spark/nginx/prime-security.conf
  deploy/spark/update/update-prime-agent.sh
  deploy/spark/update/update-webui.sh
  deploy/spark/container/Containerfile
  deploy/spark/container/install-rootless.sh
  deploy/spark/container/activate-rootless.sh
  deploy/spark/container/create-rootless-backup.sh
  deploy/spark/container/rollback-rootless.sh
  deploy/spark/container/install-user-codex-credential.sh
  deploy/spark/container/model_gateway.py
  deploy/spark/container/runner_broker.py
  deploy/spark/container/runner_client.py
  deploy/spark/container/runner_launch.py
  deploy/spark/systemd/prime-model-gateway.service
  deploy/spark/systemd/prime-runner-broker.service
  docs/releases/v0.3.1.md
)
for path in "${required[@]}"; do
  [[ -f $path ]] || { echo "Missing release file: $path" >&2; exit 1; }
done

bash -n install.sh deploy/spark/update/update-prime-agent.sh deploy/spark/update/update-webui.sh \
  deploy/spark/container/install-rootless.sh deploy/spark/container/activate-rootless.sh \
  deploy/spark/container/create-rootless-backup.sh deploy/spark/container/rollback-rootless.sh \
  deploy/spark/container/install-user-codex-credential.sh \
  deploy/spark/container/prime-container-entrypoint.sh
python3 -m compileall -q deploy/spark/dashboard
python3 -m unittest discover -s deploy/spark/dashboard -p 'test*.py'

if command -v node >/dev/null; then
  node --check deploy/spark/dashboard/app-v2.js
else
  echo "Note: Node.js unavailable; JavaScript syntax check skipped." >&2
fi

grep -Fq 'docs/prime-webui-sample.jpg' README.md
grep -Fq 'v0.3.1' README.md
grep -Fq 'does **not** authenticate with PAM' README.md
grep -Fq 'prime-web-password' README.md
echo "Release validation passed."
