#!/usr/bin/env bash
set -euo pipefail

SOURCE_FILE="${1:-}"
ENV_FILE="${FIREMONEY_ENV_FILE:-/etc/firemoney/firemoney.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run with sudo: sudo bash scripts/linux/import_firemoney_env.sh <env-file>" >&2
  exit 1
fi

if [[ -z "$SOURCE_FILE" || ! -f "$SOURCE_FILE" ]]; then
  echo "source env file not found: ${SOURCE_FILE:-<empty>}" >&2
  exit 1
fi

install -d -m 0755 "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 0600 "$ENV_FILE"
chown root:root "$ENV_FILE"

python3 - "$SOURCE_FILE" "$ENV_FILE" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
allowed_keys = {
    "FEISHU_ENABLED",
    "FEISHU_WEBHOOK_URL",
    "FEISHU_WEBHOOK_SECRET",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_RECEIVE_ID",
    "FEISHU_RECEIVE_ID_TYPE",
    "FEISHU_OPEN_CHAT_ID",
    "FEISHU_API_BASE_URL",
}

updates: dict[str, str] = {}
for line in source.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    key = key.strip()
    if key in allowed_keys:
        updates[key] = value.strip()

if not updates:
    raise SystemExit("no supported FEISHU_* keys found")

existing = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
output: list[str] = []
seen: set[str] = set()
for line in existing:
    stripped = line.strip()
    raw_key = stripped.split("=", 1)[0].strip().lstrip("#").strip() if "=" in stripped else ""
    if raw_key in updates:
        output.append(f"{raw_key}={updates[raw_key]}")
        seen.add(raw_key)
    else:
        output.append(line)

for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")

target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
print("updated_keys=" + ",".join(sorted(updates)))
PY

chmod 0600 "$ENV_FILE"
chown root:root "$ENV_FILE"
