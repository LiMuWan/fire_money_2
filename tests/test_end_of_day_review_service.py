from __future__ import annotations

import unittest
from dataclasses import dataclass

from server.firemoney_server.application.end_of_day_review_service import (
    EndOfDayReviewService,
)
from server.firemoney_server.application.stability_review_service import (
    StabilityReviewService,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    OneToTwoEventType,
    PaperAccount,
    PaperTradeEvent,
    PaperTradeRecord,
    TradingDayContext,
)


@dataclass(frozen=True)
class Settings:
    minimum_sample_for_stability: int = 30


def _trade_context() -> TradingDayContext:
    return TradingDayContext(
        requested_date="2026-05-08",
        trade_date="2026-05-08",
        previous_trade_date="2026-05-07",
        next_trade_date="2026-05-11",
        is_trading_day=True,
        note="",
    )


def _event(
    event_type: OneToTwoEventType,
    trade_date: str = "2026-05-08",
) -> PaperTradeEvent:
    return PaperTradeEvent(
        event_id=f"{event_type.value}-{trade_date}",
        event_type=event_type,
        symbol="600001",
        name="样本股",
        trade_date=trade_date,
        price=10.0,
        quantity=100,
        amount=1000.0,
        message=event_type.value,
        created_at="20260508093000",
    )


def _trade() -> PaperTradeRecord:
    return PaperTradeRecord(
        trade_id="sample-1",
        symbol="600001",
        name="样本股",
        opened_at="2026-05-06",
        closed_at="2026-05-08",
        entry_price=10.0,
        exit_price=9.6,
        quantity=100,
        entry_amount=1000.0,
        exit_amount=960.0,
        realized_pnl=-40.0,
        realized_pnl_pct=-0.04,
        holding_trade_days=2,
        exit_reason="stop_loss_t1",
        position_label="低位平台突破",
        success=False,
        warning_count=1,
        max_favorable_pct=0.01,
        max_adverse_pct=0.04,
        profit_drawdown_ratio=0.0,
    )


def _account() -> PaperAccount:
    return PaperAccount(
        account_id="paper",
        last_trade_date="2026-05-08",
        cash=99960.0,
        initial_cash=100000.0,
        equity=99960.0,
        max_position_pct=0.08,
        max_daily_trades=1,
        daily_trade_count=0,
        positions=(),
        events=(
            _event(OneToTwoEventType.STOP_WARNING, "2026-05-07"),
            _event(OneToTwoEventType.T1_SELL, "2026-05-08"),
        ),
        closed_trades=(_trade(),),
    )


class EndOfDayReviewServiceTest(unittest.TestCase):
    def test_build_review_records_eod_and_formats_summary(self) -> None:
        notifications: list[tuple[bool, str, str]] = []
        records: list[tuple[str, str, FeishuNotificationResult]] = []
        stability_service = StabilityReviewService(Settings())
        service = EndOfDayReviewService(
            notify_or_prepare=lambda notify, title, message: self._notify(
                notifications,
                notify,
                title,
                message,
            ),
            record_notification=lambda workflow, trade_date, result: records.append(
                (workflow, trade_date, result)
            ),
            build_stability_report=stability_service.build_report,
            board_shadow_hint=lambda: "经营提示：查看封板波段主线分年收益和回撤",
            regime_label=lambda regime: regime or "待确认",
        )

        review = service.build_review(
            report_date="2026-05-08",
            trade_context=_trade_context(),
            account=_account(),
            notify=False,
        )

        self.assertEqual(review.sample_count, 1)
        self.assertEqual(review.success_count, 0)
        self.assertEqual(review.warning_count, 0)
        self.assertEqual(review.realized_pnl, -40.0)
        self.assertEqual(review.max_drawdown, -40.0)
        self.assertEqual(review.stability_stage, "观察期")
        self.assertIn("完成样本 1 笔", review.summary)
        self.assertIn("T+1 卖出 1", review.notification.message)
        self.assertEqual(notifications[0][0], False)
        self.assertEqual(records[0][0], "eod")
        self.assertEqual(records[0][1], "2026-05-08")

    def test_build_review_marks_title_when_market_data_is_unavailable(self) -> None:
        notifications: list[tuple[bool, str, str]] = []
        service = EndOfDayReviewService(
            notify_or_prepare=lambda notify, title, message: self._notify(
                notifications,
                notify,
                title,
                message,
            ),
            record_notification=lambda workflow, trade_date, result: None,
            build_stability_report=StabilityReviewService(Settings()).build_report,
            board_shadow_hint=lambda: "hint",
            regime_label=lambda regime: regime or "待确认",
        )

        review = service.build_review(
            report_date="2026-05-08",
            trade_context=_trade_context(),
            account=_account(),
            data_unavailable=True,
            notify=False,
        )

        self.assertEqual(review.notification.title, "FireMoney 尾盘 | 暂停 | 2026-05-08")
        self.assertIn("行情数据不可用", review.notification.message)

    def _notify(
        self,
        notifications: list[tuple[bool, str, str]],
        notify: bool,
        title: str,
        message: str,
    ) -> FeishuNotificationResult:
        notifications.append((notify, title, message))
        return FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title=title,
            message=message,
            webhook_configured=False,
        )


if __name__ == "__main__":
    unittest.main()
