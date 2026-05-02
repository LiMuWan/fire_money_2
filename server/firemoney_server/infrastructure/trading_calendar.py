"""Trading-day resolution for the one-to-two workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from shared.contracts import TradingDayContext


DEFAULT_A_SHARE_HOLIDAYS = frozenset(
    {
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
        "2026-05-04",
        "2026-05-05",
    }
)


@dataclass(frozen=True)
class ResolvedTradingDay:
    requested_date: str
    trade_date: str
    previous_trade_date: str
    next_trade_date: str
    is_trading_day: bool
    note: str

    def to_contract(self) -> TradingDayContext:
        return TradingDayContext(
            requested_date=self.requested_date,
            trade_date=self.trade_date,
            previous_trade_date=self.previous_trade_date,
            next_trade_date=self.next_trade_date,
            is_trading_day=self.is_trading_day,
            note=self.note,
        )


class TradingCalendar(Protocol):
    def resolve(self, requested_date: str | None = None) -> ResolvedTradingDay:
        """Resolve a requested date into the nearest usable trading context."""
        ...


class WeekdayTradingCalendar:
    """Fallback A-share calendar using weekdays plus known holiday closures."""

    def __init__(self, holidays: set[str] | frozenset[str] | None = None) -> None:
        self._holidays = frozenset(holidays or DEFAULT_A_SHARE_HOLIDAYS)

    def resolve(self, requested_date: str | None = None) -> ResolvedTradingDay:
        requested = _parse_date(requested_date) if requested_date else date.today()
        trade_date = requested if self._is_trading_day(requested) else self._previous(requested)
        previous_trade_date = self._previous(trade_date - timedelta(days=1))
        next_trade_date = self._next(trade_date + timedelta(days=1))
        is_trading_day = requested == trade_date
        note = (
            "requested date is an A-share trading day"
            if is_trading_day
            else f"requested date is closed; using previous trading day {trade_date.isoformat()}"
        )
        return ResolvedTradingDay(
            requested_date=requested.isoformat(),
            trade_date=trade_date.isoformat(),
            previous_trade_date=previous_trade_date.isoformat(),
            next_trade_date=next_trade_date.isoformat(),
            is_trading_day=is_trading_day,
            note=note,
        )

    def _is_trading_day(self, value: date) -> bool:
        return value.weekday() < 5 and value.isoformat() not in self._holidays

    def _previous(self, value: date) -> date:
        current = value
        while not self._is_trading_day(current):
            current -= timedelta(days=1)
        return current

    def _next(self, value: date) -> date:
        current = value
        while not self._is_trading_day(current):
            current += timedelta(days=1)
        return current


class AkshareTradingCalendar:
    """AkShare-backed trading calendar with weekday fallback."""

    def __init__(self, fallback: TradingCalendar | None = None) -> None:
        self._fallback = fallback or WeekdayTradingCalendar()
        self._trade_dates: frozenset[str] | None = None

    def resolve(self, requested_date: str | None = None) -> ResolvedTradingDay:
        try:
            trade_dates = self._load_trade_dates()
        except Exception:
            return self._fallback.resolve(requested_date)

        requested = _parse_date(requested_date) if requested_date else date.today()
        trade_date = self._previous(requested, trade_dates)
        previous_trade_date = self._previous(trade_date - timedelta(days=1), trade_dates)
        next_trade_date = self._next(trade_date + timedelta(days=1), trade_dates)
        is_trading_day = requested.isoformat() in trade_dates
        note = (
            "requested date is an A-share trading day"
            if is_trading_day
            else f"requested date is closed; using previous trading day {trade_date.isoformat()}"
        )
        return ResolvedTradingDay(
            requested_date=requested.isoformat(),
            trade_date=trade_date.isoformat(),
            previous_trade_date=previous_trade_date.isoformat(),
            next_trade_date=next_trade_date.isoformat(),
            is_trading_day=is_trading_day,
            note=note,
        )

    def _load_trade_dates(self) -> frozenset[str]:
        if self._trade_dates is not None:
            return self._trade_dates
        import akshare as ak  # type: ignore

        frame = ak.tool_trade_date_hist_sina()
        records = getattr(frame, "to_dict", lambda *_args, **_kwargs: [])("records")
        trade_dates = []
        for item in records:
            raw = item.get("trade_date") or item.get("日期") or item.get("date")
            if not raw:
                continue
            trade_dates.append(_parse_date(str(raw)).isoformat())
        if not trade_dates:
            raise RuntimeError("AkShare trading calendar returned no dates")
        self._trade_dates = frozenset(trade_dates)
        return self._trade_dates

    def _previous(self, value: date, trade_dates: frozenset[str]) -> date:
        current = value
        while current.isoformat() not in trade_dates:
            current -= timedelta(days=1)
        return current

    def _next(self, value: date, trade_dates: frozenset[str]) -> date:
        current = value
        while current.isoformat() not in trade_dates:
            current += timedelta(days=1)
        return current


def _parse_date(value: str) -> date:
    raw = value.strip()
    if "-" in raw:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    return datetime.strptime(raw, "%Y%m%d").date()
