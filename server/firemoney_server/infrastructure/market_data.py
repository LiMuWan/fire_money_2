"""Market data provider boundary for one-to-two strategy."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from server.firemoney_server.domain.one_to_two_types import (
    FundamentalSnapshot,
    HistoricalPriceBar,
    IntradayPriceBar,
    MarketTrendRow,
    OneToTwoMarketRow,
    TickSnapshot,
)
from shared.contracts import MainlineNewsItem
from server.firemoney_server.infrastructure.market_trend_cache import (
    MarketTrendSnapshotCache,
)
from server.firemoney_server.infrastructure.sina_full_market import SinaFullMarketClient


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

    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        """Load normalized full-market rows for trend-root scanning."""
        ...

    def load_fundamental_snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        """Load a best-effort fundamental snapshot."""
        ...

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        """Load normalized daily bars for replay accounting."""
        ...

    def load_intraday_bars(
        self,
        symbol: str,
        trade_date: str,
        interval_minutes: int = 1,
    ) -> tuple[IntradayPriceBar, ...]:
        """Load normalized intraday bars for execution-quality validation."""
        ...

    def load_tick_snapshots(
        self,
        symbol: str,
        trade_date: str,
    ) -> tuple[TickSnapshot, ...]:
        """Load normalized tick or order-book snapshots for queue/fill validation."""
        ...


from server.firemoney_server.infrastructure.sample_market_data import (
    SampleMarketDataProvider,
)
class AkshareMarketDataProvider:
    """AkShare-backed market data provider with local cache and safe failure."""

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_MARKET_DATA_CACHE_DIR,
        fallback: MarketDataProvider | None = None,
        cache_ttl_seconds: float = 60.0,
        enrich_candidate_history: bool = False,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._fallback = fallback
        self._cache_ttl_seconds = cache_ttl_seconds
        self._enrich_candidate_history = enrich_candidate_history
        self._row_cache: dict[str, tuple[float, tuple[OneToTwoMarketRow, ...]]] = {}
        self._history_cache: dict[tuple[str, str], dict[str, float]] = {}
        self._intraday_minute_cache: dict[
            tuple[str, int],
            tuple[float, tuple[IntradayPriceBar, ...]],
        ] = {}
        self._trend_snapshot_cache = MarketTrendSnapshotCache(
            self._cache_dir,
            ttl_seconds=max(cache_ttl_seconds, 1800.0),
        )
        self._sina_full_market_client = SinaFullMarketClient()

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        has_memory_cache = trade_date in self._row_cache
        cached_rows = self._cached_rows(trade_date)
        if cached_rows is not None:
            return cached_rows

        if not has_memory_cache:
            disk_rows = self._load_cached_rows(trade_date, allow_stale=False)
            if disk_rows is not None:
                self._remember_rows(trade_date, disk_rows)
                return disk_rows

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
            rows = self._cached_or_fallback_rows(trade_date)
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

    def load_cached_one_to_two_rows(
        self,
        trade_date: str,
        *,
        allow_stale: bool = True,
    ) -> tuple[OneToTwoMarketRow, ...] | None:
        """Return same-date cached rows for timeout recovery without live I/O."""

        rows = self._cached_rows(trade_date)
        if rows is not None:
            return rows
        return self._load_cached_rows(trade_date, allow_stale=allow_stale)

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

    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        cached_rows = self._trend_snapshot_cache.load(trade_date, allow_stale=False)
        if cached_rows is not None:
            return cached_rows

        rows: tuple[MarketTrendRow, ...] = ()
        try:
            import akshare as ak  # type: ignore
        except Exception:
            rows = self._load_sina_full_market_rows(trade_date)
            if rows:
                return rows
            return self._fallback_trend_rows(trade_date)

        try:
            spot = ak.stock_zh_a_spot_em()
            self._cache_payload(trade_date, "stock_zh_a_spot_em", spot)
            rows = self._trend_rows_from_spot(spot, trade_date)
        except Exception:
            rows = self._load_sina_full_market_rows(trade_date)
            if rows:
                return rows
            rows = self._load_alternative_full_market_rows(ak, trade_date)
            if rows:
                self._trend_snapshot_cache.remember(trade_date, rows)
                return rows
            cached_stale = self._trend_snapshot_cache.load(trade_date, allow_stale=True)
            if cached_stale is not None:
                return cached_stale
            return self._fallback_trend_rows(trade_date)
        if not rows:
            rows = self._load_sina_full_market_rows(trade_date)
        if not rows:
            rows = self._load_alternative_full_market_rows(ak, trade_date)
        if not rows:
            cached_stale = self._trend_snapshot_cache.load(trade_date, allow_stale=True)
            if cached_stale is not None:
                return cached_stale
            return self._fallback_trend_rows(trade_date)
        self._trend_snapshot_cache.remember(trade_date, rows)
        return rows

    def load_fundamental_snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        if self._fallback is not None and hasattr(self._fallback, "load_fundamental_snapshot"):
            fallback_snapshot = self._fallback.load_fundamental_snapshot(symbol)
        else:
            fallback_snapshot = None
        try:
            import akshare as ak  # type: ignore
        except Exception:
            return fallback_snapshot

        try:
            indicator = ak.stock_financial_abstract_ths(symbol=symbol)
            self._cache_payload("latest", f"stock_financial_abstract_ths_{symbol}", indicator)
        except Exception:
            return fallback_snapshot
        records = getattr(indicator, "to_dict", lambda *_args, **_kwargs: [])("records")
        if not records:
            return fallback_snapshot
        item = records[0]
        name = self._first_text(item, ("股票简称", "名称", "name"))
        snapshot = FundamentalSnapshot(
            symbol=symbol,
            name=name,
            report_date=self._first_text(item, ("报告期", "报告日期", "date")),
            roe_pct=self._first_float(item, ("净资产收益率", "ROE", "roe")),
            revenue_growth_pct=self._first_float(item, ("营业总收入同比增长率", "营收同比", "revenue_growth")),
            net_profit_growth_pct=self._first_float(item, ("净利润同比增长率", "归母净利润同比", "net_profit_growth")),
            gross_margin_pct=self._first_float(item, ("销售毛利率", "毛利率", "gross_margin")),
            debt_ratio_pct=self._first_float(item, ("资产负债率", "debt_ratio")),
            pe_ttm=self._first_float(item, ("市盈率TTM", "PE(TTM)", "pe_ttm")),
            pb=self._first_float(item, ("市净率", "PB", "pb")),
            dividend_yield_pct=self._first_float(item, ("股息率", "dividend_yield")),
            summary="AkShare 同花顺财务摘要",
        )
        if not any(
            abs(value) > 0
            for value in (
                snapshot.roe_pct,
                snapshot.revenue_growth_pct,
                snapshot.net_profit_growth_pct,
                snapshot.gross_margin_pct,
                snapshot.debt_ratio_pct,
                snapshot.pe_ttm,
                snapshot.pb,
                snapshot.dividend_yield_pct,
            )
        ):
            return fallback_snapshot
        return snapshot

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

    def load_intraday_bars(
        self,
        symbol: str,
        trade_date: str,
        interval_minutes: int = 1,
    ) -> tuple[IntradayPriceBar, ...]:
        cached_minute_bars = self._cached_intraday_minute_bars(symbol, interval_minutes)
        if cached_minute_bars is not None:
            filtered = tuple(
                item for item in cached_minute_bars if item.trade_date == trade_date
            )
            if filtered:
                return filtered

        disk_cached = self._load_cached_intraday_minute_bars(symbol, interval_minutes)
        if disk_cached is not None:
            self._remember_intraday_minute_bars(symbol, interval_minutes, disk_cached)
            filtered = tuple(item for item in disk_cached if item.trade_date == trade_date)
            if filtered:
                return filtered

        try:
            import akshare as ak  # type: ignore
        except Exception:
            if self._fallback is not None and hasattr(self._fallback, "load_intraday_bars"):
                return self._fallback.load_intraday_bars(
                    symbol,
                    trade_date,
                    interval_minutes,
                )
            raise MarketDataUnavailable(
                "AkShare minute bars are not integrated yet; use a fallback provider."
            )

        try:
            prefixed_symbol = symbol
            if not symbol.startswith(("sh", "sz", "bj")):
                prefixed_symbol = ("sh" if symbol.startswith("6") else "sz") + symbol
            raw = ak.stock_zh_a_minute(
                symbol=prefixed_symbol,
                period=str(interval_minutes),
                adjust="",
            )
            records = getattr(raw, "to_dict", lambda *_args, **_kwargs: [])("records")
            normalized = self._intraday_bars_from_minute_records(
                records=records,
            )
            if normalized:
                minute_bars = tuple(normalized)
                self._remember_intraday_minute_bars(symbol, interval_minutes, minute_bars)
                filtered = tuple(
                    item for item in minute_bars if item.trade_date == trade_date
                )
                if filtered:
                    return filtered
        except Exception:
            pass

        if interval_minutes == 1:
            try:
                tick_snapshots = self.load_tick_snapshots(symbol, trade_date)
                normalized = self._intraday_bars_from_tick_snapshots(
                    tick_snapshots=tick_snapshots,
                    interval_minutes=interval_minutes,
                )
                if normalized:
                    return tuple(normalized)
            except Exception:
                pass

        if self._fallback is not None and hasattr(self._fallback, "load_intraday_bars"):
            return self._fallback.load_intraday_bars(
                symbol,
                trade_date,
                interval_minutes,
            )
        raise MarketDataUnavailable("AkShare intraday trades returned no usable rows")

    def load_tick_snapshots(
        self,
        symbol: str,
        trade_date: str,
    ) -> tuple[TickSnapshot, ...]:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            if self._fallback is not None and hasattr(self._fallback, "load_tick_snapshots"):
                return self._fallback.load_tick_snapshots(symbol, trade_date)
            raise MarketDataUnavailable(
                "Tick or order-book snapshots are not integrated yet; use a fallback provider."
            )

        prefixed_symbol = symbol
        if not symbol.startswith(("sh", "sz", "bj")):
            prefixed_symbol = ("sh" if symbol.startswith("6") else "sz") + symbol
        try:
            raw = ak.stock_zh_a_tick_tx_js(symbol=prefixed_symbol)
        except Exception as exc:
            if self._fallback is not None and hasattr(self._fallback, "load_tick_snapshots"):
                return self._fallback.load_tick_snapshots(symbol, trade_date)
            raise MarketDataUnavailable(
                "AkShare tick snapshots are unavailable"
            ) from exc

        records = getattr(raw, "to_dict", lambda *_args, **_kwargs: [])("records")
        normalized: list[TickSnapshot] = []
        for item in records:
            timestamp = str(item.get("成交时间", "")).strip()
            last_price = self._first_float(item, ("成交价格",))
            volume = self._first_float(item, ("成交量",))
            amount = self._first_float(item, ("成交金额",))
            if not timestamp or last_price <= 0:
                continue
            normalized.append(
                TickSnapshot(
                    trade_date=trade_date,
                    timestamp=timestamp,
                    last_price=last_price,
                    volume=volume,
                    amount=amount,
                    side=str(item.get("性质", "")).strip(),
                )
            )
        if normalized:
            return tuple(normalized)
        if self._fallback is not None and hasattr(self._fallback, "load_tick_snapshots"):
            return self._fallback.load_tick_snapshots(symbol, trade_date)
        raise MarketDataUnavailable("AkShare tick snapshots returned no usable rows")

    def _intraday_bars_from_trade_records(
        self,
        records: list[dict[str, Any]],
        trade_date: str,
    ) -> list[IntradayPriceBar]:
        normalized: list[IntradayPriceBar] = []
        bucket: dict[str, list[dict[str, float]]] = {}
        for item in records:
            timestamp = str(item.get("时间", "")).strip()
            price = self._first_float(item, ("成交价",))
            volume_hands = self._first_float(item, ("手数",))
            if not timestamp or price <= 0 or volume_hands <= 0:
                continue
            minute_key = timestamp[:5]
            bucket.setdefault(minute_key, []).append(
                {
                    "price": price,
                    "volume": volume_hands * 100,
                    "amount": price * volume_hands * 100,
                }
            )
        for minute_key in sorted(bucket):
            samples = bucket[minute_key]
            prices = [item["price"] for item in samples]
            volumes = [item["volume"] for item in samples]
            amounts = [item["amount"] for item in samples]
            normalized.append(
                IntradayPriceBar(
                    trade_date=trade_date,
                    timestamp=minute_key,
                    open_price=prices[0],
                    high_price=max(prices),
                    low_price=min(prices),
                    close_price=prices[-1],
                    volume=sum(volumes),
                    amount=sum(amounts),
                )
            )
        return normalized

    def _intraday_bars_from_minute_records(
        self,
        records: list[dict[str, Any]],
    ) -> list[IntradayPriceBar]:
        normalized: list[IntradayPriceBar] = []
        for item in records:
            raw_day = str(item.get("day", "")).strip()
            if not raw_day or " " not in raw_day:
                continue
            day_part, time_part = raw_day.split(" ", 1)
            open_price = self._first_float(item, ("open",))
            high_price = self._first_float(item, ("high",))
            low_price = self._first_float(item, ("low",))
            close_price = self._first_float(item, ("close",))
            if min(open_price, high_price, low_price, close_price) <= 0:
                continue
            normalized.append(
                IntradayPriceBar(
                    trade_date=day_part,
                    timestamp=time_part[:5],
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=self._first_float(item, ("volume",)),
                    amount=self._first_float(item, ("amount",)),
                )
            )
        return normalized

    def _intraday_bars_from_tick_snapshots(
        self,
        tick_snapshots: tuple[TickSnapshot, ...],
        interval_minutes: int = 1,
    ) -> list[IntradayPriceBar]:
        bucket: dict[str, list[TickSnapshot]] = {}
        for item in tick_snapshots:
            if not item.timestamp:
                continue
            minute_key = item.timestamp[:5]
            bucket.setdefault(minute_key, []).append(item)
        normalized: list[IntradayPriceBar] = []
        for minute_key in sorted(bucket):
            samples = bucket[minute_key]
            prices = [item.last_price for item in samples if item.last_price > 0]
            if not prices:
                continue
            normalized.append(
                IntradayPriceBar(
                    trade_date=samples[0].trade_date,
                    timestamp=minute_key,
                    open_price=prices[0],
                    high_price=max(prices),
                    low_price=min(prices),
                    close_price=prices[-1],
                    volume=sum(item.volume for item in samples),
                    amount=sum(item.amount for item in samples),
                )
            )
        return normalized

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
        cache_file = self._rows_cache_path(trade_date)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "trade_date": trade_date,
                    "rows": [item.__dict__ for item in rows],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_cached_rows(
        self,
        trade_date: str,
        *,
        allow_stale: bool = False,
    ) -> tuple[OneToTwoMarketRow, ...] | None:
        cache_file = self._rows_cache_path(trade_date)
        if not cache_file.exists():
            return None
        if (
            not allow_stale
            and (
                self._cache_ttl_seconds <= 0
                or time.time() - cache_file.stat().st_mtime > self._cache_ttl_seconds
            )
        ):
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            rows = tuple(OneToTwoMarketRow(**row) for row in payload.get("rows", ()))
        except Exception:
            return None
        return rows

    def _cached_or_fallback_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        # Same-day stale cache is a resilience fallback only after live refresh
        # fails. Normal paths still prefer fresh AkShare data.
        rows = self._load_cached_rows(trade_date, allow_stale=True)
        if rows is not None:
            return rows
        return self._fallback_rows(trade_date)

    def _rows_cache_path(self, trade_date: str) -> Path:
        return self._cache_dir / f"{trade_date}_one_to_two_rows.json"

    def _cached_intraday_minute_bars(
        self,
        symbol: str,
        interval_minutes: int,
    ) -> tuple[IntradayPriceBar, ...] | None:
        cached = self._intraday_minute_cache.get((symbol, interval_minutes))
        if not cached:
            return None
        cached_at, bars = cached
        if time.monotonic() - cached_at <= self._cache_ttl_seconds:
            return bars
        return None

    def _load_cached_intraday_minute_bars(
        self,
        symbol: str,
        interval_minutes: int,
    ) -> tuple[IntradayPriceBar, ...] | None:
        cache_file = self._intraday_cache_path(symbol, interval_minutes)
        if not cache_file.exists():
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            bars = tuple(IntradayPriceBar(**row) for row in rows)
        except Exception:
            return None
        return bars

    def _remember_intraday_minute_bars(
        self,
        symbol: str,
        interval_minutes: int,
        bars: tuple[IntradayPriceBar, ...],
    ) -> None:
        self._intraday_minute_cache[(symbol, interval_minutes)] = (
            time.monotonic(),
            bars,
        )
        cache_file = self._intraday_cache_path(symbol, interval_minutes)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "interval_minutes": interval_minutes,
                    "rows": [item.__dict__ for item in bars],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _intraday_cache_path(self, symbol: str, interval_minutes: int) -> Path:
        safe_symbol = symbol.replace("/", "_")
        return self._cache_dir / f"intraday_{safe_symbol}_{interval_minutes}m.json"

    def _fallback_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        if not self._fallback:
            raise MarketDataUnavailable("AkShare market data is unavailable")
        return self._fallback.load_one_to_two_rows(trade_date)

    def _fallback_trend_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        rows = self._trend_rows_from_cached_spot(trade_date)
        if rows:
            return rows
        one_to_two_rows = self._cached_or_fallback_rows(trade_date)
        return tuple(self._trend_row_from_one_to_two_row(row) for row in one_to_two_rows)

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
            history = (
                self._history_profile(ak, symbol, trade_date, latest)
                if self._enrich_candidate_history
                else self._quick_history_profile(latest)
            )
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
            if not auction_amount and turnover_amount:
                auction_amount = turnover_amount * 0.04
            sealed_amount = self._first_float(item, ("封板资金", "封单资金"))
            if not sealed_amount and turnover_amount:
                # Some AkShare limit-up-pool snapshots do not expose seal money.
                # Use a conservative proxy so missing columns do not masquerade as weak sealing.
                sealed_amount = turnover_amount * 0.12
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
                    sealed_amount=sealed_amount,
                    turnover_amount=turnover_amount,
                    turnover_rate=(
                        self._first_float(spot_item, ("换手率",))
                        or self._first_float(item, ("换手率",))
                    ),
                    open_pct=open_pct if open_price else min(open_pct, 0.025),
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
                    volume_ratio_5=history["volume_ratio_5"],
                    rsi_14=history["rsi_14"],
                    position_percentile_60=history["position_percentile_60"],
                    market_cap=self._normalize_market_cap(
                        self._first_float(
                            spot_item,
                            ("总市值", "总市值(元)", "总市值(亿)"),
                        )
                        or self._first_float(
                            item,
                            ("总市值", "总市值(元)", "总市值(亿)"),
                        )
                    ),
                    float_market_cap=self._normalize_market_cap(
                        self._first_float(
                            spot_item,
                            ("流通市值", "流通市值(元)", "流通市值(亿)"),
                        )
                        or self._first_float(
                            item,
                            ("流通市值", "流通市值(元)", "流通市值(亿)"),
                        )
                    ),
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
                    volume_ratio_5=1.5,
                    rsi_14=65.0,
                    position_percentile_60=0.75,
                    market_cap=self._normalize_market_cap(
                        self._first_float(item, ("总市值", "总市值(元)", "总市值(亿)"))
                    ),
                    float_market_cap=self._normalize_market_cap(
                        self._first_float(item, ("流通市值", "流通市值(元)", "流通市值(亿)"))
                    ),
                )
            )
        return tuple(rows)

    def _trend_rows_from_spot(self, spot: Any, trade_date: str) -> tuple[MarketTrendRow, ...]:
        rows: list[MarketTrendRow] = []
        records = getattr(spot, "to_dict", lambda *_args, **_kwargs: [])("records")
        for item in records:
            symbol = self._normalize_symbol(
                str(item.get("代码") or item.get("code") or "").strip()
            )
            name = str(item.get("名称") or item.get("name") or "").strip()
            latest = self._first_float(item, ("最新价", "最新", "trade", "price"))
            previous_close = self._first_float(
                item,
                ("昨收", "昨日收盘价", "settlement", "close"),
            )
            if not symbol or not name or latest <= 0 or previous_close <= 0:
                continue
            industry = self._first_text(
                item,
                ("所处行业", "行业", "所属行业", "板块"),
            )
            rows.append(
                MarketTrendRow(
                    symbol=symbol,
                    name=name,
                    trade_date=trade_date,
                    board=self._board(symbol),
                    latest_price=latest,
                    previous_close=previous_close,
                    change_pct=self._first_float(
                        item,
                        ("涨跌幅", "涨幅", "changepercent"),
                    ),
                    turnover_amount=self._first_float(
                        item,
                        ("成交额", "成交金额", "amount"),
                    ),
                    turnover_rate=self._first_float(item, ("换手率", "turnoverratio")),
                    market_cap=self._normalize_market_cap(
                        self._first_float(
                            item,
                            ("总市值", "总市值(元)", "总市值(亿)", "mktcap"),
                        )
                    ),
                    float_market_cap=self._normalize_market_cap(
                        self._first_float(
                            item,
                            ("流通市值", "流通市值(元)", "流通市值(亿)", "nmc"),
                        )
                    ),
                    industry=industry,
                    theme=industry,
                    is_st="ST" in name.upper(),
                    is_delisting="退" in name,
                    data_source="full_market_spot",
                )
            )
        return tuple(rows)

    def _load_alternative_full_market_rows(
        self,
        ak: Any,
        trade_date: str,
    ) -> tuple[MarketTrendRow, ...]:
        try:
            spot = ak.stock_zh_a_spot()
            self._cache_payload(trade_date, "stock_zh_a_spot", spot)
        except Exception:
            return ()
        rows = self._trend_rows_from_spot(spot, trade_date)
        return tuple(
            MarketTrendRow(
                **{
                    **row.__dict__,
                    "data_source": "full_market_spot_alt",
                }
            )
            for row in rows
        )

    def _load_sina_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        try:
            rows = self._sina_full_market_client.load_rows(trade_date)
        except Exception:
            return ()
        if rows:
            self._trend_snapshot_cache.remember(trade_date, rows)
        return rows

    def _trend_rows_from_cached_spot(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        cache_file = self._cache_dir / f"{trade_date}_stock_zh_a_spot_em.json"
        if not cache_file.exists():
            return ()
        try:
            records = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return ()
        rows = self._trend_rows_from_records(records, trade_date, data_source="cached_full_market_spot")
        return rows

    def _trend_rows_from_records(
        self,
        records: list[dict[str, Any]],
        trade_date: str,
        *,
        data_source: str,
    ) -> tuple[MarketTrendRow, ...]:
        class _Records:
            def to_dict(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
                return records

        rows = self._trend_rows_from_spot(_Records(), trade_date)
        return tuple(
            MarketTrendRow(
                **{
                    **row.__dict__,
                    "data_source": data_source,
                }
            )
            for row in rows
        )

    @staticmethod
    def _trend_row_from_one_to_two_row(row: OneToTwoMarketRow) -> MarketTrendRow:
        change_pct = (
            (row.latest_price - row.previous_close) / row.previous_close * 100
            if row.previous_close > 0
            else 0.0
        )
        return MarketTrendRow(
            symbol=row.symbol,
            name=row.name,
            trade_date=row.trade_date,
            board=row.board,
            latest_price=row.latest_price,
            previous_close=row.previous_close,
            change_pct=change_pct,
            turnover_amount=row.turnover_amount,
            turnover_rate=row.turnover_rate,
            market_cap=row.market_cap,
            float_market_cap=row.float_market_cap,
            industry=row.theme,
            theme=row.theme,
            is_st=row.is_st,
            is_delisting=row.is_delisting,
            data_source="one_to_two_candidate_fallback",
        )

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

        fallback = self._quick_history_profile(latest)
        if not self._enrich_candidate_history:
            self._history_cache[cache_key] = fallback
            return fallback

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
        volumes = [self._first_float(item, ("成交量", "成交量(手)")) for item in records]
        if not closes:
            self._history_cache[cache_key] = fallback
            return fallback
        pressure_candidates = [price for price in highs[-60:-1] if price > latest]
        base_close = closes[-20] if len(closes) >= 20 and closes[-20] else closes[0]
        recent_volumes = [item for item in volumes[-6:-1] if item > 0]
        volume_ratio_5 = (
            volumes[-1] / (sum(recent_volumes) / len(recent_volumes))
            if volumes and volumes[-1] > 0 and recent_volumes
            else fallback["volume_ratio_5"]
        )
        high_60 = max(highs[-60:]) if highs else fallback["high_60"]
        low_60 = min(lows[-60:]) if lows else latest * 0.85
        position_range_60 = high_60 - low_60
        profile = {
            "low_20": min(lows[-20:]) if lows else fallback["low_20"],
            "high_60": high_60,
            "pressure_price": (
                min(pressure_candidates)
                if pressure_candidates
                else max(high_60, latest * 1.12)
            ),
            "ma_5": sum(closes[-5:]) / min(len(closes), 5),
            "ma_10": sum(closes[-10:]) / min(len(closes), 10),
            "ma_20": sum(closes[-20:]) / min(len(closes), 20),
            "recent_gain_pct": (closes[-1] - base_close) / base_close if base_close else 0.0,
            "volume_ratio_5": volume_ratio_5,
            "rsi_14": self._rsi(closes[-15:]) if len(closes) >= 15 else fallback["rsi_14"],
            "position_percentile_60": (
                (closes[-1] - low_60) / position_range_60
                if position_range_60 > 0
                else fallback["position_percentile_60"]
            ),
        }
        self._history_cache[cache_key] = profile
        return profile

    @staticmethod
    def _quick_history_profile(latest: float) -> dict[str, float]:
        return {
            "low_20": latest * 0.88,
            "high_60": latest * 1.04,
            "pressure_price": latest * 1.12,
            "ma_5": latest * 0.98,
            "ma_10": latest * 0.96,
            "ma_20": latest * 0.94,
            "recent_gain_pct": 0.12,
            "volume_ratio_5": 1.5,
            "rsi_14": 65.0,
            "position_percentile_60": 0.75,
        }

    def _rsi(self, closes: list[float]) -> float:
        if len(closes) < 2:
            return 65.0
        gains: list[float] = []
        losses: list[float] = []
        for previous, current in zip(closes, closes[1:]):
            change = current - previous
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))
        average_gain = sum(gains) / len(gains)
        average_loss = sum(losses) / len(losses)
        if average_loss <= 0:
            return 100.0
        rs = average_gain / average_loss
        return 100 - (100 / (1 + rs))

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

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        raw = symbol.strip()
        if raw.isdigit() and len(raw) == 6:
            return raw
        suffix = raw[-6:]
        if suffix.isdigit():
            return suffix
        return raw

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

    @staticmethod
    def _normalize_market_cap(value: float) -> float:
        if value <= 0:
            return 0.0
        if value < 1_000_000:
            return value * 100_000_000
        return value

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
