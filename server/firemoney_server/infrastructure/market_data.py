"""Market data provider boundary for one-to-two strategy."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from server.firemoney_server.domain.one_to_two import (
    HistoricalPriceBar,
    OneToTwoMarketRow,
)
from shared.contracts import MainlineNewsItem


DEFAULT_MARKET_DATA_CACHE_DIR = Path(".firemoney") / "market_data"


class MarketDataUnavailable(RuntimeError):
    """Raised when the configured market data source cannot provide data."""


class MarketDataProvider(Protocol):
    """Boundary for real market data providers."""

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        """Load normalized one-to-two rows for a trade date."""
        ...

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        """Load normalized mainline news items for continuity review."""
        ...

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        """Load normalized daily bars for replay accounting."""
        ...


class SampleMarketDataProvider:
    """Deterministic one-to-two sample data for preview and tests."""

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        return (
            OneToTwoMarketRow(
                symbol="600001",
                name="主线首板候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1200,
                latest_price=10.52,
                previous_close=9.56,
                limit_up_price=10.52,
                first_limit_up_time="09:48",
                sealed_amount=36000000,
                turnover_amount=180000000,
                turnover_rate=6.2,
                open_pct=0.045,
                auction_amount=12000000,
                low_20=8.8,
                high_60=10.6,
                pressure_price=11.8,
                ma_5=10.0,
                ma_10=9.7,
                ma_20=9.2,
                recent_gain_pct=0.18,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600007",
                name="平台突破候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1400,
                latest_price=12.1,
                previous_close=11.0,
                limit_up_price=12.1,
                first_limit_up_time="10:18",
                sealed_amount=26000000,
                turnover_amount=210000000,
                turnover_rate=5.6,
                open_pct=0.026,
                auction_amount=10000000,
                low_20=10.6,
                high_60=12.2,
                pressure_price=13.7,
                ma_5=11.6,
                ma_10=11.2,
                ma_20=10.9,
                recent_gain_pct=0.16,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600008",
                name="突破确认候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1500,
                latest_price=13.2,
                previous_close=12.0,
                limit_up_price=13.2,
                first_limit_up_time="10:02",
                sealed_amount=28000000,
                turnover_amount=220000000,
                turnover_rate=5.2,
                open_pct=0.034,
                auction_amount=11000000,
                low_20=11.0,
                high_60=13.4,
                pressure_price=15.0,
                ma_5=12.7,
                ma_10=12.1,
                ma_20=11.4,
                recent_gain_pct=0.18,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600009",
                name="承接确认候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1300,
                latest_price=9.9,
                previous_close=9.0,
                limit_up_price=9.9,
                first_limit_up_time="10:12",
                sealed_amount=24000000,
                turnover_amount=190000000,
                turnover_rate=4.9,
                open_pct=0.028,
                auction_amount=9000000,
                low_20=8.3,
                high_60=10.0,
                pressure_price=11.4,
                ma_5=9.5,
                ma_10=9.1,
                ma_20=8.7,
                recent_gain_pct=0.15,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600010",
                name="主线换手候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1600,
                latest_price=15.4,
                previous_close=14.0,
                limit_up_price=15.4,
                first_limit_up_time="10:26",
                sealed_amount=33000000,
                turnover_amount=260000000,
                turnover_rate=6.8,
                open_pct=0.021,
                auction_amount=13000000,
                low_20=13.4,
                high_60=15.6,
                pressure_price=17.6,
                ma_5=14.9,
                ma_10=14.3,
                ma_20=13.8,
                recent_gain_pct=0.2,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600011",
                name="龙头备选候选",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1800,
                latest_price=18.7,
                previous_close=17.0,
                limit_up_price=18.7,
                first_limit_up_time="10:28",
                sealed_amount=36000000,
                turnover_amount=300000000,
                turnover_rate=7.1,
                open_pct=0.039,
                auction_amount=15000000,
                low_20=16.0,
                high_60=19.0,
                pressure_price=21.2,
                ma_5=18.0,
                ma_10=17.4,
                ma_20=16.7,
                recent_gain_pct=0.22,
                theme="AI端侧主线",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600002",
                name="高位跟风拦截",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=900,
                latest_price=16.5,
                previous_close=15.0,
                limit_up_price=16.5,
                first_limit_up_time="09:40",
                sealed_amount=18000000,
                turnover_amount=120000000,
                turnover_rate=8.5,
                open_pct=0.085,
                auction_amount=9000000,
                low_20=9.2,
                high_60=16.8,
                pressure_price=17.0,
                ma_5=15.2,
                ma_10=13.6,
                ma_20=12.0,
                recent_gain_pct=0.52,
                theme="高位加速",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="300003",
                name="非主板拦截",
                trade_date=trade_date,
                board="创业板",
                is_st=False,
                is_delisting=False,
                listing_days=800,
                latest_price=22.0,
                previous_close=20.0,
                limit_up_price=24.0,
                first_limit_up_time="10:20",
                sealed_amount=22000000,
                turnover_amount=160000000,
                turnover_rate=5.1,
                open_pct=0.03,
                auction_amount=8000000,
                low_20=18.0,
                high_60=23.0,
                pressure_price=25.0,
                ma_5=21.0,
                ma_10=20.5,
                ma_20=19.5,
                recent_gain_pct=0.16,
                theme="非主板",
                market_temperature=74,
                first_board_count=45,
            ),
            OneToTwoMarketRow(
                symbol="600004",
                name="弱封板拦截",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1000,
                latest_price=8.8,
                previous_close=8.0,
                limit_up_price=8.8,
                first_limit_up_time="11:12",
                sealed_amount=3000000,
                turnover_amount=130000000,
                turnover_rate=4.1,
                open_pct=0.015,
                auction_amount=3500000,
                low_20=7.4,
                high_60=8.9,
                pressure_price=10.2,
                ma_5=8.4,
                ma_10=8.1,
                ma_20=7.9,
                recent_gain_pct=0.14,
                theme="同题材跟风",
                market_temperature=74,
                first_board_count=45,
            ),
        )

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        symbol_text = "、".join(symbols[:3])
        return (
            MainlineNewsItem(
                title=f"{theme} 继续获得资金关注，核心候选 {symbol_text} 进入观察",
                source="sample",
                published_at="09:20",
                related_symbols=symbols[:3],
            ),
            MainlineNewsItem(
                title=f"{theme} 分歧中仍有涨停样本，需结合封板质量确认持续性",
                source="sample",
                published_at="10:30",
                related_symbols=symbols[:3],
            ),
        )

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        sample_bars = {
            "600001": (
                HistoricalPriceBar(
                    trade_date="2026-04-30",
                    open_price=10.52,
                    high_price=10.52,
                    low_price=10.20,
                    close_price=10.52,
                    volume=1200000,
                    amount=12624000,
                ),
                HistoricalPriceBar(
                    trade_date="2026-05-06",
                    open_price=10.88,
                    high_price=11.38,
                    low_price=10.72,
                    close_price=11.20,
                    volume=1800000,
                    amount=20160000,
                ),
                HistoricalPriceBar(
                    trade_date="2026-05-07",
                    open_price=11.18,
                    high_price=11.50,
                    low_price=10.94,
                    close_price=11.36,
                    volume=1500000,
                    amount=17040000,
                ),
                HistoricalPriceBar(
                    trade_date="2026-05-08",
                    open_price=11.30,
                    high_price=11.42,
                    low_price=10.98,
                    close_price=11.05,
                    volume=1300000,
                    amount=14365000,
                ),
            )
        }
        bars = sample_bars.get(symbol, ())
        return tuple(
            bar for bar in bars if start_date <= bar.trade_date <= end_date
        )


class AkshareMarketDataProvider:
    """AkShare-backed market data provider with local cache and safe failure."""

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_MARKET_DATA_CACHE_DIR,
        fallback: MarketDataProvider | None = None,
        cache_ttl_seconds: float = 60.0,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._fallback = fallback
        self._cache_ttl_seconds = cache_ttl_seconds
        self._row_cache: dict[str, tuple[float, tuple[OneToTwoMarketRow, ...]]] = {}
        self._history_cache: dict[tuple[str, str], dict[str, float]] = {}

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        cached_rows = self._cached_rows(trade_date)
        if cached_rows is not None:
            return cached_rows

        try:
            import akshare as ak  # type: ignore
        except Exception:
            rows = self._fallback_rows(trade_date)
            self._remember_rows(trade_date, rows)
            return rows

        try:
            previous_pool = ak.stock_zt_pool_previous_em(
                date=trade_date.replace("-", "")
            )
            self._cache_payload(trade_date, "stock_zt_pool_previous_em", previous_pool)
        except Exception:
            rows = self._fallback_rows(trade_date)
            self._remember_rows(trade_date, rows)
            return rows

        try:
            spot = ak.stock_zh_a_spot_em()
            self._cache_payload(trade_date, "stock_zh_a_spot_em", spot)
        except Exception:
            spot = ()
        rows = self._rows_from_previous_pool(
            previous_pool,
            spot,
            trade_date,
            ak,
        )
        if not rows and self._fallback is not None:
            rows = self._fallback_rows(trade_date)
        self._remember_rows(trade_date, rows)
        return rows

    def load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            if self._fallback is not None and hasattr(self._fallback, "load_mainline_news"):
                return self._fallback.load_mainline_news(theme, symbols)
            return ()

        news: list[MainlineNewsItem] = []
        for symbol in symbols[:5]:
            try:
                raw_news = ak.stock_news_em(symbol=symbol)
                records = getattr(raw_news, "to_dict", lambda *_args, **_kwargs: [])("records")
                self._cache_payload("latest", f"stock_news_em_{symbol}", raw_news)
            except Exception:
                continue
            for item in records[:3]:
                title = self._first_text(item, ("新闻标题", "标题", "title"))
                if not title:
                    continue
                news.append(
                    MainlineNewsItem(
                        title=title,
                        source=self._first_text(item, ("文章来源", "来源", "source")) or "东方财富",
                        published_at=self._first_text(item, ("发布时间", "时间", "datetime")),
                        related_symbols=(symbol,),
                        url=self._first_text(item, ("新闻链接", "链接", "url")),
                    )
                )
        if news:
            return tuple(news[:8])
        if self._fallback is not None and hasattr(self._fallback, "load_mainline_news"):
            return self._fallback.load_mainline_news(theme, symbols)
        return ()

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            if self._fallback is not None and hasattr(self._fallback, "load_price_bars"):
                return self._fallback.load_price_bars(symbol, start_date, end_date)
            raise MarketDataUnavailable("AkShare historical bars are unavailable")

        try:
            bars = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
            self._cache_payload(
                start_date,
                f"stock_zh_a_hist_{symbol}_{end_date}",
                bars,
            )
        except Exception as exc:
            if self._fallback is not None and hasattr(self._fallback, "load_price_bars"):
                return self._fallback.load_price_bars(symbol, start_date, end_date)
            raise MarketDataUnavailable("AkShare historical bars are unavailable") from exc

        records = getattr(bars, "to_dict", lambda *_args, **_kwargs: [])("records")
        normalized: list[HistoricalPriceBar] = []
        for item in records:
            trade_date = self._normalize_date(
                item.get("日期") or item.get("date") or item.get("trade_date")
            )
            if not trade_date:
                continue
            open_price = self._first_float(item, ("开盘", "open"))
            high_price = self._first_float(item, ("最高", "high"))
            low_price = self._first_float(item, ("最低", "low"))
            close_price = self._first_float(item, ("收盘", "close"))
            if min(open_price, high_price, low_price, close_price) <= 0:
                continue
            normalized.append(
                HistoricalPriceBar(
                    trade_date=trade_date,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=self._first_float(item, ("成交量", "volume")),
                    amount=self._first_float(item, ("成交额", "amount")),
                )
            )
        return tuple(sorted(normalized, key=lambda item: item.trade_date))

    def _cached_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...] | None:
        cached = self._row_cache.get(trade_date)
        if not cached:
            return None
        cached_at, rows = cached
        if time.monotonic() - cached_at <= self._cache_ttl_seconds:
            return rows
        return None

    def _remember_rows(
        self,
        trade_date: str,
        rows: tuple[OneToTwoMarketRow, ...],
    ) -> None:
        self._row_cache[trade_date] = (time.monotonic(), rows)

    def _fallback_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        if not self._fallback:
            raise MarketDataUnavailable("AkShare market data is unavailable")
        return self._fallback.load_one_to_two_rows(trade_date)

    def _rows_from_previous_pool(
        self,
        previous_pool: Any,
        spot: Any,
        trade_date: str,
        ak: Any,
    ) -> tuple[OneToTwoMarketRow, ...]:
        rows: list[OneToTwoMarketRow] = []
        records = getattr(previous_pool, "to_dict", lambda *_args, **_kwargs: [])(
            "records"
        )
        spot_by_symbol = {
            str(item.get("代码", "")): item
            for item in getattr(spot, "to_dict", lambda *_args, **_kwargs: [])("records")
        }
        market_temperature = (
            self._market_temperature(spot_by_symbol.values())
            or self._market_temperature(records)
            or (55 if records else 0)
        )
        first_board_count = sum(
            1
            for item in records
            if str(item.get("代码", ""))
            and self._board_count(item) == 1
            and self._board(str(item.get("代码", ""))) == "主板"
        )
        for item in records[:80]:
            symbol = str(item.get("代码", ""))
            name = str(item.get("名称", ""))
            if not symbol or self._board_count(item) != 1:
                continue
            spot_item = spot_by_symbol.get(symbol, {})
            latest = self._first_float(spot_item, ("最新价",)) or self._first_float(item, ("最新价",))
            limit_up_price = self._first_float(item, ("涨停价", "最新价")) or round(latest * 1.1, 2)
            previous_close = self._first_float(spot_item, ("昨收", "昨日收盘价")) or round(
                limit_up_price / 1.1,
                2,
            )
            if latest <= 0 or previous_close <= 0:
                continue
            history = self._history_profile(ak, symbol, trade_date, latest)
            open_price = self._first_float(spot_item, ("今开", "开盘价")) or self._first_float(
                item,
                ("开盘价",),
            )
            open_pct = (
                (open_price - previous_close) / previous_close
                if open_price and previous_close
                else self._first_float(item, ("竞价涨幅", "开盘涨幅", "涨跌幅")) / 100
            )
            turnover_amount = self._first_float(spot_item, ("成交额",)) or self._first_float(
                item,
                ("成交额", "昨日成交额"),
            )
            auction_amount = self._first_float(
                item,
                ("竞价金额", "竞价成交额", "竞价额", "集合竞价成交额"),
            )
            rows.append(
                OneToTwoMarketRow(
                    symbol=symbol,
                    name=name,
                    trade_date=trade_date,
                    board=self._board(symbol),
                    is_st="ST" in name.upper(),
                    is_delisting="退" in name,
                    listing_days=999,
                    latest_price=latest,
                    previous_close=previous_close,
                    limit_up_price=limit_up_price,
                    first_limit_up_time=self._format_time(
                        item.get("昨日封板时间") or item.get("首次封板时间")
                    ),
                    sealed_amount=self._first_float(item, ("封板资金", "封单资金")),
                    turnover_amount=turnover_amount,
                    turnover_rate=(
                        self._first_float(spot_item, ("换手率",))
                        or self._first_float(item, ("换手率",))
                    ),
                    open_pct=open_pct,
                    auction_amount=auction_amount,
                    low_20=history["low_20"],
                    high_60=history["high_60"],
                    pressure_price=history["pressure_price"],
                    ma_5=history["ma_5"],
                    ma_10=history["ma_10"],
                    ma_20=history["ma_20"],
                    recent_gain_pct=history["recent_gain_pct"],
                    theme=self._first_text(item, ("所属行业", "所属概念", "概念", "题材")),
                    market_temperature=market_temperature,
                    first_board_count=first_board_count,
                )
            )
        return tuple(rows)

    def _rows_from_spot(self, spot: Any, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        rows: list[OneToTwoMarketRow] = []
        records = getattr(spot, "to_dict", lambda *_args, **_kwargs: [])("records")
        for item in records[:80]:
            symbol = str(item.get("代码", ""))
            name = str(item.get("名称", ""))
            latest = self._float(item.get("最新价"))
            previous_close = self._float(item.get("昨收"))
            if not symbol or latest <= 0 or previous_close <= 0:
                continue
            board = self._board(symbol)
            rows.append(
                OneToTwoMarketRow(
                    symbol=symbol,
                    name=name,
                    trade_date=trade_date,
                    board=board,
                    is_st="ST" in name.upper(),
                    is_delisting="退" in name,
                    listing_days=999,
                    latest_price=latest,
                    previous_close=previous_close,
                    limit_up_price=round(previous_close * 1.1, 2),
                    first_limit_up_time="",
                    sealed_amount=0.0,
                    turnover_amount=self._float(item.get("成交额")),
                    turnover_rate=self._float(item.get("换手率")),
                    open_pct=self._float(item.get("涨跌幅")) / 100,
                    auction_amount=0.0,
                    low_20=latest * 0.88,
                    high_60=latest * 1.04,
                    pressure_price=latest * 1.12,
                    ma_5=latest * 0.98,
                    ma_10=latest * 0.96,
                    ma_20=latest * 0.94,
                    recent_gain_pct=0.12,
                    theme="AkShare 实时候选",
                    market_temperature=65,
                )
            )
        return tuple(rows)

    def _history_profile(
        self,
        ak: Any,
        symbol: str,
        trade_date: str,
        latest: float,
    ) -> dict[str, float]:
        cache_key = (trade_date, symbol)
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        fallback = {
            "low_20": latest * 0.88,
            "high_60": latest * 1.04,
            "pressure_price": latest * 1.12,
            "ma_5": latest * 0.98,
            "ma_10": latest * 0.96,
            "ma_20": latest * 0.94,
            "recent_gain_pct": 0.12,
        }
        try:
            end = datetime.strptime(trade_date.replace("-", ""), "%Y%m%d")
            start = (end - timedelta(days=140)).strftime("%Y%m%d")
            hist = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            records = getattr(hist, "to_dict", lambda *_args, **_kwargs: [])("records")
        except Exception:
            self._history_cache[cache_key] = fallback
            return fallback
        closes = [self._float(item.get("收盘")) for item in records if self._float(item.get("收盘")) > 0]
        lows = [self._float(item.get("最低")) for item in records if self._float(item.get("最低")) > 0]
        highs = [self._float(item.get("最高")) for item in records if self._float(item.get("最高")) > 0]
        if not closes:
            self._history_cache[cache_key] = fallback
            return fallback
        pressure_candidates = [price for price in highs[-60:-1] if price > latest]
        base_close = closes[-20] if len(closes) >= 20 and closes[-20] else closes[0]
        profile = {
            "low_20": min(lows[-20:]) if lows else fallback["low_20"],
            "high_60": max(highs[-60:]) if highs else fallback["high_60"],
            "pressure_price": (
                min(pressure_candidates)
                if pressure_candidates
                else max(max(highs[-60:]) if highs else latest, latest * 1.12)
            ),
            "ma_5": sum(closes[-5:]) / min(len(closes), 5),
            "ma_10": sum(closes[-10:]) / min(len(closes), 10),
            "ma_20": sum(closes[-20:]) / min(len(closes), 20),
            "recent_gain_pct": (closes[-1] - base_close) / base_close if base_close else 0.0,
        }
        self._history_cache[cache_key] = profile
        return profile

    def _market_temperature(self, records: Any) -> int:
        changes = [self._float(item.get("涨跌幅")) for item in records]
        valid = [item for item in changes if item != 0]
        if not valid:
            return 0
        positive_ratio = sum(1 for item in valid if item > 0) / len(valid)
        strong_ratio = sum(1 for item in valid if item >= 9.5) / len(valid)
        return int(round(35 + positive_ratio * 45 + min(strong_ratio * 400, 20)))

    def _cache_payload(self, trade_date: str, name: str, payload: Any) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        target = self._cache_dir / f"{trade_date}_{name}.json"
        records = getattr(payload, "to_dict", lambda *_args, **_kwargs: [])("records")
        target.write_text(
            json.dumps(records[:200], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _board(self, symbol: str) -> str:
        if symbol.startswith("300"):
            return "创业板"
        if symbol.startswith("688"):
            return "科创板"
        if symbol.startswith(("8", "4")):
            return "北交所"
        return "主板"

    def _format_time(self, value: Any) -> str:
        raw = str(value or "").strip().replace(":", "")
        if raw.endswith(".0"):
            raw = raw[:-2]
        if len(raw) == 4 and raw.isdigit():
            return f"{raw[:2]}:{raw[2:4]}"
        raw = raw.zfill(6)
        if len(raw) != 6 or not raw.isdigit():
            return ""
        return f"{raw[:2]}:{raw[2:4]}"

    def _board_count(self, item: dict[str, Any]) -> int:
        for key in ("昨日连板数", "连板数"):
            count = self._int(item.get(key))
            if count:
                return count
        stat = str(item.get("涨停统计", ""))
        if "/" in stat:
            return self._int(stat.split("/", 1)[0])
        return 0

    def _float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _int(self, value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _first_float(self, item: dict[str, Any], keys: tuple[str, ...]) -> float:
        for key in keys:
            value = self._float(item.get(key))
            if value:
                return value
        return 0.0

    def _first_text(self, item: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = str(item.get(key, "")).strip()
            if value and value.lower() != "nan":
                return value
        return ""

    def _normalize_date(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw or raw.lower() == "nan":
            return ""
        if "-" in raw:
            try:
                return datetime.strptime(raw[:10], "%Y-%m-%d").date().isoformat()
            except ValueError:
                return ""
        if len(raw) >= 8 and raw[:8].isdigit():
            try:
                return datetime.strptime(raw[:8], "%Y%m%d").date().isoformat()
            except ValueError:
                return ""
        return ""
