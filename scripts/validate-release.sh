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
)
for path in "${required[@]}"; do
  [[ -f $path ]] || { echo "Missing release file: $path" >&2; exit 1; }
done

bash -n install.sh deploy/spark/update/update-prime-agent.sh deploy/spark/update/update-webui.sh
python3 -m compileall -q deploy/spark/dashboard
python3 -m unittest discover -s deploy/spark/dashboard -p 'test*.py'

if command -v node >/dev/null; then
  node --check deploy/spark/dashboard/app-v2.js
else
  echo "Note: Node.js unavailable; JavaScript syntax check skipped." >&2
fi

grep -Fq 'docs/prime-webui-sample.jpg' README.md
grep -Fq 'v0.2.0' README.md
echo "Release validation passed."
