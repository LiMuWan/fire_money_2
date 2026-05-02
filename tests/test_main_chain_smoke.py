import json
import os
import tempfile
import unittest
from pathlib import Path

from client.desktop.firemoney_client import LocalMainChainAdapter
from client.desktop.firemoney_client.preview import build_preview
from server.firemoney_server import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.domain.one_to_two import OneToTwoMarketRow
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
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

    def test_notification_records_are_persisted_for_review(self) -> None:
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

            records = service.load_notification_records()
            payload = contract_to_dict(records)

            self.assertGreaterEqual(len(records), 3)
            self.assertIsInstance(records[0], NotificationRecord)
            self.assertEqual(records[0].status, NotificationStatus.PREPARED)
            self.assertEqual(payload[0]["status"], "prepared")
            self.assertIn("eod", {record.workflow for record in records})
            self.assertIn("watch:open", {record.workflow for record in records})
            self.assertEqual(
                sum(1 for record in records if record.workflow == "morning"),
                1,
            )

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
            self.assertEqual(sold.account.positions, ())
            self.assertEqual(sold.account.events[0].event_type.value, "t1_sell")
            self.assertEqual(len(sold.account.closed_trades), 1)
            self.assertLess(sold.account.closed_trades[0].realized_pnl, 0)

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
            self.assertEqual(stability.status, "observation")

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
            self.assertIn("模拟盘不是实盘", html)
            self.assertIn("15:10 尾盘测评", html)
            self.assertIn("样本少于 30 笔", html)
            self.assertIn("通知记录", html)
            self.assertIn("watch:open", html)
            self.assertIn("prepared", html)
            self.assertIn("本地调度", html)
            self.assertIn("09:31", html)
            self.assertIn("watch / open", html)
            self.assertIn("已执行", html)
            self.assertIn("尾盘测评", html)
            self.assertIn("稳定性观察", html)
            self.assertIn("持仓 700 股", html)
            self.assertNotIn("示例龙头", html)
            self.assertNotIn("csv_export", html)
            self.assertNotIn("确认委托", html)
            self.assertNotIn("回执", html)
            self.assertNotIn("orders/draft-600001.csv", html)
            self.assertNotIn("AppData/Local/Temp", html)


if __name__ == "__main__":
    unittest.main()
