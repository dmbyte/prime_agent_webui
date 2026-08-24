#!/usr/bin/env bash
set -euo pipefail

fail=0
for endpoint in 30000 30001; do
  if ! curl --fail --silent --max-time 10 "http://127.0.0.1:${endpoint}/v1/models" >/dev/null; then
    echo "FAIL: model endpoint ${endpoint}" >&2
    fail=1
  fi
done

if ! curl --fail --silent --max-time 10 http://127.0.0.1:7681/terminal/ >/dev/null; then
  echo "FAIL: private Prime browser interface" >&2
  fail=1
fi

auth_status="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' --max-time 10 https://127.0.0.1:8443/)"
if [[ "${auth_status}" != "401" ]]; then
  echo "FAIL: authenticated HTTPS endpoint returned ${auth_status}, expected 401 without credentials" >&2
  fail=1
fi

lan_auth_status="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' --max-time 10 https://172.16.253.231:8443/)"
if [[ "${lan_auth_status}" != "401" ]]; then
  echo "FAIL: LAN PAM endpoint returned ${lan_auth_status}, expected 401 without credentials" >&2
  fail=1
fi

if ss -ltn | awk '$4 ~ /(^|:)(3000[01]|7681)$/ && $4 !~ /^127\.0\.0\.1:/ {exit 1}'; then
  :
else
  echo "FAIL: a model endpoint is not loopback-only" >&2
  fail=1
fi

available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
if (( available_kib < 20 * 1024 * 1024 )); then
  echo "FAIL: less than 20 GiB memory available" >&2
  fail=1
fi

if (( fail != 0 )); then exit 1; fi
echo "PASS: both local models healthy, private, and memory headroom >= 20 GiB"
