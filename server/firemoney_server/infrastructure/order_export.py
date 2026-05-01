"""CSV order export adapter for the semi-automatic execution route."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from shared.contracts import OrderTicket


DEFAULT_ORDER_EXPORT_DIR = Path("exports") / "orders"


@dataclass(frozen=True)
class OrderExportResult:
    """Result returned after a local order export is prepared."""

    path: str
    row_count: int


class CsvOrderExporter:
    """Writes confirmed order tickets to a local CSV file for user review."""

    FIELDNAMES = (
        "order_id",
        "review_id",
        "symbol",
        "name",
        "side",
        "quantity",
        "limit_price",
        "route",
        "requires_confirmation",
        "confirmation_status",
        "status",
    )

    def __init__(self, output_dir: str | Path = DEFAULT_ORDER_EXPORT_DIR) -> None:
        self._output_dir = Path(output_dir)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def export(self, ticket: OrderTicket) -> OrderExportResult:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        target = self._output_dir / f"{ticket.order_id}.csv"

        with target.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerow(
                {
                    "order_id": ticket.order_id,
                    "review_id": ticket.review_id,
                    "symbol": ticket.symbol,
                    "name": ticket.name,
                    "side": ticket.side,
                    "quantity": ticket.quantity,
                    "limit_price": ticket.limit_price,
                    "route": ticket.route,
                    "requires_confirmation": ticket.requires_confirmation,
                    "confirmation_status": ticket.confirmation_status.value,
                    "status": ticket.status,
                }
            )

        return OrderExportResult(path=target.as_posix(), row_count=1)
