#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${FIREMONEY_APP_DIR:-/opt/firemoney}"
PYTHON="${FIREMONEY_PYTHON:-$APP_DIR/.venv/bin/python}"
PORT="${FIREMONEY_PREVIEW_PORT:-8765}"
LOG_DIR="${FIREMONEY_LOG_DIR:-$APP_DIR/.firemoney/logs}"
PREVIEW_DIR="$APP_DIR/client/desktop/preview"
PREVIEW_HTML="$PREVIEW_DIR/core_workflow.html"
RUNTIME_STATUS="$PREVIEW_DIR/runtime_status.json"
LOCK_FILE="/tmp/firemoney-preview-refresh.lock"

mkdir -p "$LOG_DIR" "$PREVIEW_DIR"
cd "$APP_DIR"

preview_ok=true
if ! flock -n "$LOCK_FILE" bash -c '
  set -euo pipefail
  "$0" -B -m client.desktop.firemoney_client.preview
' "$PYTHON" >>"$LOG_DIR/firemoney_preview_refresh.log" 2>&1; then
  preview_ok=false
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] preview_refresh_failed" >>"$LOG_DIR/firemoney_preview_refresh.log"
  cat >"$PREVIEW_HTML" <<HTML
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FireMoney 预览生成失败</title>
  <style>
    body { margin: 0; font-family: sans-serif; background: #f7f4ed; color: #142019; }
    main { max-width: 920px; margin: 10vh auto; padding: 32px; border: 1px solid #d7b6a4; border-radius: 24px; background: #fffaf2; }
    h1 { margin: 0 0 12px; font-size: 32px; }
    p { font-size: 18px; line-height: 1.7; }
    code { padding: 2px 6px; border-radius: 8px; background: #eee6d8; }
  </style>
</head>
<body>
  <main>
    <h1>FireMoney 预览生成失败，今日禁止参考旧指挥单</h1>
    <p>刷新时间：$(date '+%Y-%m-%d %H:%M:%S')</p>
    <p>系统已用安全页覆盖旧页面，避免把过期买点当成今天的交易依据。请检查 <code>$LOG_DIR/firemoney_preview_refresh.log</code> 后再恢复交易页面。</p>
  </main>
</body>
</html>
HTML
fi

schedule_raw=""
schedule_ok=false
if schedule_raw="$("$PYTHON" -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief 2>&1)"; then
  schedule_ok=true
fi

paper_raw=""
if paper_raw="$("$PYTHON" -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief 2>&1)"; then
  :
fi

beta_state="$(systemctl is-active firemoney-beta-watch.service 2>/dev/null || true)"
preview_state="$(systemctl is-active firemoney-preview.service 2>/dev/null || true)"
http_ok=false
if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/core_workflow.html" >/dev/null 2>&1; then
  http_ok=true
fi

"$PYTHON" -B - "$RUNTIME_STATUS" "$preview_state" "$beta_state" "$http_ok" "$schedule_ok" "$preview_ok" "$schedule_raw" "$paper_raw" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

target = Path(sys.argv[1])
preview_state = sys.argv[2]
beta_state = sys.argv[3]
http_ok = sys.argv[4].lower() == "true"
schedule_ok = sys.argv[5].lower() == "true"
preview_ok = sys.argv[6].lower() == "true"
schedule_raw = sys.argv[7]
paper_raw = sys.argv[8]

if "诊断：blocked" in schedule_raw or "diagnosis: blocked" in schedule_raw.lower():
    schedule_status = "blocked"
elif "诊断：warning" in schedule_raw or "diagnosis: warning" in schedule_raw.lower():
    schedule_status = "warning"
elif "诊断：ready" in schedule_raw or "diagnosis: ready" in schedule_raw.lower():
    schedule_status = "ready"
else:
    schedule_status = "ready" if schedule_ok else "blocked"

status = (
    "ready"
    if preview_state == "active"
    and http_ok
    and preview_ok
    and schedule_status != "blocked"
    else "blocked"
)
findings = [
    f"preview_service={preview_state}",
    f"beta_watch_service={beta_state}",
    "preview_http_200" if http_ok else "preview_http_failed",
    "preview_refresh_ok" if preview_ok else "preview_refresh_failed",
    f"schedule_health={schedule_status}",
]
if not schedule_ok:
    findings.append("schedule_health_failed")
if schedule_status == "blocked":
    findings.append("schedule_health_blocked")

payload = {
    "status": status,
    "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "url": "http://127.0.0.1:8765/core_workflow.html",
    "findings": findings,
    "actions": ["auto_refreshed_preview"],
    "beta_watch": beta_state,
    "schedule_health_ok": schedule_ok,
    "preview_refresh_ok": preview_ok,
    "schedule_health_status": schedule_status,
    "schedule_health": None,
    "schedule_health_raw": schedule_raw,
    "paper_db": {
        "status": "ready" if paper_raw else "unknown",
        "tone": "warning" if "未达标" in paper_raw or "小仓" in paper_raw else "neutral",
        "headline": "已刷新真实账本摘要" if paper_raw else "暂无真实账本摘要",
        "action": "以 paper-db --brief 为准复核收益质量。",
        "raw": paper_raw[:2000],
    },
}
target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
