from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from server.firemoney_server import MainChainService
from server.firemoney_server.domain.one_to_two_types import (
    HistoricalPriceBar,
    OneToTwoMarketRow,
)
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from shared.contracts import MainlineNewsItem


class SlowCachedMarketDataProvider:
    def __init__(self, rows: tuple[OneToTwoMarketRow, ...]) -> None:
        self._rows = rows

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        del trade_date
        threading.Event().wait(1.0)
        return self._rows

    def load_cached_one_to_two_rows(
        self,
        trade_date: str,
        *,
        allow_stale: bool = True,
    ) -> tuple[OneToTwoMarketRow, ...] | None:
        del trade_date, allow_stale
        return self._rows

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        del theme, symbols
        return ()

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        del symbol, start_date, end_date
        return ()


class FailingCachedMarketDataProvider(SlowCachedMarketDataProvider):
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        del trade_date
        raise RuntimeError("live source unavailable")


class MarketDataTimeoutRecoveryTest(unittest.TestCase):
    def test_morning_report_uses_same_day_cache_when_live_source_times_out(self) -> None:
        provider = SlowCachedMarketDataProvider(
            SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MainChainService(
                market_data_provider=provider,
                paper_store=PaperTradeStore(Path(temp_dir) / "paper_trades.json"),
            )

            report = service.build_one_to_two_morning_report(
                trade_date="2026-04-30",
                notify=False,
                market_data_timeout_seconds=0.01,
            )

        self.assertNotEqual(report.status, "data_unavailable")
        self.assertGreater(len(report.candidates), 0)

    def test_paper_decision_uses_same_day_cache_when_live_source_times_out(self) -> None:
        provider = SlowCachedMarketDataProvider(
            SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MainChainService(
                market_data_provider=provider,
                paper_store=PaperTradeStore(Path(temp_dir) / "paper_trades.json"),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
                market_data_timeout_seconds=0.01,
            )

        self.assertNotEqual(report.status, "data_unavailable")
        self.assertNotEqual(report.market_regime, "market_data_unavailable_day")
        self.assertGreater(report.candidate_count, 0)

    def test_watch_open_does_not_use_cached_rows_to_write_buy_on_timeout(self) -> None:
        provider = SlowCachedMarketDataProvider(
            SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MainChainService(
                market_data_provider=provider,
                paper_store=PaperTradeStore(Path(temp_dir) / "paper_trades.json"),
            )

            report = service.run_one_to_two_watch(
                trade_date="2026-04-30",
                phase="open",
                notify=False,
                market_data_timeout_seconds=0.01,
            )

        self.assertEqual(report.status, "data_unavailable")
        self.assertFalse(report.account.positions)
        self.assertFalse(report.account.events)

    def test_strategy_decision_marks_unavailable_when_live_source_fails_without_cache(self) -> None:
        class FailingProvider(FailingCachedMarketDataProvider):
            def load_cached_one_to_two_rows(
                self,
                trade_date: str,
                *,
                allow_stale: bool = True,
            ) -> tuple[OneToTwoMarketRow, ...] | None:
                del trade_date, allow_stale
                return None

        provider = FailingProvider(
            SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MainChainService(
                market_data_provider=provider,
                paper_store=PaperTradeStore(Path(temp_dir) / "paper_trades.json"),
            )

            report = service.build_strategy_decision_report(
                trade_date="2026-04-30",
                market_data_timeout_seconds=0.01,
            )

        self.assertEqual(report.status, "data_unavailable")
        self.assertEqual(report.market_regime, "market_data_unavailable_day")

    def test_paper_decision_uses_same_day_cache_when_live_source_errors(self) -> None:
        provider = FailingCachedMarketDataProvider(
            SampleMarketDataProvider().load_one_to_two_rows("2026-04-30")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MainChainService(
                market_data_provider=provider,
                paper_store=PaperTradeStore(Path(temp_dir) / "paper_trades.json"),
            )

            report = service.build_paper_trading_decision_report(
                trade_date="2026-04-30",
                market_data_timeout_seconds=0.01,
            )

        self.assertNotEqual(report.status, "data_unavailable")
        self.assertNotEqual(report.market_regime, "market_data_unavailable_day")
        self.assertGreater(report.candidate_count, 0)


if __name__ == "__main__":
    unittest.main()
