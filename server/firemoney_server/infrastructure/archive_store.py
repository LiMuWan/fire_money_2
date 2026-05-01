"""Local persistence for completed trade archive records."""

from __future__ import annotations

import csv
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from shared.contracts import TradeArchiveRecord


DEFAULT_ARCHIVE_STORE_PATH = Path(".firemoney") / "trade_archives.json"
DEFAULT_ARCHIVE_LIMIT = 50
DEFAULT_ARCHIVE_EXPORT_DIR = Path("exports") / "archives"


class TradeArchiveStore:
    """Stores compact completed-trade records in local workspace JSON."""

    def __init__(
        self,
        path: str | Path = DEFAULT_ARCHIVE_STORE_PATH,
        export_dir: str | Path = DEFAULT_ARCHIVE_EXPORT_DIR,
    ) -> None:
        self._path = Path(path)
        self._export_dir = Path(export_dir)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def export_dir(self) -> Path:
        return self._export_dir

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

    def export_recent(
        self,
        target_path: str | Path | None = None,
        format: str = "json",
        limit: int = DEFAULT_ARCHIVE_LIMIT,
    ) -> Path:
        """Export recent archive records for external review."""

        records = self.load_recent(limit=limit)
        normalized_format = format.lower()
        if normalized_format not in {"json", "csv"}:
            raise ValueError(f"unsupported archive export format: {format}")

        target = (
            Path(target_path)
            if target_path
            else self._export_dir / f"trade_archives.{normalized_format}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if normalized_format == "csv":
            self._write_csv(target, records)
        else:
            self._write_json(target, records)
        return target

    def clear(self) -> bool:
        """Delete local archive records without touching exported reports."""

        if not self._path.exists():
            return False
        self._path.unlink()
        return True

    def load_recent(self, limit: int = DEFAULT_ARCHIVE_LIMIT) -> tuple[TradeArchiveRecord, ...]:
        if not self._path.exists():
            return ()
        try:
            with self._path.open("r", encoding="utf-8") as file:
                payload: list[dict[str, Any]] = json.load(file)
            return tuple(
                self._record_from_payload(item)
                for item in payload[:limit]
            )
        except (JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            return ()

    def _write_json(
        self,
        target: Path,
        records: tuple[TradeArchiveRecord, ...],
    ) -> None:
        target.write_text(
            json.dumps(
                [self._record_to_payload(item) for item in records],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_csv(
        self,
        target: Path,
        records: tuple[TradeArchiveRecord, ...],
    ) -> None:
        fieldnames = tuple(self._record_to_payload(records[0]).keys()) if records else (
            "archive_id",
            "order_id",
            "symbol",
            "name",
            "trade_date",
            "opened_at",
            "closed_at",
            "realized_pnl",
            "realized_pnl_pct",
            "outcome",
            "signal_summary",
            "risk_summary",
            "execution_summary",
            "recap_summary",
            "next_action",
            "tags",
        )
        with target.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                payload = self._record_to_payload(record)
                payload["tags"] = "|".join(payload["tags"])
                writer.writerow(payload)

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
