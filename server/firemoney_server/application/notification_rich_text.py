"""Rich notification payload helpers shared by Feishu adapters."""

from __future__ import annotations

from shared.notification_highlight import (
    feishu_card_template_for_tone,
    highlight_notification_lines,
)


def feishu_message_card(title: str, message: str) -> dict[str, object]:
    lines = highlight_notification_lines(message)
    header_tone = next(
        (line.tone for line in lines if line.tone != "neutral"),
        "neutral",
    )
    elements: list[dict[str, object]] = []
    for line in lines[:32]:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": _line_markdown(line.label, line.text),
                },
            }
        )
    if len(lines) > 32:
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"还有 {len(lines) - 32} 行，请到本地驾驶舱查看完整内容。",
                    }
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": feishu_card_template_for_tone(header_tone),
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": elements,
    }


def _line_markdown(label: str, text: str) -> str:
    return f"**[{_escape_lark_md(label)}]** {_escape_lark_md(text)}"


def _escape_lark_md(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
    )


__all__ = ["feishu_message_card"]
