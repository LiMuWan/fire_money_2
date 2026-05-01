"""Local persistence for completed trade archive records."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from shared.contracts import TradeArchiveRecord


DEFAULT_ARCHIVE_STORE_PATH = Path(".firemoney") / "trade_archives.json"
DEFAULT_ARCHIVE_LIMIT = 50


class TradeArchiveStore:
    """Stores compact completed-trade records in local workspace JSON."""

    def __init__(self, path: str | Path = DEFAULT_ARCHIVE_STORE_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, record: TradeArchiveRecord) -> tuple[TradeArchiveRecord, ...]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        records = [item for item in self.load_recent() if item.archive_id != record.archive_id]
        records.insert(0, record)
        records = records[:DEFAULT_ARCHIVE_LIMIT]
        payload = [self._record_to_payload(item) for item in records]
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return tuple(records)

    def load_recent(self, limit: int = DEFAULT_ARCHIVE_LIMIT) -> tuple[TradeArchiveRecord, ...]:
        if not self._path.exists():
            return ()
        try:
            with self._path.open("r", encoding="utf-8") as file:
                payload: list[dict[str, Any]] = json.load(file)
        except (JSONDecodeError, OSError):
            return ()
        return tuple(
            self._record_from_payload(item)
            for item in payload[:limit]
        )

    def _record_to_payload(self, record: TradeArchiveRecord) -> dict[str, Any]:
        return {
            "archive_id": record.archive_id,
            "order_id": record.order_id,
            "symbol": record.symbol,
            "name": record.name,
            "trade_date": record.trade_date,
            "opened_at": record.opened_at,
            "closed_at": record.closed_at,
            "realized_pnl": record.realized_pnl,
            "realized_pnl_pct": record.realized_pnl_pct,
            "outcome": record.outcome,
            "signal_summary": record.signal_summary,
            "risk_summary": record.risk_summary,
            "execution_summary": record.execution_summary,
            "recap_summary": record.recap_summary,
            "next_action": record.next_action,
            "tags": list(record.tags),
        }

    def _record_from_payload(self, payload: dict[str, Any]) -> TradeArchiveRecord:
        return TradeArchiveRecord(
            archive_id=str(payload["archive_id"]),
            order_id=str(payload["order_id"]),
            symbol=str(payload["symbol"]),
            name=str(payload["name"]),
            trade_date=str(payload["trade_date"]),
            opened_at=str(payload["opened_at"]),
            closed_at=str(payload["closed_at"]),
            realized_pnl=float(payload["realized_pnl"]),
            realized_pnl_pct=float(payload["realized_pnl_pct"]),
            outcome=str(payload["outcome"]),
            signal_summary=str(payload["signal_summary"]),
            risk_summary=str(payload["risk_summary"]),
            execution_summary=str(payload["execution_summary"]),
            recap_summary=str(payload["recap_summary"]),
            next_action=str(payload["next_action"]),
            tags=tuple(str(item) for item in payload.get("tags", ())),
        )
