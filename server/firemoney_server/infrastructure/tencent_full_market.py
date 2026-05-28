"""Tencent quote fallback adapter for full-market trend scanning."""

from __future__ import annotations

from urllib.parse import quote
from urllib.request import Request, urlopen

from server.firemoney_server.domain.one_to_two_types import MarketTrendRow


class TencentFullMarketClient:
    """Builds full-market spot rows from a code universe and Tencent quotes."""

    _BASE_URL = "https://qt.gtimg.cn/q="

    def __init__(self, *, batch_size: int = 80, timeout_seconds: float = 8.0) -> None:
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds

    def load_rows(
        self,
        trade_date: str,
        universe: tuple[tuple[str, str], ...],
    ) -> tuple[MarketTrendRow, ...]:
        rows: list[MarketTrendRow] = []
        names_by_symbol = {symbol: name for symbol, name in universe}
        for batch in self._batches(tuple(symbol for symbol, _name in universe)):
            quoted_codes = ",".join(self._quote_code(symbol) for symbol in batch)
            if not quoted_codes:
                continue
            try:
                text = self._load_quotes(quoted_codes)
            except Exception:
                continue
            rows.extend(self._rows_from_quote_text(text, trade_date, names_by_symbol))
        return tuple(rows)

    def _load_quotes(self, quoted_codes: str) -> str:
        request = Request(
            self._BASE_URL + quote(quoted_codes, safe=","),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://stockapp.finance.qq.com/",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:
            return response.read().decode("gbk", "ignore")

    @classmethod
    def _rows_from_quote_text(
        cls,
        text: str,
        trade_date: str,
        names_by_symbol: dict[str, str],
    ) -> list[MarketTrendRow]:
        rows: list[MarketTrendRow] = []
        for raw_line in text.split(";"):
            if "=" not in raw_line:
                continue
            _var_name, raw_payload = raw_line.split("=", 1)
            fields = raw_payload.strip().strip('"').split("~")
            if len(fields) < 5:
                continue
            symbol = cls._symbol(fields[2])
            name = fields[1] or names_by_symbol.get(symbol, "")
            latest = cls._float(fields[3])
            previous_close = cls._float(fields[4])
            if not symbol or not name or latest <= 0 or previous_close <= 0:
                continue
            change_index = 32 if len(fields) > 32 else -3
            amount_index = 37 if len(fields) > 37 else len(fields) - 2
            turnover_index = 38 if len(fields) > 38 else len(fields) - 1
            amount = cls._float(fields[amount_index]) * 10_000
            rows.append(
                MarketTrendRow(
                    symbol=symbol,
                    name=name,
                    trade_date=trade_date,
                    board=cls._board(symbol),
                    latest_price=latest,
                    previous_close=previous_close,
                    change_pct=cls._float(fields[change_index]) if change_index >= -len(fields) else 0.0,
                    turnover_amount=amount,
                    turnover_rate=cls._float(fields[turnover_index]) if turnover_index >= 0 else 0.0,
                    market_cap=0.0,
                    float_market_cap=0.0,
                    industry="",
                    theme="",
                    is_st="ST" in name.upper(),
                    is_delisting="退" in name,
                    data_source="full_market_spot_tencent",
                )
            )
        return rows

    def _batches(self, symbols: tuple[str, ...]):
        for index in range(0, len(symbols), max(1, self._batch_size)):
            yield symbols[index : index + self._batch_size]

    @staticmethod
    def _quote_code(symbol: str) -> str:
        if symbol.startswith(("600", "601", "603", "605", "688", "689", "900")):
            return f"sh{symbol}"
        if symbol.startswith(("000", "001", "002", "003", "200", "300", "301")):
            return f"sz{symbol}"
        if symbol.startswith(("8", "4", "9")):
            return f"bj{symbol}"
        return symbol

    @staticmethod
    def _symbol(raw: str) -> str:
        value = raw.strip()
        suffix = value[-6:]
        if suffix.isdigit():
            return suffix
        return value

    @staticmethod
    def _float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _board(symbol: str) -> str:
        if symbol.startswith("300"):
            return "创业板"
        if symbol.startswith("688"):
            return "科创板"
        if symbol.startswith(("8", "4", "9")):
            return "北交所"
        return "主板"


__all__ = ["TencentFullMarketClient"]


