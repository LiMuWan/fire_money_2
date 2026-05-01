"""Market data provider boundary for one-to-two strategy."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from server.firemoney_server.domain.one_to_two import OneToTwoMarketRow


DEFAULT_MARKET_DATA_CACHE_DIR = Path(".firemoney") / "market_data"


class MarketDataUnavailable(RuntimeError):
    """Raised when the configured market data source cannot provide data."""


class MarketDataProvider(Protocol):
    """Boundary for real market data providers."""

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        """Load normalized one-to-two rows for a trade date."""
        ...


class SampleMarketDataProvider:
    """Deterministic one-to-two sample data for preview and tests."""

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        return (
            OneToTwoMarketRow(
                symbol="600001",
                name="低位突破样例",
                trade_date=trade_date,
                board="主板",
                is_st=False,
                is_delisting=False,
                listing_days=1200,
                latest_price=10.52,
                previous_close=9.56,
                limit_up_price=10.52,
                first_limit_up_time="10:05",
                sealed_amount=32000000,
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
                theme="低位平台突破",
                market_temperature=74,
            ),
            OneToTwoMarketRow(
                symbol="600002",
                name="高位乖离样例",
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
            ),
            OneToTwoMarketRow(
                symbol="300003",
                name="创业板样例",
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
            ),
        )


class AkshareMarketDataProvider:
    """AkShare-backed market data provider with local cache and safe failure."""

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_MARKET_DATA_CACHE_DIR,
        fallback: MarketDataProvider | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._fallback = fallback

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            return self._fallback_rows(trade_date)

        try:
            previous_pool = ak.stock_zt_pool_previous_em(
                date=trade_date.replace("-", "")
            )
            spot = ak.stock_zh_a_spot_em()
            self._cache_payload(trade_date, "stock_zt_pool_previous_em", previous_pool)
            self._cache_payload(trade_date, "stock_zh_a_spot_em", spot)
        except Exception:
            return self._fallback_rows(trade_date)
        rows = self._rows_from_previous_pool(
            previous_pool,
            spot,
            trade_date,
            ak,
        )
        if rows or self._fallback is None:
            return rows
        return self._fallback_rows(trade_date)

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
        spot_by_symbol = {
            str(item.get("代码", "")): item
            for item in getattr(spot, "to_dict", lambda *_args, **_kwargs: [])("records")
        }
        market_temperature = self._market_temperature(spot_by_symbol.values())
        records = getattr(previous_pool, "to_dict", lambda *_args, **_kwargs: [])(
            "records"
        )
        for item in records[:80]:
            symbol = str(item.get("代码", ""))
            name = str(item.get("名称", ""))
            if not symbol or self._board_count(item) != 1:
                continue
            spot_item = spot_by_symbol.get(symbol, {})
            latest = self._float(spot_item.get("最新价")) or self._float(item.get("最新价"))
            limit_up_price = self._float(item.get("涨停价")) or round(latest * 1.1, 2)
            previous_close = self._float(spot_item.get("昨收")) or round(
                limit_up_price / 1.1,
                2,
            )
            if latest <= 0 or previous_close <= 0:
                continue
            history = self._history_profile(ak, symbol, trade_date, latest)
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
                    sealed_amount=self._float(item.get("封板资金")),
                    turnover_amount=(
                        self._float(spot_item.get("成交额"))
                        or self._float(item.get("成交额"))
                    ),
                    turnover_rate=(
                        self._float(spot_item.get("换手率"))
                        or self._float(item.get("换手率"))
                    ),
                    open_pct=self._float(spot_item.get("涨跌幅")) / 100,
                    auction_amount=0.0,
                    low_20=history["low_20"],
                    high_60=history["high_60"],
                    pressure_price=history["pressure_price"],
                    ma_5=history["ma_5"],
                    ma_10=history["ma_10"],
                    ma_20=history["ma_20"],
                    recent_gain_pct=history["recent_gain_pct"],
                    theme=str(item.get("所属行业", "")),
                    market_temperature=market_temperature,
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
            return fallback
        closes = [self._float(item.get("收盘")) for item in records if self._float(item.get("收盘")) > 0]
        lows = [self._float(item.get("最低")) for item in records if self._float(item.get("最低")) > 0]
        highs = [self._float(item.get("最高")) for item in records if self._float(item.get("最高")) > 0]
        if not closes:
            return fallback
        pressure_candidates = [price for price in highs[-60:-1] if price > latest]
        base_close = closes[-20] if len(closes) >= 20 and closes[-20] else closes[0]
        return {
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
