import json
import os
import subprocess
import sys
import tempfile
import unittest
import threading
from dataclasses import replace
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from client.desktop.firemoney_client import LocalMainChainAdapter
from client.desktop.firemoney_client.preview import build_preview
from server.firemoney_server import MainChainService
from server.firemoney_server.application.beta_rehearsal import (
    build_one_to_two_beta_launch_plan,
    run_one_to_two_beta_rehearsal,
)
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.domain.one_to_two import (
    HistoricalPriceBar,
    OneToTwoMarketRow,
)
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.local_env import load_local_feishu_env
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    SampleMarketDataProvider,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.one_to_two_config import load_one_to_two_settings
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar
from shared.contracts import (
    FeishuNotificationResult,
    MainlineNewsItem,
    NotificationRecord,
    NotificationStatus,
    OneToTwoBacktestAuditReport,
    OneToTwoHistoricalReplayReport,
    OneToTwoMorningReport,
    OneToTwoBetaRehearsalReport,
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
    scheduler_state_store: SchedulerStateStore | None = None,
    scheduler_run_store: SchedulerRunStore | None = None,
    trading_calendar=None,
) -> MainChainService:
    return MainChainService(
        market_data_provider=market_data_provider,
        paper_store=paper_store or PaperTradeStore(root / "paper_trades.json"),
        notification_store=notification_store
        or NotificationRecordStore(root / "notifications.json"),
        scheduler_state_store=scheduler_state_store
        or SchedulerStateStore(root / "scheduler_state.json"),
        scheduler_run_store=scheduler_run_store
        or SchedulerRunStore(root / "scheduler_runs.json"),
        trading_calendar=trading_calendar or WeekdayTradingCalendar(),
    )


def _risk_break_row(trade_date: str) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="低位突破候选",
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
        name="低位突破候选",
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
    def __init__(
        self,
        rows: tuple[OneToTwoMarketRow, ...],
        news: tuple[MainlineNewsItem, ...] = (),
        price_bars: tuple[HistoricalPriceBar, ...] = (),
    ) -> None:
        self._rows = rows
        self._news = news
        self._price_bars = price_bars

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
                first_board_count=row.first_board_count,
            )
            for row in self._rows
        )

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        return self._news

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        return tuple(
            bar
            for bar in self._price_bars
            if start_date <= bar.trade_date <= end_date
        )


class FailingOneToTwoProvider:
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        raise RuntimeError("market data unavailable")

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        raise RuntimeError("news unavailable")

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        raise RuntimeError("bars unavailable")


class FakeFeishuApiServer:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], dict[str, object]]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body) if body else {}
                outer.requests.append((self.path, dict(self.headers), payload))
                if self.path == "/open-apis/auth/v3/tenant_access_token/internal":
                    response = {"code": 0, "tenant_access_token": "tenant_token"}
                elif self.path.startswith("/open-apis/im/v1/messages"):
                    response = {"code": 0, "data": {"message_id": "om_test"}}
                else:
                    response = {"code": 404, "msg": "not found"}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeFeishuApiServer":
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


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
            self.assertGreaterEqual(payload["candidates"][0]["sealing_score"], 18)
            self.assertGreaterEqual(payload["candidates"][0]["mainline_score"], 14)
            self.assertGreaterEqual(payload["candidates"][0]["leader_score"], 16)
            self.assertIn("龙头候选", payload["candidates"][0]["leader_label"])

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
                name="一字买不到拦截",
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
            self.assertGreaterEqual(candidates["600001"].score, 78)
            self.assertEqual(candidates["600001"].position_profile.label, "低位平台突破")
            self.assertGreaterEqual(candidates["600001"].sealing_score, 18)
            self.assertGreaterEqual(candidates["600001"].leader_score, 16)
            self.assertIn("封板", candidates["600001"].discipline_summary)
            self.assertEqual(candidates["600002"].status, "blocked")
            self.assertTrue(
                any("乖离" in blocker or "高位" in blocker for blocker in candidates["600002"].blockers)
            )
            self.assertEqual(candidates["300003"].status, "blocked")
            self.assertTrue(any("创业板" in blocker for blocker in candidates["300003"].blockers))
            self.assertEqual(one_word.status, "blocked")
            self.assertTrue(any("买不到" in blocker for blocker in one_word.blockers))

    def test_low_breakout_needs_market_width_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
            thin_width_row = replace(
                base_row,
                symbol="600008",
                first_board_count=10,
            )
            report = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((thin_width_row,)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            candidate = report.candidates[0]

            self.assertEqual(candidate.status, "blocked")
            self.assertTrue(any("首板宽度" in blocker for blocker in candidate.blockers))
            self.assertTrue(any("可执行候选" in blocker for blocker in candidate.blockers))

    def test_one_to_two_requires_product_open_confirmation_window(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
        low_open_row = replace(
            base_row,
            symbol="600005",
            open_pct=-0.01,
        )
        high_open_row = replace(
            base_row,
            symbol="600006",
            open_pct=0.081,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((low_open_row, high_open_row)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            candidates = {candidate.symbol: candidate for candidate in report.candidates}
            self.assertEqual(candidates["600005"].status, "blocked")
            self.assertTrue(any("红盘开" in blocker for blocker in candidates["600005"].blockers))
            self.assertEqual(candidates["600006"].status, "blocked")
            self.assertTrue(any("高开超过 7%" in blocker for blocker in candidates["600006"].blockers))

    def test_weak_sealed_board_is_blocked_for_mainline_leader_candidate(self) -> None:
        weak_row = OneToTwoMarketRow(
            symbol="600008",
            name="弱封板样本",
            trade_date="2026-05-01",
            board="主板",
            is_st=False,
            is_delisting=False,
            listing_days=700,
            latest_price=11.0,
            previous_close=10.0,
            limit_up_price=11.0,
            first_limit_up_time="11:15",
            sealed_amount=2000000,
            turnover_amount=120000000,
            turnover_rate=4.2,
            open_pct=0.02,
            auction_amount=3000000,
            low_20=9.2,
            high_60=11.1,
            pressure_price=13.0,
            ma_5=10.6,
            ma_10=10.1,
            ma_20=9.7,
            recent_gain_pct=0.16,
            theme="主线跟风",
            market_temperature=74,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((weak_row,)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            ).candidates[0]

        self.assertEqual(candidate.status, "blocked")
        self.assertTrue(any("封板资金不足" in blocker for blocker in candidate.blockers))

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
            self.assertEqual(checks["notification_store"].status, "ready")
            self.assertEqual(checks["feishu"].status, "warning")
            self.assertEqual(checks["scheduler"].status, "ready")
            self.assertEqual(checks["scheduler_state"].status, "ready")
            self.assertEqual(checks["scheduler_runs"].status, "ready")
            self.assertEqual(service._paper_store.load().positions, ())
            self.assertEqual(service._paper_store.load().events, ())
            self.assertEqual(payload["checks"][0]["check_id"], "strategy_config")

    def test_beta_doctor_blocks_non_trading_day_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-05-02",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["trading_day"].status, "blocked")
            self.assertIn("非交易日", checks["trading_day"].detail)

    def test_doctor_blocks_when_local_state_path_is_not_writable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            not_a_directory = root / "not-a-directory"
            not_a_directory.write_text("blocked", encoding="utf-8")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(
                    not_a_directory / "notifications.json"
                ),
            )

            report = service.build_one_to_two_doctor_report(trade_date="2026-05-01")
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["notification_store"].status, "blocked")
            self.assertIn("not-a-directory", checks["notification_store"].detail)

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

    def test_beta_doctor_requires_sent_feishu_test_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=store,
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-04-30",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["trading_day"].status, "ready")
            self.assertEqual(checks["feishu"].status, "blocked")
            self.assertIn("feishu-test sent", checks["feishu"].detail)

    def test_beta_doctor_accepts_verified_feishu_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(root / "notifications.json")
            store.append(
                workflow="feishu:test",
                trade_date="2026-04-30",
                result=FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="FireMoney 一进二飞书测试",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=store,
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-04-30",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "ready")
            self.assertEqual(checks["trading_day"].status, "ready")
            self.assertEqual(checks["feishu"].status, "ready")

    def test_beta_doctor_accepts_verified_feishu_app_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(root / "notifications.json")
            store.append(
                workflow="feishu:test",
                trade_date="2026-04-30",
                result=FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="FireMoney 一进二飞书测试",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=store,
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_APP_ID": "cli_test",
                    "FEISHU_APP_SECRET": "secret_test",
                    "FEISHU_RECEIVE_ID": "oc_test",
                    "FEISHU_RECEIVE_ID_TYPE": "chat_id",
                },
                clear=True,
            ):
                report = service.build_one_to_two_doctor_report(
                    trade_date="2026-04-30",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "ready")
            self.assertEqual(checks["feishu"].status, "ready")
            self.assertIn("应用机器人", checks["feishu"].detail)

    def test_beta_doctor_blocks_invalid_feishu_webhook_url(self) -> None:
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
                    trade_date="2026-04-30",
                    beta=True,
                )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["feishu"].status, "blocked")
            self.assertIn("飞书群机器人 webhook", checks["feishu"].detail)

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

    def test_akshare_provider_uses_previous_pool_when_spot_snapshot_fails(self) -> None:
        class FakeFrame:
            def __init__(self, records: list[dict[str, object]]) -> None:
                self._records = records

            def to_dict(self, orient: str) -> list[dict[str, object]]:
                if orient != "records":
                    raise AssertionError(f"unexpected orient: {orient}")
                return self._records

        class FakeAk:
            def __init__(self) -> None:
                self.previous_calls = 0
                self.spot_calls = 0

            def stock_zt_pool_previous_em(self, date: str) -> FakeFrame:
                self.previous_calls += 1
                if date != "20260430":
                    raise AssertionError(f"unexpected date: {date}")
                return FakeFrame(
                    [
                        {
                            "代码": "600123",
                            "名称": "低位测试",
                            "最新价": 11.0,
                            "涨停价": 11.0,
                            "成交额": 200000000,
                            "换手率": 6.0,
                            "昨日封板时间": "100500",
                            "昨日连板数": 1,
                            "竞价金额": 12000000,
                            "开盘涨幅": 4.0,
                            "所属行业": "测试题材",
                        }
                    ]
                )

            def stock_zh_a_spot_em(self) -> FakeFrame:
                self.spot_calls += 1
                raise RuntimeError("spot snapshot unavailable")

            def stock_zh_a_hist(self, **_kwargs: object) -> FakeFrame:
                return FakeFrame(
                    [
                        {"收盘": 9.0, "最低": 8.8, "最高": 9.4},
                        {"收盘": 9.4, "最低": 9.0, "最高": 9.8},
                        {"收盘": 10.0, "最低": 9.6, "最高": 10.8},
                    ]
                )

        real_import = __import__
        fake_ak = FakeAk()
        ticks = iter((100.0, 110.0, 200.0, 201.0))

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = AkshareMarketDataProvider(
                cache_dir=Path(temp_dir),
                cache_ttl_seconds=10,
            )
            with patch("builtins.__import__", side_effect=fake_import), patch(
                "server.firemoney_server.infrastructure.market_data.time.monotonic",
                side_effect=lambda: next(ticks),
            ):
                rows = provider.load_one_to_two_rows("2026-04-30")
                cached_rows = provider.load_one_to_two_rows("2026-04-30")
                refreshed_rows = provider.load_one_to_two_rows("2026-04-30")

        self.assertEqual(len(rows), 1)
        self.assertIs(cached_rows, rows)
        self.assertIsNot(refreshed_rows, rows)
        self.assertEqual(fake_ak.previous_calls, 2)
        self.assertEqual(fake_ak.spot_calls, 2)
        self.assertEqual(rows[0].symbol, "600123")
        self.assertEqual(rows[0].board, "主板")
        self.assertEqual(rows[0].theme, "测试题材")
        self.assertGreaterEqual(rows[0].market_temperature, 50)

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

    def test_candidate_and_position_include_exit_plan_and_continuity(self) -> None:
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

            candidate = morning.candidates[0]
            position = open_trigger.account.positions[0]
            self.assertIsNotNone(candidate.exit_plan)
            self.assertIsNotNone(candidate.mainline_continuity)
            self.assertEqual(candidate.exit_plan.first_take_profit_pct, 0.08)
            self.assertIn("盈利 8%", candidate.exit_plan.summary)
            self.assertGreaterEqual(candidate.mainline_continuity.score, 45)
            self.assertIsNotNone(position.exit_plan)
            self.assertIsNotNone(position.mainline_continuity)
            self.assertIn("盈利 8%", position.risk_note)

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

    def test_take_profit_exits_after_t1_when_first_target_is_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            profit_row = _weak_after_two_days_row("2026-05-06")
            profit_row = OneToTwoMarketRow(
                **(profit_row.__dict__ | {"latest_price": 11.38, "theme": "AI端侧主线"})
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((profit_row,)),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.events[0].event_type.value, "take_profit")
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "take_profit_first_target")

    def test_trailing_take_profit_exits_after_strong_gain_reverses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            strong_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-06").__dict__
                    | {
                        "latest_price": 12.2,
                        "theme": "AI绔晶涓荤嚎",
                    }
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((strong_row,)),
            )
            hold = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="open",
                notify=False,
            )
            self.assertEqual(hold.account.positions[0].peak_price, 12.2)

            pullback_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-07").__dict__
                    | {
                        "latest_price": 11.4,
                        "theme": "AI绔晶涓荤嚎",
                    }
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((pullback_row,)),
            )
            risk = service.run_one_to_two_watch(
                trade_date="2026-05-07",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.events[0].event_type.value, "take_profit")
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "trailing_take_profit")

    def test_mainline_fade_exits_after_t1_even_without_news(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            fading_row = _weak_after_two_days_row("2026-05-06")
            fading_row = OneToTwoMarketRow(
                **(
                    fading_row.__dict__
                    | {
                        "latest_price": 10.8,
                        "theme": "",
                        "market_temperature": 0,
                        "sealed_amount": 0,
                        "first_limit_up_time": "",
                        "turnover_rate": 0,
                        "recent_gain_pct": 0,
                        "low_20": 1.0,
                        "high_60": 99.0,
                    }
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((fading_row,)),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.events[0].event_type.value, "mainline_fade_exit")
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "mainline_fade_exit")

    def test_mainline_news_is_added_to_watch_message_without_trading_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            news = (
                MainlineNewsItem(
                    title="AI端侧主线继续发酵",
                    source="东方财富",
                    published_at="2026-05-06 09:45",
                    related_symbols=("600001",),
                ),
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_weak_after_two_days_row("2026-05-06"),),
                    news=news,
                ),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertIn("主线持续性", risk.notification.message)
            self.assertIn("消息 1 条", risk.notification.message)
            self.assertIn("AI端侧主线继续发酵", risk.notification.message)

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
            self.assertIn("卖点纪律", morning.notification.message)
            self.assertIn("主线持续性", morning.notification.message)
            self.assertIn("持仓", open_trigger.notification.message)
            self.assertIn("卖点计划", open_trigger.notification.message)
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

    def test_feishu_test_cli_records_connectivity_check_without_trading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_path = root / "notifications.json"
            paper_path = root / "paper_trades.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "feishu-test",
                    "--sample-data",
                    "--no-notify",
                    "--trade-date",
                    "2026-04-30",
                    "--paper-store",
                    str(paper_path),
                    "--notification-store",
                    str(notification_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)
            records = NotificationRecordStore(notification_path).load()

            self.assertEqual(payload["status"], "prepared")
            self.assertIn("不是交易信号", payload["message"])
            self.assertEqual(records[0].workflow, "feishu:test")
            self.assertEqual(PaperTradeStore(paper_path).load().events, ())

    def test_beta_check_cli_runs_feishu_test_before_doctor(self) -> None:
        class SendingFeishuNotifier:
            def notify(self, title: str, message: str) -> FeishuNotificationResult:
                return FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title=title,
                    message=message,
                    webhook_configured=True,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )
            service._feishu_notifier = SendingFeishuNotifier()

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                report = service.build_one_to_two_beta_readiness_report(
                    trade_date="2026-04-30",
                )

            self.assertEqual(report.status, "ready")
            self.assertEqual(report.feishu_test.status, NotificationStatus.SENT)
            self.assertEqual(report.doctor_report.status, "ready")
            self.assertIn("beta-start", report.next_action)

    def test_beta_check_skips_feishu_test_on_non_trading_day(self) -> None:
        class RaisingFeishuNotifier:
            def notify(self, title: str, message: str) -> FeishuNotificationResult:
                raise AssertionError("non-trading beta-check must not send Feishu")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )
            service._feishu_notifier = RaisingFeishuNotifier()

            report = service.build_one_to_two_beta_readiness_report(
                trade_date="2026-05-02",
            )

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.feishu_test.error, "non-trading day")
            checks = {check.check_id: check for check in report.doctor_report.checks}
            self.assertEqual(checks["trading_day"].status, "blocked")

    def test_beta_check_blocks_invalid_webhook_without_sending(self) -> None:
        class RaisingFeishuNotifier:
            def notify(self, title: str, message: str) -> FeishuNotificationResult:
                raise AssertionError("invalid webhook must not send Feishu")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )
            service._feishu_notifier = RaisingFeishuNotifier()

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://example.com/hook",
                },
                clear=True,
            ):
                report = service.build_one_to_two_beta_readiness_report(
                    trade_date="2026-04-30",
                )

            self.assertEqual(report.status, "blocked")
            self.assertIn("feishu not ready", report.feishu_test.error or "")
            checks = {check.check_id: check for check in report.doctor_report.checks}
            self.assertEqual(checks["feishu"].status, "blocked")

    def test_beta_check_cli_rejects_no_notify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "beta-check",
                    "--sample-data",
                    "--no-notify",
                    "--trade-date",
                    "2026-04-30",
                    "--paper-store",
                    str(root / "paper_trades.json"),
                    "--notification-store",
                    str(root / "notifications.json"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["mode"], "beta-check")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("--no-notify", payload["summary"])

    def test_scheduler_runs_are_persisted_and_read_by_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scheduler_run_path = root / "scheduler_runs.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "schedule",
                    "--sample-data",
                    "--no-notify",
                    "--trade-date",
                    "2026-04-30",
                    "--at",
                    "09:31",
                    "--paper-store",
                    str(root / "paper_trades.json"),
                    "--scheduler-state",
                    str(root / "scheduler_state.json"),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["run_id"], "one-to-two-schedule-2026-04-30-09:31")
            self.assertEqual(payload["executed_count"], 4)
            records = SchedulerRunStore(scheduler_run_path).load()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run"]["executed_count"], 4)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "scheduler-runs",
                    "--scheduler-runs",
                    str(scheduler_run_path),
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
            audit_payload = json.loads(completed.stdout)

            self.assertEqual(audit_payload["mode"], "scheduler-runs")
            self.assertEqual(audit_payload["record_count"], 1)
            self.assertEqual(
                audit_payload["records"][0]["run"]["run_id"],
                "one-to-two-schedule-2026-04-30-09:31",
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

    def test_backtest_audit_reports_data_quality_and_admission_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            report = service.build_one_to_two_backtest_audit(
                end_date="2026-04-30",
                max_trade_days=30,
            )
            payload = contract_to_dict(report)

            self.assertIsInstance(report, OneToTwoBacktestAuditReport)
            self.assertEqual(report.status, "warning")
            self.assertEqual(report.usable_trade_days, 30)
            self.assertGreaterEqual(report.stability_report.sample_count, 1)
            self.assertIn("回测仍处观察期", report.summary)
            checks = {check.check_id: check for check in report.data_quality_checks}
            self.assertEqual(checks["data_window"].status, "ready")
            self.assertEqual(checks["sample_size"].status, "warning")
            self.assertEqual(checks["rule_version"].status, "ready")
            self.assertIn("Point-in-Time", report.limitations[0])
            self.assertEqual(payload["data_quality_checks"][0]["check_id"], "data_window")
            self.assertEqual(paper_store.load().closed_trades, ())

    def test_backtest_audit_cli_brief_prints_standard_flow_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "backtest-audit",
                    "--brief",
                    "--sample-data",
                    "--end-date",
                    "2026-04-30",
                    "--max-trade-days",
                    "30",
                    "--paper-store",
                    str(root / "paper_trades.json"),
                    "--notification-store",
                    str(root / "notifications.json"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )

            self.assertIn("FireMoney 回测准入：warning", completed.stdout)
            self.assertIn("数据质量：", completed.stdout)
            self.assertIn("样本数：warning", completed.stdout)
            self.assertIn("Point-in-Time", completed.stdout)
            self.assertFalse((root / "paper_trades.json").exists())

    def test_historical_replay_uses_as_of_candidate_and_future_bars_for_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            report = service.run_one_to_two_historical_replay(
                as_of_date="2026-04-30",
                holding_days=3,
            )
            payload = contract_to_dict(report)

            self.assertIsInstance(report, OneToTwoHistoricalReplayReport)
            self.assertEqual(report.status, "warning")
            self.assertEqual(report.as_of_date, "2026-04-30")
            self.assertIsNotNone(report.candidate)
            self.assertIsNotNone(report.trade)
            self.assertEqual(report.candidate.symbol, "600001")
            self.assertEqual(report.trade.entry_date, "2026-04-30")
            self.assertEqual(report.trade.exit_reason, "take_profit_first_target")
            self.assertGreater(report.trade.realized_pnl_pct, 0)
            self.assertGreater(report.trade.risk_reward_ratio, 1)
            self.assertTrue(
                any("后续日线只用于模拟卖点" in item for item in report.no_future_leakage_notes)
            )
            checks = {check.check_id: check for check in report.quality_checks}
            self.assertEqual(checks["no_future_selection"].status, "ready")
            self.assertEqual(checks["price_bars"].status, "ready")
            self.assertEqual(checks["daily_bar_sequence"].status, "warning")
            self.assertEqual(payload["trade"]["exit_reason"], "take_profit_first_target")

    def test_historical_replay_cli_brief_prints_profit_loss_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "replay",
                    "--brief",
                    "--sample-data",
                    "--trade-date",
                    "2026-04-30",
                    "--holding-days",
                    "3",
                    "--paper-store",
                    str(root / "paper_trades.json"),
                    "--notification-store",
                    str(root / "notifications.json"),
                    "--scheduler-state",
                    str(root / "scheduler_state.json"),
                    "--scheduler-runs",
                    str(root / "scheduler_runs.json"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )

            self.assertIn("FireMoney 历史逐日回放：warning", completed.stdout)
            self.assertIn("候选：", completed.stdout)
            self.assertIn("盈亏比：", completed.stdout)
            self.assertIn("无未来函数说明", completed.stdout)
            self.assertIn("后续日线只用于模拟卖点", completed.stdout)

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
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            scheduler_run_path.parent.mkdir(parents=True, exist_ok=True)
            scheduler_run_path.write_text("{}", encoding="utf-8")
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
                    "--scheduler-runs",
                    str(scheduler_run_path),
                    "--notification-store",
                    str(notifications_path),
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
            self.assertEqual(scheduler_run_path.read_text(encoding="utf-8"), "{}")
            self.assertFalse(notifications_path.exists())
            self.assertEqual(PaperTradeStore(paper_path).load().events, ())

    def test_beta_start_cli_blocks_before_scheduler_when_doctor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            scheduler_run_path.parent.mkdir(parents=True, exist_ok=True)
            scheduler_run_path.write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "beta-start",
                    "--sample-data",
                    "--trade-date",
                    "2026-04-30",
                    "--at",
                    "09:31",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                    "--notification-store",
                    str(notifications_path),
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
            self.assertEqual(scheduler_run_path.read_text(encoding="utf-8"), "{}")
            self.assertFalse(notifications_path.exists())
            self.assertEqual(PaperTradeStore(paper_path).load().events, ())

    def test_beta_start_cli_runs_due_scheduler_after_verified_feishu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            store = NotificationRecordStore(notifications_path)
            store.append(
                workflow="feishu:test",
                trade_date="2026-04-30",
                result=FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="FireMoney 一进二飞书测试",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            with FakeFeishuApiServer() as fake_feishu:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "client.desktop.firemoney_client.one_to_two_cli",
                        "beta-start",
                        "--sample-data",
                        "--trade-date",
                        "2026-04-30",
                        "--at",
                        "09:31",
                        "--paper-store",
                        str(paper_path),
                        "--scheduler-state",
                        str(scheduler_path),
                        "--scheduler-runs",
                        str(scheduler_run_path),
                        "--notification-store",
                        str(notifications_path),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env={
                        **os.environ,
                        "PYTHONIOENCODING": "utf-8",
                        "FEISHU_ENABLED": "true",
                        "FEISHU_APP_ID": "cli_test",
                        "FEISHU_APP_SECRET": "secret_test",
                        "FEISHU_RECEIVE_ID": "oc_test",
                        "FEISHU_API_BASE_URL": fake_feishu.url,
                    },
                    check=True,
                    capture_output=True,
                    encoding="utf-8",
                    text=True,
                )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["run_id"], "one-to-two-schedule-2026-04-30-09:31")
            self.assertEqual(payload["executed_count"], 4)
            self.assertEqual(SchedulerRunStore(scheduler_run_path).load()[0]["run"]["executed_count"], 4)
            account = PaperTradeStore(paper_path).load()
            self.assertEqual(len(account.positions), 1)
            self.assertTrue(
                any(record.workflow == "watch:open" for record in NotificationRecordStore(notifications_path).load())
            )
            self.assertGreaterEqual(
                sum(
                    1
                    for path, _, _ in fake_feishu.requests
                    if path.startswith("/open-apis/im/v1/messages")
                ),
                4,
            )

    def test_beta_rehearsal_runs_full_day_in_isolated_state(self) -> None:
        report = run_one_to_two_beta_rehearsal(
            trade_date="2026-04-30",
            market_data_provider=SampleMarketDataProvider(),
            trading_calendar=WeekdayTradingCalendar(),
        )
        payload = contract_to_dict(report)

        self.assertIsInstance(report, OneToTwoBetaRehearsalReport)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["trade_date"], "2026-04-30")
        self.assertEqual(len(payload["schedule_runs"]), 9)
        self.assertEqual(sum(run["executed_count"] for run in payload["schedule_runs"]), 9)
        self.assertEqual(payload["notification_record_count"], 9)
        self.assertGreaterEqual(payload["paper_event_count"], 3)
        self.assertIn(payload["doctor_report"]["status"], {"ready", "warning"})
        self.assertFalse(
            any(
                check["status"] == "blocked"
                for check in payload["doctor_report"]["checks"]
            )
        )
        self.assertEqual(payload["stability_report"]["status"], "observation")

    def test_beta_launch_plan_lists_next_trade_day_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                report = build_one_to_two_beta_launch_plan(
                    trade_date="2026-05-03",
                    service=service,
                    trading_calendar=WeekdayTradingCalendar(),
                )
            payload = contract_to_dict(report)

            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["requested_date"], "2026-05-03")
            self.assertEqual(payload["trade_date"], "2026-04-30")
            self.assertEqual(payload["next_trade_date"], "2026-05-06")
            self.assertEqual(payload["blockers"], [])
            self.assertIn("beta-plan-2026-05-03", payload["report_id"])
            self.assertIn("beta-check --trade-date 2026-05-06", payload["launch_commands"][1])
            self.assertIn("beta-start --trade-date 2026-05-06", payload["launch_commands"][2])

    def test_beta_plan_cli_is_read_only_and_returns_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "beta-plan",
                    "--sample-data",
                    "--trade-date",
                    "2026-05-03",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                    "--notification-store",
                    str(notifications_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["next_trade_date"], "2026-05-06")
            self.assertIn("beta-check --trade-date 2026-05-06", payload["launch_commands"][1])
            self.assertFalse(paper_path.exists())
            self.assertFalse(scheduler_path.exists())
            self.assertFalse(scheduler_run_path.exists())
            self.assertFalse(notifications_path.exists())

    def test_beta_plan_cli_brief_prints_human_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "beta-plan",
                    "--brief",
                    "--sample-data",
                    "--trade-date",
                    "2026-05-03",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                    "--notification-store",
                    str(notifications_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )

            self.assertIn("FireMoney Beta 上线计划：ready", completed.stdout)
            self.assertIn("下一交易日：2026-05-06", completed.stdout)
            self.assertIn("阻断项：无", completed.stdout)
            self.assertIn("beta-check --trade-date 2026-05-06", completed.stdout)
            self.assertFalse(paper_path.exists())
            self.assertFalse(scheduler_path.exists())
            self.assertFalse(scheduler_run_path.exists())
            self.assertFalse(notifications_path.exists())

    def test_beta_rehearsal_cli_does_not_touch_live_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "beta-rehearsal",
                    "--trade-date",
                    "2026-04-30",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                    "--notification-store",
                    str(notifications_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["trade_date"], "2026-04-30")
            self.assertFalse(paper_path.exists())
            self.assertFalse(scheduler_path.exists())
            self.assertFalse(scheduler_run_path.exists())
            self.assertFalse(notifications_path.exists())

    def test_beta_schedule_cli_rejects_no_notify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "schedule",
                    "--sample-data",
                    "--beta",
                    "--no-notify",
                    "--trade-date",
                    "2026-04-30",
                    "--at",
                    "09:31",
                    "--paper-store",
                    str(paper_path),
                    "--scheduler-state",
                    str(scheduler_path),
                    "--scheduler-runs",
                    str(scheduler_run_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["mode"], "schedule")
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("不能同时使用 --no-notify", payload["summary"])
            self.assertFalse(paper_path.exists())
            self.assertFalse(scheduler_path.exists())
            self.assertFalse(scheduler_run_path.exists())

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

    def test_feishu_notifier_checks_business_response_code(self) -> None:
        class FakeFeishuResponse:
            status = 200

            def __init__(self, body: bytes) -> None:
                self._body = body

            def __enter__(self) -> "FakeFeishuResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return self._body

        env = {
            "FEISHU_ENABLED": "true",
            "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
        }
        success_body = b'{"StatusCode":0,"StatusMessage":"success"}'
        failed_body = b'{"StatusCode":9499,"StatusMessage":"sign invalid"}'

        with patch.dict(os.environ, env, clear=True):
            with patch(
                "server.firemoney_server.infrastructure.feishu_notifier.request.urlopen",
                return_value=FakeFeishuResponse(success_body),
            ):
                sent = FeishuNotifier().notify("title", "message")
            with patch(
                "server.firemoney_server.infrastructure.feishu_notifier.request.urlopen",
                return_value=FakeFeishuResponse(failed_body),
            ):
                failed = FeishuNotifier().notify("title", "message")

        self.assertEqual(sent.status, NotificationStatus.SENT)
        self.assertEqual(failed.status, NotificationStatus.FAILED)
        self.assertIn("9499", failed.error or "")
        self.assertIn("sign invalid", failed.error or "")

    def test_feishu_notifier_sends_with_app_credentials(self) -> None:
        class FakeFeishuResponse:
            status = 200

            def __init__(self, body: bytes) -> None:
                self._body = body

            def __enter__(self) -> "FakeFeishuResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return self._body

        env = {
            "FEISHU_ENABLED": "true",
            "FEISHU_APP_ID": "cli_test",
            "FEISHU_APP_SECRET": "secret_test",
            "FEISHU_RECEIVE_ID": "oc_test",
            "FEISHU_RECEIVE_ID_TYPE": "chat_id",
        }
        captured = []

        def fake_urlopen(req, timeout=8):
            captured.append(req)
            if len(captured) == 1:
                return FakeFeishuResponse(
                    b'{"code":0,"tenant_access_token":"tenant_token"}'
                )
            return FakeFeishuResponse(b'{"code":0,"data":{"message_id":"om_test"}}')

        with patch.dict(os.environ, env, clear=True):
            with patch(
                "server.firemoney_server.infrastructure.feishu_notifier.request.urlopen",
                side_effect=fake_urlopen,
            ):
                sent = FeishuNotifier().notify("title", "message")

        self.assertEqual(sent.status, NotificationStatus.SENT)
        self.assertTrue(sent.webhook_configured)
        self.assertEqual(len(captured), 2)
        self.assertIn("/open-apis/auth/v3/tenant_access_token/internal", captured[0].full_url)
        self.assertIn(
            "/open-apis/im/v1/messages?receive_id_type=chat_id",
            captured[1].full_url,
        )
        self.assertEqual(captured[1].get_header("Authorization"), "Bearer tenant_token")
        send_payload = json.loads(captured[1].data.decode("utf-8"))
        self.assertEqual(send_payload["receive_id"], "oc_test")
        self.assertEqual(send_payload["msg_type"], "text")
        content = json.loads(send_payload["content"])
        self.assertIn("title", content["text"])
        self.assertIn("message", content["text"])

    def test_local_feishu_env_loads_only_allowed_missing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "feishu.env"
            env_path.write_text(
                "\n".join(
                    (
                        "FEISHU_ENABLED=true",
                        "FEISHU_APP_ID=cli_test",
                        "FEISHU_APP_SECRET=secret_test",
                        "FEISHU_RECEIVE_ID=oc_test",
                        "IGNORED_KEY=ignored",
                    )
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FEISHU_APP_ID": "already_set"}, clear=True):
                loaded = load_local_feishu_env(env_path)

                self.assertEqual(
                    loaded,
                    (
                        "FEISHU_ENABLED",
                        "FEISHU_APP_SECRET",
                        "FEISHU_RECEIVE_ID",
                    ),
                )
                self.assertEqual(os.environ["FEISHU_APP_ID"], "already_set")
                self.assertEqual(os.environ["FEISHU_RECEIVE_ID"], "oc_test")
                self.assertNotIn("IGNORED_KEY", os.environ)

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
        self.assertEqual(settings.min_score, 78)
        self.assertEqual(settings.max_position_pct, 0.08)
        self.assertEqual(settings.max_daily_trades, 1)
        self.assertEqual(settings.max_holding_trade_days, 2)
        self.assertEqual(settings.discipline_exit_min_gain_pct, 0.03)
        self.assertEqual(payload["parameters"]["min_confirm_open_pct"], 0.0)
        self.assertEqual(payload["parameters"]["max_confirm_open_pct"], 0.07)
        self.assertEqual(settings.min_confirm_open_pct, 0.0)
        self.assertEqual(settings.max_confirm_open_pct, 0.07)
        self.assertEqual(settings.first_take_profit_pct, 0.08)
        self.assertEqual(settings.strong_take_profit_pct, 0.15)
        self.assertEqual(settings.trailing_stop_pct, 0.06)
        self.assertEqual(settings.mainline_fade_score, 45)
        self.assertEqual(settings.min_low_breakout_first_board_count, 15)
        self.assertEqual(settings.min_low_breakout_ready_candidates, 2)
        self.assertIn("创业板", settings.excluded_boards)

    def test_preview_file_can_be_generated_without_legacy_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "core_workflow.html"

            output = build_preview(target)

            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("FireMoney 主线首板", html)
            self.assertIn("主线首板专项台", html)
            self.assertIn("候选池与封板纪律", html)
            self.assertIn("封板", html)
            self.assertIn("龙头", html)
            self.assertIn("主线首板候选", html)
            self.assertIn("低位平台突破", html)
            self.assertIn("主线持续性", html)
            self.assertIn("卖点计划", html)
            self.assertIn("盈利 8%", html)
            self.assertIn("消息", html)
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
            self.assertIn("Beta 预检", html)
            self.assertIn("beta-plan", html)
            self.assertIn("beta-plan --brief", html)
            self.assertIn("beta-rehearsal", html)
            self.assertIn("beta-check", html)
            self.assertIn("beta-start", html)
            self.assertIn("主线首板策略配置", html)
            self.assertIn("行情源", html)
            self.assertIn("飞书通知", html)
            self.assertIn("本地调度", html)
            self.assertIn("09:31", html)
            self.assertIn("watch / open", html)
            self.assertIn("已执行", html)
            self.assertIn("尾盘测评", html)
            self.assertIn("稳定性观察", html)
            self.assertIn("回测准入", html)
            self.assertIn("数据窗口", html)
            self.assertIn("幸存者偏差", html)
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
            self.assertNotIn("样例", html)
            self.assertNotIn("csv_export", html)
            self.assertNotIn("确认委托", html)
            self.assertNotIn("回执", html)
            self.assertNotIn("orders/draft-600001.csv", html)
            self.assertNotIn("AppData/Local/Temp", html)


if __name__ == "__main__":
    unittest.main()
