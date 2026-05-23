from __future__ import annotations

import unittest
from dataclasses import dataclass

from server.firemoney_server.application.mainline_continuity_service import (
    MainlineContinuityService,
)
from shared.contracts import (
    MainlineContinuity,
    MainlineNewsItem,
    OneToTwoCandidate,
    OneToTwoPositionProfile,
)


@dataclass(frozen=True)
class Settings:
    mainline_fade_score: float = 45.0


class CountingNewsProvider:
    def __init__(self, news: tuple[MainlineNewsItem, ...]) -> None:
        self.news = news
        self.call_count = 0

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        self.call_count += 1
        return self.news


def _candidate(symbol: str, theme: str = "mainline") -> OneToTwoCandidate:
    return OneToTwoCandidate(
        symbol=symbol,
        name=f"stock-{symbol}",
        trade_date="2026-05-22",
        score=90.0,
        status="ready",
        latest_price=10.5,
        limit_up_price=10.5,
        entry_price=10.5,
        stop_loss=9.9,
        position_limit_pct=0.08,
        first_board_score=20.0,
        auction_score=20.0,
        position_score=20.0,
        theme_score=20.0,
        liquidity_score=20.0,
        position_profile=OneToTwoPositionProfile(
            label="low breakout",
            low_position_score=20.0,
            breakout_score=20.0,
            pressure_score=20.0,
            moving_average_score=20.0,
            volume_score=20.0,
            summary="test",
            risk_notes=(),
        ),
        blockers=(),
        warnings=(),
        rationale="test",
        next_action="test",
        mainline_continuity=MainlineContinuity(
            theme=theme,
            score=70.0,
            status="watch",
            hot_stock_count=1,
            limit_up_count=1,
            news_count=0,
            latest_news=(),
            reasons=("base",),
            risk_notes=(),
            next_action="watch",
        ),
    )


class MainlineContinuityServiceTest(unittest.TestCase):
    def test_reuses_news_lookup_for_same_theme_and_symbol_window(self) -> None:
        news = (
            MainlineNewsItem(
                title="mainline positive",
                source="test",
                published_at="2026-05-22 09:00",
                related_symbols=("600001",),
            ),
        )
        provider = CountingNewsProvider(news)
        service = MainlineContinuityService(
            settings=Settings(),
            market_data_provider=provider,
        )
        candidates = (_candidate("600001"), _candidate("600002"))

        first = service.with_live_mainline_continuity(candidates[0], candidates)
        second = service.with_live_mainline_continuity(candidates[1], candidates)

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(first.mainline_continuity.news_count, 1)
        self.assertEqual(second.mainline_continuity.news_count, 1)

    def test_refreshes_news_lookup_after_cache_ttl(self) -> None:
        provider = CountingNewsProvider(
            (
                MainlineNewsItem(
                    title="mainline positive",
                    source="test",
                    published_at="2026-05-22 09:00",
                    related_symbols=("600001",),
                ),
            )
        )
        service = MainlineContinuityService(
            settings=Settings(),
            market_data_provider=provider,
            news_cache_ttl_seconds=0.0,
        )
        candidates = (_candidate("600001"), _candidate("600002"))

        service.with_live_mainline_continuity(candidates[0], candidates)
        service.with_live_mainline_continuity(candidates[1], candidates)

        self.assertEqual(provider.call_count, 2)


if __name__ == "__main__":
    unittest.main()
