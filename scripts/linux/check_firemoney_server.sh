#!/usr/bin/env bash
set -euo pipefail

PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
URL="${FIREMONEY_HEALTH_URL:-http://127.0.0.1:${PORT}/core_workflow.html}"
WAIT_SECONDS="${FIREMONEY_HEALTH_WAIT_SECONDS:-30}"

echo "== systemd =="
systemctl --no-pager --plain status firemoney-preview.service || true
systemctl --no-pager --plain status firemoney-beta-watch.service || true

echo "== listeners =="
ss -ltnp "sport = :$PORT" || true

echo "== http =="
ready=0
for _ in $(seq 1 "$WAIT_SECONDS"); do
  if curl -fsS --max-time 5 "$URL" >/tmp/firemoney_preview_health.html; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  echo "preview_http_timeout waited=${WAIT_SECONDS}s url=$URL" >&2
  exit 1
fi

grep -q "FireMoney" /tmp/firemoney_preview_health.html
echo "preview_http_ok $URL"

echo "== schedule health =="
"${FIREMONEY_PYTHON:-/opt/firemoney/.venv/bin/python}" -B -m \
  client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
