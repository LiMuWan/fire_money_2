#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
URL="${FIREMONEY_HEALTH_URL:-http://127.0.0.1:${PORT}/core_workflow.html}"
WAIT_SECONDS="${FIREMONEY_HEALTH_WAIT_SECONDS:-30}"

cd "$APP_DIR"

echo "== systemd =="
PREVIEW_STATE="$(systemctl is-active firemoney-preview.service || true)"
BETA_STATE="$(systemctl is-active firemoney-beta-watch.service || true)"
echo "firemoney-preview.service: $PREVIEW_STATE"
echo "firemoney-beta-watch.service: $BETA_STATE"
if [[ "$PREVIEW_STATE" != "active" ]]; then
  systemctl --no-pager --plain status firemoney-preview.service || true
fi

echo "== listeners =="
ss -ltnp "sport = :$PORT" || true

echo "== http =="
ready=0
for _ in $(seq 1 "$WAIT_SECONDS"); do
  if curl -fsS --max-time 5 "$URL" >/tmp/firemoney_preview_health.html 2>/dev/null; then
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
