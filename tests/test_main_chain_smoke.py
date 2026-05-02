import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from client.desktop.firemoney_client import LocalMainChainAdapter
from client.desktop.firemoney_client.preview import build_preview
from server.firemoney_server import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.domain.one_to_two import OneToTwoMarketRow
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    SampleMarketDataProvider,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.one_to_two_config import load_one_to_two_settings
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar
from shared.contracts import (
    FeishuNotificationResult,
    NotificationRecord,
    NotificationStatus,
    OneToTwoMorningReport,
    OneToTwoScheduleRun,
    PaperAccount,
    PaperTradeRecord,
    PaperTradeStatus,
    contract_to_dict,
)


def _build_service(
    root: Path,
    market_data_provider=None,
    paper_store: PaperTradeStore | None = None,
    notification_store: NotificationRecordStore | None = None,
    trading_calendar=None,
) -> MainChainService:
    return MainChainService(
        market_data_provider=market_data_provider,
        paper_store=paper_store or PaperTradeStore(root / "paper_trades.json"),
        notification_store=notification_store
        or NotificationRecordStore(root / "notifications.json"),
        trading_calendar=trading_calendar or WeekdayTradingCalendar(),
    )


def _risk_break_row(trade_date: str) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="低位突破样例",
        trade_date=trade_date,
        board="主板",
        is_st=False,
        is_delisting=False,
        listing_days=1200,
        latest_price=9.8,
        previous_close=9.56,
        limit_up_price=10.52,
        first_limit_up_time="10:05",
        sealed_amount=32000000,
        turnover_amount=180000000,
        turnover_rate=6.2,
        open_pct=0.03,
        auction_amount=12000000,
        low_20=8.8,
        high_60=10.6,
        pressure_price=11.8,
        ma_5=9.3,
        ma_10=9.2,
        ma_20=9.1,
        recent_gain_pct=0.12,
        theme="低位平台突破",
        market_temperature=74,
    )


def _weak_after_two_days_row(trade_date: str) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="低位突破样例",
        trade_date=trade_date,
        board="主板",
        is_st=False,
        is_delisting=False,
        listing_days=1200,
        latest_price=10.6,
        previous_close=10.52,
        limit_up_price=11.57,
        first_limit_up_time="10:05",
        sealed_amount=32000000,
        turnover_amount=180000000,
        turnover_rate=6.2,
        open_pct=0.01,
        auction_amount=12000000,
        low_20=8.8,
        high_60=10.6,
        pressure_price=11.8,
        ma_5=10.1,
        ma_10=9.8,
        ma_20=9.3,
        recent_gain_pct=0.18,
        theme="低位平台突破",
        market_temperature=74,
    )


class StaticOneToTwoProvider:
    def __init__(self, rows: tuple[OneToTwoMarketRow, ...]) -> None:
        self._rows = rows

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        return tuple(
            OneToTwoMarketRow(
                symbol=row.symbol,
                name=row.name,
                trade_date=trade_date,
                board=row.board,
                is_st=row.is_st,
                is_delisting=row.is_delisting,
                listing_days=row.listing_days,
                latest_price=row.latest_price,
                previous_close=row.previous_close,
                limit_up_price=row.limit_up_price,
                first_limit_up_time=row.first_limit_up_time,
                sealed_amount=row.sealed_amount,
                turnover_amount=row.turnover_amount,
                turnover_rate=row.turnover_rate,
                open_pct=row.open_pct,
                auction_amount=row.auction_amount,
                low_20=row.low_20,
                high_60=row.high_60,
                pressure_price=row.pressure_price,
                ma_5=row.ma_5,
                ma_10=row.ma_10,
                ma_20=row.ma_20,
                recent_gain_pct=row.recent_gain_pct,
                theme=row.theme,
                market_temperature=row.market_temperature,
            )
            for row in self._rows
        )


class FailingOneToTwoProvider:
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        raise RuntimeError("market data unavailable")


def _closed_trade_record(index: int, realized_pnl_pct: float = 0.02) -> PaperTradeRecord:
    entry_price = 10.0
    exit_price = round(entry_price * (1 + realized_pnl_pct), 2)
    quantity = 100
    entry_amount = entry_price * quantity
    exit_amount = exit_price * quantity
    return PaperTradeRecord(
        trade_id=f"sample-{index}",
        symbol=f"600{index % 1000:03d}",
        name=f"样本{index}",
        opened_at="2026-04-30",
        closed_at="2026-05-06",
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_amount=entry_amount,
        exit_amount=exit_amount,
        realized_pnl=round(exit_amount - entry_amount, 2),
        realized_pnl_pct=realized_pnl_pct,
        holding_trade_days=1,
        exit_reason="take_profit" if realized_pnl_pct > 0 else "stop_loss_t1",
        position_label="低位平台突破",
        success=realized_pnl_pct > 0,
        warning_count=0 if realized_pnl_pct > 0 else 1,
    )


class MainChainSmokeTest(unittest.TestCase):
    def test_one_to_two_contracts_are_json_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            payload = contract_to_dict(report)

            self.assertIsInstance(report, OneToTwoMorningReport)
            self.assertEqual(payload["notification"]["status"], "prepared")
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["trade_context"]["trade_date"], "2026-04-30")
            self.assertIsInstance(payload["candidates"], list)
            self.assertEqual(payload["candidates"][0]["position_profile"]["label"], "低位平台突破")

    def test_weekend_request_uses_previous_trading_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-02",
                notify=False,
            )

            self.assertEqual(report.trade_date, "2026-04-30")
            self.assertFalse(report.trade_context.is_trading_day)
            self.assertIn("previous trading day", report.trade_context.note)

    def test_one_to_two_scores_low_breakout_and_blocks_risky_boards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            candidates = {candidate.symbol: candidate for candidate in report.candidates}
            one_word_row = OneToTwoMarketRow(
                symbol="600004",
                name="一字买不到样例",
                trade_date="2026-05-01",
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=700,
                latest_price=11.0,
                previous_close=10.0,
                limit_up_price=11.0,
                first_limit_up_time="09:30",
                sealed_amount=88000000,
                turnover_amount=120000000,
                turnover_rate=1.2,
                open_pct=0.1,
                auction_amount=100000,
                low_20=9.4,
                high_60=10.9,
                pressure_price=12.4,
                ma_5=10.6,
                ma_10=10.1,
                ma_20=9.8,
                recent_gain_pct=0.15,
                theme="一字观察",
                market_temperature=74,
            )
            one_word = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((one_word_row,)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            ).candidates[0]

            self.assertEqual(candidates["600001"].status, "ready")
            self.assertGreaterEqual(candidates["600001"].score, 70)
            self.assertEqual(candidates["600001"].position_profile.label, "低位平台突破")
            self.assertEqual(candidates["600002"].status, "blocked")
            self.assertTrue(
                any("乖离" in blocker or "高位" in blocker for blocker in candidates["600002"].blockers)
            )
            self.assertEqual(candidates["300003"].status, "blocked")
            self.assertTrue(any("创业板" in blocker for blocker in candidates["300003"].blockers))
            self.assertEqual(one_word.status, "blocked")
            self.assertTrue(any("买不到" in blocker for blocker in one_word.blockers))

    def test_one_to_two_market_data_failure_blocks_trading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=FailingOneToTwoProvider(),
            )

            report = service.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            watch = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                notify=False,
            )

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.candidates, ())
            self.assertIn("行情数据不可用", report.summary)
            self.assertEqual(watch.account.positions, ())
            self.assertEqual(watch.account.events, ())

    def test_doctor_report_checks_runtime_readiness_without_trading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            report = service.build_one_to_two_doctor_report(trade_date="2026-05-01")
            payload = contract_to_dict(report)

            self.assertEqual(report.report_id, "one-to-two-doctor-2026-04-30")
            self.assertEqual(report.status, "warning")
            checks = {check.check_id: check for check in report.checks}
            self.assertEqual(checks["strategy_config"].status, "ready")
            self.assertEqual(checks["market_data"].status, "ready")
            self.assertEqual(checks["paper_store"].status, "ready")
            self.assertEqual(checks["feishu"].status, "warning")
            self.assertEqual(checks["scheduler"].status, "ready")
            self.assertEqual(service._paper_store.load().positions, ())
            self.assertEqual(service._paper_store.load().events, ())
            self.assertEqual(payload["checks"][0]["check_id"], "strategy_config")

    def test_beta_doctor_blocks_when_feishu_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            with patch.dict(os.environ, {}, clear=True):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-05-01",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["market_data"].status, "ready")
            self.assertEqual(checks["feishu"].status, "blocked")
            self.assertIn("FEISHU_ENABLED=true", checks["feishu"].next_action)

    def test_beta_doctor_accepts_feishu_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://example.com/hook",
                },
                clear=True,
            ):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-05-01",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "ready")
            self.assertEqual(checks["feishu"].status, "ready")

    def test_doctor_report_blocks_when_market_data_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=FailingOneToTwoProvider(),
            )

            report = service.build_one_to_two_doctor_report(trade_date="2026-05-01")
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["market_data"].status, "blocked")
            self.assertEqual(service._paper_store.load().positions, ())
            self.assertEqual(service._paper_store.load().events, ())

    def test_doctor_report_explains_missing_akshare_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=AkshareMarketDataProvider(),
            )

            with patch(
                "server.firemoney_server.application.main_chain.importlib.util.find_spec",
                return_value=None,
            ):
                report = service.build_one_to_two_doctor_report(trade_date="2026-05-01")
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["market_data"].status, "blocked")
            self.assertIn("AkShare 未安装", checks["market_data"].detail)
            self.assertIn("requirements.txt", checks["market_data"].next_action)

    def test_one_to_two_paper_buy_respects_position_and_daily_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            watch = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            second_watch = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )

            self.assertEqual(len(watch.account.positions), 1)
            position = watch.account.positions[0]
            self.assertEqual(position.status, PaperTradeStatus.HOLDING)
            self.assertLessEqual(
                position.position_value,
                watch.account.initial_cash * watch.account.max_position_pct,
            )
            self.assertEqual(watch.account.daily_trade_count, 1)
            self.assertEqual(watch.account.events[0].event_type.value, "paper_buy")
            self.assertEqual(len(second_watch.account.events), 1)
            self.assertEqual(second_watch.account.daily_trade_count, 1)

    def test_watch_phases_do_not_buy_before_open_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            scan = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="scan",
                notify=False,
            )
            auction = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="auction",
                notify=False,
            )
            open_trigger = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )

            self.assertEqual(scan.account.positions, ())
            self.assertEqual(auction.account.positions, ())
            self.assertEqual(open_trigger.account.events[0].event_type.value, "paper_buy")
            self.assertEqual(open_trigger.account.positions[0].status, PaperTradeStatus.HOLDING)

    def test_feishu_messages_include_actionable_one_to_two_discipline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            morning = service.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            open_trigger = service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            eod = service.build_one_to_two_end_of_day_review(
                trade_date="2026-05-01",
                notify=False,
            )

            self.assertIn("候选入池", morning.notification.message)
            self.assertIn("止损", morning.notification.message)
            self.assertIn("仓位上限 8%", morning.notification.message)
            self.assertIn("T+1", morning.notification.message)
            self.assertIn("持仓", open_trigger.notification.message)
            self.assertIn("模拟盘不是实盘", open_trigger.notification.message)
            self.assertIn("样本少于 30 笔", eod.notification.message)
            self.assertIn("最新样本：暂无完成样本", eod.notification.message)

    def test_notification_records_are_persisted_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(
                root / "notifications.json",
                created_at_provider=lambda: "20260501085000",
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=store,
            )

            service.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            service.build_one_to_two_end_of_day_review(
                trade_date="2026-05-01",
                notify=False,
            )

            records = service.load_notification_records()
            payload = contract_to_dict(records)

            self.assertGreaterEqual(len(records), 3)
            self.assertIsInstance(records[0], NotificationRecord)
            self.assertEqual(records[0].status, NotificationStatus.PREPARED)
            self.assertEqual(payload[0]["status"], "prepared")
            self.assertEqual(payload[0]["created_at"], "20260501085000")
            self.assertIn("eod", {record.workflow for record in records})
            self.assertIn("watch:open", {record.workflow for record in records})
            self.assertEqual(
                sum(1 for record in records if record.workflow == "morning"),
                1,
            )

    def test_notification_records_can_be_filtered_and_read_by_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=store,
            )

            service.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            service.build_one_to_two_end_of_day_review(
                trade_date="2026-05-01",
                notify=False,
            )

            filtered = service.load_notification_records(
                workflow="watch:open",
                status=NotificationStatus.PREPARED,
                limit=1,
            )
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].workflow, "watch:open")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "notifications",
                    "--notification-store",
                    str(store.path),
                    "--workflow",
                    "watch:open",
                    "--status",
                    "prepared",
                    "--limit",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["mode"], "notifications")
            self.assertEqual(payload["record_count"], 1)
            self.assertEqual(payload["records"][0]["workflow"], "watch:open")
            self.assertEqual(payload["records"][0]["status"], "prepared")

    def test_one_to_two_stop_warning_obeys_t1_before_sell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            buy_service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            buy_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            risk_service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((_risk_break_row("2026-05-01"),)),
                paper_store=paper_store,
            )

            warning = risk_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="risk",
                notify=False,
            )
            sold = risk_service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(warning.account.positions[0].status, PaperTradeStatus.WARNING)
            self.assertEqual(warning.account.events[0].event_type.value, "stop_warning")
            self.assertIn("止损预警", warning.notification.message)
            self.assertIn("当日只预警不卖出", warning.notification.message)
            self.assertIn("下一交易日仍低于止损再模拟卖出", warning.notification.message)
            self.assertIn("止损价", warning.notification.message)
            self.assertEqual(sold.account.positions, ())
            self.assertEqual(sold.account.events[0].event_type.value, "t1_sell")
            self.assertEqual(len(sold.account.closed_trades), 1)
            self.assertLess(sold.account.closed_trades[0].realized_pnl, 0)
            self.assertIn("完成样本", sold.notification.message)
            self.assertIn("stop_loss_t1", sold.notification.message)
            self.assertIn("实现盈亏：-", sold.notification.message)

    def test_weak_position_exits_after_two_trading_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            buy_service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            buy_service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )
            weak_service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_weak_after_two_days_row("2026-05-07"),)
                ),
                paper_store=paper_store,
            )

            weak = weak_service.run_one_to_two_watch(
                trade_date="2026-05-07",
                phase="risk",
                notify=False,
            )

            self.assertEqual(weak.account.positions, ())
            self.assertEqual(weak.account.events[0].event_type.value, "discipline_exit")
            self.assertEqual(weak.account.closed_trades[0].exit_reason, "discipline_weak_after_2_days")
            self.assertEqual(weak.account.closed_trades[0].holding_trade_days, 2)
            self.assertIn("完成样本", weak.notification.message)
            self.assertIn("discipline_weak_after_2_days", weak.notification.message)
            self.assertIn("持仓 2 日", weak.notification.message)

    def test_paper_store_does_not_roll_account_backward(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PaperTradeStore(Path(temp_dir) / "paper_trades.json")

            current = store.prepare_for_trade_date("2026-05-06")
            older = store.prepare_for_trade_date("2026-04-30")

            self.assertEqual(current.last_trade_date, "2026-05-06")
            self.assertEqual(older.last_trade_date, "2026-05-06")

    def test_stability_report_uses_closed_trade_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            buy_service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            buy_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            risk_service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((_risk_break_row("2026-05-01"),)),
                paper_store=paper_store,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="risk",
                notify=False,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            stability = risk_service.build_one_to_two_stability_report()

            self.assertEqual(stability.sample_count, 1)
            self.assertEqual(stability.stop_warning_rate, 1.0)
            self.assertLess(stability.average_return_pct, 0)
            self.assertEqual(stability.position_label_distribution["低位平台突破"], 1)
            self.assertEqual(stability.exit_reason_distribution["stop_loss_t1"], 1)
            self.assertEqual(stability.status, "observation")
            self.assertEqual(stability.sample_stage, "观察期")
            self.assertEqual(stability.next_milestone, 30)
            self.assertIn("少于 30", stability.strategy_boundary_suggestion)
            self.assertEqual(len(stability.recent_samples), 1)
            self.assertEqual(stability.recent_samples[0].symbol, "600001")
            self.assertEqual(stability.recent_samples[0].exit_reason, "stop_loss_t1")
            self.assertLess(stability.recent_samples[0].realized_pnl_pct, 0)

    def test_stability_cli_reads_current_paper_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            buy_service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            buy_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            risk_service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((_risk_break_row("2026-05-01"),)),
                paper_store=paper_store,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="risk",
                notify=False,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "stability",
                    "--paper-store",
                    str(paper_store.path),
                    "--sample-data",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["report_id"], "one-to-two-stability")
            self.assertEqual(payload["sample_count"], 1)
            self.assertEqual(payload["status"], "observation")
            self.assertEqual(payload["sample_stage"], "观察期")
            self.assertEqual(payload["next_milestone"], 30)
            self.assertEqual(payload["exit_reason_distribution"]["stop_loss_t1"], 1)
            self.assertEqual(
                payload["position_label_distribution"]["低位平台突破"],
                1,
            )
            self.assertEqual(payload["recent_samples"][0]["symbol"], "600001")
            self.assertEqual(payload["recent_samples"][0]["exit_reason"], "stop_loss_t1")

    def test_stability_report_adds_30_50_100_sample_stage_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-05-06",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=account.daily_trade_count,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=tuple(
                        _closed_trade_record(index)
                        for index in range(30)
                    ),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            stage_30 = service.build_one_to_two_stability_report()
            self.assertEqual(stage_30.status, "reviewable")
            self.assertEqual(stage_30.sample_stage, "30 笔初评")
            self.assertEqual(stage_30.next_milestone, 50)
            self.assertIn("低位平台突破", stage_30.strategy_boundary_suggestion)
            self.assertEqual(len(stage_30.recent_samples), 5)
            self.assertEqual(stage_30.recent_samples[0].trade_id, "sample-0")

            account_30 = paper_store.load()
            paper_store.save(
                PaperAccount(
                    account_id=account_30.account_id,
                    last_trade_date=account_30.last_trade_date,
                    cash=account_30.cash,
                    initial_cash=account_30.initial_cash,
                    equity=account_30.equity,
                    max_position_pct=account_30.max_position_pct,
                    max_daily_trades=account_30.max_daily_trades,
                    daily_trade_count=account_30.daily_trade_count,
                    positions=account_30.positions,
                    events=account_30.events,
                    closed_trades=tuple(
                        _closed_trade_record(index)
                        for index in range(50)
                    ),
                )
            )
            stage_50 = service.build_one_to_two_stability_report()
            self.assertEqual(stage_50.sample_stage, "50 笔复评")
            self.assertEqual(stage_50.next_milestone, 100)

            account_50 = paper_store.load()
            paper_store.save(
                PaperAccount(
                    account_id=account_50.account_id,
                    last_trade_date=account_50.last_trade_date,
                    cash=account_50.cash,
                    initial_cash=account_50.initial_cash,
                    equity=account_50.equity,
                    max_position_pct=account_50.max_position_pct,
                    max_daily_trades=account_50.max_daily_trades,
                    daily_trade_count=account_50.daily_trade_count,
                    positions=account_50.positions,
                    events=account_50.events,
                    closed_trades=tuple(
                        _closed_trade_record(index)
                        for index in range(100)
                    ),
                )
            )
            stage_100 = service.build_one_to_two_stability_report()
            self.assertEqual(stage_100.sample_stage, "100 笔定边界")
            self.assertEqual(stage_100.next_milestone, 0)
            self.assertIn("100 笔以上复盘", stage_100.next_action)

    def test_end_of_day_review_uses_closed_trade_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            buy_service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            buy_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            risk_service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((_risk_break_row("2026-05-01"),)),
                paper_store=paper_store,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="risk",
                notify=False,
            )
            risk_service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            review = risk_service.build_one_to_two_end_of_day_review(
                trade_date="2026-05-06",
                notify=False,
            )

            self.assertEqual(review.sample_count, 1)
            self.assertEqual(review.success_count, 0)
            self.assertEqual(review.warning_count, 1)
            self.assertLess(review.realized_pnl, 0)
            self.assertLess(review.max_drawdown, 0)
            self.assertIn("完成样本 1 笔", review.summary)
            self.assertIn("成功 0 笔", review.summary)
            self.assertEqual(review.stability_stage, "观察期")
            self.assertEqual(review.next_milestone, 30)
            self.assertIn("少于 30", review.strategy_boundary_suggestion)
            self.assertIn("稳定性阶段", review.notification.message)
            self.assertIn("边界建议", review.notification.message)
            self.assertIn("当日 T+1 卖出：1", review.notification.message)
            self.assertIn("已归档样本：1", review.notification.message)
            self.assertIn("最新样本", review.notification.message)
            self.assertIn("stop_loss_t1", review.notification.message)
            self.assertIn("收益 -", review.notification.message)

    def test_backtest_replays_closed_samples_without_mutating_live_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            report = service.run_one_to_two_backtest(
                start_date="2026-04-28",
                end_date="2026-04-30",
                max_trade_days=3,
            )

            self.assertGreaterEqual(report.sample_count, 1)
            self.assertEqual(paper_store.load().closed_trades, ())
            self.assertEqual(paper_store.load().positions, ())

    def test_scheduler_runs_due_jobs_once_per_trading_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            scheduler = OneToTwoScheduler(
                service=service,
                state_store=SchedulerStateStore(root / "scheduler_state.json"),
            )

            first = scheduler.run_due(
                trade_date="2026-04-30",
                at_time="09:31",
                notify=False,
            )
            second = scheduler.run_due(
                trade_date="2026-04-30",
                at_time="09:31",
                notify=False,
            )

            self.assertIsInstance(first, OneToTwoScheduleRun)
            self.assertEqual(first.due_count, 4)
            self.assertEqual(first.executed_count, 4)
            self.assertEqual(second.executed_count, 0)
            self.assertEqual(second.skipped_count, 4)
            account = PaperTradeStore(root / "paper_trades.json").load()
            self.assertEqual(len(account.positions), 1)
            self.assertEqual(account.events[0].event_type.value, "paper_buy")

    def test_scheduler_does_not_backfill_expired_open_buy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            scheduler = OneToTwoScheduler(
                service=service,
                state_store=SchedulerStateStore(root / "scheduler_state.json"),
            )

            result = scheduler.run_due(
                trade_date="2026-04-30",
                at_time="15:30",
                notify=False,
            )

            self.assertEqual(result.executed_count, 1)
            self.assertEqual(
                {task.task_id for task in result.tasks if task.status == "expired"},
                {
                    "morning",
                    "watch-scan",
                    "watch-auction",
                    "watch-open",
                    "watch-risk-1000",
                    "watch-risk-1100",
                    "watch-risk-1400",
                    "watch-risk-1450",
                },
            )
            account = PaperTradeStore(root / "paper_trades.json").load()
            self.assertEqual(account.positions, ())
            self.assertFalse(
                any(event.event_type.value == "paper_buy" for event in account.events)
            )

    def test_scheduler_skips_non_trading_requested_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            scheduler = OneToTwoScheduler(
                service=service,
                state_store=SchedulerStateStore(root / "scheduler_state.json"),
            )

            result = scheduler.run_due(
                trade_date="2026-05-02",
                at_time="15:30",
                notify=False,
            )

            self.assertEqual(result.due_count, 0)
            self.assertEqual(result.executed_count, 0)
            self.assertEqual({task.status for task in result.tasks}, {"closed"})
            self.assertEqual(PaperTradeStore(root / "paper_trades.json").load().events, ())

    def test_beta_schedule_cli_blocks_before_scheduler_when_doctor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "schedule",
                    "--sample-data",
                    "--beta",
                    "--trade-date",
                    "2026-04-30",
                    "--at",
                    "09:31",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["report_id"], "one-to-two-doctor-2026-04-30")
            self.assertFalse(scheduler_path.exists())
            self.assertEqual(PaperTradeStore(paper_path).load().events, ())

    def test_feishu_notifier_is_safe_without_webhook(self) -> None:
        old_enabled = os.environ.get("FEISHU_ENABLED")
        old_webhook = os.environ.get("FEISHU_WEBHOOK_URL")
        try:
            os.environ["FEISHU_ENABLED"] = "false"
            os.environ.pop("FEISHU_WEBHOOK_URL", None)

            disabled = FeishuNotifier().notify("title", "message")
            os.environ["FEISHU_ENABLED"] = "true"
            prepared = FeishuNotifier().notify("title", "message")

            self.assertIsInstance(disabled, FeishuNotificationResult)
            self.assertEqual(disabled.status, NotificationStatus.DISABLED)
            self.assertEqual(prepared.status, NotificationStatus.PREPARED)
            self.assertFalse(prepared.webhook_configured)
        finally:
            if old_enabled is None:
                os.environ.pop("FEISHU_ENABLED", None)
            else:
                os.environ["FEISHU_ENABLED"] = old_enabled
            if old_webhook is None:
                os.environ.pop("FEISHU_WEBHOOK_URL", None)
            else:
                os.environ["FEISHU_WEBHOOK_URL"] = old_webhook

    def test_client_adapter_exposes_only_one_to_two_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = LocalMainChainAdapter(
                _build_service(
                    Path(temp_dir),
                    market_data_provider=SampleMarketDataProvider(),
                )
            )

            report = adapter.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            self.assertIsInstance(report, OneToTwoMorningReport)
            self.assertFalse(hasattr(adapter, "load_snapshot"))
            self.assertFalse(hasattr(adapter, "export_trade_archives"))

    def test_one_to_two_config_is_json_and_defaults_to_single_core_line(self) -> None:
        config_path = Path(
            "server/firemoney_server/infrastructure/config/one_to_two_strategy.zh_CN.json"
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        settings = load_one_to_two_settings()

        self.assertEqual(payload["strategy_id"], settings.strategy_id)
        self.assertEqual(settings.max_position_pct, 0.08)
        self.assertEqual(settings.max_daily_trades, 1)
        self.assertEqual(settings.max_holding_trade_days, 2)
        self.assertEqual(settings.discipline_exit_min_gain_pct, 0.03)
        self.assertIn("创业板", settings.excluded_boards)

    def test_preview_file_can_be_generated_without_legacy_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "core_workflow.html"

            output = build_preview(target)

            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("FireMoney 一进二", html)
            self.assertIn("一进二专项台", html)
            self.assertIn("低位平台突破", html)
            self.assertIn("模拟盘与风险", html)
            self.assertIn("飞书通知", html)
            self.assertIn("08:50 早盘判断", html)
            self.assertIn("候选入池", html)
            self.assertIn("止损预警", html)
            self.assertIn("T+1 处理", html)
            self.assertIn("当日只预警不卖出", html)
            self.assertIn("下一交易日仍低于止损再模拟卖出", html)
            self.assertIn("当前纪律", html)
            self.assertIn("下一步", html)
            self.assertIn("data-status=\"warning\"", html)
            self.assertIn("模拟盘不是实盘", html)
            self.assertIn("15:10 尾盘测评", html)
            self.assertIn("当日 T+1 卖出：0", html)
            self.assertIn("已归档样本：1", html)
            self.assertIn("样本少于 30 笔", html)
            self.assertIn("通知记录", html)
            self.assertIn("watch:risk", html)
            self.assertIn("prepared", html)
            self.assertIn("运行体检", html)
            self.assertIn("一进二策略配置", html)
            self.assertIn("行情源", html)
            self.assertIn("飞书通知", html)
            self.assertIn("本地调度", html)
            self.assertIn("09:31", html)
            self.assertIn("watch / open", html)
            self.assertIn("已执行", html)
            self.assertIn("尾盘测评", html)
            self.assertIn("稳定性观察", html)
            self.assertIn("稳定性阶段", html)
            self.assertIn("最近样本", html)
            self.assertIn("低位换手样本", html)
            self.assertIn("discipline_take_profit", html)
            self.assertIn("3.80%", html)
            self.assertIn("位置分布", html)
            self.assertIn("退出原因", html)
            self.assertIn("阶段", html)
            self.assertIn("下一门槛", html)
            self.assertIn("边界建议", html)
            self.assertIn("2 个交易日不走强则纪律退出", html)
            self.assertIn("持仓 700 股", html)
            self.assertNotIn("示例龙头", html)
            self.assertNotIn("csv_export", html)
            self.assertNotIn("确认委托", html)
            self.assertNotIn("回执", html)
            self.assertNotIn("orders/draft-600001.csv", html)
            self.assertNotIn("AppData/Local/Temp", html)


if __name__ == "__main__":
    unittest.main()
