"""Shared presentation helpers for notification records."""

from __future__ import annotations

from typing import Any


def notification_display_title(record: Any) -> str:
    """Normalize action notification titles across CLI and HTML preview."""

    title = getattr(record, "title", "")
    workflow = getattr(record, "workflow", "")
    message = getattr(record, "message", "")
    if workflow == "watch:open" and not title.startswith("FireMoney 模拟买入"):
        symbol_line = next(
            (
                line.strip()
                for line in message.splitlines()
                if line.strip().startswith(("模拟买入：", "持仓："))
            ),
            "",
        )
        suffix = symbol_name_from_notification_line(symbol_line)
        return f"FireMoney 模拟买入：{suffix}" if suffix else "FireMoney 模拟买入"
    if workflow == "watch:risk" and not title.startswith("FireMoney 模拟卖出"):
        symbol_line = next(
            (
                line.strip()
                for line in message.splitlines()
                if line.strip().startswith(("模拟卖出：", "完成样本："))
            ),
            "",
        )
        suffix = symbol_name_from_notification_line(symbol_line)
        return f"FireMoney 模拟卖出：{suffix}" if suffix else "FireMoney 模拟卖出"
    return title


def first_notification_detail(message: str) -> str:
    for line in message.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith(("交易日：", "阶段：", "最新事件：")):
            continue
        return text
    return ""


def symbol_name_from_notification_line(line: str) -> str:
    if not line:
        return ""
    text = line.split("：", 1)[-1].strip()
    if "）" in text:
        return text.split("）", 1)[0] + "）"
    if ")" in text:
        return text.split(")", 1)[0] + ")"
    return text.split(" 股", 1)[0]


__all__ = [
    "first_notification_detail",
    "notification_display_title",
    "symbol_name_from_notification_line",
]
