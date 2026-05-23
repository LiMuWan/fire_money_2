"""Shared semantic highlighting helpers for notification messages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HighlightedNotificationLine:
    text: str
    tone: str
    label: str


_TONE_RULES: tuple[tuple[str, str, str], ...] = (
    ("buy", "今日动作：买入", "买入"),
    ("sell", "今日动作：卖出", "卖出"),
    ("discipline", "今日动作：空仓", "空仓"),
    ("discipline", "今日动作：防守空仓", "空仓"),
    ("danger", "今日动作：暂停", "暂停"),
    ("danger", "行情异常暂停", "异常"),
    ("danger", "异常原因", "异常"),
    ("danger", "数据异常", "异常"),
    ("buy", "买入", "买入"),
    ("buy", "候选入池", "买点"),
    ("buy", "主线首板候选", "候选"),
    ("sell", "卖出", "卖出"),
    ("sell", "止盈", "止盈"),
    ("sell", "退出", "退出"),
    ("danger", "止损", "止损"),
    ("danger", "风险", "风险"),
    ("danger", "预警", "预警"),
    ("danger", "硬拦截", "拦截"),
    ("profit", "收益", "收益"),
    ("profit", "盈亏", "盈亏"),
    ("profit", "回撤", "回撤"),
    ("profit", "账户", "账户"),
    ("profit", "交易结果", "结果"),
    ("discipline", "纪律", "纪律"),
    ("discipline", "空仓", "空仓"),
    ("discipline", "T+1", "T+1"),
    ("discipline", "主升持有", "主升"),
    ("discipline", "主线持续性", "主线"),
    ("next", "下一步", "下一步"),
    ("next", "复核", "复核"),
    ("next", "取消条件", "取消"),
)


def highlight_notification_lines(message: str) -> tuple[HighlightedNotificationLine, ...]:
    return tuple(
        highlight_notification_line(line)
        for line in message.splitlines()
        if line.strip()
    )


def highlight_notification_line(line: str) -> HighlightedNotificationLine:
    text = line.strip()
    tone, label = _line_tone(text)
    return HighlightedNotificationLine(text=text, tone=tone, label=label)


def feishu_card_template_for_tone(tone: str) -> str:
    return {
        "buy": "green",
        "sell": "wathet",
        "danger": "red",
        "profit": "turquoise",
        "discipline": "orange",
        "next": "blue",
    }.get(tone, "green")


def _line_tone(text: str) -> tuple[str, str]:
    if text.startswith("-"):
        text = text.lstrip("-").strip()
    for tone, keyword, label in _TONE_RULES:
        if keyword in text:
            return tone, label
    if any(value in text for value in ("ready_to_buy", "operate_when_signal_exists")):
        return "buy", "策略"
    if any(value in text for value in ("blocked", "failed", "stand_aside")):
        return "danger", "状态"
    return "neutral", "信息"


__all__ = [
    "HighlightedNotificationLine",
    "feishu_card_template_for_tone",
    "highlight_notification_line",
    "highlight_notification_lines",
]
