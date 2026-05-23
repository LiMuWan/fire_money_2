from __future__ import annotations

import unittest

from shared.notification_highlight import (
    highlight_notification_line,
    highlight_notification_lines,
)
from server.firemoney_server.application.notification_rich_text import (
    feishu_message_card,
)


class NotificationHighlightTest(unittest.TestCase):
    def test_highlight_notification_lines_classifies_trading_focus(self) -> None:
        lines = highlight_notification_lines(
            "\n".join(
                (
                    "买入：主线首板候选(600001)",
                    "止损 10.1，严格 T+1",
                    "下一步：09:31 复核触发条件",
                )
            )
        )

        self.assertEqual([line.tone for line in lines], ["buy", "danger", "next"])
        self.assertEqual([line.label for line in lines], ["买入", "止损", "下一步"])

    def test_highlight_notification_line_marks_profit_and_discipline(self) -> None:
        self.assertEqual(highlight_notification_line("收益 -6.84%").tone, "profit")
        self.assertEqual(
            highlight_notification_line("卖点纪律：T+1 后执行").tone,
            "discipline",
        )
        self.assertEqual(highlight_notification_line("今日动作：防守空仓").tone, "discipline")
        self.assertEqual(highlight_notification_line("今日动作：暂停，行情不可用").tone, "danger")

    def test_feishu_message_card_uses_highlighted_markdown(self) -> None:
        card = feishu_message_card(
            "FireMoney 早评",
            "买入：主线首板候选(600001)\n止损 10.1\n下一步：复核触发条件",
        )

        self.assertEqual(card["header"]["template"], "green")
        content = card["elements"][0]["text"]["content"]
        self.assertIn("**[买入]**", content)
        self.assertIn("600001", content)


if __name__ == "__main__":
    unittest.main()
