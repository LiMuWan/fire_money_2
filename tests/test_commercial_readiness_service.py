from __future__ import annotations

import unittest
from datetime import date, timedelta

from server.firemoney_server.application.commercial_readiness_service import (
    CommercialReadinessService,
)
from shared.contracts import (
    FeishuNotificationResult,
    LimitUpBoardShadowSystemMetric,
    NotificationRecord,
    NotificationStatus,
    OneToTwoMorningReport,
    PaperAccount,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    TradingDayContext,
)


def _trade_context() -> TradingDayContext:
    return TradingDayContext(
        requested_date="2026-05-08",
        trade_date="2026-05-08",
        previous_trade_date="2026-05-07",
        next_trade_date="2026-05-11",
        is_trading_day=True,
        note="",
    )


def _account() -> PaperAccount:
    return PaperAccount(
        account_id="paper",
        last_trade_date="2026-05-08",
        cash=100000.0,
        initial_cash=100000.0,
        equity=100000.0,
        max_position_pct=0.08,
        max_daily_trades=1,
        daily_trade_count=0,
        positions=(),
        events=(),
        closed_trades=(),
    )


def _morning_report() -> OneToTwoMorningReport:
    return OneToTwoMorningReport(
        report_id="morning-2026-05-08",
        trade_date="2026-05-08",
        trade_context=_trade_context(),
        market_temperature=72,
        status="ready",
        summary="主线清晰",
        candidates=(),
        account=_account(),
        notification=FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title="早评",
            message="",
            webhook_configured=True,
        ),
        next_action="继续值守",
    )


def _notification(index: int, status: NotificationStatus = NotificationStatus.SENT) -> NotificationRecord:
    workflow = ("morning", "watch:open", "watch:risk", "eod")[index % 4]
    return NotificationRecord(
        record_id=f"notification-{index}",
        channel="feishu",
        workflow=workflow,
        trade_date="2026-05-08",
        status=status,
        title="通知",
        message="",
        created_at=f"20260508{index:06d}",
    )


def _workflow_notification(
    trade_date: str,
    workflow: str,
    index: int,
    status: NotificationStatus = NotificationStatus.SENT,
) -> NotificationRecord:
    return NotificationRecord(
        record_id=f"notification-{trade_date}-{workflow}-{index}",
        channel="feishu",
        workflow=workflow,
        trade_date=trade_date,
        status=status,
        title="通知",
        message="",
        created_at=f"{trade_date.replace('-', '')}{index:06d}",
    )


def _weekday_dates(count: int, end: str = "2026-05-29") -> tuple[str, ...]:
    current = date.fromisoformat(end)
    dates: list[str] = []
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current -= timedelta(days=1)
    return tuple(reversed(dates))


def _daily_morning_eod_notifications(count: int) -> tuple[NotificationRecord, ...]:
    records: list[NotificationRecord] = []
    for index, trade_date in enumerate(_weekday_dates(count), 1):
        records.append(_workflow_notification(trade_date, "morning", index * 2))
        records.append(_workflow_notification(trade_date, "eod", index * 2 + 1))
    return tuple(records)


def _paper_database_report(closed_count: int = 30) -> PaperTradeDatabaseReport:
    return PaperTradeDatabaseReport(
        report_id="paper-db",
        database_path=":memory:",
        status="ready",
        account_id="paper",
        last_trade_date="2026-05-08",
        cash=100000.0,
        equity=110000.0,
        total_realized_pnl=10000.0,
        total_realized_return_pct=0.10,
        win_rate=0.6,
        average_realized_return_pct=0.01,
        average_profit_drawdown_ratio=1.4,
        risk_quality_pass_rate=0.8,
        snapshot_count=closed_count,
        event_count=closed_count * 2,
        open_position_count=0,
        closed_trade_count=closed_count,
        positions=(),
        recent_events=(),
        recent_trades=(),
        quality_buckets=(),
        guard_buckets=(),
        next_action="继续跑",
    )


def _backtest_report(status: str = "ready") -> PaperBacktestReport:
    return PaperBacktestReport(
        report_id="paper-backtest",
        start_date="2020-01-01",
        end_date="2026-05-05",
        status=status,
        strategy_id="board-shadow-system",
        summary="验证通过",
        overall=LimitUpBoardShadowSystemMetric("overall", 100, 0.62, 0.8, 0.03),
        train=LimitUpBoardShadowSystemMetric("train", 70, 0.62, 0.7, 0.03),
        validation=LimitUpBoardShadowSystemMetric("validation", 30, 0.6, 0.1, 0.02),
        yearly=(),
        negative_years=(),
        weak_years=(),
        buy_rule_summary=(),
        improvement_notes=(),
        no_future_leakage_notes=(),
        limitations=(),
        next_action="继续验证",
    )


class CommercialReadinessServiceTest(unittest.TestCase):
    def test_compliance_keeps_commercial_launch_blocked(self) -> None:
        service = CommercialReadinessService()

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=tuple(_notification(index) for index in range(60)),
        )

        self.assertEqual(report.status, "blocked")
        self.assertIn("暂不能对外商用", report.headline)
        self.assertEqual(report.gates[0].gate_id, "compliance")
        self.assertEqual(report.gates[0].tone, "danger")

    def test_real_paper_sample_gate_requires_30_closed_trades(self) -> None:
        service = CommercialReadinessService()

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(closed_count=10),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=tuple(_notification(index) for index in range(60)),
        )

        paper_gate = next(gate for gate in report.gates if gate.gate_id == "paper_ledger")
        self.assertEqual(paper_gate.tone, "warning")
        self.assertIn("还没到 30 笔", paper_gate.detail)

    def test_notification_gate_requires_delivery_samples(self) -> None:
        service = CommercialReadinessService()

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=(),
        )

        notification_gate = next(gate for gate in report.gates if gate.gate_id == "notification")
        self.assertEqual(notification_gate.tone, "danger")
        self.assertIn("没有早评", notification_gate.detail)

    def test_notification_gate_counts_watch_open_and_risk_as_key_delivery(self) -> None:
        service = CommercialReadinessService()
        records = (
            _workflow_notification("2026-05-08", "morning", 1),
            _workflow_notification("2026-05-08", "watch:open", 2),
            _workflow_notification("2026-05-08", "watch:risk", 3),
            _workflow_notification("2026-05-08", "eod", 4),
        )

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=records,
        )

        notification_gate = next(gate for gate in report.gates if gate.gate_id == "notification")
        operations_gate = next(gate for gate in report.gates if gate.gate_id == "operations_30d")
        self.assertEqual(notification_gate.metrics["买卖通知"], "2")
        self.assertEqual(notification_gate.metrics["送达率"], "100%")
        self.assertEqual(operations_gate.metrics["买卖通知"], "2")

    def test_operations_gate_tracks_30_day_coverage(self) -> None:
        service = CommercialReadinessService()

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(closed_count=12),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=_daily_morning_eod_notifications(12),
        )

        gate = next(gate for gate in report.gates if gate.gate_id == "operations_30d")
        self.assertEqual(gate.tone, "warning")
        self.assertEqual(gate.metrics["覆盖交易日"], "12/30")
        self.assertEqual(gate.metrics["连续覆盖"], "12/30")
        self.assertEqual(gate.metrics["早评送达"], "12")
        self.assertEqual(gate.metrics["晚评送达"], "12")
        self.assertIn("还没证明连续 30 日", gate.detail)

    def test_operations_gate_passes_after_30_covered_days_and_closed_trades(self) -> None:
        service = CommercialReadinessService()

        report = service.build_report(
            report=_morning_report(),
            schedule_health_report=None,
            paper_database_report=_paper_database_report(closed_count=30),
            paper_backtest_report=_backtest_report(),
            doctor_report=None,
            notification_records=_daily_morning_eod_notifications(30),
        )

        gate = next(gate for gate in report.gates if gate.gate_id == "operations_30d")
        self.assertEqual(gate.tone, "success")
        self.assertEqual(gate.metrics["覆盖交易日"], "30/30")
        self.assertEqual(gate.metrics["闭环交易"], "30/30")


if __name__ == "__main__":
    unittest.main()
