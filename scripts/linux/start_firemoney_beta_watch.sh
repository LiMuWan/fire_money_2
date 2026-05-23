#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
PYTHON="${FIREMONEY_PYTHON:-$APP_DIR/.venv/bin/python}"
INTERVAL_SECONDS="${FIREMONEY_BETA_INTERVAL_SECONDS:-60}"
MARKET_DATA_TIMEOUT_SECONDS="${FIREMONEY_MARKET_DATA_TIMEOUT_SECONDS:-20}"
ALLOW_MARKET_DATA_TIMEOUT="${FIREMONEY_ALLOW_MARKET_DATA_TIMEOUT:-true}"
LOG_DIR="${FIREMONEY_LOG_DIR:-$APP_DIR/.firemoney/logs}"
LOCK_FILE="/tmp/firemoney-beta-watch.lock"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

ARGS=(
  -B
  -m client.desktop.firemoney_client.one_to_two_cli
  beta-start
  --loop
  --interval-seconds "$INTERVAL_SECONDS"
  --market-data-timeout-seconds "$MARKET_DATA_TIMEOUT_SECONDS"
)

if [[ "$ALLOW_MARKET_DATA_TIMEOUT" == "true" || "$ALLOW_MARKET_DATA_TIMEOUT" == "1" ]]; then
  ARGS+=(--allow-market-data-timeout)
fi

exec flock -n "$LOCK_FILE" "$PYTHON" "${ARGS[@]}" \
  >>"$LOG_DIR/firemoney_beta_watch.log" 2>&1
