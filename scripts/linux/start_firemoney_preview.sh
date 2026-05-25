#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
PYTHON="${FIREMONEY_PYTHON:-$APP_DIR/.venv/bin/python}"
BIND="${FIREMONEY_PREVIEW_BIND:-0.0.0.0}"
PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
LOG_DIR="${FIREMONEY_LOG_DIR:-$APP_DIR/.firemoney/logs}"
LOCK_FILE="/tmp/firemoney-preview-${PORT}.lock"
REFRESH_INTERVAL_SECONDS="${FIREMONEY_PREVIEW_REFRESH_INTERVAL_SECONDS:-60}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec flock -n "$LOCK_FILE" bash -c '
  set -euo pipefail
  APP_DIR="$0"
  BIND="$1"
  PORT="$2"
  INTERVAL_SECONDS="$3"
  LOG_PATH="$4"
  PYTHON="$5"
  (
    while true; do
      "$APP_DIR/scripts/linux/refresh_firemoney_preview.sh" || true
      sleep "$INTERVAL_SECONDS"
    done
  ) >>"$LOG_PATH" 2>&1 &
  exec "$PYTHON" -B scripts/linux/firemoney_preview_server.py \
    --bind "$BIND" \
    --port "$PORT" \
    --directory client/desktop/preview
' "$APP_DIR" "$BIND" "$PORT" "$REFRESH_INTERVAL_SECONDS" "$LOG_DIR/firemoney_preview.log" "$PYTHON" >>"$LOG_DIR/firemoney_preview.log" 2>&1
