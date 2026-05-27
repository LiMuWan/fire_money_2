"""Sina full-market spot adapter for mainline trend scanning."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.firemoney_server.domain.one_to_two_types import MarketTrendRow


class SinaFullMarketClient:
    """Loads A-share spot rows from Sina's market-center endpoint."""

    _BASE_URL = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData"
    )

    def __init__(
        self,
        *,
        page_size: int = 80,
        max_pages: int = 90,
        max_workers: int = 8,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._page_size = page_size
        self._max_pages = max_pages
        self._max_workers = max_workers
        self._timeout_seconds = timeout_seconds

    def load_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        rows: list[MarketTrendRow] = []
        seen: set[str] = set()
        records_by_page: dict[int, list[dict[str, object]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, self._max_workers)) as executor:
            futures = {
                executor.submit(self._load_page, page): page
                for page in range(1, self._max_pages + 1)
            }
            for future in as_completed(futures):
                page = futures[future]
                try:
                    records_by_page[page] = future.result()
                except Exception:
                    records_by_page[page] = []

        for page in range(1, self._max_pages + 1):
            records = records_by_page.get(page, [])
            if not records:
                break
            page_rows = self.rows_from_records(records, trade_date)
            for row in page_rows:
                if row.symbol in seen:
                    continue
                seen.add(row.symbol)
                rows.append(row)
            if len(records) < self._page_size:
                break
        return tuple(rows)

    def _load_page(self, page: int) -> list[dict[str, object]]:
        query = urlencode(
            {
                "page": page,
                "num": self._page_size,
                "sort": "symbol",
                "asc": 1,
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            }
        )
        request = Request(
            f"{self._BASE_URL}?{query}",
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:
            text = response.read().decode("utf-8", "ignore").strip()
        if not text:
            return []
        payload = json.loads(text)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @classmethod
    def rows_from_records(
        cls,
        records: list[dict[str, object]],
        trade_date: str,
    ) -> tuple[MarketTrendRow, ...]:
        rows: list[MarketTrendRow] = []
        for item in records:
            code = str(item.get("code") or "").strip()
            raw_symbol = str(item.get("symbol") or "").strip().lower()
            symbol = cls._symbol(code, raw_symbol)
            name = str(item.get("name") or "").strip()
            latest = cls._float(item.get("trade"))
            previous_close = cls._float(item.get("settlement"))
            if not symbol or not name or latest <= 0 or previous_close <= 0:
                continue
            rows.append(
                MarketTrendRow(
                    symbol=symbol,
                    name=name,
                    trade_date=trade_date,
                    board=cls._board(symbol, raw_symbol),
                    latest_price=latest,
                    previous_close=previous_close,
                    change_pct=cls._float(item.get("changepercent")),
                    turnover_amount=cls._float(item.get("amount")),
                    turnover_rate=cls._float(item.get("turnoverratio")),
                    market_cap=cls._sina_market_cap(item.get("mktcap")),
                    float_market_cap=cls._sina_market_cap(item.get("nmc")),
                    industry=str(item.get("industry") or item.get("category") or ""),
                    theme=str(item.get("industry") or item.get("category") or ""),
                    is_st="ST" in name.upper(),
                    is_delisting="退" in name,
                    data_source="full_market_spot_sina",
                )
            )
        return tuple(rows)

    @staticmethod
    def _symbol(code: str, raw_symbol: str) -> str:
        if code.isdigit() and len(code) == 6:
            return code
        suffix = raw_symbol[-6:]
        if suffix.isdigit():
            return suffix
        return code or suffix

    @staticmethod
    def _float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _sina_market_cap(value: object) -> float:
        raw = SinaFullMarketClient._float(value)
        if raw <= 0:
            return 0.0
        return raw * 10_000

    @staticmethod
    def _board(symbol: str, raw_symbol: str) -> str:
        if raw_symbol.startswith("bj") or symbol.startswith(("8", "4", "9")):
            return "北交所"
        if symbol.startswith("300"):
            return "创业板"
        if symbol.startswith("688"):
            return "科创板"
        return "主板"


__all__ = ["SinaFullMarketClient"]
