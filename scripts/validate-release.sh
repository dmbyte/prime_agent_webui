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
  deploy/spark/dashboard/skill-governance.css
  deploy/spark/nginx/prime-agent.conf
  deploy/spark/nginx/prime-security.conf
  deploy/spark/update/update-prime-agent.sh
  deploy/spark/update/update-webui.sh
  deploy/spark/update/update-openshell.sh
  deploy/spark/container/Containerfile
  deploy/spark/container/install-user-codex-credential.sh
  deploy/spark/container/task_common.py
  deploy/spark/container/model_gateway.py
  deploy/spark/container/openshell_runner.py
  deploy/spark/container/runner_broker.py
  deploy/spark/container/runner_client.py
  deploy/spark/container/runner_launch.py
  deploy/spark/systemd/prime-model-gateway.service
  deploy/spark/systemd/prime-runner-broker.service
  deploy/spark/openshell/gateway.toml
  deploy/spark/openshell/image-digests.json
  deploy/spark/openshell/install.sh
  deploy/spark/openshell/provision-volumes.sh
  deploy/spark/openshell/README.md
  deploy/spark/prime/install-skills.sh
  deploy/spark/prime/install-managed-skills.py
  deploy/spark/prime/test_managed_skills.py
  deploy/spark/prime/skills/bmc-headless-browser/SKILL.md
  deploy/spark/prime/skills/bmc-headless-browser/pyproject.toml
  deploy/spark/prime/skills/ipmi-redfish-bmc/SKILL.md
  deploy/spark/prime/skills/ipmi-redfish-bmc/pyproject.toml
  deploy/spark/prime/skills/prime-nvidia-catalog/SKILL.md
  deploy/spark/prime/skills/prime-nvidia-catalog/pyproject.toml
  deploy/spark/prime/AGENTS.managed.md
  deploy/spark/vllm-nemotron35/README.md
  deploy/spark/llama-qwen38/README.md
  deploy/spark/llama-qwen38/build-image.sh
  deploy/spark/llama-qwen38/llama.env.template
  deploy/spark/llama-qwen38/start.sh
  deploy/spark/systemd/llama-qwen38.service
  docs/releases/v0.5.38.md
)
for path in "${required[@]}"; do
  [[ -f $path ]] || { echo "Missing release file: $path" >&2; exit 1; }
done

bash -n install.sh deploy/spark/update/update-prime-agent.sh deploy/spark/update/update-webui.sh deploy/spark/update/update-openshell.sh \
  deploy/spark/container/install-user-codex-credential.sh \
  deploy/spark/prime/install-skills.sh \
  deploy/spark/openshell/install.sh deploy/spark/openshell/provision-volumes.sh \
  deploy/spark/container/prime-container-entrypoint.sh
python3 -m compileall -q deploy/spark/dashboard
python3 -m unittest discover -s deploy/spark/dashboard -p 'test*.py'
python3 -m unittest deploy/spark/prime/test_managed_skills.py

if command -v node >/dev/null; then
  node --check deploy/spark/dashboard/app-v2.js
else
  echo "Note: Node.js unavailable; JavaScript syntax check skipped." >&2
fi

grep -Fq 'docs/prime-webui-sample.jpg' README.md
grep -Fq 'v0.5.38' README.md
grep -Fq 'does **not** authenticate with PAM' README.md
grep -Fq 'prime-web-password' README.md
echo "Release validation passed."
