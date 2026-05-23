#!/usr/bin/env bash
set -euo pipefail

PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
URL="${FIREMONEY_HEALTH_URL:-http://127.0.0.1:${PORT}/core_workflow.html}"

echo "== systemd =="
systemctl --no-pager --plain status firemoney-preview.service || true
systemctl --no-pager --plain status firemoney-beta-watch.service || true

echo "== listeners =="
ss -ltnp "sport = :$PORT" || true

echo "== http =="
curl -fsS "$URL" >/tmp/firemoney_preview_health.html
grep -q "FireMoney" /tmp/firemoney_preview_health.html
echo "preview_http_ok $URL"

echo "== schedule health =="
"${FIREMONEY_PYTHON:-/opt/firemoney/.venv/bin/python}" -B -m \
  client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
