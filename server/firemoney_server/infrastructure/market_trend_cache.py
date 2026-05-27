"""Normalized full-market trend snapshot cache."""

from __future__ import annotations

import json
import time
from pathlib import Path

from server.firemoney_server.domain.one_to_two_types import MarketTrendRow


class MarketTrendSnapshotCache:
    """Stores normalized full-market rows for page-safe reuse."""

    def __init__(self, cache_dir: str | Path, ttl_seconds: float = 1800.0) -> None:
        self._cache_dir = Path(cache_dir)
        self._ttl_seconds = ttl_seconds
        self._memory: dict[str, tuple[float, tuple[MarketTrendRow, ...]]] = {}

    def remember(
        self,
        trade_date: str,
        rows: tuple[MarketTrendRow, ...],
    ) -> None:
        if not rows:
            return
        self._memory[trade_date] = (time.monotonic(), rows)
        cache_file = self._cache_path(trade_date)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "trade_date": trade_date,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "row_count": len(rows),
                    "rows": [row.__dict__ for row in rows],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def load(
        self,
        trade_date: str,
        *,
        allow_stale: bool = False,
    ) -> tuple[MarketTrendRow, ...] | None:
        cached = self._memory.get(trade_date)
        if cached:
            cached_at, rows = cached
            if self._is_fresh_monotonic(cached_at) or allow_stale:
                return self._with_cache_source(rows, stale=not self._is_fresh_monotonic(cached_at))

        cache_file = self._cache_path(trade_date)
        if not cache_file.exists():
            return None
        stale = self._is_stale_file(cache_file)
        if stale and not allow_stale:
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            rows = tuple(MarketTrendRow(**row) for row in payload.get("rows", ()))
        except Exception:
            return None
        if not rows:
            return None
        if any(not row.symbol.isdigit() for row in rows):
            return None
        self._memory[trade_date] = (time.monotonic(), rows)
        return self._with_cache_source(rows, stale=stale)

    def _cache_path(self, trade_date: str) -> Path:
        return self._cache_dir / f"{trade_date}_full_market_trend_rows.json"

    def _is_fresh_monotonic(self, cached_at: float) -> bool:
        return self._ttl_seconds > 0 and time.monotonic() - cached_at <= self._ttl_seconds

    def _is_stale_file(self, cache_file: Path) -> bool:
        return self._ttl_seconds <= 0 or time.time() - cache_file.stat().st_mtime > self._ttl_seconds

    @staticmethod
    def _with_cache_source(
        rows: tuple[MarketTrendRow, ...],
        *,
        stale: bool,
    ) -> tuple[MarketTrendRow, ...]:
        source = "full_market_spot_cache_stale" if stale else "full_market_spot_cache"
        return tuple(
            MarketTrendRow(
                **{
                    **row.__dict__,
                    "data_source": source,
                }
            )
            for row in rows
        )


__all__ = ["MarketTrendSnapshotCache"]
