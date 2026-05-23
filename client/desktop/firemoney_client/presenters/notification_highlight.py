"""Client re-export for shared notification highlighting helpers."""

from __future__ import annotations

from shared.notification_highlight import (
    HighlightedNotificationLine,
    feishu_card_template_for_tone,
    highlight_notification_line,
    highlight_notification_lines,
)


__all__ = [
    "HighlightedNotificationLine",
    "feishu_card_template_for_tone",
    "highlight_notification_line",
    "highlight_notification_lines",
]
