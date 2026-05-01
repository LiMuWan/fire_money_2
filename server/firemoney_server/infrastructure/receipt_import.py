"""Broker receipt import adapter for the semi-automatic execution route."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from shared.contracts import ExecutionReceiptStatus


DEFAULT_BROKER_RECEIPT_DIR = Path("exports") / "receipts"


@dataclass(frozen=True)
class BrokerReceiptRecord:
    """One imported broker-side receipt row."""

    order_id: str
    status: ExecutionReceiptStatus
    submitted_at: str
    message: str
    next_action: str
    failure_reason: str | None = None


class BrokerReceiptImporter:
    """Reads broker-side receipt CSV files and finds the matching order."""

    FIELDNAMES = (
        "order_id",
        "status",
        "submitted_at",
        "message",
        "next_action",
        "failure_reason",
    )

    def __init__(
        self,
        receipt_dir: str | Path = DEFAULT_BROKER_RECEIPT_DIR,
    ) -> None:
        self._receipt_dir = Path(receipt_dir)

    def path_for_order(self, order_id: str) -> Path:
        return self._receipt_dir / f"{order_id}.csv"

    def save_record(self, record: BrokerReceiptRecord) -> str:
        self._receipt_dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for_order(record.order_id)
        with target.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerow(
                {
                    "order_id": record.order_id,
                    "status": record.status.value,
                    "submitted_at": record.submitted_at,
                    "message": record.message,
                    "next_action": record.next_action,
                    "failure_reason": record.failure_reason or "",
                }
            )
        return target.as_posix()

    def import_for_order(
        self,
        order_id: str,
        receipt_path: str | Path | None = None,
    ) -> BrokerReceiptRecord | None:
        path = Path(receipt_path) if receipt_path else self.path_for_order(order_id)
        if not path.exists():
            return None

        with path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("order_id") != order_id:
                    continue
                status = ExecutionReceiptStatus(row.get("status") or "submitted")
                return BrokerReceiptRecord(
                    order_id=order_id,
                    status=status,
                    submitted_at=row.get("submitted_at") or "",
                    message=row.get("message") or status.value,
                    next_action=row.get("next_action") or row.get("message") or status.value,
                    failure_reason=row.get("failure_reason") or None,
                )
        return None
