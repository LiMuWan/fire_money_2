import json
import importlib.util
import ast
import os
import subprocess
import sys
import tempfile
import unittest
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import URLError

from client.desktop.firemoney_client import LocalMainChainAdapter
from client.desktop.firemoney_client.cli.parser import build_one_to_two_parser
from client.desktop.firemoney_client.composition import build_local_main_chain_context
from client.desktop.firemoney_client.presenters.decision_presenter import (
    build_decision_cockpit_view,
)
from client.desktop.firemoney_client.presenters.notification_presenter import (
    first_notification_detail,
    notification_display_title,
)
from framework.config import (
    load_json_config,
    merge_env_overrides,
    require_config_keys,
)
from framework.scheduler import DueWindow, is_due_in_window
from framework.storage import SqliteMigration, apply_sqlite_migrations
from client.desktop.firemoney_client.preview import build_preview
from server.firemoney_server import MainChainService
from server.firemoney_server.application.beta_rehearsal import (
    build_one_to_two_beta_launch_plan,
    run_one_to_two_beta_rehearsal,
)
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.application.schedule_health_service import ScheduleHealthService
from server.firemoney_server.infrastructure.board_shadow_store import (
    LimitUpBoardShadowStore,
)
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
    LimitUpBoardShadowReport,
    LimitUpBoardShadowSystemMetric,
    LimitUpBoardShadowSystemReport,
    MainlineNewsItem,
    NotificationRecord,
    NotificationStatus,
    OneToTwoBacktestAuditReport,
    OneToTwoHistoricalReplayReport,
    OneToTwoMorningReport,
    OneToTwoBetaRehearsalReport,
    OneToTwoScheduleRun,
    OneToTwoScheduleTask,
    OneToTwoEventType,
    PaperBacktestEfficiencyCandidate,
    PaperBacktestFrictionScenario,
    PaperBacktestMonthlyMetric,
    PaperBacktestMonthlyStability,
    PaperBacktestReport,
    PaperBacktestReturnTarget,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    PaperAccount,
    PaperTradeRecord,
    PaperTradeStatus,
    PaperTradingGuardDecision,
    PaperTradingInstruction,
    StrategyDecisionReport,
    TradingDayContext,
    contract_to_dict,
)


def _build_service(
    root: Path,
    market_data_provider=None,
    paper_store: PaperTradeStore | None = None,
    feishu_notifier: FeishuNotifier | None = None,
    notification_store: NotificationRecordStore | None = None,
    scheduler_state_store: SchedulerStateStore | None = None,
    scheduler_run_store: SchedulerRunStore | None = None,
    board_shadow_store: LimitUpBoardShadowStore | None = None,
    trading_calendar=None,
) -> MainChainService:
    return MainChainService(
        market_data_provider=market_data_provider,
        paper_store=paper_store or PaperTradeStore(root / "paper_trades.json"),
        feishu_notifier=feishu_notifier,
        notification_store=notification_store
        or NotificationRecordStore(root / "notifications.json"),
        scheduler_state_store=scheduler_state_store
        or SchedulerStateStore(root / "scheduler_state.json"),
        scheduler_run_store=scheduler_run_store
        or SchedulerRunStore(root / "scheduler_runs.json"),
        board_shadow_store=board_shadow_store
        or LimitUpBoardShadowStore(root / "board_shadow_samples.json"),
        trading_calendar=trading_calendar or WeekdayTradingCalendar(),
    )


def _risk_break_row(trade_date: str) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="浣庝綅绐佺牬鍊欓€?",
        trade_date=trade_date,
        board="涓绘澘",
        is_st=False,
        is_delisting=False,
        listing_days=1200,
        latest_price=9.8,
        previous_close=9.56,
        limit_up_price=10.52,
        first_limit_up_time="10:05",
        sealed_amount=32000000,
        turnover_amount=220000000,
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
        theme="浣庝綅骞冲彴绐佺牬",
        market_temperature=74,
    )


def _weak_after_two_days_row(trade_date: str) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="浣庝綅绐佺牬鍊欓€?",
        trade_date=trade_date,
        board="涓绘澘",
        is_st=False,
        is_delisting=False,
        listing_days=1200,
        latest_price=10.6,
        previous_close=10.52,
        limit_up_price=11.57,
        first_limit_up_time="10:05",
        sealed_amount=32000000,
        turnover_amount=220000000,
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
        theme="浣庝綅骞冲彴绐佺牬",
        market_temperature=74,
    )


def _row_with_latest_price(trade_date: str, latest_price: float) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        **(
            _weak_after_two_days_row(trade_date).__dict__
            | {"latest_price": latest_price, "theme": "AI绔晶涓荤嚎"}
        )
    )


def _non_runner_row_with_latest_price(
    trade_date: str,
    latest_price: float,
) -> OneToTwoMarketRow:
    return OneToTwoMarketRow(
        symbol="600001",
        name="浣庝綅绐佺牬鍊欓€?",
        trade_date=trade_date,
        board="涓绘澘",
        is_st=False,
        is_delisting=False,
        listing_days=1200,
        latest_price=latest_price,
        previous_close=10.52,
        limit_up_price=11.57,
        first_limit_up_time="10:20",
        sealed_amount=22000000,
        turnover_amount=200000000,
        turnover_rate=14.0,
        open_pct=0.01,
        auction_amount=9000000,
        low_20=8.8,
        high_60=10.6,
        pressure_price=11.8,
        ma_5=10.1,
        ma_10=9.8,
        ma_20=9.3,
        recent_gain_pct=0.18,
        theme="普通轮动",
        market_temperature=70,
        first_board_count=50,
        volume_ratio_5=1.2,
        rsi_14=82.0,
        position_percentile_60=0.58,
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
                volume_ratio_5=row.volume_ratio_5,
                rsi_14=row.rsi_14,
                position_percentile_60=row.position_percentile_60,
                market_cap=row.market_cap,
                float_market_cap=row.float_market_cap,
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


class CountingOneToTwoProvider(StaticOneToTwoProvider):
    def __init__(self, rows: tuple[OneToTwoMarketRow, ...]) -> None:
        super().__init__(rows)
        self.row_load_count = 0

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        self.row_load_count += 1
        return super().load_one_to_two_rows(trade_date)


class SlowOneToTwoProvider(StaticOneToTwoProvider):
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        threading.Event().wait(1.0)
        return super().load_one_to_two_rows(trade_date)


def _board_shadow_bars(module):
    return [
        module.sm.DailyBar("2026-04-01", 9.0, 9.09, 9.1, 8.95, 10000)
        for _ in range(80)
    ] + [
        module.sm.DailyBar("2026-04-29", 9.3, 10.0, 10.0, 9.2, 100000),
        module.sm.DailyBar("2026-04-30", 10.0, 10.5, 10.6, 9.8, 100000),
    ]


def _board_shadow_market_fixture(
    module,
    count: int = 20,
    extra_down_count: int = 10,
    prior_start: float = 9.0,
    prior_close: float = 9.09,
    next_close: float = 10.5,
    next_high: float = 10.6,
):
    stocks = []
    histories = {}
    for index in range(count):
        symbol = f"600{index + 1:03d}"
        stock = module.sm.StockMeta(symbol, f"shadow board {index + 1}", None)
        stocks.append(stock)
        volume = 120000 if index == 0 else 100000 - index
        histories[symbol] = [
            module.sm.DailyBar(
                "2026-04-01",
                prior_start,
                prior_close,
                max(prior_start, prior_close) + 0.01,
                min(prior_start, prior_close) - 0.05,
                10000,
            )
            for _ in range(80)
        ] + [
            module.sm.DailyBar("2026-04-29", 9.3, 10.0, 10.0, 9.2, volume),
            module.sm.DailyBar("2026-04-30", 10.0, next_close, next_high, 9.8, volume),
        ]
    for index in range(extra_down_count):
        symbol = f"601{index + 1:03d}"
        stock = module.sm.StockMeta(symbol, f"shadow down {index + 1}", None)
        stocks.append(stock)
        histories[symbol] = [
            module.sm.DailyBar("2026-04-01", 9.0, 9.09, 9.1, 8.95, 10000)
            for _ in range(80)
        ] + [
            module.sm.DailyBar("2026-04-29", 9.0, 8.9, 9.1, 8.8, 10000),
            module.sm.DailyBar("2026-04-30", 8.9, 8.95, 9.0, 8.8, 10000),
        ]
    return stocks, histories


@contextmanager
def _workspace_temp_dir(name: str):
    root = Path(".firemoney") / "test_tmp" / name
    if root.exists():
        for child in root.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
    root.mkdir(parents=True, exist_ok=True)
    yield root


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
        name=f"鏍锋湰{index}",
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
        max_favorable_pct=max(0.0, realized_pnl_pct + 0.01),
        max_adverse_pct=0.004 if realized_pnl_pct > 0 else abs(realized_pnl_pct),
        profit_drawdown_ratio=(
            round(realized_pnl_pct / 0.004, 4) if realized_pnl_pct > 0 else 0.0
        ),
        entry_turnover_quality_score=92.0,
        entry_turnover_quality_label="强换手龙买点",
        entry_turnover_quality_notes=("test-quality",),
    )


def _seed_closed_trades(
    paper_store: PaperTradeStore,
    returns: tuple[float, ...],
) -> None:
    account = paper_store.load()
    paper_store.save(
        PaperAccount(
            account_id=account.account_id,
            last_trade_date="2026-04-29",
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=0,
            positions=account.positions,
            events=account.events,
            closed_trades=tuple(
                _closed_trade_record(index, realized_pnl_pct=value)
                for index, value in enumerate(returns, start=1)
            ),
        )
    )


def _downgrade_open_position_from_main_rise_runner(
    paper_store: PaperTradeStore,
) -> None:
    account = paper_store.load()
    if not account.positions:
        return
    paper_store.save(
        PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(
                replace(
                    account.positions[0],
                    entry_turnover_quality_score=74.0,
                    entry_turnover_quality_label="有效换手龙买点",
                ),
            ),
            events=account.events,
            closed_trades=account.closed_trades,
        )
    )


class FailingNotifier:
    def __init__(self, requests: list[object]) -> None:
        self.requests = requests
        self.webhook_url = "https://example.invalid/webhook"
        self.app_id = None
        self.app_secret = None

    def notify(self, title: str, message: str) -> FeishuNotificationResult:
        self.requests.append((title, message))
        return FeishuNotificationResult(
            status=NotificationStatus.FAILED,
            title=title,
            message=message,
            webhook_configured=True,
            error="test send failed",
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
            self.assertIn("board-shadow-system", payload["candidates"][0]["leader_label"])

    def test_limit_up_board_shadow_report_is_json_friendly(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_limit_up_board_shadow_report(
                    as_of_date="2026-04-29"
                )
            payload = contract_to_dict(report)

            self.assertIsInstance(report, LimitUpBoardShadowReport)
            self.assertEqual(report.status, "ready")
            self.assertEqual(report.candidate.symbol, "600001")
            self.assertEqual(report.trade.exit_reason, "take_profit")
            self.assertEqual(payload["candidate"]["take_profit_price"], 10.55)
            self.assertEqual(payload["candidate"]["market_seal_count"], 20)
            self.assertLess(payload["candidate"]["market_advance_ratio"], 0.7)
            self.assertEqual(payload["candidate"]["suggested_position_pct"], 0.08)
            self.assertIn("证据复盘", payload["limitations"][1])

    def test_limit_up_board_shadow_uses_dynamic_target_in_strong_market(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(
            module,
            extra_down_count=0,
            next_close=10.8,
            next_high=10.9,
        )
        with _workspace_temp_dir("board_shadow_dynamic_target") as root:
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_limit_up_board_shadow_report(
                    as_of_date="2026-04-29"
                )
            payload = contract_to_dict(report)

            self.assertEqual(report.status, "ready")
            self.assertEqual(report.trade.exit_reason, "take_profit")
            self.assertEqual(payload["candidate"]["take_profit_price"], 10.8)
            self.assertGreater(payload["candidate"]["market_advance_ratio"], 0.7)
            self.assertEqual(payload["candidate"]["suggested_position_pct"], 0.12)
            self.assertIn("8% 动态止盈", payload["candidate"]["risk_notes"][4])

    def test_k92_backtest_report_is_research_only_and_json_friendly(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(
            module,
            extra_down_count=0,
            next_close=10.8,
            next_high=10.9,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_k92_emotion_liquidity_backtest_report(
                    start_date="2026-04-01",
                    end_date="2026-04-30",
                )
            payload = contract_to_dict(report)

            self.assertIsInstance(report, PaperBacktestReport)
            self.assertEqual(report.strategy_id, "k92-emotion-liquidity-v1")
            self.assertIn(report.status, {"ready", "warning", "blocked"})
            self.assertEqual(report.overall.sample_count, 1)
            self.assertEqual(report.yearly[0].year, "2026")
            self.assertTrue(report.monthly)
            self.assertIn("研究影子回测", payload["limitations"][2])
            self.assertIn("不能写入模拟盘", payload["limitations"][2])

    def test_limit_up_board_shadow_dynamic_target_uses_board_day_breadth(self) -> None:
        module = self._load_board_profit_matrix_module()
        candidate = module.BoardCandidate(
            symbol="600001",
            name="board candidate",
            board_date="2026-04-30",
            index=0,
            entry_price=10.0,
            previous_close=9.09,
            close_pct=0.1,
            high_pct=0.1,
            estimated_turnover_amount=300_000_000.0,
            volume_ratio_20=1.5,
            recent_gain_pct=0.2,
            ma20_deviation_pct=0.2,
            position_percentile_60=0.7,
            first_board=True,
            ma_bullish=True,
            rank_score=12.0,
            market_seal_count=20,
            market_touch_count=30,
            market_advance_ratio=0.71,
        )
        exit_case = module.shadow_default_exit_case()

        self.assertEqual(module.resolve_take_profit_pct(candidate, exit_case), 0.08)
        self.assertEqual(module.resolve_position_pct(candidate, exit_case), 0.12)
        self.assertEqual(
            module.resolve_take_profit_pct(
                replace(candidate, market_advance_ratio=0.70),
                exit_case,
            ),
            0.055,
        )
        self.assertEqual(
            module.resolve_position_pct(
                replace(candidate, market_advance_ratio=0.70),
                exit_case,
            ),
            0.08,
        )

    def test_limit_up_board_shadow_does_not_mutate_one_to_two_paper_ledger(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_limit_up_board_shadow_report(
                    as_of_date="2026-04-29"
                )
            account = PaperTradeStore(root / "paper_trades.json").load()

            self.assertEqual(report.status, "ready")
            self.assertEqual(account.positions, ())
            self.assertEqual(account.events, ())
            self.assertEqual(account.closed_trades, ())

    def test_limit_up_board_shadow_blocks_cold_market_heat(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module, count=19)
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_limit_up_board_shadow_report(
                    as_of_date="2026-04-29"
                )

            self.assertEqual(report.status, "blocked")
            self.assertIsNone(report.candidate)
            self.assertIn("封板热度", report.quality_checks[-1].label)

    def test_limit_up_board_shadow_blocks_extended_recent_gain(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(
            module,
            count=20,
            prior_start=7.0,
            prior_close=7.2,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.build_limit_up_board_shadow_report(
                    as_of_date="2026-04-29"
                )

            self.assertEqual(report.status, "blocked")
            self.assertIsNone(report.candidate)
            self.assertIn("封板热度/候选", report.quality_checks[-1].label)

    def test_limit_up_board_shadow_record_builds_isolated_stability(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                board_shadow_store=LimitUpBoardShadowStore(
                    root / "board_shadow_samples.json",
                    created_at_provider=lambda: "20260501090000",
                ),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                first_report = service.record_limit_up_board_shadow_sample(
                    as_of_date="2026-04-29"
                )
                second_report = service.record_limit_up_board_shadow_sample(
                    as_of_date="2026-04-29"
                )
            stability = service.build_limit_up_board_shadow_stability_report()
            payload = contract_to_dict(stability)

            self.assertIn("board-shadow-2026-04-29-600001", first_report.summary)
            self.assertIn("board-shadow-2026-04-29-600001", second_report.summary)
            self.assertEqual(stability.sample_count, 1)
            self.assertEqual(stability.success_rate, 1.0)
            self.assertEqual(payload["recent_samples"][0]["created_at"], "20260501090000")
            self.assertEqual(payload["recent_samples"][0]["market_seal_count"], 20)

    def test_limit_up_board_shadow_record_notifies_without_touching_paper_ledger(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                board_shadow_store=LimitUpBoardShadowStore(
                    root / "board_shadow_samples.json",
                    created_at_provider=lambda: "20260501090000",
                ),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )
            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                report = service.record_limit_up_board_shadow_sample(
                    as_of_date="2026-04-29",
                    notify=False,
                )
            account = PaperTradeStore(root / "paper_trades.json").load()
            records = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(report.notification.status, NotificationStatus.PREPARED)
            self.assertEqual(records[0].workflow, "board-shadow:record")
            self.assertIn("独立影子样本账本", records[0].message)
            self.assertIn("不代表实盘交易指令", records[0].message)
            self.assertEqual(account.positions, ())
            self.assertEqual(account.events, ())
            self.assertEqual(account.closed_trades, ())

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
                turnover_amount=220000000,
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
                first_board_count=45,
                market_cap=10_000_000_000,
                float_market_cap=8_000_000_000,
            )
            one_word = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((one_word_row,)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            ).candidates[0]

            self.assertEqual(candidates["600001"].status, "ready")
            self.assertGreaterEqual(candidates["600001"].score, 82)
            self.assertIn("突破", candidates["600001"].position_profile.label)
            self.assertGreaterEqual(candidates["600001"].sealing_score, 18)
            self.assertGreaterEqual(candidates["600001"].leader_score, 16)
            self.assertGreaterEqual(candidates["600001"].turnover_quality_score, 86)
            self.assertTrue(candidates["600001"].turnover_quality_notes)
            self.assertIn("强换手龙", candidates["600001"].strategy_tags)
            self.assertIn("封板", candidates["600001"].discipline_summary)
            self.assertEqual(candidates["600002"].status, "blocked")
            self.assertTrue(
                any(
                    "高开" in blocker
                    or "高位" in blocker
                    or "乖离" in blocker
                    or "RSI 过热" in blocker
                    for blocker in candidates["600002"].blockers
                )
            )
            self.assertEqual(candidates["300003"].status, "blocked")
            self.assertTrue(any("创业板" in blocker for blocker in candidates["300003"].blockers))
            self.assertEqual(one_word.status, "blocked")
            self.assertTrue(
                any(
                    "一字板" in blocker
                    or "买不到" in blocker
                    or "高开" in blocker
                    for blocker in one_word.blockers
                )
            )

    def test_one_to_two_overheated_execution_score_is_watch_only(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
        overheated_row = replace(
            base_row,
            symbol="600099",
            first_limit_up_time="09:35",
            sealed_amount=120000000,
            turnover_amount=900000000,
            turnover_rate=8.0,
            open_pct=0.031,
            auction_amount=60000000,
            low_20=base_row.latest_price * 0.95,
            high_60=base_row.latest_price * 0.98,
            pressure_price=base_row.latest_price * 1.18,
            ma_5=base_row.latest_price * 0.99,
            ma_10=base_row.latest_price * 0.97,
            ma_20=base_row.latest_price * 0.95,
            recent_gain_pct=0.18,
            market_temperature=82,
            first_board_count=45,
            volume_ratio_5=2.0,
            rsi_14=72.0,
            position_percentile_60=0.78,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((overheated_row,)),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            ).candidates[0]

            self.assertEqual(candidate.status, "ready")
            self.assertGreaterEqual(candidate.score, 90)
            self.assertTrue(
                any(
                    "过热阈值" in warning or "一致性过强" in warning
                    for warning in candidate.warnings
                )
            )
            self.assertIn("board-shadow-system", candidate.strategy_tags)

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
            self.assertTrue(any("封板热度" in blocker for blocker in candidate.blockers))

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
            open_pct=0.051,
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
            self.assertTrue(any("未红盘" in blocker for blocker in candidates["600005"].blockers))
            self.assertEqual(candidates["600006"].status, "blocked")
            self.assertTrue(
                any("高开超过 3.5%" in blocker for blocker in candidates["600006"].blockers)
            )

    def test_one_to_two_requires_continuity_and_position_confirmation(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
        weak_volume_row = replace(
            base_row,
            symbol="600021",
            volume_ratio_5=0.8,
        )
        hot_rsi_row = replace(
            base_row,
            symbol="600022",
            rsi_14=91.0,
        )
        weak_position_row = replace(
            base_row,
            symbol="600023",
            position_percentile_60=0.42,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(
                    (weak_volume_row, hot_rsi_row, weak_position_row)
                ),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            candidates = {candidate.symbol: candidate for candidate in report.candidates}
            self.assertEqual(candidates["600021"].status, "blocked")
            self.assertTrue(any("量比不足" in blocker for blocker in candidates["600021"].blockers))
            self.assertEqual(candidates["600022"].status, "ready")
            self.assertIn("board-shadow-system", candidates["600022"].strategy_tags)
            self.assertEqual(candidates["600023"].status, "ready")
            self.assertIn("board-shadow-system", candidates["600023"].strategy_tags)

    def test_one_to_two_requires_turnover_dragon_quality(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
        weak_turnover_row = replace(
            base_row,
            symbol="600031",
            turnover_rate=1.8,
        )
        overheated_turnover_row = replace(
            base_row,
            symbol="600032",
            turnover_rate=22.0,
        )
        weak_seal_proxy_row = replace(
            base_row,
            symbol="600033",
            first_limit_up_time="11:10",
            sealed_amount=26000000,
            auction_amount=3000000,
            volume_ratio_5=1.1,
            rsi_14=82.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(
                    (weak_turnover_row, overheated_turnover_row, weak_seal_proxy_row)
                ),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            candidates = {candidate.symbol: candidate for candidate in report.candidates}
            self.assertEqual(candidates["600031"].status, "blocked")
            self.assertTrue(any("换手不足" in blocker for blocker in candidates["600031"].blockers))
            self.assertEqual(candidates["600032"].status, "blocked")
            self.assertTrue(any("换手过高" in blocker for blocker in candidates["600032"].blockers))
            self.assertEqual(candidates["600033"].status, "blocked")
            self.assertTrue(any("换手龙" in blocker for blocker in candidates["600033"].blockers))
            self.assertLess(candidates["600033"].turnover_quality_score, 72)

    def test_one_to_two_uses_turnover_rank_for_daily_core_pick(self) -> None:
        base_rows = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")
        with tempfile.TemporaryDirectory() as temp_dir:
            watch = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(base_rows[:6]),
            ).run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )

            self.assertEqual(watch.account.positions[0].symbol, "600001")

    def test_one_to_two_blocks_when_ready_pool_is_too_wide(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")[0]
        rows = tuple(
            replace(
                base_row,
                symbol=f"600{i:03d}",
                name=f"hot candidate {i}",
                first_board_count=80,
                sealed_amount=60000000,
                turnover_amount=220000000 + i * 1000000,
                open_pct=0.02,
                auction_amount=15000000,
            )
            for i in range(1, 21)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(rows),
            ).build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            self.assertEqual(report.status, "blocked")
            self.assertTrue(
                all(candidate.status == "blocked" for candidate in report.candidates)
            )
            self.assertTrue(
                any(
                    "超过 18" in blocker and "主线过散" in blocker
                    for blocker in report.candidates[0].blockers
                )
            )

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
            turnover_amount=220000000,
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
            first_board_count=45,
            volume_ratio_5=1.2,
            rsi_14=70.0,
            position_percentile_60=0.7,
            market_cap=10_000_000_000,
            float_market_cap=8_000_000_000,
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

            self.assertEqual(report.status, "data_unavailable")
            self.assertEqual(report.candidates, ())
            self.assertIn("行情数据不可用", report.summary)
            self.assertIn("今日战法：行情异常暂停", report.notification.message)
            self.assertNotIn("今日战法：防守空仓日", report.notification.message)
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
                    title="FireMoney 涓€杩涗簩椋炰功娴嬭瘯",
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
                    title="FireMoney 涓€杩涗簩椋炰功娴嬭瘯",
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
            self.assertIn("飞书应用机器人已配置", checks["feishu"].detail)

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

    def test_doctor_report_blocks_when_market_data_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SlowOneToTwoProvider(
                    SampleMarketDataProvider().load_one_to_two_rows("2026-05-01")
                ),
            )

            report = service.build_one_to_two_doctor_report(
                trade_date="2026-05-01",
                market_data_timeout_seconds=0.01,
            )
            checks = {check.check_id: check for check in report.checks}

            self.assertEqual(report.status, "blocked")
            self.assertEqual(checks["market_data"].status, "blocked")
            self.assertIn("超过 0 秒未返回", checks["market_data"].detail)

    def test_doctor_report_explains_missing_akshare_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=AkshareMarketDataProvider(),
            )

            with patch(
                "server.firemoney_server.application.doctor_review_service.importlib.util.find_spec",
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
                            "所属概念": "消费电子",
                            "封板资金": 30000000,
                            "总市值": 12000000000,
                            "流通市值": 8500000000,
                        }
                    ]
                )

            def stock_zh_a_spot_em(self) -> FakeFrame:
                self.spot_calls += 1
                raise RuntimeError("spot snapshot unavailable")

            def stock_zh_a_hist(self, **_kwargs: object) -> FakeFrame:
                return FakeFrame(
                    [
                        {"收盘": 9.0, "最低": 8.8, "最高": 9.4, "成交量": 1000},
                        {"收盘": 9.4, "最低": 9.0, "最高": 9.8, "成交量": 1200},
                        {"收盘": 10.0, "最低": 9.6, "最高": 10.8, "成交量": 1800},
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
        self.assertEqual(rows[0].theme, "消费电子")
        self.assertGreaterEqual(rows[0].market_temperature, 50)

    def test_akshare_provider_keeps_daily_scan_fast_by_default(self) -> None:
        class FakeFrame:
            def __init__(self, records: list[dict[str, object]]) -> None:
                self._records = records

            def to_dict(self, orient: str) -> list[dict[str, object]]:
                if orient != "records":
                    raise AssertionError(f"unexpected orient: {orient}")
                return self._records

        class FakeAk:
            def __init__(self) -> None:
                self.history_calls = 0

            def stock_zt_pool_previous_em(self, date: str) -> FakeFrame:
                if date != "20260430":
                    raise AssertionError(f"unexpected date: {date}")
                return FakeFrame(
                    [
                        {
                            "代码": "600123",
                            "名称": "快速扫描",
                            "最新价": 11.0,
                            "涨停价": 11.0,
                            "成交额": 220000000,
                            "换手率": 6.0,
                            "昨日封板时间": "100500",
                            "昨日连板数": 1,
                            "竞价金额": 12000000,
                            "开盘涨幅": 2.4,
                            "所属概念": "消费电子",
                            "封板资金": 30000000,
                            "总市值": 12000000000,
                            "流通市值": 8500000000,
                        }
                    ]
                )

            def stock_zh_a_spot_em(self) -> FakeFrame:
                return FakeFrame([])

            def stock_zh_a_hist(self, **_kwargs: object) -> FakeFrame:
                self.history_calls += 1
                return FakeFrame([])

        real_import = __import__
        fake_ak = FakeAk()

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = AkshareMarketDataProvider(cache_dir=Path(temp_dir))
            with patch("builtins.__import__", side_effect=fake_import):
                rows = provider.load_one_to_two_rows("2026-04-30")

        self.assertEqual(len(rows), 1)
        self.assertEqual(fake_ak.history_calls, 0)
        self.assertEqual(rows[0].market_cap, 12000000000)
        self.assertEqual(rows[0].float_market_cap, 8500000000)
        self.assertEqual(rows[0].volume_ratio_5, 1.5)
        self.assertEqual(rows[0].sealed_amount, 30000000)
        self.assertEqual(rows[0].auction_amount, 12000000)

    def test_akshare_provider_reuses_normalized_daily_rows_from_disk(self) -> None:
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

            def stock_zt_pool_previous_em(self, date: str) -> FakeFrame:
                if date != "20260430":
                    raise AssertionError(f"unexpected date: {date}")
                self.previous_calls += 1
                return FakeFrame(
                    [
                        {
                            "代码": "600123",
                            "名称": "缓存扫描",
                            "最新价": 11.0,
                            "涨停价": 11.0,
                            "成交额": 220000000,
                            "换手率": 6.0,
                            "昨日封板时间": "100500",
                            "昨日连板数": 1,
                            "开盘涨幅": 2.4,
                            "所属概念": "消费电子",
                            "总市值": 12000000000,
                            "流通市值": 8500000000,
                        }
                    ]
                )

            def stock_zh_a_spot_em(self) -> FakeFrame:
                return FakeFrame([])

        real_import = __import__
        fake_ak = FakeAk()

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=60)
            with patch("builtins.__import__", side_effect=fake_import):
                first = provider.load_one_to_two_rows("2026-04-30")
            second_provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=60)
            with patch("builtins.__import__", side_effect=fake_import):
                second = second_provider.load_one_to_two_rows("2026-04-30")

        self.assertEqual(fake_ak.previous_calls, 1)
        self.assertEqual(second, first)

    def test_akshare_provider_uses_stale_same_day_cache_when_refresh_fails(self) -> None:
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

            def stock_zt_pool_previous_em(self, date: str) -> FakeFrame:
                self.previous_calls += 1
                if self.previous_calls > 1:
                    raise RuntimeError("temporary akshare outage")
                return FakeFrame(
                    [
                        {
                            "代码": "600123",
                            "名称": "缓存兜底",
                            "最新价": 11.0,
                            "涨停价": 11.0,
                            "成交额": 220000000,
                            "换手率": 6.0,
                            "昨日封板时间": "100500",
                            "昨日连板数": 1,
                            "开盘涨幅": 2.4,
                            "所属概念": "消费电子",
                            "总市值": 12000000000,
                            "流通市值": 8500000000,
                        }
                    ]
                )

            def stock_zh_a_spot_em(self) -> FakeFrame:
                return FakeFrame([])

        real_import = __import__
        fake_ak = FakeAk()

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=60)
            with patch("builtins.__import__", side_effect=fake_import):
                first = provider.load_one_to_two_rows("2026-04-30")
            cache_file = root / "2026-04-30_one_to_two_rows.json"
            stale_time = 1000000000
            os.utime(cache_file, (stale_time, stale_time))
            second_provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=1)
            with patch("builtins.__import__", side_effect=fake_import):
                second = second_provider.load_one_to_two_rows("2026-04-30")

        self.assertEqual(fake_ak.previous_calls, 2)
        self.assertEqual(second, first)

    def test_sample_market_data_provider_exposes_intraday_scaffolding(self) -> None:
        provider = SampleMarketDataProvider()

        minute_bars = provider.load_intraday_bars("600001", "2026-04-30")
        ticks = provider.load_tick_snapshots("600001", "2026-04-30")

        self.assertGreaterEqual(len(minute_bars), 2)
        self.assertEqual(minute_bars[0].timestamp, "09:31")
        self.assertGreaterEqual(len(ticks), 2)
        self.assertEqual(ticks[0].timestamp, "09:30:05")
        self.assertGreater(ticks[0].bid_volume_1, 0)

    def test_akshare_provider_intraday_scaffolding_returns_data_or_clear_failure(self) -> None:
        provider = AkshareMarketDataProvider()

        try:
            minute_bars = provider.load_intraday_bars("000001", "2026-05-06")
        except Exception as exc:
            self.assertIn("intraday", str(exc).lower())
        else:
            self.assertGreater(len(minute_bars), 0)
            self.assertEqual(minute_bars[0].trade_date, "2026-05-06")
            self.assertTrue(len(minute_bars[0].timestamp) >= 5)

        try:
            tick_snapshots = provider.load_tick_snapshots("000001", "2026-05-06")
        except Exception as exc:
            self.assertIn("tick", str(exc).lower())
        else:
            self.assertGreater(len(tick_snapshots), 0)
            self.assertEqual(tick_snapshots[0].trade_date, "2026-05-06")
            self.assertTrue(len(tick_snapshots[0].timestamp) >= 8)

    def test_akshare_provider_intraday_bars_filter_to_requested_trade_date(self) -> None:
        provider = AkshareMarketDataProvider()

        try:
            minute_bars = provider.load_intraday_bars("000001", "2026-05-06")
        except Exception as exc:
            self.assertIn("intraday", str(exc).lower())
        else:
            self.assertGreater(len(minute_bars), 0)
            self.assertTrue(all(item.trade_date == "2026-05-06" for item in minute_bars))

    def test_akshare_provider_caches_intraday_minute_history_by_symbol(self) -> None:
        class FakeFrame:
            def __init__(self, records: list[dict[str, object]]) -> None:
                self._records = records

            def to_dict(self, orient: str) -> list[dict[str, object]]:
                if orient != "records":
                    raise AssertionError(f"unexpected orient: {orient}")
                return self._records

        class FakeAk:
            def __init__(self) -> None:
                self.minute_calls = 0

            def stock_zh_a_tick_tx_js(self, symbol: str) -> FakeFrame:
                raise RuntimeError(f"tick disabled for {symbol}")

            def stock_zh_a_minute(self, symbol: str, period: str, adjust: str) -> FakeFrame:
                self.minute_calls += 1
                return FakeFrame(
                    [
                        {"day": "2026-05-05 10:30:00", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1000, "amount": 10100},
                        {"day": "2026-05-06 10:30:00", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "volume": 1200, "amount": 12240},
                        {"day": "2026-05-06 11:30:00", "open": 10.2, "high": 10.4, "low": 10.1, "close": 10.3, "volume": 1500, "amount": 15450},
                    ]
                )

        real_import = __import__
        fake_ak = FakeAk()
        ticks = iter((100.0, 101.0, 102.0, 103.0))

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = AkshareMarketDataProvider(
                cache_dir=Path(temp_dir),
                cache_ttl_seconds=60,
            )
            with patch("builtins.__import__", side_effect=fake_import), patch(
                "server.firemoney_server.infrastructure.market_data.time.monotonic",
                side_effect=lambda: next(ticks),
            ):
                first = provider.load_intraday_bars("000001", "2026-05-06", interval_minutes=60)
                second = provider.load_intraday_bars("000001", "2026-05-06", interval_minutes=60)

        self.assertEqual(fake_ak.minute_calls, 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertTrue(all(item.trade_date == "2026-05-06" for item in first))

    def test_akshare_provider_persists_intraday_minute_cache_to_disk(self) -> None:
        class FakeFrame:
            def __init__(self, records: list[dict[str, object]]) -> None:
                self._records = records

            def to_dict(self, orient: str) -> list[dict[str, object]]:
                if orient != "records":
                    raise AssertionError(f"unexpected orient: {orient}")
                return self._records

        class FakeAk:
            def __init__(self) -> None:
                self.minute_calls = 0

            def stock_zh_a_tick_tx_js(self, symbol: str) -> FakeFrame:
                raise RuntimeError("tick disabled")

            def stock_zh_a_minute(self, symbol: str, period: str, adjust: str) -> FakeFrame:
                self.minute_calls += 1
                return FakeFrame(
                    [
                        {"day": "2026-05-06 10:30:00", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "volume": 1200, "amount": 12240},
                        {"day": "2026-05-06 11:30:00", "open": 10.2, "high": 10.4, "low": 10.1, "close": 10.3, "volume": 1500, "amount": 15450},
                    ]
                )

        real_import = __import__
        fake_ak = FakeAk()
        ticks = iter((100.0, 101.0, 102.0, 103.0))

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "akshare":
                return fake_ak
            return real_import(name, *args, **kwargs)

        with _workspace_temp_dir("akshare_intraday_cache_disk") as root:
            provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=60)
            with patch("builtins.__import__", side_effect=fake_import), patch(
                "server.firemoney_server.infrastructure.market_data.time.monotonic",
                side_effect=lambda: next(ticks),
            ):
                first = provider.load_intraday_bars("000001", "2026-05-06", interval_minutes=60)

            second_provider = AkshareMarketDataProvider(cache_dir=root, cache_ttl_seconds=60)
            with patch("builtins.__import__", side_effect=fake_import):
                second = second_provider.load_intraday_bars("000001", "2026-05-06", interval_minutes=60)

        self.assertEqual(fake_ak.minute_calls, 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertTrue(all(item.trade_date == "2026-05-06" for item in second))

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
            self.assertEqual(watch.account.initial_cash, 10000.0)
            self.assertEqual(position.quantity, 100)
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
            self.assertEqual(candidate.exit_plan.strong_take_profit_pct, 0.08)
            self.assertGreater(candidate.exit_plan.stop_loss_pct, 0)
            self.assertLessEqual(candidate.exit_plan.stop_loss_pct, 0.06)
            self.assertEqual(candidate.exit_plan.trailing_stop_pct, 0.02)
            self.assertIn("封板波段主线", candidate.exit_plan.summary)
            self.assertIn("第一止盈", candidate.exit_plan.summary)
            self.assertIn("最长持有 1 个交易日", candidate.exit_plan.summary)
            self.assertGreaterEqual(candidate.mainline_continuity.score, 45)
            self.assertIsNotNone(position.exit_plan)
            self.assertIsNotNone(position.mainline_continuity)
            self.assertIn("封板波段主线", position.risk_note)

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
                **(profit_row.__dict__ | {"latest_price": 14.1, "theme": "AI绔晶涓荤嚎"})
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

    def test_positive_profit_is_locked_before_first_target(self) -> None:
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
            _downgrade_open_position_from_main_rise_runner(
                service._paper_store,
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-06", 10.9),)
                ),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.events[0].event_type.value, "take_profit")
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "positive_profit_lock")
            self.assertGreater(risk.account.closed_trades[0].realized_pnl, 0)

    def test_main_rise_runner_holds_after_base_profit_lock(self) -> None:
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
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-06", 10.95),)
                ),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            decision = service.build_paper_trading_decision_report(
                trade_date="2026-05-06",
            )

            self.assertEqual(len(risk.account.positions), 1)
            self.assertEqual(risk.account.closed_trades, ())
            self.assertEqual(decision.status, "holding")
            self.assertIsNotNone(decision.holding_instruction)
            self.assertEqual(
                decision.holding_instruction.status,
                "main_rise_runner_hold",
            )
            self.assertTrue(
                any("主升持有保护线" in item for item in decision.holding_instruction.sell_triggers)
            )

    def test_regular_signal_still_locks_base_profit(self) -> None:
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
            _downgrade_open_position_from_main_rise_runner(
                service._paper_store,
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-06", 10.95),)
                ),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(
                risk.account.closed_trades[0].exit_reason,
                "positive_profit_lock",
            )

    def test_main_rise_runner_trailing_lock_after_six_percent_peak(self) -> None:
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
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-06", 11.25),)
                ),
            )
            high = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            self.assertEqual(len(high.account.positions), 1)
            self.assertEqual(high.account.positions[0].peak_price, 11.25)

            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-07", 11.0),)
                ),
            )
            risk = service.run_one_to_two_watch(
                trade_date="2026-05-07",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.events[0].event_type.value, "take_profit")
            self.assertEqual(
                risk.account.closed_trades[0].exit_reason,
                "main_rise_runner_trailing_lock",
            )

    def test_main_rise_runner_profit_floor_locks_before_round_trip(self) -> None:
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
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-06", 10.95),)
                ),
            )
            high = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            self.assertEqual(len(high.account.positions), 1)

            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(
                    (_row_with_latest_price("2026-05-07", 10.67),)
                ),
            )
            risk = service.run_one_to_two_watch(
                trade_date="2026-05-07",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(
                risk.account.closed_trades[0].exit_reason,
                "main_rise_runner_trailing_lock",
            )
            self.assertGreater(risk.account.closed_trades[0].realized_pnl, 0)

    def test_positive_profit_lock_waits_until_profit_covers_intratrade_drawdown(self) -> None:
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
            _downgrade_open_position_from_main_rise_runner(
                service._paper_store,
            )
            pullback_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-04").__dict__
                    | {"latest_price": 10.0, "theme": "AI绔晶涓荤嚎"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((pullback_row,)),
            )
            pullback = service.run_one_to_two_watch(
                trade_date="2026-05-04",
                phase="risk",
                notify=False,
            )
            self.assertEqual(pullback.account.positions[0].trough_price, 10.0)

            weak_profit_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-05").__dict__
                    | {"latest_price": 10.9, "theme": "AI绔晶涓荤嚎"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((weak_profit_row,)),
            )
            weak_profit = service.run_one_to_two_watch(
                trade_date="2026-05-05",
                phase="risk",
                notify=False,
            )
            self.assertEqual(len(weak_profit.account.positions), 1)
            self.assertEqual(weak_profit.account.closed_trades, ())

            quality_profit_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-06").__dict__
                    | {"latest_price": 11.1, "theme": "AI绔晶涓荤嚎"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((quality_profit_row,)),
            )
            quality_profit = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(quality_profit.account.positions, ())
            self.assertEqual(
                quality_profit.account.closed_trades[0].exit_reason,
                "positive_profit_lock",
            )
            self.assertGreater(
                quality_profit.account.closed_trades[0].profit_drawdown_ratio,
                1.0,
            )

    def test_weekly_hard_limit_keeps_position_duration_below_one_week(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(()),
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(
                risk.account.closed_trades[0].exit_reason,
                "discipline_weak_after_1_days",
            )
            self.assertLessEqual(risk.account.closed_trades[0].holding_trade_days, 5)

    def test_paper_trading_database_records_buy_sell_and_returns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            db_path = root / "paper_trades.sqlite3"
            paper_store = PaperTradeStore(paper_path, database_path=db_path)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            buy_report = service.build_paper_trade_database_report(
                database_path=db_path,
            )

            profit_row = _weak_after_two_days_row("2026-05-06")
            profit_row = OneToTwoMarketRow(
                **(profit_row.__dict__ | {"latest_price": 14.1, "theme": "AI绔晶涓荤嚎"})
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((profit_row,)),
                paper_store=paper_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            sell_report = service.build_paper_trade_database_report(
                database_path=db_path,
            )

            self.assertTrue(db_path.exists())
            self.assertIsInstance(buy_report, PaperTradeDatabaseReport)
            self.assertEqual(buy_report.open_position_count, 1)
            self.assertEqual(buy_report.daily_audits[0].trade_date, buy_report.last_trade_date)
            self.assertEqual(buy_report.daily_audits[0].action, "buy")
            self.assertEqual(buy_report.daily_audits[0].buy_count, 1)
            self.assertIn("买入", buy_report.daily_audits[0].summary)
            self.assertEqual(buy_report.positions[0].planned_stop_risk_pct, 0.0599)
            self.assertEqual(
                buy_report.positions[0].planned_first_target_return_pct,
                0.0798,
            )
            self.assertEqual(buy_report.positions[0].planned_reward_risk_ratio, 1.3322)
            self.assertGreaterEqual(
                buy_report.positions[0].entry_turnover_quality_score,
                86,
            )
            self.assertEqual(
                buy_report.positions[0].entry_turnover_quality_label,
                "board-shadow validated mainline",
            )
            self.assertTrue(
                buy_report.positions[0].entry_turnover_quality_notes,
            )
            self.assertEqual(buy_report.positions[0].entry_guard_status, "warmup")
            self.assertEqual(buy_report.positions[0].entry_guard_action, "allow_reduced")
            self.assertEqual(
                buy_report.positions[0].entry_guard_suggested_position_pct,
                0.12,
            )
            self.assertEqual(
                buy_report.positions[0].entry_guard_quality_bucket,
                "strong_turnover_dragon",
            )
            self.assertGreaterEqual(buy_report.event_count, 1)
            self.assertEqual(buy_report.recent_events[0].event_type, "paper_buy")
            self.assertEqual(sell_report.open_position_count, 0)
            self.assertEqual(sell_report.closed_trade_count, 1)
            self.assertEqual(sell_report.daily_audits[0].trade_date, "2026-05-06")
            self.assertEqual(sell_report.daily_audits[0].action, "sell")
            self.assertEqual(sell_report.daily_audits[0].sell_count, 1)
            self.assertGreater(sell_report.daily_audits[0].realized_pnl, 0)
            self.assertIn("卖出", sell_report.daily_audits[0].summary)
            self.assertGreater(sell_report.total_realized_pnl, 0)
            self.assertGreater(sell_report.total_realized_return_pct, 0)
            self.assertEqual(sell_report.win_rate, 1.0)
            self.assertEqual(sell_report.recent_trades[0].exit_reason, "take_profit_first_target")
            self.assertGreater(sell_report.recent_trades[0].max_favorable_pct, 0)
            self.assertEqual(sell_report.recent_trades[0].max_adverse_pct, 0)
            self.assertEqual(sell_report.recent_trades[0].profit_drawdown_ratio, 99.0)
            self.assertEqual(sell_report.recent_trades[0].planned_stop_risk_pct, 0.0599)
            self.assertEqual(
                sell_report.recent_trades[0].planned_first_target_return_pct,
                0.0798,
            )
            self.assertEqual(
                sell_report.recent_trades[0].planned_reward_risk_ratio,
                1.3322,
            )
            self.assertGreaterEqual(
                sell_report.recent_trades[0].entry_turnover_quality_score,
                86,
            )
            self.assertEqual(
                sell_report.recent_trades[0].entry_turnover_quality_label,
                "board-shadow validated mainline",
            )
            self.assertTrue(
                sell_report.recent_trades[0].entry_turnover_quality_notes,
            )
            self.assertEqual(
                sell_report.recent_trades[0].entry_guard_status,
                "warmup",
            )
            self.assertEqual(
                sell_report.recent_trades[0].entry_guard_action,
                "allow_reduced",
            )
            self.assertEqual(
                sell_report.recent_trades[0].entry_guard_quality_bucket,
                "strong_turnover_dragon",
            )
            self.assertEqual(len(sell_report.quality_buckets), 1)
            self.assertEqual(
                sell_report.quality_buckets[0].bucket,
                "strong_turnover_dragon",
            )
            self.assertEqual(sell_report.quality_buckets[0].trade_count, 1)
            self.assertEqual(sell_report.quality_buckets[0].win_rate, 1.0)
            self.assertGreater(
                sell_report.quality_buckets[0].average_realized_return_pct,
                0,
            )
            self.assertEqual(
                sell_report.quality_buckets[0].risk_quality_pass_rate,
                1.0,
            )
            self.assertEqual(len(sell_report.guard_buckets), 1)
            self.assertEqual(sell_report.guard_buckets[0].bucket, "allow_reduced")
            self.assertEqual(sell_report.guard_buckets[0].trade_count, 1)
            self.assertEqual(sell_report.guard_buckets[0].win_rate, 1.0)
            self.assertEqual(
                sell_report.guard_buckets[0].average_suggested_position_pct,
                0.12,
            )
            self.assertGreater(
                sell_report.guard_buckets[0].average_realized_return_pct,
                0,
            )
            self.assertEqual(
                sell_report.guard_buckets[0].risk_quality_pass_rate,
                1.0,
            )
            self.assertGreater(sell_report.average_profit_drawdown_ratio, 0)
            self.assertEqual(sell_report.risk_quality_pass_rate, 1.0)

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
                        "theme": "AI缁旑垯鏅舵稉鑽ゅ殠",
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
                        "theme": "AI缁旑垯鏅舵稉鑽ゅ殠",
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
            self.assertEqual(
                risk.account.closed_trades[0].exit_reason,
                "mainline_fade_profit_protect",
            )

    def _legacy_mainline_news_mojibake_assertion(self) -> None:
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
                    title="AI绔晶涓荤嚎缁х画鍙戦叺",
                    source="涓滄柟璐㈠瘜",
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

            self.assertIn("涓荤嚎鎸佺画鎬?", risk.notification.message)
            self.assertIn("娑堟伅 1 鏉?", risk.notification.message)
            self.assertIn("AI绔晶涓荤嚎缁х画鍙戦叺", risk.notification.message)

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
            self.assertIn("消息精华", morning.notification.message)
            self.assertIn("资金动向", morning.notification.message)
            self.assertIn("资金画像", morning.notification.message)
            self.assertIn("操作解读", morning.notification.message)
            self.assertIn("小账户本金 10000.00", morning.notification.message)
            self.assertIn("小账户一手制上限", morning.notification.message)
            self.assertIn("T+1", morning.notification.message)
            self.assertIn("卖点纪律", morning.notification.message)
            self.assertIn("主线持续性", morning.notification.message)
            self.assertIn("模拟买入", open_trigger.notification.message)
            self.assertIn("纪律状态", open_trigger.notification.message)
            self.assertIn("卖点计划", open_trigger.notification.message)
            self.assertIn("模拟盘不是实盘", open_trigger.notification.message)
            self.assertIn("样本少于 30 笔", eod.notification.message)
            self.assertIn("最新样本：暂无完成样本", eod.notification.message)

    def test_morning_report_includes_news_digest_and_capital_flow_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            news = (
                MainlineNewsItem(
                    title="AI主线订单继续落地，算力方向活跃",
                    source="财联社",
                    published_at="2026-05-01 08:20",
                    related_symbols=("600001",),
                ),
            )
            service = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(
                    SampleMarketDataProvider().load_one_to_two_rows("2026-05-01"),
                    news=news,
                ),
            )

            morning = service.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )

            self.assertIn("消息精华：AI主线订单继续落地", morning.notification.message)
            self.assertIn("资金动向：市场温度", morning.notification.message)
            self.assertIn("资金画像：", morning.notification.message)
            self.assertIn("封板资金：", morning.notification.message)
            self.assertIn("操作解读：只盯", morning.notification.message)

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

            self.assertEqual(len(records), 3)
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

    def test_watch_feishu_only_records_real_buy_and_sell_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = NotificationRecordStore(root / "notifications.json")
            paper_store = PaperTradeStore(root / "paper_trades.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
                notification_store=store,
            )

            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="scan",
                notify=False,
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="auction",
                notify=False,
            )
            no_action_records = NotificationRecordStore(root / "notifications.json").load()

            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(()),
                paper_store=paper_store,
                notification_store=store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-08",
                phase="risk",
                notify=False,
            )
            records = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(no_action_records, ())
            self.assertEqual(
                [record.workflow for record in records],
                ["watch:risk", "watch:open"],
            )
            self.assertIn("模拟卖出", records[0].title)
            self.assertIn("模拟卖出", records[0].message)
            self.assertIn("收益质量", records[0].message)
            self.assertIn("模拟买入", records[1].title)
            self.assertIn("模拟买入", records[1].message)

    def _legacy_take_profit_notification_old_lock_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            notification_store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
                notification_store=notification_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            profit_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-06").__dict__
                    | {"latest_price": 10.9, "theme": "AI绔晶涓荤嚎"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((profit_row,)),
                paper_store=paper_store,
                notification_store=notification_store,
            )

            service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            records = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(records[0].workflow, "watch:risk")
            self.assertIn("模拟卖出", records[0].title)
            self.assertIn("positive_profit_lock", records[0].message)

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
            store.append(
                workflow="watch:auction",
                trade_date="2026-05-01",
                result=FeishuNotificationResult(
                    status=NotificationStatus.PREPARED,
                    title="FireMoney 主线首板盘中",
                    message="竞价确认，留在本地审计。",
                    webhook_configured=False,
                    error="notification skipped",
                ),
            )
            store.append(
                workflow="watch:risk",
                trade_date="2026-05-01",
                result=FeishuNotificationResult(
                    status=NotificationStatus.PREPARED,
                    title="FireMoney 主线首板盘中",
                    message="完成样本：主线首板候选(600001)\n实现盈亏：10.00 (1.00%)",
                    webhook_configured=False,
                    error="notification skipped",
                ),
            )
            action_records = service.load_notification_records(action_only=True)
            self.assertEqual(
                {record.workflow for record in action_records},
                {"morning", "watch:open", "watch:risk", "eod"},
            )

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

            action_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "notifications",
                    "--notification-store",
                    str(store.path),
                    "--action-only",
                    "--limit",
                    "10",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            action_payload = json.loads(action_completed.stdout)

            self.assertEqual(action_payload["record_count"], 4)
            self.assertNotIn("watch:auction", json.dumps(action_payload, ensure_ascii=False))

            action_brief = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "notifications",
                    "--notification-store",
                    str(store.path),
                    "--action-only",
                    "--brief",
                    "--limit",
                    "10",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )

            self.assertIn("飞书行动流", action_brief.stdout)
            self.assertIn("FireMoney 早评", action_brief.stdout)
            self.assertIn("watch:open", action_brief.stdout)
            self.assertNotIn('"records"', action_brief.stdout)

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
            service._notification_orchestrator = type(service._notification_orchestrator)(
                sender=SendingFeishuNotifier(),
                store=service._notification_store,
            )

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

    def test_non_trading_day_does_not_send_morning_or_eod_notifications(self) -> None:
        class RaisingFeishuNotifier:
            def notify(self, title: str, message: str) -> FeishuNotificationResult:
                raise AssertionError("non-trading morning/eod must not send Feishu")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )
            service._feishu_notifier = RaisingFeishuNotifier()

            morning = service.build_one_to_two_morning_report(
                trade_date="2026-05-02",
                notify=True,
            )
            eod = service.build_one_to_two_end_of_day_review(
                trade_date="2026-05-02",
                notify=True,
            )

            self.assertEqual(morning.notification.status, NotificationStatus.PREPARED)
            self.assertEqual(eod.notification.status, NotificationStatus.PREPARED)

    def test_schedule_health_explains_non_trading_and_missing_notifications(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )

            weekend = service.build_schedule_health_report(trade_date="2026-05-16")
            trading_day = service.build_schedule_health_report(trade_date="2026-04-30")

            self.assertEqual(weekend.status, "ready")
            self.assertFalse(weekend.is_trading_day)
            self.assertIn("不应发送", weekend.summary)
            self.assertTrue(all(not item.required_notification for item in weekend.items))
            self.assertEqual(trading_day.status, "blocked")
            self.assertTrue(trading_day.is_trading_day)
            self.assertEqual(
                {item.workflow for item in trading_day.items},
                {"morning", "paper-decision", "watch:open", "eod"},
            )
            self.assertIn(
                "missing",
                {item.notification_status for item in trading_day.items},
            )
            self.assertIn("缺失阶段", trading_day.next_action)
            self.assertIn("beta-start", trading_day.items[0].next_action)

    def test_schedule_health_does_not_warn_before_notification_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            health_service = ScheduleHealthService(
                trading_calendar=WeekdayTradingCalendar(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
                scheduler_run_store=SchedulerRunStore(root / "scheduler_runs.json"),
                now_provider=lambda: datetime(2026, 4, 30, 6, 30),
            )

            report = health_service.build_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "ready")
            self.assertTrue(all(item.notification_status == "pending" for item in report.items))
            self.assertTrue(all(item.status == "ready" for item in report.items))
            self.assertIn("覆盖正常", report.summary)

    def test_schedule_health_passes_when_required_notifications_were_sent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=notification_store,
            )
            notification_store.append(
                "morning",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="早评",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            notification_store.append(
                "eod",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="晚评",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            service._scheduler_run_store.append(
                OneToTwoScheduleRun(
                    run_id="schedule-2026-04-30-0931",
                    trade_date="2026-04-30",
                    trade_context=TradingDayContext(
                        requested_date="2026-04-30",
                        trade_date="2026-04-30",
                        previous_trade_date="2026-04-29",
                        next_trade_date="2026-05-06",
                        is_trading_day=True,
                        note="test",
                    ),
                    requested_time="09:31",
                    due_count=2,
                    executed_count=2,
                    skipped_count=0,
                    tasks=(
                        OneToTwoScheduleTask(
                            task_id="paper-decision-2026-04-30",
                            mode="paper-decision",
                            phase=None,
                            scheduled_time="09:00",
                            status="completed",
                            message="done",
                            notification_status=NotificationStatus.PREPARED,
                        ),
                        OneToTwoScheduleTask(
                            task_id="watch-open-2026-04-30",
                            mode="watch",
                            phase="open",
                            scheduled_time="09:31",
                            status="completed",
                            message="done",
                            notification_status=NotificationStatus.PREPARED,
                        ),
                    ),
                    next_action="done",
                )
            )

            report = service.build_schedule_health_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "ready")
            status_by_workflow = {
                item.workflow: item.notification_status for item in report.items
            }
            self.assertEqual(status_by_workflow["morning"], "sent")
            self.assertEqual(status_by_workflow["eod"], "sent")
            self.assertEqual(status_by_workflow["paper-decision"], "not_required")
            self.assertEqual(status_by_workflow["watch:open"], "not_required")
            self.assertIn("覆盖正常", report.summary)

    def test_schedule_health_prefers_latest_sent_over_older_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notifications = (
                NotificationRecord(
                    record_id="morning-old-prepared",
                    channel="feishu",
                    workflow="morning",
                    trade_date="2026-04-30",
                    status=NotificationStatus.PREPARED,
                    title="早评",
                    message="prepared",
                    created_at="20260430085000",
                ),
                NotificationRecord(
                    record_id="morning-new-sent",
                    channel="feishu",
                    workflow="morning",
                    trade_date="2026-04-30",
                    status=NotificationStatus.SENT,
                    title="早评",
                    message="sent",
                    created_at="20260430085100",
                ),
                NotificationRecord(
                    record_id="eod-sent",
                    channel="feishu",
                    workflow="eod",
                    trade_date="2026-04-30",
                    status=NotificationStatus.SENT,
                    title="晚评",
                    message="sent",
                    created_at="20260430151000",
                ),
            )

            class ReorderedNotificationStore:
                def load(self) -> tuple[NotificationRecord, ...]:
                    return notifications

            health_service = ScheduleHealthService(
                trading_calendar=WeekdayTradingCalendar(),
                notification_store=ReorderedNotificationStore(),
                scheduler_run_store=SchedulerRunStore(root / "scheduler_runs.json"),
                now_provider=lambda: datetime(2026, 4, 30, 16, 0),
            )

            report = health_service.build_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.items[0].notification_status, "sent")
            self.assertIn("关键值守存在阻断", report.summary)

    def test_schedule_health_reads_important_runs_beyond_recent_idle_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_store = NotificationRecordStore(root / "notifications.json")
            scheduler_run_store = SchedulerRunStore(root / "scheduler_runs.json")
            health_service = ScheduleHealthService(
                trading_calendar=WeekdayTradingCalendar(),
                notification_store=notification_store,
                scheduler_run_store=scheduler_run_store,
                now_provider=lambda: datetime(2026, 4, 30, 16, 0),
            )
            notification_store.append(
                "morning",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="早评",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            notification_store.append(
                "eod",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="晚评",
                    message="sent",
                    webhook_configured=True,
                ),
            )
            context = TradingDayContext(
                requested_date="2026-04-30",
                trade_date="2026-04-30",
                previous_trade_date="2026-04-29",
                next_trade_date="2026-05-06",
                is_trading_day=True,
                note="test",
            )
            scheduler_run_store.append(
                OneToTwoScheduleRun(
                    run_id="important-open",
                    trade_date="2026-04-30",
                    trade_context=context,
                    requested_time="09:31",
                    due_count=2,
                    executed_count=2,
                    skipped_count=0,
                    tasks=(
                        OneToTwoScheduleTask(
                            task_id="paper-decision",
                            mode="paper-decision",
                            phase=None,
                            scheduled_time="09:00",
                            status="completed",
                            message="done",
                            notification_status=NotificationStatus.PREPARED,
                        ),
                        OneToTwoScheduleTask(
                            task_id="watch-open",
                            mode="watch",
                            phase="open",
                            scheduled_time="09:31",
                            status="completed",
                            message="done",
                            notification_status=NotificationStatus.PREPARED,
                        ),
                    ),
                    next_action="done",
                )
            )
            for minute in range(60):
                scheduler_run_store.append(
                    OneToTwoScheduleRun(
                        run_id=f"idle-{minute}",
                        trade_date="2026-04-30",
                        trade_context=context,
                        requested_time="14:00",
                        due_count=2,
                        executed_count=0,
                        skipped_count=2,
                        tasks=(
                            OneToTwoScheduleTask(
                                task_id="paper-decision",
                                mode="paper-decision",
                                phase=None,
                                scheduled_time="09:00",
                                status="skipped",
                                message="already completed",
                                notification_status=NotificationStatus.PREPARED,
                            ),
                            OneToTwoScheduleTask(
                                task_id="watch-open",
                                mode="watch",
                                phase="open",
                                scheduled_time="09:31",
                                status="skipped",
                                message="already completed",
                                notification_status=NotificationStatus.PREPARED,
                            ),
                        ),
                        next_action="already done",
                    )
                )

            report = health_service.build_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "ready")
            self.assertGreater(report.scheduler_run_count, 30)
            workflow_status = {item.workflow: item.schedule_status for item in report.items}
            self.assertEqual(workflow_status["paper-decision"], "skipped")
            self.assertEqual(workflow_status["watch:open"], "skipped")

    def test_schedule_health_blocks_prepared_required_notification_after_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_store = NotificationRecordStore(root / "notifications.json")
            health_service = ScheduleHealthService(
                trading_calendar=WeekdayTradingCalendar(),
                notification_store=notification_store,
                scheduler_run_store=SchedulerRunStore(root / "scheduler_runs.json"),
                now_provider=lambda: datetime(2026, 4, 30, 9, 40),
            )
            notification_store.append(
                "morning",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.PREPARED,
                    title="早评",
                    message="prepared",
                    webhook_configured=False,
                ),
            )

            report = health_service.build_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.items[0].status, "blocked")
            self.assertEqual(report.items[0].notification_status, "prepared")
            self.assertIn("只生成未发送", report.items[0].summary)
            self.assertIn("beta-start", report.items[0].next_action)

    def test_schedule_health_blocks_sent_market_data_unavailable_morning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=notification_store,
            )
            notification_store.append(
                "morning",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="FireMoney 主线首板早盘异常",
                    message="今日战法：行情异常暂停\n异常原因：行情数据不可用",
                    webhook_configured=True,
                ),
            )
            notification_store.append(
                "eod",
                "2026-04-30",
                FeishuNotificationResult(
                    status=NotificationStatus.SENT,
                    title="晚评",
                    message="sent",
                    webhook_configured=True,
                ),
            )

            report = service.build_schedule_health_report(trade_date="2026-04-30")

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.items[0].notification_status, "sent_data_unavailable")
            self.assertIn("行情异常暂停", report.items[0].summary)
            self.assertIn("阻断", report.summary)

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

    def test_beta_check_passes_market_data_timeout_to_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                notification_store=NotificationRecordStore(root / "notifications.json"),
            )

            captured: list[tuple[bool, float]] = []
            original = service.build_one_to_two_doctor_report

            def recording_doctor_report(*args, **kwargs):
                captured.append(
                    (
                        bool(kwargs.get("beta", False)),
                        float(kwargs.get("market_data_timeout_seconds", -1.0)),
                    )
                )
                return original(*args, **kwargs)

            service.build_one_to_two_doctor_report = recording_doctor_report  # type: ignore[method-assign]

            with patch.dict(
                os.environ,
                {
                    "FEISHU_ENABLED": "true",
                    "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
                },
                clear=True,
            ):
                service.build_one_to_two_beta_readiness_report(
                    trade_date="2026-04-30",
                    market_data_timeout_seconds=123.0,
                )

            self.assertEqual(captured, [(False, 123.0), (True, 123.0)])

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
            self.assertEqual(payload["executed_count"], 6)
            records = SchedulerRunStore(scheduler_run_path).load()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run"]["executed_count"], 6)

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

    def test_scheduler_run_store_keeps_important_runs_when_loop_observes_often(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index = 0

            def created_at_provider() -> str:
                nonlocal index
                index += 1
                return f"202605060900{index:04d}"

            store = SchedulerRunStore(
                root / "scheduler_runs.json",
                created_at_provider=created_at_provider,
            )
            context = TradingDayContext(
                requested_date="2026-05-06",
                trade_date="2026-05-06",
                previous_trade_date="2026-04-30",
                next_trade_date="2026-05-07",
                is_trading_day=True,
                note="test",
            )
            important = OneToTwoScheduleRun(
                run_id="important-open",
                trade_date="2026-05-06",
                trade_context=context,
                requested_time="09:31",
                due_count=1,
                executed_count=1,
                skipped_count=0,
                tasks=(
                    OneToTwoScheduleTask(
                        task_id="watch-open",
                        mode="watch",
                        phase="open",
                        scheduled_time="09:31",
                        status="completed",
                        message="open completed",
                        notification_status=NotificationStatus.PREPARED,
                    ),
                ),
                next_action="done",
            )
            store.append(important)

            for minute in range(280):
                observed = OneToTwoScheduleRun(
                    run_id=f"observed-{minute}",
                    trade_date="2026-05-06",
                    trade_context=context,
                    requested_time="08:00",
                    due_count=0,
                    executed_count=0,
                    skipped_count=0,
                    tasks=(
                        OneToTwoScheduleTask(
                            task_id="morning",
                            mode="morning",
                            phase=None,
                            scheduled_time="08:50",
                            status="pending",
                            message="waiting",
                            notification_status=NotificationStatus.PREPARED,
                        ),
                    ),
                    next_action="waiting",
                )
                store.append(observed)

            records = store.load()

            self.assertTrue(
                any(record["run"]["run_id"] == "important-open" for record in records)
            )
            observed_records = [
                record for record in records if record.get("status") == "observed"
            ]
            self.assertLessEqual(len(observed_records), 240)

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
            self.assertIn("模拟卖出", sold.notification.message)
            self.assertIn("stop_loss_t1", sold.notification.message)
            self.assertIn("实现盈亏", sold.notification.message)

    def test_weak_position_exits_when_exit_plan_max_holding_day_arrives(self) -> None:
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
                market_data_provider=StaticOneToTwoProvider(()),
                paper_store=paper_store,
            )

            weak = weak_service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )

            self.assertEqual(weak.account.positions, ())
            self.assertEqual(weak.account.events[0].event_type.value, "discipline_exit")
            self.assertEqual(weak.account.closed_trades[0].exit_reason, "discipline_weak_after_1_days")
            self.assertEqual(weak.account.closed_trades[0].holding_trade_days, 1)
            self.assertIn("模拟卖出", weak.notification.message)
            self.assertIn("持仓 1 日未走强", weak.notification.message)
            self.assertNotIn("discipline_weak_after_1_days", weak.notification.message)
            self.assertIn("持仓 1 日", weak.notification.message)

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
            self.assertEqual(review.warning_count, 0)
            self.assertEqual(review.realized_pnl, -72.0)
            self.assertEqual(review.max_drawdown, -72.0)
            self.assertIn("完成样本 1 笔", review.summary)
            self.assertIn("成功 0 笔", review.summary)
            self.assertEqual(review.stability_stage, "观察期")
            self.assertEqual(review.next_milestone, 30)
            self.assertIn("少于 30", review.strategy_boundary_suggestion)
            self.assertIn("稳定性：已归档", review.notification.message)
            self.assertIn("风险提示", review.notification.message)
            self.assertIn("T+1 卖出 1", review.notification.message)
            self.assertIn("已归档 1 笔", review.notification.message)
            self.assertIn("最新样本", review.notification.message)
            self.assertIn("stop_loss_t1", review.notification.message)
            self.assertIn("收益 -6.84%", review.notification.message)
            self.assertIn("分年收益", review.notification.message)
            self.assertIn("月度回撤", review.next_action)
            self.assertTrue(
                any("分年收益" in item for item in review.focus_points)
            )

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
            self.assertIn("样本数: warning", completed.stdout)
            self.assertIn("Point-in-Time", completed.stdout)
            self.assertFalse((root / "paper_trades.json").exists())

    def test_board_shadow_cli_brief_prints_shadow_boundary(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "client.desktop.firemoney_client.one_to_two_cli",
                "board-shadow",
                "--trade-date",
                "2026-04-29",
                "--brief",
            ],
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=90,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FireMoney 封板影子线", completed.stdout)
        self.assertIn("影子线", completed.stdout)

    def test_board_shadow_stability_cli_brief_uses_isolated_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "board-shadow-stability",
                    "--board-shadow-store",
                    str(Path(temp_dir) / "board_shadow_samples.json"),
                    "--brief",
                ],
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                timeout=90,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("FireMoney 封板影子线稳定性", completed.stdout)
            self.assertIn("样本数：0", completed.stdout)

    def test_board_shadow_system_cli_brief_prints_operating_system(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "client.desktop.firemoney_client.one_to_two_cli",
                "board-shadow-system",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2026-05-05",
                "--brief",
            ],
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=120,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FireMoney 封板波段交易体系", completed.stdout)
        self.assertIn("动态 8%/12%", completed.stdout)
        self.assertIn("不倒推买点", completed.stdout)

    def test_board_shadow_system_report_surfaces_core_metrics(self) -> None:
        with _workspace_temp_dir("board_shadow_system_report") as root:
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            fake_result = {
                "summary": {
                    "sample_count": 264,
                    "win_rate": 0.6932,
                    "position_weighted_return_pct": 0.8078,
                    "max_drawdown_pct": -0.0204,
                },
                "validation_summary": {
                    "sample_count": 38,
                    "win_rate": 0.7368,
                    "position_weighted_return_pct": 0.1012,
                    "max_drawdown_pct": -0.0098,
                },
                "suggested_position_summary": {
                    "sample_count": 264,
                    "win_rate": 0.6932,
                    "position_weighted_return_pct": 0.9651,
                    "max_drawdown_pct": -0.0203,
                },
                "suggested_position_validation_summary": {
                    "sample_count": 38,
                    "win_rate": 0.7368,
                    "position_weighted_return_pct": 0.1206,
                    "max_drawdown_pct": -0.0112,
                },
                "suggested_position_yearly": {
                    "2024": {"position_weighted_return_pct": 0.2892},
                    "2025": {"position_weighted_return_pct": 0.3603},
                    "2026": {"position_weighted_return_pct": 0.1206},
                },
            }

            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=([], {}),
            ), patch(
                "server.firemoney_server.application.main_chain.board_matrix.build_board_candidates",
                return_value=[],
            ), patch(
                "server.firemoney_server.application.main_chain.board_matrix.evaluate_case",
                return_value=fake_result,
            ):
                report = service.build_limit_up_board_shadow_system_report(
                    start_date="2024-01-01",
                    end_date="2026-05-05",
                )

            self.assertEqual(report.status, "ready")
            self.assertEqual(report.fixed_position_summary.sample_count, 264)
            self.assertAlmostEqual(
                report.dynamic_position_summary.position_weighted_return_pct,
                0.9651,
            )
            self.assertAlmostEqual(
                report.dynamic_position_validation.position_weighted_return_pct,
                0.1206,
            )
            self.assertEqual(report.yearly_dynamic_position_returns["2025"], 0.3603)
            self.assertIn("不倒推买点", report.summary)

    def test_paper_backtest_report_surfaces_yearly_profit_validation(self) -> None:
        with _workspace_temp_dir("paper_backtest_report") as root:
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            one_lot_trades = [
                {
                    "entry_date": f"{year}-{month:02d}-{day:02d}",
                    "symbol": f"600{year % 100:02d}{month:02d}{day:02d}"[-6:],
                    "name": f"{year}小账户样本{month:02d}{day:02d}",
                    "entry_price": 10.0,
                    "net_return_pct": (-0.02 if year == 2022 else 0.018),
                }
                for year in range(2020, 2027)
                for month in range(1, 11)
                for day in (5, 15)
            ]
            fake_result = {
                "suggested_position_summary": {
                    "sample_count": 240,
                    "win_rate": 0.62,
                    "position_weighted_return_pct": 0.58,
                    "max_drawdown_pct": -0.035,
                },
                "suggested_position_train_summary": {
                    "sample_count": 220,
                    "win_rate": 0.63,
                    "position_weighted_return_pct": 0.53,
                    "max_drawdown_pct": -0.035,
                },
                "suggested_position_validation_summary": {
                    "sample_count": 20,
                    "win_rate": 0.6,
                    "position_weighted_return_pct": 0.05,
                    "max_drawdown_pct": -0.012,
                },
                "suggested_position_yearly": {
                    "2020": {
                        "sample_count": 38,
                        "win_rate": 0.61,
                        "average_net_return_pct": 0.018,
                        "median_net_return_pct": 0.012,
                        "position_weighted_return_pct": 0.09,
                        "max_drawdown_pct": -0.018,
                    },
                    "2021": {
                        "sample_count": 42,
                        "win_rate": 0.64,
                        "average_net_return_pct": 0.015,
                        "median_net_return_pct": 0.011,
                        "position_weighted_return_pct": 0.11,
                        "max_drawdown_pct": -0.022,
                    },
                    "2022": {
                        "sample_count": 35,
                        "win_rate": 0.4,
                        "average_net_return_pct": -0.006,
                        "median_net_return_pct": -0.003,
                        "position_weighted_return_pct": -0.025,
                        "max_drawdown_pct": -0.051,
                    },
                    "2023": {
                        "sample_count": 37,
                        "win_rate": 0.57,
                        "average_net_return_pct": 0.01,
                        "median_net_return_pct": 0.007,
                        "position_weighted_return_pct": 0.07,
                        "max_drawdown_pct": -0.02,
                    },
                    "2024": {
                        "sample_count": 40,
                        "win_rate": 0.65,
                        "average_net_return_pct": 0.014,
                        "median_net_return_pct": 0.01,
                        "position_weighted_return_pct": 0.1,
                        "max_drawdown_pct": -0.019,
                    },
                    "2025": {
                        "sample_count": 36,
                        "win_rate": 0.58,
                        "average_net_return_pct": 0.012,
                        "median_net_return_pct": 0.008,
                        "position_weighted_return_pct": 0.08,
                        "max_drawdown_pct": -0.024,
                    },
                    "2026": {
                        "sample_count": 12,
                        "win_rate": 0.6,
                        "average_net_return_pct": 0.011,
                        "median_net_return_pct": 0.007,
                        "position_weighted_return_pct": 0.05,
                        "max_drawdown_pct": -0.012,
                    },
                },
                "one_position_trades": one_lot_trades,
            }
            stress_result = {
                "suggested_position_summary": {
                    "sample_count": 240,
                    "win_rate": 0.6,
                    "position_weighted_return_pct": 0.32,
                    "max_drawdown_pct": -0.042,
                },
                "suggested_position_validation_summary": {
                    "sample_count": 20,
                    "win_rate": 0.55,
                    "position_weighted_return_pct": 0.03,
                    "max_drawdown_pct": -0.015,
                },
                "suggested_position_yearly": {
                    year: {
                        **payload,
                        "position_weighted_return_pct": (
                            -0.01
                            if year == "2022"
                            else payload["position_weighted_return_pct"] / 2
                        ),
                    }
                    for year, payload in fake_result[
                        "suggested_position_yearly"
                    ].items()
                },
                "one_position_trades": fake_result["one_position_trades"],
            }

            def fake_evaluate_case(*args, **kwargs):
                if kwargs.get("roundtrip_cost_pct") == 0.0015:
                    return fake_result
                return stress_result

            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=([], {}),
            ), patch(
                "server.firemoney_server.application.main_chain.board_matrix.build_board_candidates",
                return_value=[],
            ), patch(
                "server.firemoney_server.application.main_chain.board_matrix.evaluate_case",
                side_effect=fake_evaluate_case,
            ):
                report = service.build_paper_backtest_report(
                    start_date="2020-01-01",
                    end_date="2026-05-05",
                )

            self.assertEqual(report.status, "warning")
            self.assertEqual(report.strategy_id, "board-shadow-system")
            self.assertEqual(tuple(item.year for item in report.yearly), (
                "2020",
                "2021",
                "2022",
                "2023",
                "2024",
                "2025",
                "2026",
            ))
            self.assertEqual(report.negative_years, ("2022",))
            self.assertIn("2022", report.weak_years)
            self.assertIn("2020 起", report.improvement_notes[0])
            self.assertIn("无未来函数", "\n".join(report.no_future_leakage_notes))
            self.assertIn("2020-01-01", report.data_coverage_notes[0])
            self.assertEqual(len(report.friction_scenarios), 5)
            self.assertEqual(report.friction_scenarios[0].label, "baseline_cost_0.15pct")
            self.assertEqual(report.friction_scenarios[-1].status, "blocked")
            self.assertIn("2022", report.friction_scenarios[-1].negative_years)
            self.assertIsNotNone(report.return_target)
            self.assertEqual(report.return_target.weakest_year, "2022")
            self.assertEqual(report.return_target.required_linear_position_multiple, 0.0)
            self.assertIn("不能把年化 100% 当成加仓目标", report.return_target.conclusion)
            self.assertIsNotNone(report.monthly_stability)
            self.assertEqual(report.monthly_stability.total_months, 70)

    def test_strategy_decision_report_prefers_audited_main_line(self) -> None:
        with _workspace_temp_dir("strategy_decision_report") as root:
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            fake_report = LimitUpBoardShadowSystemReport(
                report_id="limit-up-board-shadow-system-2024-01-01-to-2026-05-05",
                start_date="2024-01-01",
                end_date="2026-05-05",
                status="ready",
                system_name="mainboard_10cm_limit_up_board_shadow_system",
                summary="audited board shadow system",
                buy_rules=(),
                sell_rules=(),
                position_rules=(),
                fixed_position_summary=LimitUpBoardShadowSystemMetric(
                    label="fixed",
                    sample_count=264,
                    win_rate=0.6932,
                    position_weighted_return_pct=0.8078,
                    max_drawdown_pct=-0.0204,
                ),
                fixed_position_validation=LimitUpBoardShadowSystemMetric(
                    label="fixed validation",
                    sample_count=38,
                    win_rate=0.7368,
                    position_weighted_return_pct=0.1012,
                    max_drawdown_pct=-0.0098,
                ),
                dynamic_position_summary=LimitUpBoardShadowSystemMetric(
                    label="dynamic",
                    sample_count=264,
                    win_rate=0.6932,
                    position_weighted_return_pct=0.9651,
                    max_drawdown_pct=-0.0203,
                ),
                dynamic_position_validation=LimitUpBoardShadowSystemMetric(
                    label="dynamic validation",
                    sample_count=38,
                    win_rate=0.7368,
                    position_weighted_return_pct=0.1206,
                    max_drawdown_pct=-0.0112,
                ),
                yearly_dynamic_position_returns={
                    "2024": 0.2892,
                    "2025": 0.3603,
                    "2026": 0.1206,
                },
                factor_validation_notes=(
                    "主线默认热度和涨幅约束已被验证。",
                ),
                no_future_leakage_notes=(),
                limitations=(),
                next_action="continue audited operation",
            )

            with patch.object(
                service,
                "build_limit_up_board_shadow_system_report",
                return_value=fake_report,
            ):
                report = service.build_strategy_decision_report(
                    trade_date="2026-05-08",
                    end_date="2026-05-05",
                )

            self.assertIsInstance(report, StrategyDecisionReport)
            self.assertEqual(report.selected_strategy_id, "board-shadow-system")
            self.assertEqual(report.selected_action, "operate_when_signal_exists")
            self.assertEqual(report.selected_role, "main_operating_line")
            self.assertEqual(
                {option.strategy_id for option in report.options},
                {"board-shadow-system", "cash"},
            )
            self.assertTrue(any(option.strategy_id == "cash" for option in report.options))
            self.assertIn("2024-01-01", report.risk_rules[-1])

    def test_board_shadow_system_brief_surfaces_factor_validation_notes(self) -> None:
        from client.desktop.firemoney_client.presenters.brief_formatters import (
            format_board_shadow_system_brief,
        )

        report = LimitUpBoardShadowSystemReport(
            report_id="limit-up-board-shadow-system-2024-01-01-to-2026-05-05",
            start_date="2024-01-01",
            end_date="2026-05-05",
            status="ready",
            system_name="mainboard_10cm_limit_up_board_shadow_system",
            summary="shadow mainline",
            buy_rules=(),
            sell_rules=(),
            position_rules=(),
            fixed_position_summary=LimitUpBoardShadowSystemMetric("fixed", 1, 1.0, 0.1, -0.01),
            fixed_position_validation=LimitUpBoardShadowSystemMetric("fixed validation", 1, 1.0, 0.05, -0.01),
            dynamic_position_summary=LimitUpBoardShadowSystemMetric("dynamic", 1, 1.0, 0.12, -0.01),
            dynamic_position_validation=LimitUpBoardShadowSystemMetric("dynamic validation", 1, 1.0, 0.06, -0.01),
            yearly_dynamic_position_returns={"2024": 0.12},
            factor_validation_notes=(
                "不要放宽 20 日涨幅上限。",
                "局部主线集中度和过热过滤实验没有给出更优默认结果。",
            ),
            no_future_leakage_notes=(),
            limitations=(),
            next_action="continue",
        )

        text = format_board_shadow_system_brief(report)
        self.assertIn("因子验证结论", text)
        self.assertIn("不要放宽 20 日涨幅上限", text)
        self.assertIn("局部主线集中度和过热过滤实验没有给出更优默认结果", text)

    def test_paper_trading_decision_report_builds_single_command_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertIsInstance(report, PaperTradingDecisionReport)
            self.assertEqual(report.selected_strategy_id, "board-shadow-system")
            self.assertEqual(report.status, "ready_to_buy")
            self.assertTrue(report.should_buy)
            self.assertIsNotNone(report.instruction)
            self.assertEqual(report.instruction.symbol, "600001")
            self.assertEqual(report.instruction.action, "paper_buy")
            self.assertEqual(report.instruction.entry_window, "09:31-09:45")
            self.assertEqual(report.execution_track, "board_shadow_system_execution")
            self.assertEqual(report.instruction.quantity, 100)
            self.assertAlmostEqual(report.instruction.cash_budget, 1052.0)
            self.assertAlmostEqual(report.instruction.position_pct, 0.1052)
            self.assertEqual(report.instruction.planned_stop_risk_pct, 0.0599)
            self.assertEqual(report.instruction.planned_first_target_return_pct, 0.0798)
            self.assertAlmostEqual(
                report.instruction.planned_reward_risk_ratio,
                1.3333,
                places=4,
            )
            self.assertGreater(
                report.instruction.max_intratrade_drawdown_budget_pct,
                report.instruction.planned_stop_risk_pct,
            )
            self.assertTrue(
                any("入场风险预算" in item for item in report.instruction.risk_notes)
            )
            self.assertTrue(
                any("2024-01-01" in item for item in report.decision_rules)
            )
            self.assertFalse((root / "paper_trades.json").exists())
            self.assertEqual(PaperTradeStore(root / "paper_trades.json").load().events, ())

    def test_paper_trading_decision_uses_board_shadow_mainline_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )
            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(decision.execution_track, "board_shadow_system_execution")
            self.assertIsNotNone(decision.instruction)
            self.assertEqual(decision.instruction.strategy_id, "board-shadow-system")
            self.assertEqual(watch.account.positions[0].symbol, decision.instruction.symbol)
            self.assertEqual(
                watch.account.positions[0].entry_turnover_quality_label,
                "board-shadow validated mainline",
            )
            self.assertEqual(watch.account.positions[0].opened_score, 100.0)

    def test_watch_open_routes_from_same_morning_candidate_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base_rows = SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")

            class FlakyProvider:
                def __init__(self) -> None:
                    self.calls = 0

                def load_one_to_two_rows(self, trade_date: str):
                    self.calls += 1
                    if self.calls == 1:
                        return base_rows
                    return tuple(
                        replace(
                            row,
                            market_temperature=20,
                            turnover_amount=1_000_000,
                            sealed_amount=1,
                        )
                        for row in base_rows
                    )

                def load_mainline_news(self, *args, **kwargs):
                    return ()

            provider = FlakyProvider()
            service = _build_service(
                root,
                market_data_provider=provider,
            )

            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(provider.calls, 1)
            self.assertEqual(watch.account.positions[0].symbol, "600001")
            self.assertEqual(
                watch.account.positions[0].entry_turnover_quality_label,
                "board-shadow validated mainline",
            )

    def test_paper_trading_decision_skips_high_price_candidate_for_small_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_rows = SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
            high_price = OneToTwoMarketRow(
                **(
                    base_rows[0].__dict__
                    | {
                        "symbol": "600088",
                        "name": "高价跳过",
                        "latest_price": 66.04,
                        "previous_close": 60.04,
                        "limit_up_price": 66.04,
                        "turnover_amount": 900_000_000,
                        "sealed_amount": 150_000_000,
                        "auction_amount": 40_000_000,
                        "ma_20": 58.0,
                        "market_cap": 14_000_000_000,
                        "float_market_cap": 10_000_000_000,
                    }
                )
            )
            low_price = OneToTwoMarketRow(
                **(
                    base_rows[1].__dict__
                    | {
                        "symbol": "600099",
                        "name": "低价可买",
                        "latest_price": 10.3,
                        "previous_close": 9.36,
                        "limit_up_price": 10.3,
                        "turnover_amount": 900_000_000,
                        "sealed_amount": 150_000_000,
                        "auction_amount": 40_000_000,
                    }
                )
            )
            extra_rows = tuple(
                OneToTwoMarketRow(
                    **(
                        low_price.__dict__
                        | {
                            "symbol": f"6001{index:02d}",
                            "name": f"低价可买{index}",
                            "turnover_amount": 850_000_000 + index * 1_000_000,
                        }
                    )
                )
                for index in range(3, 7)
            )
            service = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(
                    (high_price, low_price, *extra_rows)
                ),
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.status, "ready_to_buy")
            self.assertIsNotNone(decision.instruction)
            self.assertEqual(decision.instruction.symbol, "600099")
            self.assertEqual(decision.instruction.quantity, 100)
            self.assertLessEqual(decision.instruction.cash_budget, 2000)

    def test_paper_trading_decision_stands_aside_without_board_shadow_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = tuple(
                replace(row, recent_gain_pct=0.25)
                for row in SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(rows),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(report.execution_track, "cash_stand_aside")
            self.assertEqual(report.status, "stand_aside")
            self.assertFalse(report.should_buy)
            self.assertIsNone(report.instruction)

    def test_mainline_market_cap_gate_blocks_outside_50_to_800_yi(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")[0]
            too_small = OneToTwoMarketRow(
                **(base.__dict__ | {"symbol": "600098", "name": "小市值剔除", "market_cap": 4_000_000_000})
            )
            too_large = OneToTwoMarketRow(
                **(base.__dict__ | {"symbol": "600099", "name": "大市值剔除", "market_cap": 90_000_000_000})
            )
            service = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider((too_small, too_large)),
            )

            report = service.build_one_to_two_morning_report(
                trade_date="2026-04-30",
                notify=False,
            )

            by_symbol = {candidate.symbol: candidate for candidate in report.candidates}
            self.assertEqual(by_symbol["600098"].status, "blocked")
            self.assertEqual(by_symbol["600099"].status, "blocked")
            self.assertTrue(any("50" in item for item in by_symbol["600098"].blockers))
            self.assertTrue(any("800" in item for item in by_symbol["600099"].blockers))

    def test_paper_trading_decision_stands_aside_on_non_mainline_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            with patch.object(
                service,
                "build_strategy_decision_report",
                return_value=StrategyDecisionReport(
                    report_id="strategy-2026-04-30",
                    trade_date="2026-04-30",
                    status="ready",
                    evidence_end_date="2026-05-05",
                    market_regime="defense_stand_aside_day",
                    regime_rationale="非主线策略不进入每日模拟盘经营。",
                    regime_action="defense_stand_aside",
                    k92_regime="ebb_stand_aside_day",
                    k92_gate="block",
                    k92_rationale="K92 守门：退潮空仓。",
                    selected_strategy_id="legacy-research-line",
                    selected_action="stand_aside",
                    selected_role="legacy_research",
                    summary="legacy research must stand aside",
                    options=(),
                    risk_rules=(),
                    next_action="stand aside",
                ),
            ):
                report = service.build_paper_trading_decision_report(
                    trade_date="2026-04-30",
                )

            self.assertEqual(report.market_regime, "defense_stand_aside_day")
            self.assertEqual(report.selected_strategy_id, "legacy-research-line")
            self.assertEqual(report.status, "stand_aside")
            self.assertFalse(report.should_buy)
            self.assertIsNone(report.instruction)

    def test_k92_ebb_gate_blocks_daily_strategy_even_when_mainline_is_strong(self) -> None:
        base_row = SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")[0]
        rows = tuple(
            replace(
                base_row,
                symbol=f"600{index + 1:03d}",
                name=f"K92退潮候选{index + 1}",
                market_temperature=78,
                turnover_amount=220_000_000 + index * 10_000_000,
                sealed_amount=35_000_000,
                auction_amount=12_000_000,
                first_board_count=45,
                volume_ratio_5=1.6,
                position_percentile_60=0.95,
                market_cap=12_000_000_000,
                float_market_cap=9_000_000_000,
            )
            for index in range(4)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=StaticOneToTwoProvider(rows),
            )

            strategy = service.build_strategy_decision_report(trade_date="2026-04-30")
            paper = service.build_paper_trading_decision_report(trade_date="2026-04-30")

            self.assertEqual(strategy.market_regime, "trend_main_rise_day")
            self.assertEqual(strategy.k92_gate, "block")
            self.assertEqual(strategy.selected_strategy_id, "cash")
            self.assertEqual(paper.status, "stand_aside")
            self.assertFalse(paper.should_buy)

            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(watch.account.positions, ())
            self.assertEqual(watch.account.events[0].event_type, OneToTwoEventType.BLOCKED)
            self.assertIn("主线守门要求空仓", watch.account.events[0].message)

    def test_non_mainline_sample_stands_aside_in_daily_paper_trade_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            report = service.build_paper_trading_decision_report(
                trade_date="2026-05-12",
            )

            self.assertEqual(report.market_regime, "defense_stand_aside_day")
            self.assertFalse(report.should_buy)
            self.assertIsNone(report.instruction)
            self.assertEqual(report.status, "stand_aside")

    def test_paper_trading_decision_is_local_only_and_does_not_notify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
                notify=False,
            )
            records = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(report.notification.status, NotificationStatus.PREPARED)
            self.assertEqual(records, ())
            self.assertIn("买点", report.notification.message)
            self.assertIn("卖点纪律", report.notification.message)
            self.assertIn("600001", report.notification.message)
            self.assertEqual(PaperTradeStore(root / "paper_trades.json").load().events, ())

    def test_paper_decision_builds_holding_instruction_for_existing_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-05-06",
                market_data_timeout_seconds=1,
            )

            self.assertEqual(report.status, "holding")
            self.assertFalse(report.should_buy)
            self.assertIsNone(report.instruction)
            self.assertIsNotNone(report.holding_instruction)
            self.assertEqual(report.holding_instruction.symbol, "600001")
            self.assertEqual(report.holding_instruction.positive_lock_price, 10.84)
            self.assertEqual(report.holding_instruction.hard_exit_trade_days, 5)
            self.assertIn("watch --phase risk", report.holding_instruction.next_command)

    def test_paper_trading_decision_notifies_holding_sell_points(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-05-06",
                notify=False,
            )
            records = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(report.status, "holding")
            self.assertEqual(report.notification.status, NotificationStatus.PREPARED)
            self.assertEqual([record.workflow for record in records], ["watch:open"])
            self.assertIn("卖点/持仓处置", report.notification.message)
            self.assertIn("卖出触发", report.notification.message)
            self.assertIn("watch --phase risk", report.notification.message)


    def test_watch_risk_exits_existing_position_without_live_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            db_path = root / "paper_trades.sqlite3"
            paper_store = PaperTradeStore(paper_path, database_path=db_path)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider(()),
                paper_store=paper_store,
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-08",
                phase="risk",
                notify=False,
            )
            db_report = service.build_paper_trade_database_report(database_path=db_path)

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "discipline_weak_after_1_days")
            self.assertEqual(risk.account.closed_trades[0].holding_trade_days, 3)
            self.assertEqual(db_report.closed_trade_count, 1)
            self.assertEqual(db_report.open_position_count, 0)

    def test_watch_risk_times_out_market_data_and_still_exits_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )
            service = _build_service(
                root,
                market_data_provider=SlowOneToTwoProvider(
                    SampleMarketDataProvider().load_one_to_two_rows("2026-05-08")
                ),
                paper_store=paper_store,
            )

            risk = service.run_one_to_two_watch(
                trade_date="2026-05-08",
                phase="risk",
                notify=False,
                market_data_timeout_seconds=0.01,
            )

            self.assertEqual(risk.account.positions, ())
            self.assertEqual(risk.account.closed_trades[0].exit_reason, "discipline_weak_after_1_days")

    def test_paper_guard_blocks_new_entries_after_consecutive_losses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            _seed_closed_trades(paper_store, (-0.02, -0.018))
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )
            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(decision.status, "guard_blocked")
            self.assertFalse(decision.should_buy)
            self.assertEqual(decision.guard_decision.action, "stand_aside")
            self.assertIsNone(decision.instruction)
            self.assertEqual(watch.account.positions, ())
            self.assertEqual(watch.account.events[0].event_type.value, "blocked")

    def test_paper_guard_reduces_position_when_recent_quality_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            _seed_closed_trades(paper_store, (0.01, -0.006, 0.008, -0.004, 0.006))
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )
            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(decision.status, "ready_to_buy")
            self.assertTrue(decision.should_buy)
            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertIsNotNone(decision.instruction)
            self.assertEqual(decision.instruction.quantity, 100)
            self.assertAlmostEqual(decision.instruction.position_pct, 0.1052)
            self.assertEqual(watch.account.positions[0].quantity, 100)
            self.assertEqual(watch.account.positions[0].position_value, 1052.0)
            self.assertEqual(watch.account.positions[0].entry_guard_status, "reduced")
            self.assertEqual(
                watch.account.positions[0].entry_guard_action,
                "allow_reduced",
            )
            self.assertEqual(
                watch.account.positions[0].entry_guard_suggested_position_pct,
                0.12,
            )

    def test_paper_guard_reduces_after_flat_closed_trade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            _seed_closed_trades(paper_store, (0.0,))
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertEqual(decision.guard_decision.suggested_position_pct, 0.12)

    def test_paper_guard_reduces_when_profit_does_not_cover_drawdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            weak_trade = _closed_trade_record(1, realized_pnl_pct=0.01)
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(
                        replace(
                            weak_trade,
                            max_adverse_pct=0.02,
                            profit_drawdown_ratio=0.5,
                        ),
                    ),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertEqual(decision.guard_decision.risk_quality_pass_rate, 0.0)
            self.assertEqual(decision.guard_decision.consecutive_quality_failures, 1)
            self.assertEqual(decision.guard_decision.average_profit_drawdown_ratio, 0.5)

    def test_paper_guard_reduces_when_risk_quality_pass_rate_is_low(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            healthy = _closed_trade_record(1, realized_pnl_pct=0.02)
            weak_first = replace(
                _closed_trade_record(2, realized_pnl_pct=-0.002),
                entry_turnover_quality_score=74.0,
            )
            weak_second = replace(
                _closed_trade_record(3, realized_pnl_pct=-0.002),
                entry_turnover_quality_score=74.0,
            )
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(healthy, weak_first, weak_second),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertLess(decision.guard_decision.risk_quality_pass_rate, 0.6)
            self.assertTrue(
                any(
                    "盈利覆盖回撤达标率" in item or "同类买点质量段" in item
                    for item in decision.guard_decision.reasons
                )
            )

    def test_paper_guard_reduces_when_average_profit_drawdown_ratio_is_low(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            low_ratio_first = replace(
                _closed_trade_record(1, realized_pnl_pct=0.01),
                max_adverse_pct=0.009,
                profit_drawdown_ratio=0.95,
            )
            low_ratio_second = replace(
                _closed_trade_record(2, realized_pnl_pct=0.012),
                max_adverse_pct=0.011,
                profit_drawdown_ratio=0.95,
            )
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(low_ratio_first, low_ratio_second),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertLess(decision.guard_decision.average_profit_drawdown_ratio, 1.0)
            self.assertTrue(
                any(
                    "平均赚撤比" in item or "同类买点质量段" in item
                    for item in decision.guard_decision.reasons
                )
            )

    def test_paper_guard_reduces_when_candidate_quality_bucket_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            strong_loss = replace(
                _closed_trade_record(1, realized_pnl_pct=-0.002),
                entry_turnover_quality_score=92.0,
            )
            strong_win = replace(
                _closed_trade_record(2, realized_pnl_pct=0.006),
                entry_turnover_quality_score=92.0,
            )
            strong_flat = replace(
                _closed_trade_record(4, realized_pnl_pct=0.0),
                entry_turnover_quality_score=92.0,
            )
            unrelated_win = replace(
                _closed_trade_record(3, realized_pnl_pct=0.03),
                entry_turnover_quality_score=74.0,
                entry_turnover_quality_label="有效换手龙买点",
            )
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(strong_win, strong_loss, strong_flat, unrelated_win),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.status, "ready_to_buy")
            self.assertEqual(decision.guard_decision.action, "allow_reduced")
            self.assertEqual(
                decision.guard_decision.candidate_quality_bucket,
                "strong_turnover_dragon",
            )
            self.assertEqual(decision.guard_decision.candidate_quality_sample_count, 3)
            self.assertAlmostEqual(decision.instruction.position_pct, 0.1052)
            self.assertTrue(
                any("同类买点质量段" in item for item in decision.guard_decision.reasons)
            )

    def test_paper_guard_blocks_after_consecutive_quality_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            weak_first = _closed_trade_record(1, realized_pnl_pct=0.01)
            weak_second = _closed_trade_record(2, realized_pnl_pct=0.012)
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(
                        replace(
                            weak_second,
                            max_adverse_pct=0.024,
                            profit_drawdown_ratio=0.5,
                        ),
                        replace(
                            weak_first,
                            max_adverse_pct=0.02,
                            profit_drawdown_ratio=0.5,
                        ),
                    ),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )
            watch = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertEqual(decision.status, "guard_blocked")
            self.assertFalse(decision.should_buy)
            self.assertEqual(decision.guard_decision.action, "stand_aside")
            self.assertEqual(decision.guard_decision.consecutive_quality_failures, 2)
            self.assertEqual(decision.guard_decision.risk_quality_pass_rate, 0.0)
            self.assertEqual(watch.account.positions, ())
            self.assertEqual(watch.account.events[0].event_type.value, "blocked")

    def test_paper_guard_blocks_when_candidate_quality_bucket_keeps_failing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            account = paper_store.load()
            weak_first = replace(
                _closed_trade_record(1, realized_pnl_pct=0.01),
                max_adverse_pct=0.02,
                profit_drawdown_ratio=0.5,
                entry_turnover_quality_score=92.0,
            )
            weak_second = replace(
                _closed_trade_record(2, realized_pnl_pct=0.012),
                max_adverse_pct=0.024,
                profit_drawdown_ratio=0.5,
                entry_turnover_quality_score=92.0,
            )
            strong_healthy = replace(
                _closed_trade_record(4, realized_pnl_pct=0.03),
                entry_turnover_quality_score=92.0,
            )
            healthy_other_bucket = replace(
                _closed_trade_record(3, realized_pnl_pct=0.03),
                entry_turnover_quality_score=74.0,
                entry_turnover_quality_label="有效换手龙买点",
            )
            paper_store.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date="2026-04-29",
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=(
                        healthy_other_bucket,
                        weak_second,
                        weak_first,
                        strong_healthy,
                    ),
                )
            )
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
            )

            decision = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
            )

            self.assertEqual(decision.status, "guard_blocked")
            self.assertFalse(decision.should_buy)
            self.assertEqual(decision.guard_decision.action, "stand_aside")
            self.assertEqual(
                decision.guard_decision.candidate_quality_bucket,
                "strong_turnover_dragon",
            )
            self.assertEqual(decision.guard_decision.candidate_quality_sample_count, 3)
            self.assertTrue(
                any("同类买点质量段" in item for item in decision.guard_decision.reasons)
            )

    def test_paper_trade_records_intratrade_drawdown_quality(self) -> None:
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
            pullback_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-04").__dict__
                    | {"latest_price": 10.2, "theme": "AI绔晶涓荤嚎"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((pullback_row,)),
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-04",
                phase="risk",
                notify=False,
            )
            profit_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-06").__dict__
                    | {"latest_price": 10.9, "theme": "AI绔晶涓荤嚎"}
                )
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

            trade = risk.account.closed_trades[0]
            self.assertGreater(trade.realized_pnl_pct, trade.max_adverse_pct)
            self.assertEqual(trade.max_adverse_pct, 0.0304)
            self.assertGreater(trade.max_favorable_pct, 0)
            self.assertGreater(trade.profit_drawdown_ratio, 1.0)

    def test_paper_decision_times_out_to_data_unavailable_without_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=SlowOneToTwoProvider(
                    SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
                ),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
                market_data_timeout_seconds=0.01,
            )

            self.assertEqual(report.status, "data_unavailable")
            self.assertFalse(report.should_buy)
            self.assertIsNone(report.instruction)
            self.assertEqual(report.market_regime, "market_data_unavailable_day")

    def test_paper_decision_cli_brief_prints_command_sheet(self) -> None:
        with _workspace_temp_dir("paper_decision_cli") as root:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "paper-decision",
                    "--brief",
                    "--sample-data",
                    "--trade-date",
                    "2026-04-30",
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

            self.assertIn("FireMoney 模拟盘指挥单", completed.stdout)
            self.assertIn("600001", completed.stdout)
            self.assertIn("09:31-09:45", completed.stdout)

    def test_morning_no_notify_cli_does_not_record_prepared_notification(self) -> None:
        with _workspace_temp_dir("morning_no_notify") as root:
            notification_path = root / "notifications.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "morning",
                    "--sample-data",
                    "--no-notify",
                    "--trade-date",
                    "2026-04-30",
                    "--paper-store",
                    str(root / "paper_trades.json"),
                    "--notification-store",
                    str(notification_path),
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

            records = NotificationRecordStore(notification_path).load()

            self.assertIn('"status": "ready"', completed.stdout)
            self.assertEqual(records, ())

    def test_non_mainline_day_cli_briefs_show_cash_route(self) -> None:
        with _workspace_temp_dir("non_mainline_cash_cli") as root:
            strategy = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "strategy-decision",
                    "--brief",
                    "--sample-data",
                    "--trade-date",
                    "2026-05-12",
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
            decision = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "client.desktop.firemoney_client.one_to_two_cli",
                    "paper-decision",
                    "--brief",
                    "--sample-data",
                    "--trade-date",
                    "2026-05-12",
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

            self.assertIn("defense_stand_aside_day", strategy.stdout)
            self.assertIn("现金防守", strategy.stdout)
            self.assertIn("defense_stand_aside_day", decision.stdout)
            self.assertIn("现金防守", decision.stdout)

    def test_execution_quality_report_uses_intraday_scaffolding(self) -> None:
        with _workspace_temp_dir("execution_quality_report") as root:
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
            )

            report = service.build_one_to_two_execution_quality_report(
                symbol="600001",
                trade_date="2026-04-30",
            )

            self.assertEqual(report.status, "ready")
            self.assertEqual(report.minute_bar_count, 2)
            self.assertEqual(report.tick_snapshot_count, 2)
            self.assertGreater(report.max_bid_queue_volume, 0)
            self.assertEqual(report.first_five_minute_buy_amount_pct, 1.0)
            self.assertEqual(report.first_five_minute_sell_amount_pct, 0.0)
            self.assertGreater(report.max_single_tick_amount, 0)
            self.assertGreater(report.open_window_amount, 0)
            self.assertGreaterEqual(report.auction_window_amount, 0)
            self.assertGreater(report.buy_drive_score, 0)
            self.assertIn(report.entry_momentum_signal, {"watch", "candidate"})
            self.assertGreater(len(report.entry_momentum_reasons), 0)
            self.assertIn("Tick", report.next_action)

    def test_execution_quality_report_gracefully_blocks_without_intraday_data(self) -> None:
        class NoIntradayProvider(SampleMarketDataProvider):
            def load_intraday_bars(
                self,
                symbol: str,
                trade_date: str,
                interval_minutes: int = 1,
            ):
                raise RuntimeError("intraday source unavailable")

            def load_tick_snapshots(self, symbol: str, trade_date: str):
                raise RuntimeError("tick source unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(
                Path(temp_dir),
                market_data_provider=NoIntradayProvider(),
            )

            report = service.build_one_to_two_execution_quality_report(
                symbol="600001",
                trade_date="2026-04-30",
            )

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.minute_bar_count, 0)
            self.assertEqual(report.tick_snapshot_count, 0)
            self.assertIn("intraday source unavailable", report.limitations[0])
            self.assertIn("tick source unavailable", report.limitations[1])

    def test_execution_quality_cli_brief_prints_intraday_metrics(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "client.desktop.firemoney_client.one_to_two_cli",
                "execution-quality",
                "--sample-data",
                "--symbol",
                "600001",
                "--trade-date",
                "2026-04-30",
                "--brief",
            ],
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=90,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("FireMoney 主线执行质量验证", completed.stdout)
        self.assertIn("分钟线数量", completed.stdout)
        self.assertIn("Tick 快照数量", completed.stdout)
        self.assertIn("买盘驱动分", completed.stdout)
        self.assertIn("入场动量信号", completed.stdout)

    def test_cli_parser_rejects_early_main_rise_mode(self) -> None:
        parser = build_one_to_two_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["early-main-rise"])

    def test_cli_parser_rejects_early_main_rise_replay_mode(self) -> None:
        parser = build_one_to_two_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["early-main-rise-replay"])

    def test_cli_parser_rejects_early_main_rise_backtest_mode(self) -> None:
        parser = build_one_to_two_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["early-main-rise-backtest"])

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
            self.assertEqual(report.trade.exit_reason, "max_holding_close")
            self.assertGreater(report.trade.realized_pnl_pct, 0)
            self.assertGreater(report.trade.risk_reward_ratio, 0)
            self.assertTrue(
                any("后续日线只用于模拟卖点" in item for item in report.no_future_leakage_notes)
            )
            checks = {check.check_id: check for check in report.quality_checks}
            self.assertEqual(checks["no_future_selection"].status, "ready")
            self.assertEqual(checks["price_bars"].status, "ready")
            self.assertEqual(checks["daily_bar_sequence"].status, "warning")
            self.assertEqual(payload["trade"]["exit_reason"], "max_holding_close")

    def test_research_backtest_rank_ignores_future_outcome_fields(self) -> None:
        module = self._load_research_backtest_module()

        visible_fields = {
            "symbol": "600001",
            "name": "涓荤嚎棣栨澘鍊欓€?",
            "first_board_date": "2026-04-29",
            "second_day_date": "2026-04-30",
            "first_board_pct": 0.1,
            "second_open_pct": 0.03,
            "score": 87.0,
            "position_label": "breakout",
            "estimated_turnover_amount": 300000000.0,
            "recent_gain_pct": 0.12,
            "ma20_deviation_pct": 0.14,
            "pressure_distance_pct": None,
            "volume_ratio_5": 1.5,
            "rsi_14": 65.0,
            "position_percentile_60": 0.75,
            "first_board_count": 60,
            "ready_candidate_count": 8,
            "second_day_one_word": False,
            "blockers": (),
        }
        strong_future = module.Match(
            **visible_fields,
            second_close_pct=0.1,
            second_high_pct=0.1,
            buy_open_to_close_pct=0.068,
            second_board_closed=True,
            second_board_touched=True,
            buy_day_positive=True,
        )
        weak_future = module.Match(
            **visible_fields,
            second_close_pct=-0.06,
            second_high_pct=0.02,
            buy_open_to_close_pct=-0.087,
            second_board_closed=False,
            second_board_touched=False,
            buy_day_positive=False,
        )

        self.assertEqual(
            module.selection_rank_key(strong_future),
            module.selection_rank_key(weak_future),
        )
        self.assertEqual(
            module.low_first_selection_rank_key(strong_future),
            module.low_first_selection_rank_key(weak_future),
        )
        self.assertEqual(
            module.open_sweet_selection_rank_key(strong_future),
            module.open_sweet_selection_rank_key(weak_future),
        )

    def test_research_backtest_can_filter_position_labels(self) -> None:
        module = self._load_research_backtest_module()
        base = {
            "symbol": "600001",
            "name": "涓荤嚎棣栨澘鍊欓€?",
            "first_board_date": "2026-04-29",
            "second_day_date": "2026-04-30",
            "first_board_pct": 0.1,
            "second_close_pct": 0.02,
            "second_open_pct": 0.02,
            "second_high_pct": 0.04,
            "buy_open_to_close_pct": 0.0,
            "score": 90.0,
            "estimated_turnover_amount": 300000000.0,
            "recent_gain_pct": 0.12,
            "ma20_deviation_pct": 0.14,
            "pressure_distance_pct": None,
            "volume_ratio_5": 1.5,
            "rsi_14": 65.0,
            "position_percentile_60": 0.75,
            "first_board_count": 60,
            "ready_candidate_count": 8,
            "second_day_one_word": False,
            "blockers": (),
            "second_board_closed": False,
            "second_board_touched": False,
            "buy_day_positive": True,
        }
        low_breakout = module.Match(**(base | {"position_label": "low_breakout"}))
        breakout = module.Match(
            **(base | {"symbol": "600002", "position_label": "breakout"})
        )

        filtered = module.apply_market_width_gate(
            matches=[low_breakout, breakout],
            min_score=80,
            max_score=0,
            allowed_position_labels=module.parse_allowed_position_labels(
                "low_breakout"
            ),
            min_low_breakout_first_board_count=0,
            min_low_breakout_ready_candidates=0,
            max_ready_candidates=0,
        )

        self.assertEqual(tuple(item.symbol for item in filtered), ("600001",))

    def test_research_backtest_can_filter_overwide_ready_pool(self) -> None:
        module = self._load_research_backtest_module()
        matches = [
            module.Match(
                symbol=f"600{i:03d}",
                name=f"hot candidate {i}",
                first_board_date="2026-04-29",
                second_day_date="2026-04-30",
                first_board_pct=0.1,
                second_close_pct=0.02,
                second_open_pct=0.02,
                second_high_pct=0.04,
                buy_open_to_close_pct=0.0,
                score=90.0,
                position_label="breakout",
                estimated_turnover_amount=300000000.0,
                recent_gain_pct=0.12,
                ma20_deviation_pct=0.14,
                pressure_distance_pct=None,
                volume_ratio_5=1.5,
                rsi_14=65.0,
                position_percentile_60=0.75,
                first_board_count=60,
                ready_candidate_count=0,
                second_day_one_word=False,
                blockers=(),
                second_board_closed=False,
                second_board_touched=False,
                buy_day_positive=True,
            )
            for i in range(1, 20)
        ]

        filtered = module.apply_market_width_gate(
            matches=matches,
            min_score=80,
            max_score=0,
            allowed_position_labels=module.parse_allowed_position_labels(
                "breakout"
            ),
            min_low_breakout_first_board_count=0,
            min_low_breakout_ready_candidates=0,
            max_ready_candidates=18,
        )

        self.assertEqual(filtered, [])

    def test_profit_matrix_baseline_matches_product_score_gate(self) -> None:
        module = self._load_profit_matrix_module()

        baseline = module.baseline_case()
        focused_cases = module.build_entry_cases(wide=False)
        focused_max_scores = {case["max_score"] for case in focused_cases}

        self.assertEqual(baseline["entry"]["min_score"], 82)
        self.assertEqual(baseline["entry"]["max_score"], 90)
        self.assertIn(None, focused_max_scores)
        self.assertIn(88, focused_max_scores)
        self.assertIn(90, focused_max_scores)
        self.assertIn(92, focused_max_scores)

    def test_strategy_matrix_one_position_uses_visible_rank_and_overlap_gate(
        self,
    ) -> None:
        module = self._load_strategy_matrix_module()

        high_rank_loser = module.Trade(
            strategy_id="sealed",
            strategy_name="sealed",
            symbol="600001",
            name="visible high rank",
            signal_date="2026-04-30",
            entry_date="2026-04-30",
            exit_date="2026-05-06",
            entry_price=10.0,
            exit_price=9.0,
            gross_return_pct=-0.1,
            net_return_pct=-0.1,
            hold_days=2,
            reason="test",
            rank_score=10.0,
            rank_turnover_amount=100.0,
        )
        low_rank_future_winner = module.Trade(
            strategy_id="sealed",
            strategy_name="sealed",
            symbol="600002",
            name="future winner",
            signal_date="2026-04-30",
            entry_date="2026-04-30",
            exit_date="2026-05-06",
            entry_price=10.0,
            exit_price=12.0,
            gross_return_pct=0.2,
            net_return_pct=0.2,
            hold_days=2,
            reason="test",
            rank_score=1.0,
            rank_turnover_amount=999.0,
        )
        overlapping_trade = module.Trade(
            strategy_id="sealed",
            strategy_name="sealed",
            symbol="600003",
            name="overlap",
            signal_date="2026-05-05",
            entry_date="2026-05-05",
            exit_date="2026-05-07",
            entry_price=10.0,
            exit_price=11.0,
            gross_return_pct=0.1,
            net_return_pct=0.1,
            hold_days=2,
            reason="test",
            rank_score=20.0,
            rank_turnover_amount=100.0,
        )
        later_trade = module.Trade(
            strategy_id="sealed",
            strategy_name="sealed",
            symbol="600004",
            name="later",
            signal_date="2026-05-07",
            entry_date="2026-05-07",
            exit_date="2026-05-08",
            entry_price=10.0,
            exit_price=12.0,
            gross_return_pct=0.2,
            net_return_pct=0.2,
            hold_days=1,
            reason="test",
            rank_score=5.0,
            rank_turnover_amount=100.0,
        )

        daily_top = module.select_daily_top_trades(
            [low_rank_future_winner, high_rank_loser, overlapping_trade, later_trade]
        )
        selected = module.select_one_position_trades(daily_top)
        summary = module.summarize_position_trades(selected, position_pct=0.08)

        self.assertEqual([item.symbol for item in daily_top], ["600001", "600003", "600004"])
        self.assertEqual([item.symbol for item in selected], ["600001", "600004"])
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["win_count"], 1)
        self.assertEqual(summary["position_weighted_return_pct"], 0.0079)

    def test_limit_up_board_profit_matrix_keeps_validation_gate(self) -> None:
        module = self._load_board_profit_matrix_module()
        base = {
            "summary": {
                "sample_count": 100,
                "win_rate": 0.55,
                "position_weighted_return_pct": 0.12,
                "max_drawdown_pct": -0.03,
            },
            "train_summary": {
                "sample_count": 80,
                "position_weighted_return_pct": 0.10,
            },
            "validation_summary": {
                "sample_count": 20,
                "position_weighted_return_pct": -0.01,
            },
            "yearly": {
                "2024": {"sample_count": 40, "position_weighted_return_pct": 0.04},
                "2025": {"sample_count": 40, "position_weighted_return_pct": 0.05},
                "2026": {"sample_count": 20, "position_weighted_return_pct": -0.01},
            },
        }

        self.assertFalse(module.qualifies_result(base))
        base["validation_summary"]["position_weighted_return_pct"] = 0.02
        base["yearly"]["2026"]["position_weighted_return_pct"] = 0.02

        self.assertTrue(module.qualifies_result(base))

    def test_limit_up_board_profit_matrix_profiles_separate_attack_from_balance(
        self,
    ) -> None:
        module = self._load_board_profit_matrix_module()

        def result(case_id: str, total: float, validation: float) -> dict:
            return {
                "entry_case": {"case_id": case_id},
                "exit_case": {"case_id": "exit"},
                "rank_case": "score",
                "summary": {
                    "sample_count": 160,
                    "win_rate": 0.62,
                    "position_weighted_return_pct": total,
                    "max_drawdown_pct": -0.02,
                },
                "train_summary": {
                    "sample_count": 120,
                    "win_rate": 0.61,
                    "position_weighted_return_pct": total - validation,
                    "max_drawdown_pct": -0.02,
                },
                "validation_summary": {
                    "sample_count": 40,
                    "win_rate": 0.7,
                    "position_weighted_return_pct": validation,
                    "max_drawdown_pct": -0.01,
                },
                "yearly": {},
                "exit_reasons": {},
                "score": validation * 130 + total * 45,
            }

        profiles = module.build_result_profiles(
            [
                result("balanced", total=0.70, validation=0.10),
                result("attack", total=0.90, validation=0.03),
            ]
        )

        self.assertEqual(profiles["balanced"]["entry_case"], "balanced")
        self.assertEqual(profiles["attack"]["entry_case"], "attack")

    def test_limit_up_board_profit_matrix_stop_wins_same_daily_bar_collision(
        self,
    ) -> None:
        module = self._load_board_profit_matrix_module()
        candidate = module.BoardCandidate(
            symbol="600001",
            name="board candidate",
            board_date="2026-04-30",
            index=0,
            entry_price=10.0,
            previous_close=9.09,
            close_pct=0.1,
            high_pct=0.1,
            estimated_turnover_amount=300_000_000.0,
            volume_ratio_20=1.5,
            recent_gain_pct=0.2,
            ma20_deviation_pct=0.2,
            position_percentile_60=0.7,
            first_board=True,
            ma_bullish=True,
            rank_score=12.0,
        )
        bars = [
            module.sm.DailyBar("2026-04-30", 9.8, 10.0, 10.0, 9.8, 10000),
            module.sm.DailyBar("2026-05-06", 10.0, 10.2, 10.6, 9.3, 10000),
        ]
        exit_case = module.ExitCase(
            case_id="collision",
            stop_loss_pct=0.06,
            take_profit_pct=0.05,
            max_hold_days=1,
            weak_next_open_exit_pct=None,
        )

        trade = module.simulate_board_trade(
            candidate,
            bars,
            exit_case,
            roundtrip_cost_pct=0.0015,
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade.reason, "stop_loss")
        self.assertEqual(trade.exit_price, 9.4)

    def test_limit_up_board_walk_forward_requires_stable_training_edge(self) -> None:
        module = self._load_board_profit_matrix_module()
        default = {
            "position_weighted_return_pct": 0.10,
            "win_rate": 0.70,
            "max_drawdown_pct": -0.02,
        }

        self.assertFalse(
            module.beats_default_in_training(
                {
                    "position_weighted_return_pct": 0.119,
                    "win_rate": 0.70,
                    "max_drawdown_pct": -0.02,
                },
                default,
            )
        )
        self.assertFalse(
            module.beats_default_in_training(
                {
                    "position_weighted_return_pct": 0.13,
                    "win_rate": 0.69,
                    "max_drawdown_pct": -0.02,
                },
                default,
            )
        )
        self.assertFalse(
            module.beats_default_in_training(
                {
                    "position_weighted_return_pct": 0.13,
                    "win_rate": 0.70,
                    "max_drawdown_pct": -0.021,
                },
                default,
            )
        )
        self.assertTrue(
            module.beats_default_in_training(
                {
                    "position_weighted_return_pct": 0.121,
                    "win_rate": 0.70,
                    "max_drawdown_pct": -0.02,
                },
                default,
            )
        )

    def test_research_backtest_blocks_one_word_by_open_without_future_low(self) -> None:
        module = self._load_research_backtest_module()
        bars = [
            module.DailyBar("2026-01-01", 8.0, 8.0, 8.1, 7.9, 10000)
            for _ in range(70)
        ]
        bars[-3] = module.DailyBar("2026-04-28", 9.0, 9.0, 9.1, 8.9, 10000)
        bars[-2] = module.DailyBar("2026-04-29", 9.0, 9.9, 9.9, 9.0, 30000)
        bars[-1] = module.DailyBar("2026-04-30", 10.85, 10.3, 10.89, 10.0, 40000)
        stock = module.StockMeta("600001", "涓荤嚎棣栨澘鍊欓€?", "2020-01-01")

        match = module.build_match(
            stock=stock,
            bars=bars,
            index=len(bars) - 2,
            next_bar=bars[-1],
            first_pct=0.1,
            min_turnover_amount=1,
            liquidity_score_amount=1,
            recent_gain_block_pct=0.45,
            high_deviation_block_pct=1,
            near_pressure_pct=0,
            min_confirm_open_pct=0,
            max_confirm_open_pct=0.2,
            min_volume_ratio_5=0,
            min_rsi_14=0,
            max_rsi_14=100,
            min_position_percentile_60=0,
        )

        self.assertTrue(match.second_day_one_word)
        self.assertIn("second_day_one_word_untradable", match.blockers)

    def test_research_backtest_trailing_stop_uses_previous_peak_only(self) -> None:
        module = self._load_research_backtest_module()
        match = module.Match(
            symbol="600001",
            name="涓荤嚎棣栨澘鍊欓€?",
            first_board_date="2026-04-29",
            second_day_date="2026-04-30",
            first_board_pct=0.1,
            second_close_pct=0.01,
            second_open_pct=0.02,
            second_high_pct=0.09,
            buy_open_to_close_pct=0.01,
            score=90.0,
            position_label="breakout",
            estimated_turnover_amount=300000000.0,
            recent_gain_pct=0.12,
            ma20_deviation_pct=0.14,
            pressure_distance_pct=None,
            volume_ratio_5=1.5,
            rsi_14=65.0,
            position_percentile_60=0.75,
            first_board_count=60,
            ready_candidate_count=8,
            second_day_one_word=False,
            blockers=(),
            second_board_closed=False,
            second_board_touched=False,
            buy_day_positive=True,
        )
        histories = {
            "600001": [
                module.DailyBar("2026-04-30", 10.0, 10.1, 10.3, 9.9, 10000),
                module.DailyBar("2026-05-06", 10.1, 10.2, 11.0, 9.8, 10000),
                module.DailyBar("2026-05-07", 10.2, 10.3, 10.4, 10.0, 10000),
            ]
        }

        trade = module.simulate_trade(
            match=match,
            histories=histories,
            stop_loss_pct=0.2,
            first_take_profit_pct=0.5,
            strong_take_profit_pct=0.08,
            trailing_stop_pct=0.01,
            discipline_exit_min_gain_pct=-1,
            max_holding_trade_days=2,
            max_simulation_trade_days=2,
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade.exit_reason, "trailing_take_profit")
        self.assertEqual(trade.exit_date, "2026-05-07")

    def test_research_backtest_adds_cached_universe_when_provider_is_partial(self) -> None:
        module = self._load_research_backtest_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            (cache_dir / "000001.json").write_text(
                json.dumps({"name": "娣卞競涓绘澘鏍锋湰", "rows": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            stocks = {
                "600001": module.StockMeta("600001", "娌競涓绘澘鏍锋湰", "2020-01-01"),
            }

            added = module.add_cached_universe(stocks, cache_dir)

            self.assertEqual(added, 1)
            self.assertIn("000001", stocks)
            self.assertEqual(stocks["000001"].name, "娣卞競涓绘澘鏍锋湰")

    def _load_research_backtest_module(self):
        spec = importlib.util.spec_from_file_location(
            "firemoney_research_backtest_for_test",
            Path("tools/research_one_to_two_backtest.py"),
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _load_profit_matrix_module(self):
        spec = importlib.util.spec_from_file_location(
            "firemoney_profit_matrix_for_test",
            Path("tools/research_one_to_two_profit_matrix.py"),
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _load_strategy_matrix_module(self):
        spec = importlib.util.spec_from_file_location(
            "firemoney_strategy_matrix_for_test",
            Path("tools/research_strategy_matrix_backtest.py"),
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _load_board_profit_matrix_module(self):
        spec = importlib.util.spec_from_file_location(
            "firemoney_board_profit_matrix_for_test",
            Path("tools/research_limit_up_board_profit_matrix.py"),
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_historical_replay_cli_brief_prints_profit_loss_ratio(self) -> None:
        with _workspace_temp_dir("historical_replay_cli") as root:
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

            self.assertIn("FireMoney", completed.stdout)
            self.assertIn("SampleMarketDataProvider", completed.stdout)
            self.assertIn("max_holding_close", completed.stdout)
            self.assertIn("2.00R", completed.stdout)
            self.assertIn("2026-04-30", completed.stdout)

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
            self.assertEqual(first.due_count, 6)
            self.assertEqual(first.executed_count, 6)
            self.assertEqual(second.executed_count, 0)
            self.assertEqual(second.skipped_count, 6)
            account = PaperTradeStore(root / "paper_trades.json").load()
            self.assertEqual(len(account.positions), 1)
            self.assertEqual(account.events[0].event_type.value, "paper_buy")

    def test_scheduler_retries_required_notification_when_send_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests: list[object] = []
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                feishu_notifier=FailingNotifier(requests=requests),
            )
            state_store = SchedulerStateStore(root / "scheduler_state.json")
            scheduler = OneToTwoScheduler(
                service=service,
                state_store=state_store,
            )

            first = scheduler.run_due(
                trade_date="2026-04-30",
                at_time="08:50",
                notify=True,
            )
            second = scheduler.run_due(
                trade_date="2026-04-30",
                at_time="08:51",
                notify=True,
            )

            first_morning = next(task for task in first.tasks if task.task_id == "morning")
            self.assertEqual(first_morning.notification_status, NotificationStatus.FAILED)
            self.assertEqual(state_store.load(), ("2026-04-30:strategy-decision",))
            second_morning = next(task for task in second.tasks if task.task_id == "morning")
            self.assertEqual(second_morning.notification_status, NotificationStatus.FAILED)
            self.assertEqual(len(requests), 2)

    def test_scheduler_retries_required_notification_when_only_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_enabled = os.environ.get("FEISHU_ENABLED")
            old_webhook = os.environ.get("FEISHU_WEBHOOK_URL")
            old_app_id = os.environ.get("FEISHU_APP_ID")
            old_app_secret = os.environ.get("FEISHU_APP_SECRET")
            old_receive_id = os.environ.get("FEISHU_RECEIVE_ID")
            try:
                os.environ["FEISHU_ENABLED"] = "true"
                os.environ.pop("FEISHU_WEBHOOK_URL", None)
                os.environ.pop("FEISHU_APP_ID", None)
                os.environ.pop("FEISHU_APP_SECRET", None)
                os.environ.pop("FEISHU_RECEIVE_ID", None)
                service = _build_service(
                    root,
                    market_data_provider=SampleMarketDataProvider(),
                )
                state_store = SchedulerStateStore(root / "scheduler_state.json")
                scheduler = OneToTwoScheduler(
                    service=service,
                    state_store=state_store,
                )

                first = scheduler.run_due(
                    trade_date="2026-04-30",
                    at_time="08:50",
                    notify=True,
                )
                second = scheduler.run_due(
                    trade_date="2026-04-30",
                    at_time="08:51",
                    notify=True,
                )
            finally:
                if old_enabled is None:
                    os.environ.pop("FEISHU_ENABLED", None)
                else:
                    os.environ["FEISHU_ENABLED"] = old_enabled
                if old_webhook is None:
                    os.environ.pop("FEISHU_WEBHOOK_URL", None)
                else:
                    os.environ["FEISHU_WEBHOOK_URL"] = old_webhook
                if old_app_id is None:
                    os.environ.pop("FEISHU_APP_ID", None)
                else:
                    os.environ["FEISHU_APP_ID"] = old_app_id
                if old_app_secret is None:
                    os.environ.pop("FEISHU_APP_SECRET", None)
                else:
                    os.environ["FEISHU_APP_SECRET"] = old_app_secret
                if old_receive_id is None:
                    os.environ.pop("FEISHU_RECEIVE_ID", None)
                else:
                    os.environ["FEISHU_RECEIVE_ID"] = old_receive_id

            first_morning = next(task for task in first.tasks if task.task_id == "morning")
            second_morning = next(task for task in second.tasks if task.task_id == "morning")
            self.assertEqual(first_morning.notification_status, NotificationStatus.PREPARED)
            self.assertEqual(second_morning.notification_status, NotificationStatus.PREPARED)
            self.assertNotIn("2026-04-30:morning", state_store.load())

    def test_scheduler_retries_done_required_notification_without_sent_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_enabled = os.environ.get("FEISHU_ENABLED")
            old_webhook = os.environ.get("FEISHU_WEBHOOK_URL")
            old_app_id = os.environ.get("FEISHU_APP_ID")
            old_app_secret = os.environ.get("FEISHU_APP_SECRET")
            old_receive_id = os.environ.get("FEISHU_RECEIVE_ID")
            try:
                os.environ["FEISHU_ENABLED"] = "true"
                os.environ.pop("FEISHU_WEBHOOK_URL", None)
                os.environ.pop("FEISHU_APP_ID", None)
                os.environ.pop("FEISHU_APP_SECRET", None)
                os.environ.pop("FEISHU_RECEIVE_ID", None)
                service = _build_service(
                    root,
                    market_data_provider=SampleMarketDataProvider(),
                )
                notification_store = NotificationRecordStore(root / "notifications.json")
                notification_store.append(
                    workflow="morning",
                    trade_date="2026-04-30",
                    result=FeishuNotificationResult(
                        status=NotificationStatus.PREPARED,
                        title="早评",
                        message="prepared",
                        webhook_configured=False,
                    ),
                )
                state_store = SchedulerStateStore(root / "scheduler_state.json")
                state_store.mark_done("2026-04-30:morning")
                scheduler = OneToTwoScheduler(
                    service=service,
                    state_store=state_store,
                )

                result = scheduler.run_due(
                    trade_date="2026-04-30",
                    at_time="08:51",
                    notify=True,
                )
            finally:
                if old_enabled is None:
                    os.environ.pop("FEISHU_ENABLED", None)
                else:
                    os.environ["FEISHU_ENABLED"] = old_enabled
                if old_webhook is None:
                    os.environ.pop("FEISHU_WEBHOOK_URL", None)
                else:
                    os.environ["FEISHU_WEBHOOK_URL"] = old_webhook
                if old_app_id is None:
                    os.environ.pop("FEISHU_APP_ID", None)
                else:
                    os.environ["FEISHU_APP_ID"] = old_app_id
                if old_app_secret is None:
                    os.environ.pop("FEISHU_APP_SECRET", None)
                else:
                    os.environ["FEISHU_APP_SECRET"] = old_app_secret
                if old_receive_id is None:
                    os.environ.pop("FEISHU_RECEIVE_ID", None)
                else:
                    os.environ["FEISHU_RECEIVE_ID"] = old_receive_id

            morning = next(task for task in result.tasks if task.task_id == "morning")
            self.assertEqual(morning.status, "completed")
            self.assertEqual(morning.notification_status, NotificationStatus.PREPARED)
            self.assertGreaterEqual(
                len(
                    [
                        record
                        for record in notification_store.load()
                        if record.workflow == "morning"
                    ]
                ),
                2,
            )

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

            self.assertEqual(result.executed_count, 2)
            self.assertEqual(
                {
                    task.task_id
                    for task in result.tasks
                    if task.status == "completed"
                },
                {"eod", "board-shadow-record"},
            )
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
                    "strategy-decision",
                    "paper-decision",
                },
            )
            account = PaperTradeStore(root / "paper_trades.json").load()
            self.assertEqual(account.positions, ())
            self.assertFalse(
                any(event.event_type.value == "paper_buy" for event in account.events)
            )

    def test_scheduler_records_board_shadow_after_eod_without_paper_trade(self) -> None:
        module = self._load_board_profit_matrix_module()
        stocks, histories = _board_shadow_market_fixture(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                board_shadow_store=LimitUpBoardShadowStore(
                    root / "board_shadow_samples.json",
                    created_at_provider=lambda: "20260501152000",
                ),
            )
            scheduler = OneToTwoScheduler(
                service=service,
                state_store=SchedulerStateStore(root / "scheduler_state.json"),
            )

            with patch(
                "server.firemoney_server.application.main_chain.board_matrix.load_cached_research_data",
                return_value=(stocks, histories),
            ):
                result = scheduler.run_due(
                    trade_date="2026-04-30",
                    at_time="15:20",
                    notify=False,
                )
            account = PaperTradeStore(root / "paper_trades.json").load()
            shadow_stability = service.build_limit_up_board_shadow_stability_report()
            notifications = NotificationRecordStore(root / "notifications.json").load()

            self.assertEqual(result.executed_count, 2)
            self.assertTrue(
                any(
                    task.task_id == "board-shadow-record"
                    and task.status == "completed"
                    for task in result.tasks
                )
            )
            self.assertEqual(shadow_stability.sample_count, 1)
            self.assertEqual(shadow_stability.recent_samples[0].as_of_date, "2026-04-29")
            self.assertTrue(
                any(
                    record.workflow == "board-shadow:record"
                    and record.status == NotificationStatus.PREPARED
                    for record in notifications
                )
            )
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
                    "--trade-date",
                    "2026-04-30",
                    "--at",
                    "09:31",
                    "--market-data-timeout-seconds",
                    "0",
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

    def test_beta_start_cli_rejects_sample_data_before_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_path = root / "paper_trades.json"
            scheduler_path = root / "scheduler_state.json"
            scheduler_run_path = root / "scheduler_runs.json"
            notifications_path = root / "notifications.json"
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
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("--sample-data", payload["summary"])
            self.assertFalse(scheduler_path.exists())
            self.assertEqual(scheduler_run_path.read_text(encoding="utf-8"), "{}")
            self.assertFalse(notifications_path.exists())
            self.assertEqual(PaperTradeStore(paper_path).load().events, ())

    def test_beta_start_cli_can_run_in_limited_mode_when_only_market_data_is_blocked(self) -> None:
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
                    title="FireMoney beta feishu test",
                    message="sent",
                    webhook_configured=True,
                ),
            )
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
                    "--market-data-timeout-seconds",
                    "0.01",
                    "--allow-market-data-timeout",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("--sample-data", payload["summary"])

    def test_beta_start_cli_auto_sends_feishu_test_before_limited_mode(self) -> None:
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
                    "--market-data-timeout-seconds",
                    "0.01",
                    "--allow-market-data-timeout",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                encoding="utf-8",
                text=True,
            )
            payload = json.loads(completed.stdout)
            records = NotificationRecordStore(notifications_path).load()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("--sample-data", payload["summary"])
            self.assertEqual(records, ())

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
        self.assertEqual(len(payload["schedule_runs"]), 10)
        self.assertEqual(sum(run["executed_count"] for run in payload["schedule_runs"]), 12)
        self.assertEqual(payload["notification_record_count"], 4)
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
            self.assertIn("board-shadow-system --start-date 2024-01-01 --brief", payload["launch_commands"][3])

    def test_beta_launch_plan_does_not_block_on_live_market_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = CountingOneToTwoProvider(
                SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
            )
            service = _build_service(
                Path(temp_dir),
                market_data_provider=provider,
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
            self.assertEqual(provider.row_load_count, 0)
            market_check = next(
                check
                for check in payload["doctor_report"]["checks"]
                if check["check_id"] == "market_data"
            )
            self.assertIn("计划模式", market_check["detail"])

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
            self.assertIn("board-shadow-system --start-date 2024-01-01 --brief", payload["launch_commands"][3])
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
            self.assertIn("board-shadow-system --start-date 2024-01-01 --brief", completed.stdout)
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
            self.assertIn("--no-notify", payload["summary"])
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

    def test_feishu_notifier_retries_transient_webhook_network_error(self) -> None:
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
        captured = []

        def fake_urlopen(req, timeout=8):
            captured.append(json.loads(req.data.decode("utf-8")))
            if len(captured) == 1:
                raise URLError(OSError("getaddrinfo failed"))
            return FakeFeishuResponse(b'{"StatusCode":0,"StatusMessage":"success"}')

        with patch.dict(os.environ, env, clear=True):
            with patch(
                "server.firemoney_server.infrastructure.feishu_notifier.request.urlopen",
                side_effect=fake_urlopen,
            ):
                sent = FeishuNotifier(
                    retry_attempts=2,
                    retry_delay_seconds=0,
                ).notify("title", "早评：message")

        self.assertEqual(sent.status, NotificationStatus.SENT)
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["msg_type"], "interactive")
        self.assertEqual(captured[1]["msg_type"], "interactive")

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
        self.assertEqual(send_payload["msg_type"], "interactive")
        content = json.loads(send_payload["content"])
        self.assertEqual(content["header"]["title"]["content"], "title")
        self.assertIn("message", content["elements"][0]["text"]["content"])

    def test_feishu_notifier_uses_card_webhook_with_text_fallback(self) -> None:
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
        captured = []

        def fake_urlopen(req, timeout=8):
            captured.append(json.loads(req.data.decode("utf-8")))
            if len(captured) == 1:
                raise URLError("interactive card disabled")
            return FakeFeishuResponse(b'{"StatusCode":0,"StatusMessage":"success"}')

        with patch.dict(os.environ, env, clear=True):
            with patch(
                "server.firemoney_server.infrastructure.feishu_notifier.request.urlopen",
                side_effect=fake_urlopen,
            ):
                sent = FeishuNotifier().notify("title", "买入：message")

        self.assertEqual(sent.status, NotificationStatus.SENT)
        self.assertEqual(captured[0]["msg_type"], "interactive")
        self.assertEqual(captured[0]["card"]["header"]["template"], "green")
        self.assertEqual(captured[1]["msg_type"], "text")
        self.assertIn("title\n买入：message", captured[1]["content"]["text"])

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
            self.assertTrue(hasattr(adapter, "build_limit_up_board_shadow_report"))
            self.assertTrue(hasattr(adapter, "record_limit_up_board_shadow_sample"))
            self.assertTrue(hasattr(adapter, "build_limit_up_board_shadow_system_report"))
            self.assertTrue(hasattr(adapter, "build_paper_backtest_report"))
            self.assertTrue(hasattr(adapter, "build_strategy_decision_report"))

    def test_gateway_protocol_stays_server_free(self) -> None:
        gateway = Path("client/desktop/firemoney_client/gateway.py")
        adapter = Path("client/desktop/firemoney_client/adapter.py")

        self.assertNotIn(
            "server.firemoney_server",
            gateway.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "server.firemoney_server",
            adapter.read_text(encoding="utf-8"),
        )

    def test_gateway_protocol_matches_local_adapter_public_surface(self) -> None:
        def class_methods(path: Path, class_name: str) -> set[str]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    return {
                        item.name
                        for item in node.body
                        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
                    }
            self.fail(f"{class_name} not found in {path}")

        gateway_methods = class_methods(
            Path("client/desktop/firemoney_client/gateway.py"),
            "MainChainGateway",
        )
        adapter_methods = class_methods(
            Path("client/desktop/firemoney_client/adapter.py"),
            "LocalMainChainAdapter",
        )

        self.assertEqual(gateway_methods, adapter_methods)

    def test_local_composition_builds_usable_main_chain_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = build_local_main_chain_context(
                sample_data=True,
                paper_store_path=root / "paper_trades.json",
                notification_store_path=root / "notifications.json",
                scheduler_state_path=root / "scheduler_state.json",
                scheduler_runs_path=root / "scheduler_runs.json",
            )

            report = context.adapter.build_one_to_two_morning_report(
                trade_date="2026-05-01",
                notify=False,
            )
            context.scheduler_state_store.mark_done("test-task")

            self.assertIsInstance(report, OneToTwoMorningReport)
            self.assertTrue(context.scheduler_state_store.is_done("test-task"))
            self.assertEqual(context.scheduler_run_store.load(limit=1), ())

    def test_sample_data_context_defaults_to_isolated_sample_state(self) -> None:
        context = build_local_main_chain_context(sample_data=True)

        self.assertIn(".firemoney", str(context.service._paper_store.path))
        self.assertIn("sample", str(context.service._paper_store.path))
        self.assertTrue(str(context.service._paper_store.path).endswith("paper_trades.json"))
        self.assertIn("sample", str(context.scheduler_state_store.path))
        self.assertIn("sample", str(context.scheduler_run_store.path))

    def test_sample_data_context_keeps_custom_paper_store_database_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store_path = root / "custom_sample_paper.json"
            context = build_local_main_chain_context(
                sample_data=True,
                paper_store_path=paper_store_path,
            )

            context.adapter.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
            )

            self.assertTrue(paper_store_path.exists())
            self.assertTrue(paper_store_path.with_suffix(".sqlite3").exists())

    def test_one_to_two_config_is_json_and_defaults_to_single_core_line(self) -> None:
        config_path = Path(
            "server/firemoney_server/infrastructure/config/one_to_two_strategy.zh_CN.json"
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        settings = load_one_to_two_settings()

        self.assertEqual(payload["strategy_id"], settings.strategy_id)
        self.assertEqual(settings.min_score, 82)
        self.assertEqual(settings.max_execution_score, 90)
        self.assertEqual(settings.initial_cash, 10000)
        self.assertEqual(settings.max_position_pct, 0.35)
        self.assertTrue(settings.small_account_mode_enabled)
        self.assertEqual(settings.small_account_min_lot_shares, 100)
        self.assertEqual(settings.small_account_target_position_pct, 0.18)
        self.assertEqual(settings.small_account_reduced_target_position_pct, 0.12)
        self.assertEqual(settings.small_account_max_position_pct, 0.35)
        self.assertEqual(settings.small_account_reduced_max_position_pct, 0.2)
        self.assertEqual(settings.max_daily_trades, 1)
        self.assertEqual(settings.max_holding_trade_days, 2)
        self.assertEqual(settings.hard_max_holding_trade_days, 5)
        self.assertEqual(settings.discipline_exit_min_gain_pct, 0.04)
        self.assertEqual(settings.positive_lock_profit_pct, 0.03)
        self.assertEqual(settings.minimum_reward_risk_ratio, 2.0)
        self.assertEqual(settings.paper_guard_max_consecutive_quality_failures, 2)
        self.assertEqual(settings.paper_guard_min_quality_bucket_samples, 3)
        self.assertEqual(settings.paper_guard_quality_bucket_block_losses, 2)
        self.assertEqual(payload["parameters"]["min_confirm_open_pct"], 0.0)
        self.assertEqual(payload["parameters"]["max_confirm_open_pct"], 0.035)
        self.assertEqual(settings.min_confirm_open_pct, 0.0)
        self.assertEqual(settings.max_confirm_open_pct, 0.035)
        self.assertEqual(settings.min_turnover_amount, 200000000)
        self.assertEqual(settings.liquidity_score_amount, 80000000)
        self.assertEqual(settings.min_turnover_dragon_score, 72)
        self.assertEqual(settings.min_turnover_dragon_turnover_rate, 3.0)
        self.assertEqual(settings.max_turnover_dragon_turnover_rate, 18.0)
        self.assertEqual(settings.min_turnover_dragon_sealed_ratio, 0.1)
        self.assertEqual(settings.min_turnover_dragon_auction_ratio, 0.025)
        self.assertEqual(settings.first_take_profit_pct, 0.12)
        self.assertEqual(settings.strong_take_profit_pct, 0.1)
        self.assertEqual(settings.stop_loss_pct, 0.04)
        self.assertEqual(settings.trailing_stop_pct, 0.02)
        self.assertEqual(settings.main_rise_runner_min_quality_score, 86)
        self.assertEqual(settings.main_rise_runner_min_opened_score, 90)
        self.assertEqual(settings.main_rise_runner_min_mainline_score, 75)
        self.assertEqual(settings.main_rise_runner_trailing_start_pct, 0.06)
        self.assertEqual(settings.main_rise_runner_trailing_stop_pct, 0.02)
        self.assertEqual(settings.main_rise_runner_profit_floor_pct, 0.015)
        self.assertEqual(settings.mainline_fade_score, 45)
        self.assertEqual(settings.min_low_breakout_first_board_count, 45)
        self.assertEqual(settings.min_low_breakout_ready_candidates, 6)
        self.assertEqual(settings.max_ready_candidates, 18)
        self.assertEqual(settings.min_volume_ratio_5, 1.0)
        self.assertEqual(settings.min_rsi_14, 55)
        self.assertEqual(settings.max_rsi_14, 85)
        self.assertEqual(settings.min_position_percentile_60, 0.55)
        self.assertEqual(settings.allowed_position_labels, ("低位平台突破", "平台突破", "低位启动"))
        self.assertEqual(settings.selection_rank, "turnover")
        self.assertIn("创业板", settings.excluded_boards)

    def test_framework_layer_has_no_firemoney_business_imports(self) -> None:
        forbidden_prefixes = (
            "server.firemoney_server",
            "client.desktop",
            "shared.contracts",
        )
        violations: list[str] = []
        for path in Path("framework").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names = (node.module or "",)
                else:
                    continue
                for module in names:
                    if module.startswith(forbidden_prefixes):
                        violations.append(f"{path}:{module}")

        self.assertEqual(violations, [])

    def test_preview_renderer_does_not_import_firemoney_infrastructure(self) -> None:
        forbidden = "server.firemoney_server.infrastructure"
        renderer_files = (
            Path("client/desktop/firemoney_client/renderer.py"),
            Path("client/desktop/firemoney_client/render_sections.py"),
        )
        for renderer in renderer_files:
            self.assertNotIn(
                forbidden,
                renderer.read_text(encoding="utf-8"),
            )

    def test_notification_preview_highlights_decision_focus(self) -> None:
        from client.desktop.firemoney_client.render_sections import (
            render_notification_message,
        )

        html = render_notification_message(
            "08:50 早盘判断",
            "买入：主线首板候选(600001)\n止损 10.1\n下一步：09:31 复核触发条件",
        )

        self.assertIn('data-tone="buy"', html)
        self.assertIn('data-tone="danger"', html)
        self.assertIn('data-tone="next"', html)
        self.assertIn("notification-chip", html)

    def test_preview_entry_delegates_service_assembly(self) -> None:
        preview = Path("client/desktop/firemoney_client/preview.py")
        preview_data = Path("client/desktop/firemoney_client/preview_data.py")

        self.assertLessEqual(len(preview.read_text(encoding="utf-8").splitlines()), 60)
        self.assertIn(
            "build_preview_workflow_data",
            preview.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "server.firemoney_server.infrastructure",
            preview.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "server.firemoney_server.infrastructure",
            preview_data.read_text(encoding="utf-8"),
        )

    def test_preview_backtest_cache_rejects_stale_coverage(self) -> None:
        from client.desktop.firemoney_client.preview_data import (
            PAPER_BACKTEST_PREVIEW_CACHE_VERSION,
            _read_paper_backtest_report,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "paper_backtest.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "preview_cache_version": PAPER_BACKTEST_PREVIEW_CACHE_VERSION,
                        "data_coverage_end": "2026-04-30",
                        "current_month_notes": (
                            "本月回测：请求到 2026-05-23，但日线研究缓存只覆盖到 2026-04-30，2026-05 尚未完整纳入战法回测。",
                        ),
                    }
                ),
                encoding="utf-8",
            )

            self.assertIsNone(
                _read_paper_backtest_report(
                    cache_path,
                    requested_end_date="2026-05-23",
                )
            )

    def test_cli_brief_formatters_do_not_import_server_layers(self) -> None:
        forbidden = ("server.firemoney_server",)
        presenter_files = (
            Path("client/desktop/firemoney_client/presenters/brief_formatters.py"),
            Path("client/desktop/firemoney_client/presenters/decision_presenter.py"),
            Path("client/desktop/firemoney_client/presenters/notification_presenter.py"),
            Path("client/desktop/firemoney_client/presenters/trust_presenter.py"),
        )
        for presenter in presenter_files:
            tree = ast.parse(presenter.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        self.assertFalse(module.startswith(forbidden), module)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    self.assertFalse(module.startswith(forbidden), module)

    def test_cli_parser_exposes_core_modes_without_service_imports(self) -> None:
        parser = build_one_to_two_parser()

        paper_args = parser.parse_args(
            [
                "paper-decision",
                "--sample-data",
                "--trade-date",
                "2026-05-09",
                "--brief",
            ]
        )
        strategy_args = parser.parse_args(
            [
                "strategy-decision",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2026-05-05",
                "--brief",
            ]
        )
        backtest_args = parser.parse_args(
            [
                "paper-backtest",
                "--start-date",
                "2020-01-01",
                "--end-date",
                "2026-05-05",
                "--refresh-cache",
                "--brief",
            ]
        )
        k92_backtest_args = parser.parse_args(
            [
                "k92-backtest",
                "--start-date",
                "2020-01-01",
                "--end-date",
                "2026-05-05",
                "--brief",
            ]
        )
        missed_args = parser.parse_args(
            [
                "missed-opportunities",
                "--start-date",
                "2026-05-01",
                "--end-date",
                "2026-05-05",
                "--brief",
            ]
        )

        self.assertEqual(paper_args.mode, "paper-decision")
        self.assertTrue(paper_args.sample_data)
        self.assertTrue(paper_args.brief)
        self.assertEqual(paper_args.trade_date, "2026-05-09")
        self.assertEqual(strategy_args.mode, "strategy-decision")
        self.assertEqual(strategy_args.start_date, "2024-01-01")
        self.assertEqual(strategy_args.end_date, "2026-05-05")
        self.assertEqual(backtest_args.mode, "paper-backtest")
        self.assertEqual(backtest_args.start_date, "2020-01-01")
        self.assertEqual(backtest_args.end_date, "2026-05-05")
        self.assertTrue(backtest_args.refresh_cache)
        self.assertEqual(k92_backtest_args.mode, "k92-backtest")
        self.assertEqual(k92_backtest_args.start_date, "2020-01-01")
        self.assertEqual(k92_backtest_args.end_date, "2026-05-05")
        self.assertEqual(missed_args.mode, "missed-opportunities")
        self.assertEqual(missed_args.start_date, "2026-05-01")
        self.assertEqual(missed_args.end_date, "2026-05-05")

        parser_module = Path("client/desktop/firemoney_client/cli/parser.py")
        tree = ast.parse(parser_module.read_text(encoding="utf-8"))
        forbidden = ("server.firemoney_server", "client.desktop.firemoney_client.presenters")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            else:
                continue
            for module in modules:
                self.assertFalse(module.startswith(forbidden), module)

    def test_missed_opportunity_report_flags_uncaptured_profitable_backtest_trades(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = _build_service(
                root,
                paper_store=PaperTradeStore(root / "paper_trades.json"),
                notification_store=NotificationRecordStore(root / "notifications.json"),
                scheduler_run_store=SchedulerRunStore(root / "scheduler_runs.json"),
            )

            report = service.build_missed_opportunity_report(
                start_date="2026-05-01",
                end_date="2026-05-23",
                limit=10,
            )

            self.assertEqual(report.status, "warning")
            self.assertGreaterEqual(report.backtest_trade_count, 1)
            self.assertGreaterEqual(report.missed_profit_count, 1)
            self.assertGreater(report.missed_account_return_pct, 0.0)
            self.assertTrue(any(item.paper_status == "missed" for item in report.items))
            self.assertIn("错失盈利机会", report.summary)

    def test_cli_entry_keeps_brief_formatting_out_of_dispatcher(self) -> None:
        cli = Path("client/desktop/firemoney_client/one_to_two_cli.py")
        tree = ast.parse(cli.read_text(encoding="utf-8"))
        formatter_names = (
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        )

        self.assertNotIn("_format_beta_plan_brief", formatter_names)
        self.assertNotIn("_format_notifications_brief", formatter_names)

    def test_cli_entry_stays_thin_after_runtime_split(self) -> None:
        cli = Path("client/desktop/firemoney_client/one_to_two_cli.py")
        tree = ast.parse(cli.read_text(encoding="utf-8"))
        source = cli.read_text(encoding="utf-8")
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(f"{'.' * node.level}{node.module or ''}")

        self.assertLessEqual(len(source.splitlines()), 30)
        self.assertIn(".cli.parser", imports)
        self.assertIn(".cli.runtime", imports)
        self.assertNotIn("server.firemoney_server.application.one_to_two_scheduler", imports)
        self.assertFalse(
            any(module.startswith("server.firemoney_server") for module in imports),
            imports,
        )
        self.assertNotIn("client.desktop.firemoney_client.composition", imports)
        self.assertNotIn("client.desktop.firemoney_client.presenters.brief_formatters", imports)

    def test_cli_runtime_delegates_terminal_output(self) -> None:
        runtime = Path("client/desktop/firemoney_client/cli/runtime.py")
        source = runtime.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(f"{'.' * node.level}{node.module or ''}")

        self.assertIn(".output", imports)
        self.assertIn(".handlers", imports)
        self.assertIn(".schedule_runner", imports)
        self.assertLessEqual(len(source.splitlines()), 80)
        self.assertNotIn(".presenters.brief_formatters", imports)
        self.assertNotIn("OneToTwoScheduler", source)
        self.assertNotIn("build_one_to_two_beta_launch_plan", source)
        self.assertNotIn("run_one_to_two_beta_rehearsal", source)
        self.assertNotIn("_BRIEF_FORMATTERS", source)
        self.assertNotIn("json.dumps", source)

    def test_cli_handlers_cover_parser_modes(self) -> None:
        from client.desktop.firemoney_client.cli.handlers import HANDLED_MODES
        from client.desktop.firemoney_client.cli.schedule_runner import SCHEDULE_MODES

        parser = build_one_to_two_parser()
        mode_action = next(action for action in parser._actions if action.dest == "mode")
        parser_modes = set(mode_action.choices)

        self.assertEqual(parser_modes, set(HANDLED_MODES) | set(SCHEDULE_MODES))
        self.assertFalse(set(HANDLED_MODES) & set(SCHEDULE_MODES))
        self.assertIn("schedule", SCHEDULE_MODES)
        self.assertIn("beta-start", SCHEDULE_MODES)

    def test_cli_schedule_runner_owns_scheduler_execution(self) -> None:
        runtime = Path("client/desktop/firemoney_client/cli/runtime.py").read_text(
            encoding="utf-8"
        )
        handlers = Path("client/desktop/firemoney_client/cli/handlers.py").read_text(
            encoding="utf-8"
        )
        schedule_runner = Path(
            "client/desktop/firemoney_client/cli/schedule_runner.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("OneToTwoScheduler", runtime)
        self.assertNotIn("OneToTwoScheduler", handlers)
        self.assertIn("OneToTwoScheduler", schedule_runner)
        self.assertIn("run_schedule_command", schedule_runner)
        self.assertIn("run_beta_start_command", schedule_runner)

    def test_cli_output_keeps_service_execution_out(self) -> None:
        output = Path("client/desktop/firemoney_client/cli/output.py")
        tree = ast.parse(output.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(f"{'.' * node.level}{node.module or ''}")

        self.assertFalse(
            any(module.startswith("server.firemoney_server") for module in imports),
            imports,
        )
        self.assertNotIn(".composition", imports)

    def test_paper_backtest_brief_formatter_outputs_yearly_metrics(self) -> None:
        from client.desktop.firemoney_client.presenters.brief_formatters import (
            format_paper_backtest_brief,
        )

        report = PaperBacktestReport(
            report_id="paper-backtest-2020-01-01-to-2026-05-05",
            start_date="2020-01-01",
            end_date="2026-05-05",
            status="warning",
            strategy_id="board-shadow-system",
            summary="年度验证有弱点",
            overall=LimitUpBoardShadowSystemMetric(
                label="overall",
                sample_count=2,
                win_rate=0.5,
                position_weighted_return_pct=0.04,
                max_drawdown_pct=-0.01,
            ),
            train=LimitUpBoardShadowSystemMetric(
                label="train",
                sample_count=1,
                win_rate=1.0,
                position_weighted_return_pct=0.03,
                max_drawdown_pct=0.0,
            ),
            validation=LimitUpBoardShadowSystemMetric(
                label="validation",
                sample_count=1,
                win_rate=0.0,
                position_weighted_return_pct=0.01,
                max_drawdown_pct=-0.01,
            ),
            yearly=(
                MainChainService._to_paper_backtest_yearly_metric(
                    "2020",
                    {
                        "sample_count": 1,
                        "win_rate": 1.0,
                        "average_net_return_pct": 0.04,
                        "median_net_return_pct": 0.04,
                        "position_weighted_return_pct": 0.03,
                        "max_drawdown_pct": 0.0,
                    },
                ),
                MainChainService._to_paper_backtest_yearly_metric(
                    "2021",
                    {
                        "sample_count": 1,
                        "win_rate": 0.0,
                        "average_net_return_pct": -0.02,
                        "median_net_return_pct": -0.02,
                        "position_weighted_return_pct": -0.01,
                        "max_drawdown_pct": -0.01,
                    },
                ),
            ),
            negative_years=("2021",),
            weak_years=("2021",),
            buy_rule_summary=("只用当日可见字段",),
            improvement_notes=("逐年展示收益",),
            no_future_leakage_notes=("未来日线只用于卖点模拟",),
            limitations=("不能保证每笔盈利",),
            next_action="继续验证",
            data_coverage_start="2020-01-01",
            data_coverage_end="2026-05-05",
            data_coverage_notes=("缓存覆盖完整",),
            friction_scenarios=(
                PaperBacktestFrictionScenario(
                    label="stress_cost_0.50pct",
                    roundtrip_cost_pct=0.005,
                    sample_count=2,
                    win_rate=0.5,
                    position_weighted_return_pct=0.03,
                    max_drawdown_pct=-0.012,
                    validation_return_pct=0.008,
                    negative_years=(),
                    weakest_year="2021",
                    weakest_year_return_pct=0.004,
                    status="warning",
                    conclusion="Friction stress is fragile",
                ),
            ),
            return_target=PaperBacktestReturnTarget(
                target_annual_return_pct=1.0,
                weakest_year="2020",
                weakest_year_return_pct=0.03,
                required_linear_position_multiple=33.33,
                projected_max_drawdown_pct=0.0,
                conclusion="Do not rely on leverage alone to chase 100% annual return.",
            ),
            efficiency_candidates=(
                PaperBacktestEfficiencyCandidate(
                    label="6.5% first target",
                    total_return_pct=3.9215,
                    max_drawdown_pct=-0.0218,
                    validation_return_pct=0.1064,
                    weakest_full_year_return_pct=0.1006,
                    monthly_positive_ratio=0.79,
                    worst_month_return_pct=-0.011,
                    conclusion="Parallel-validate this higher-efficiency challenger.",
                ),
            ),
            monthly_stability=PaperBacktestMonthlyStability(
                total_months=24,
                positive_months=18,
                positive_month_ratio=0.75,
                worst_month="2021-02",
                worst_month_return_pct=-0.012,
                longest_losing_streak=2,
                conclusion="Monthly stability is solid, but future positive months are never guaranteed.",
            ),
            monthly=(
                PaperBacktestMonthlyMetric(
                    month="2021-01",
                    position_weighted_return_pct=0.021,
                    status="ready",
                    conclusion="月度正收益",
                ),
                PaperBacktestMonthlyMetric(
                    month="2021-02",
                    position_weighted_return_pct=-0.012,
                    status="warning",
                    conclusion="月度小幅回撤",
                ),
            ),
            current_month_notes=("本月回测：2026-05 尚未完整纳入战法回测。",),
        )

        text = format_paper_backtest_brief(report)

        self.assertIn("模拟盘买入算法回测", text)
        self.assertIn("2020", text)
        self.assertIn("2021", text)
        self.assertIn("亏损年份：2021", text)
        self.assertIn("执行摩擦压力", text)
        self.assertIn("stress_cost_0.50pct", text)
        self.assertIn("年化 100% 目标检查", text)
        self.assertIn("33.33x", text)
        self.assertIn("同仓位效率挑战者", text)
        self.assertIn("6.5% first target", text)
        self.assertIn("月度稳定性", text)
        self.assertIn("18/24", text)
        self.assertIn("月度收益", text)
        self.assertIn("2021-02", text)
        self.assertIn("本月回测状态", text)
        self.assertIn("2026-05 尚未完整纳入", text)

    def test_notification_presenter_unifies_action_titles(self) -> None:
        buy_record = NotificationRecord(
            record_id="buy",
            channel="feishu",
            workflow="watch:open",
            trade_date="2026-05-09",
            status=NotificationStatus.PREPARED,
            title="FireMoney 盘中值守",
            message="交易日：2026-05-09\n持仓：主线首板候选(600001) 300 股",
            created_at="20260509093100",
        )
        sell_record = NotificationRecord(
            record_id="sell",
            channel="feishu",
            workflow="watch:risk",
            trade_date="2026-05-09",
            status=NotificationStatus.PREPARED,
            title="FireMoney 风险值守",
            message="阶段：risk\n完成样本：主线首板候选(600001)",
            created_at="20260509145000",
        )

        self.assertEqual(
            notification_display_title(buy_record),
            "FireMoney 模拟买入：主线首板候选(600001)",
        )
        self.assertEqual(
            notification_display_title(sell_record),
            "FireMoney 模拟卖出：主线首板候选(600001)",
        )
        self.assertEqual(
            first_notification_detail(sell_record.message),
            "完成样本：主线首板候选(600001)",
        )

    def test_decision_presenter_builds_cockpit_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account = PaperAccount(
                account_id="one-to-two-paper",
                last_trade_date="2026-05-09",
                cash=10000.0,
                initial_cash=10000.0,
                equity=10000.0,
                max_position_pct=0.35,
                max_daily_trades=1,
                daily_trade_count=0,
                positions=(),
                events=(),
                closed_trades=(),
            )
            watch_report = _build_service(
                Path(temp_dir),
                market_data_provider=SampleMarketDataProvider(),
            ).build_one_to_two_morning_report(trade_date="2026-05-01", notify=False)
        watch_report = replace(watch_report, account=account)
        strategy_report = StrategyDecisionReport(
            report_id="strategy-2026-05-09",
            trade_date="2026-05-09",
            status="ready",
            evidence_end_date="2026-05-05",
            market_regime="trend_main_rise_day",
            regime_rationale="主线候选密度高，优先做趋势主升。",
            regime_action="attack_trend_main_rise",
            k92_regime="leader_attack_day",
            k92_gate="confirm",
            k92_rationale="K92 守门：龙头进攻日。",
            selected_strategy_id="board-shadow-system",
            selected_action="operate_when_signal_exists",
            selected_role="main_operating_line",
            summary="test strategy",
            options=(),
            risk_rules=(),
            next_action="run paper-decision",
        )
        paper_report = PaperTradingDecisionReport(
            report_id="paper-2026-05-09",
            trade_date="2026-05-09",
            status="ready_to_buy",
            market_regime="trend_main_rise_day",
            execution_track="board_shadow_system_execution",
            selected_strategy_id="board-shadow-system",
            selected_action="operate_when_signal_exists",
            evidence_end_date="2026-05-05",
            should_buy=True,
            instruction=PaperTradingInstruction(
                action="buy",
                strategy_id="board-shadow-system",
                symbol="600001",
                name="主线首板候选",
                timing="early_session",
                entry_window="09:31-09:45",
                entry_trigger="test trigger",
                entry_price=10.52,
                stop_loss=10.1,
                first_take_profit_price=11.78,
                planned_stop_risk_pct=0.0399,
                planned_first_target_return_pct=0.1198,
                planned_reward_risk_ratio=3.0,
                max_intratrade_drawdown_budget_pct=0.1198,
                position_pct=0.1052,
                cash_budget=1052.0,
                quantity=100,
                confidence="high",
                rationale="test rationale",
                invalidation_rules=(),
                sell_rules=(),
                risk_notes=(),
                next_check_time="09:31",
            ),
            holding_instruction=None,
            candidate_count=9,
            ready_count=6,
            blocked_count=3,
            account_equity=10000.0,
            account_cash=10000.0,
            existing_position_count=0,
            guard_decision=PaperTradingGuardDecision(
                status="reduced",
                action="allow_reduced",
                review_sample_count=1,
                win_rate=0.0,
                average_return_pct=0.0,
                max_drawdown_pct=0.0,
                consecutive_losses=1,
                consecutive_quality_failures=1,
                average_profit_drawdown_ratio=0.0,
                risk_quality_pass_rate=0.0,
                suggested_position_pct=0.12,
                reasons=("test guard",),
                next_action="test next",
            ),
            summary="test paper",
            decision_rules=(),
            next_action="09:31 复核触发条件",
        )

        view = build_decision_cockpit_view(
            strategy_report,
            paper_report,
            watch_report,
        )

        self.assertEqual(view.action_state, "buy")
        self.assertIn("买入 主线首板候选", view.action_label)
        self.assertIn("今天只盯 主线首板候选（600001）", view.execution_summary)
        self.assertIn("仓位 11%", view.execution_summary)
        self.assertIn("数据来源", view.data_mode_line)
        self.assertIn("封板波段主线", view.strategy_line)
        self.assertIn("有信号才出手", view.strategy_line)
        self.assertIn("600001", view.buy_line)
        self.assertIn("建议仓位 12%", view.risk_line)
        self.assertIn("09:31", view.next_step)
        self.assertIn("趋势主升日", view.regime_line)
        self.assertIn("主升进攻", view.regime_line)

    def test_framework_backed_local_stores_keep_existing_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notification_store = NotificationRecordStore(
                root / "notifications.json",
                created_at_provider=lambda: "20260509090000",
            )
            notification_store.append(
                workflow="morning",
                trade_date="2026-05-09",
                result=FeishuNotificationResult(
                    status=NotificationStatus.PREPARED,
                    title="test",
                    message="prepared",
                    webhook_configured=False,
                ),
            )
            state_store = SchedulerStateStore(root / "scheduler_state.json")
            state_store.mark_done("watch-open-2026-05-09")

            scheduler_run_store = SchedulerRunStore(
                root / "scheduler_runs.json",
                created_at_provider=lambda: "20260509152000",
            )
            schedule_run = OneToTwoScheduleRun(
                run_id="schedule-2026-05-09-1520",
                trade_date="2026-05-09",
                trade_context=TradingDayContext(
                    requested_date="2026-05-09",
                    trade_date="2026-05-09",
                    previous_trade_date="2026-05-08",
                    next_trade_date="2026-05-11",
                    is_trading_day=True,
                    note="test",
                ),
                requested_time="15:20",
                due_count=0,
                executed_count=0,
                skipped_count=0,
                tasks=(),
                next_action="done",
            )
            scheduler_run_store.append(schedule_run)

            self.assertEqual(notification_store.load()[0].workflow, "morning")
            self.assertTrue(state_store.is_done("watch-open-2026-05-09"))
            self.assertEqual(state_store.load(), ("watch-open-2026-05-09",))
            self.assertEqual(
                scheduler_run_store.load()[0]["run"]["run_id"],
                "schedule-2026-05-09-1520",
            )

    def test_framework_config_scheduler_and_sqlite_helpers_are_generic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text('{"mode": "local", "limit": 3}', encoding="utf-8")

            config = load_json_config(config_path)
            merged = merge_env_overrides(
                config,
                {"mode": "APP_MODE"},
                environ={"APP_MODE": "remote"},
            )
            require_config_keys(merged, ("mode", "limit"))

            db_path = root / "app.db"
            version = apply_sqlite_migrations(
                db_path,
                (
                    SqliteMigration(
                        version=1,
                        statements=(
                            "CREATE TABLE records (id INTEGER PRIMARY KEY, name TEXT)",
                        ),
                    ),
                ),
            )

            self.assertEqual(merged["mode"], "remote")
            self.assertTrue(is_due_in_window("09:35", DueWindow("09:30", "09:45")))
            self.assertFalse(is_due_in_window("09:29", DueWindow("09:30", "09:45")))
            self.assertEqual(version, 1)

    def test_paper_exit_policy_keeps_storage_and_notification_out(self) -> None:
        policy = Path("server/firemoney_server/application/paper_exit_policy.py")
        source = policy.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server.infrastructure.paper_store",
            "server.firemoney_server.infrastructure.paper_database",
            "server.firemoney_server.infrastructure.notification_store",
            "server.firemoney_server.infrastructure.feishu_notifier",
            "server.firemoney_server.infrastructure.market_data",
        )
        for module in imports:
            self.assertFalse(module.startswith(forbidden), module)
        self.assertNotIn("exit_position", source)

    def test_paper_entry_policy_keeps_storage_and_notification_out(self) -> None:
        policy = Path("server/firemoney_server/application/paper_entry_policy.py")
        source = policy.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server.infrastructure.paper_store",
            "server.firemoney_server.infrastructure.paper_database",
            "server.firemoney_server.infrastructure.notification_store",
            "server.firemoney_server.infrastructure.feishu_notifier",
            "server.firemoney_server.infrastructure.market_data",
        )
        for module in imports:
            self.assertFalse(module.startswith(forbidden), module)
        self.assertNotIn("buy_candidate", source)
        self.assertNotIn("record_candidate_event", source)

    def test_preview_file_can_be_generated_without_legacy_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "core_workflow.html"

            output = build_preview(target)

            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("FireMoney 主线首板", html)
            self.assertIn("主线首板专项台", html)
            self.assertIn("龙虎榜雷达", html)
            self.assertIn("50-800 亿市值带", html)
            self.assertIn("通测分组", html)
            self.assertIn("重点剔除名单", html)
            self.assertIn("今日决策驾驶舱", html)
            self.assertIn("下一步命令", html)
            self.assertIn("预览 · 真实优先", html)
            self.assertIn("真实账本优先于静态样例", html)
            self.assertIn("runtime-chip", html)
            self.assertIn("runtime-next", html)
            self.assertIn("renderRuntimeChips", html)
            self.assertIn('makeChip("交易"', html)
            self.assertIn("小仓验证", html)
            self.assertIn("体检模式", html)
            self.assertIn("确认早评已发送", html)
            self.assertIn("早评/飞书链路存在阻断", html)
            self.assertIn("真实 sent 记录优先", html)
            self.assertIn("运行状态已过期", html)
            self.assertIn("旧状态不可作为今天交易依据", html)
            self.assertIn("runtime_status_stale", html)
            self.assertIn("真实账本", html)
            self.assertNotIn("data-truth-banner", html)
            self.assertIn("今天只盯", html)
            self.assertIn("数据来源", html)
            self.assertIn("实时值守", html)
            self.assertIn("runtime_status.json", html)
            self.assertIn("真实模拟盘", html)
            self.assertIn("真实收益守门", html)
            self.assertIn("applyPaperDbToTrustCard", html)
            self.assertIn("applyRuntimeGateToCockpit", html)
            self.assertIn("先修值守，再谈买入", html)
            self.assertIn("真实运行优先", html)
            self.assertIn("真实运行闸门", html)
            self.assertIn("指挥单暂停", html)
            self.assertIn("runtime-gate-panel", html)
            self.assertIn("服务正常，但有通知阻断", html)
            self.assertIn("每日策略决策", html)
            self.assertIn("证据截止", html)
            self.assertIn("模拟盘交易指挥单", html)
            self.assertIn("买点证据", html)
            self.assertIn("结构突破", html)
            self.assertIn("运行信任", html)
            self.assertIn("收益守门", html)
            self.assertIn("今日执行闸门", html)
            self.assertIn("早评/晚评覆盖", html)
            self.assertIn("漏发定位", html)
            self.assertIn("schedule-health-card", html)
            self.assertIn("调度：", html)
            self.assertIn("飞书：", html)
            self.assertIn("home-execution-panel", html)
            self.assertIn("交易指挥单", html)
            self.assertIn("看完整指挥单", html)
            self.assertIn("证据中心", html)
            self.assertIn("evidence-stack", html)
            self.assertIn("候选、雷达、账本、回测和运行预检", html)
            self.assertIn("通知记录", html)
            self.assertNotIn("绀轰緥榫欏ご", html)
            self.assertNotIn("鏍蜂緥", html)
            self.assertNotIn("csv_export", html)
            self.assertNotIn("纭濮旀墭", html)
            self.assertNotIn("鍥炴墽", html)
            self.assertNotIn("orders/draft-600001.csv", html)
            self.assertNotIn("AppData/Local/Temp", html)

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
                    title="AI主线继续发酵",
                    source="财联社",
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

            self.assertIn("主线持续性：", risk.notification.message)
            self.assertIn("消息 1 条", risk.notification.message)
            self.assertIn("AI主线继续发酵", risk.notification.message)

    def test_take_profit_notification_uses_sell_card_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paper_store = PaperTradeStore(root / "paper_trades.json")
            notification_store = NotificationRecordStore(root / "notifications.json")
            service = _build_service(
                root,
                market_data_provider=SampleMarketDataProvider(),
                paper_store=paper_store,
                notification_store=notification_store,
            )
            service.run_one_to_two_watch(
                trade_date="2026-05-01",
                phase="open",
                notify=False,
            )
            profit_row = OneToTwoMarketRow(
                **(
                    _weak_after_two_days_row("2026-05-06").__dict__
                    | {"latest_price": 11.9, "theme": "AI主线"}
                )
            )
            service = _build_service(
                root,
                market_data_provider=StaticOneToTwoProvider((profit_row,)),
                paper_store=paper_store,
                notification_store=notification_store,
            )

            service.run_one_to_two_watch(
                trade_date="2026-05-06",
                phase="risk",
                notify=False,
            )
            records = NotificationRecordStore(root / "notifications.json").load()
            risk_record = next(record for record in records if record.workflow == "watch:risk")

            self.assertIn("模拟卖出", risk_record.title)
            self.assertIn("第一目标止盈", risk_record.message)
            self.assertNotIn("take_profit_first_target", risk_record.message)


if __name__ == "__main__":
    unittest.main()
