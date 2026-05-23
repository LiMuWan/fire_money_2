"""Live mainline continuity enrichment for paper watch candidates."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Protocol

from shared.contracts import MainlineContinuity, MainlineNewsItem, OneToTwoCandidate


class MainlineContinuitySettingsLike(Protocol):
    mainline_fade_score: float


class MainlineNewsProviderLike(Protocol):
    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        """Load latest mainline news for a theme and symbol set."""


class MainlineContinuityService:
    """Adds live breadth/news evidence without mutating the base candidate."""

    DEFAULT_NEWS_CACHE_TTL_SECONDS = 300.0

    def __init__(
        self,
        *,
        settings: MainlineContinuitySettingsLike,
        market_data_provider: MainlineNewsProviderLike,
        news_cache_ttl_seconds: float = DEFAULT_NEWS_CACHE_TTL_SECONDS,
    ) -> None:
        self._settings = settings
        self._market_data_provider = market_data_provider
        self._news_cache_ttl_seconds = news_cache_ttl_seconds
        self._news_cache: dict[
            tuple[str, tuple[str, ...]],
            tuple[float, tuple[MainlineNewsItem, ...]],
        ] = {}

    def with_live_mainline_continuity(
        self,
        candidate: OneToTwoCandidate,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> OneToTwoCandidate:
        base = candidate.mainline_continuity
        if base is None:
            return candidate

        symbols = tuple(item.symbol for item in candidates[:8])
        news = self._load_mainline_news(base.theme, symbols)
        hot_stock_count = sum(
            1
            for item in candidates
            if item.mainline_continuity
            and item.mainline_continuity.theme == base.theme
        )
        limit_up_count = sum(
            1 for item in candidates if item.latest_price >= item.limit_up_price * 0.995
        )
        news_bonus = min(len(news) * 3, 12)
        breadth_bonus = min(hot_stock_count * 4 + limit_up_count * 3, 18)
        adjusted_score = min(100.0, base.score + news_bonus + breadth_bonus)
        risk_notes = list(base.risk_notes)
        if not news:
            risk_notes.append("未抓取到新的主线消息，只按价格和封板持续性观察")

        status = (
            "strong"
            if adjusted_score >= 75
            else "watch"
            if adjusted_score >= self._settings.mainline_fade_score
            else "fading"
        )
        continuity = MainlineContinuity(
            theme=base.theme,
            score=round(adjusted_score, 2),
            status=status,
            hot_stock_count=hot_stock_count,
            limit_up_count=limit_up_count,
            news_count=len(news),
            latest_news=news[:5],
            reasons=(
                *base.reasons,
                f"同主线候选 {hot_stock_count} 个",
                f"近涨停强度 {limit_up_count} 个",
                f"消息证据 {len(news)} 条",
            ),
            risk_notes=tuple(dict.fromkeys(risk_notes)),
            next_action=(
                "主线仍有持续性，按止盈和回撤纪律观察。"
                if status == "strong"
                else "主线仍需确认，达到第一止盈优先落袋。"
                if status == "watch"
                else "主线持续性衰减，T+1 已到优先退出。"
            ),
        )
        return replace(candidate, mainline_continuity=continuity)

    def _load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        cache_key = (theme, symbols)
        cached = self._news_cache.get(cache_key)
        if cached is not None and self._news_cache_ttl_seconds > 0:
            cached_at, cached_news = cached
            if time.monotonic() - cached_at <= self._news_cache_ttl_seconds:
                return cached_news
        try:
            news = self._market_data_provider.load_mainline_news(theme, symbols)
        except Exception:
            news = ()
        self._news_cache[cache_key] = (time.monotonic(), news)
        return news


__all__ = ["MainlineContinuityService"]
