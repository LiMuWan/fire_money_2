#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
ENV_FILE="${FIREMONEY_ENV_FILE:-/etc/firemoney/firemoney.env}"
SERVICE_USER="${FIREMONEY_SERVICE_USER:-ubuntu}"

PRESERVED_ENV=(
  FIREMONEY_APP_DIR
  FIREMONEY_PYTHON
  FIREMONEY_PREVIEW_BIND
  FIREMONEY_PREVIEW_PORT
  FIREMONEY_BETA_INTERVAL_SECONDS
  FIREMONEY_MARKET_DATA_TIMEOUT_SECONDS
  FIREMONEY_ALLOW_MARKET_DATA_TIMEOUT
  FEISHU_ENABLED
  FEISHU_WEBHOOK_URL
  FEISHU_WEBHOOK_SECRET
  FEISHU_APP_ID
  FEISHU_APP_SECRET
  FEISHU_RECEIVE_ID
  FEISHU_RECEIVE_ID_TYPE
  FEISHU_OPEN_CHAT_ID
  FEISHU_API_BASE_URL
)

if [[ -r "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

APP_DIR="${FIREMONEY_APP_DIR:-$APP_DIR}"
PYTHON="${FIREMONEY_PYTHON:-$APP_DIR/.venv/bin/python}"

cd "$APP_DIR"

if [[ "$(id -u)" -eq 0 && -n "$SERVICE_USER" && "$SERVICE_USER" != "root" ]]; then
  IFS=,
  exec sudo --preserve-env="${PRESERVED_ENV[*]}" -u "$SERVICE_USER" \
    "$PYTHON" -B -m client.desktop.firemoney_client.one_to_two_cli "$@"
fi

exec "$PYTHON" -B -m client.desktop.firemoney_client.one_to_two_cli "$@"
