#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
PYTHON="${FIREMONEY_PYTHON:-$APP_DIR/.venv/bin/python}"
BIND="${FIREMONEY_PREVIEW_BIND:-0.0.0.0}"
PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
LOG_DIR="${FIREMONEY_LOG_DIR:-$APP_DIR/.firemoney/logs}"
LOCK_FILE="/tmp/firemoney-preview-${PORT}.lock"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec flock -n "$LOCK_FILE" bash -c '
  set -euo pipefail
  "$0" -B -m client.desktop.firemoney_client.preview
  exec "$0" -B scripts/linux/firemoney_preview_server.py \
    --bind "$1" \
    --port "$2" \
    --directory client/desktop/preview
' "$PYTHON" "$BIND" "$PORT" >>"$LOG_DIR/firemoney_preview.log" 2>&1
