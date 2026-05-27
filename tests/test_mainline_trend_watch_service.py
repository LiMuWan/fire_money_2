from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from server.firemoney_server.application.mainline_trend_watch_service import (
    MainlineTrendWatchService,
)
from server.firemoney_server.domain.one_to_two_types import (
    FundamentalSnapshot,
    HistoricalPriceBar,
    MarketTrendRow,
)


class FakeTrendProvider:
    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        return (
            MarketTrendRow(
                symbol="603256",
                name="宏和科技",
                trade_date=trade_date,
                board="主板",
                latest_price=12.18,
                previous_close=11.86,
                change_pct=2.7,
                turnover_amount=680_000_000,
                turnover_rate=7.8,
                market_cap=10_800_000_000,
                float_market_cap=8_900_000_000,
                industry="电子布 PCB",
                theme="AI服务器PCB上游电子布",
            ),
            MarketTrendRow(
                symbol="600002",
                name="金岭高科",
                trade_date=trade_date,
                board="主板",
                latest_price=16.5,
                previous_close=15.0,
                change_pct=10.0,
                turnover_amount=1_400_000_000,
                turnover_rate=17.0,
                market_cap=22_000_000_000,
                float_market_cap=15_000_000_000,
                industry="半导体",
                theme="高位加速",
            ),
        )

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        if symbol == "603256":
            return _bars(end_date, start=7.8, end=12.18, wave=0.08, amount=680_000_000)
        if symbol == "600002":
            return _bars(end_date, start=6.5, end=16.5, wave=0.22, amount=1_400_000_000)
        return ()

    def load_fundamental_snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        if symbol == "603256":
            return FundamentalSnapshot(
                symbol=symbol,
                name="宏和科技",
                report_date="2026Q1",
                roe_pct=8.4,
                revenue_growth_pct=18.0,
                net_profit_growth_pct=42.0,
                gross_margin_pct=28.5,
                debt_ratio_pct=32.0,
                pe_ttm=38.0,
            )
        return None


class FallbackTrendProvider(FakeTrendProvider):
    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        rows = super().load_full_market_rows(trade_date)
        return tuple(
            MarketTrendRow(
                **{
                    **row.__dict__,
                    "data_source": "one_to_two_candidate_fallback",
                }
            )
            for row in rows[:1]
        )


class CachedFullMarketTrendProvider(FakeTrendProvider):
    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        rows = super().load_full_market_rows(trade_date)
        return tuple(
            MarketTrendRow(
                **{
                    **row.__dict__,
                    "data_source": "full_market_spot_cache",
                }
            )
            for row in rows
        )


class CountingTrendProvider(FakeTrendProvider):
    def __init__(self) -> None:
        self.price_bar_calls = 0
        self.fundamental_calls = 0

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        self.price_bar_calls += 1
        return super().load_price_bars(symbol, start_date, end_date)

    def load_fundamental_snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        self.fundamental_calls += 1
        return super().load_fundamental_snapshot(symbol)


def _bars(
    end_date: str,
    *,
    start: float,
    end: float,
    wave: float,
    amount: float,
) -> tuple[HistoricalPriceBar, ...]:
    end_day = datetime.strptime(end_date, "%Y-%m-%d").date()
    bars: list[HistoricalPriceBar] = []
    for index in range(130):
        progress = index / 129
        close = start + (end - start) * progress
        close *= 1 + (((index % 15) - 7) / 7) * wave * 0.05
        if index == 129:
            close = end
        day = (end_day - timedelta(days=129 - index)).isoformat()
        bars.append(
            HistoricalPriceBar(
                trade_date=day,
                open_price=round(close * 0.99, 2),
                high_price=round(close * 1.02, 2),
                low_price=round(close * 0.98, 2),
                close_price=round(close, 2),
                volume=amount / max(close, 0.01),
                amount=amount * (0.7 + progress * 0.3),
            )
        )
    return tuple(bars)


class MainlineTrendWatchServiceTest(unittest.TestCase):
    def test_build_report_explains_mainline_root_and_entry_plan(self) -> None:
        service = MainlineTrendWatchService(market_data_provider=FakeTrendProvider())

        report = service.build_report(trade_date="2026-05-27", limit=5)

        self.assertEqual(report.status, "watch_only")
        self.assertIn("全市场主升根因扫描", report.summary)
        self.assertGreaterEqual(len(report.items), 1)
        item = report.items[0]
        self.assertEqual(item.symbol, "603256")
        self.assertIn("AI服务器PCB", item.theme)
        self.assertIn("净利增速", item.value_case)
        self.assertIn("成交额", item.capital_case)
        self.assertIn("主升", item.next_action)
        self.assertGreater(item.logic_score, 80)
        self.assertGreater(item.value_score, 60)
        self.assertGreater(item.capital_attraction_score, 60)
        self.assertIn("不写入模拟盘", "；".join(report.rules))

    def test_high_position_candidate_is_not_ranked_above_root_candidate(self) -> None:
        service = MainlineTrendWatchService(market_data_provider=FakeTrendProvider())

        report = service.build_report(trade_date="2026-05-27", limit=5)

        symbols = [item.symbol for item in report.items]
        self.assertLess(symbols.index("603256"), symbols.index("600002"))
        high_item = next(item for item in report.items if item.symbol == "600002")
        self.assertTrue(
            any("追" in risk or "偏高" in risk for risk in high_item.risks),
            high_item.risks,
        )

    def test_degraded_data_is_explicit_when_full_market_snapshot_falls_back(self) -> None:
        service = MainlineTrendWatchService(market_data_provider=FallbackTrendProvider())

        report = service.build_report(trade_date="2026-05-27", limit=3)

        self.assertIn("degraded_data", report.summary)
        self.assertTrue(
            any("不是完整全市场覆盖" in item for item in report.limitations),
            report.limitations,
        )
        self.assertEqual(report.items[0].symbol, "603256")

    def test_cached_full_market_snapshot_is_not_marked_as_candidate_degraded(self) -> None:
        service = MainlineTrendWatchService(
            market_data_provider=CachedFullMarketTrendProvider()
        )

        report = service.build_report(trade_date="2026-05-27", limit=3)

        self.assertIn("cached_full_market", report.summary)
        self.assertFalse(any("不是完整全市场覆盖" in item for item in report.limitations))
        self.assertTrue(any("30分钟内" in item for item in report.limitations))

    def test_fast_snapshot_mode_skips_deep_history_and_fundamental_fetches(self) -> None:
        provider = CountingTrendProvider()
        service = MainlineTrendWatchService(market_data_provider=provider)

        report = service.build_report(
            trade_date="2026-05-27",
            limit=2,
            fast_snapshot=True,
        )

        self.assertEqual(provider.price_bar_calls, 0)
        self.assertEqual(provider.fundamental_calls, 0)
        self.assertGreater(len(report.items), 0)
        self.assertTrue(any("页面快照模式" in item for item in report.limitations))


if __name__ == "__main__":
    unittest.main()
