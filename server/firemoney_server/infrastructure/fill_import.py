"""Broker fill import adapter for the semi-automatic execution route."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from shared.contracts import ExitExecution, FillExecution, OrderTicket
from server.firemoney_server.domain.message_catalog import (
    DomainMessages,
    load_domain_messages,
)


DEFAULT_FILL_DIR = Path("exports") / "fills"


@dataclass(frozen=True)
class BrokerFillRecord:
    """One broker-side fill row."""

    order_id: str
    symbol: str
    filled_quantity: int
    avg_price: float
    filled_at: str
    source: str = "broker_csv"
    message: str = ""


@dataclass(frozen=True)
class BrokerExitRecord:
    """One broker-side exit fill row."""

    order_id: str
    symbol: str
    exited_quantity: int
    avg_price: float
    exited_at: str
    reason: str
    message: str = ""


class BrokerFillImporter:
    """Reads broker fill CSV files and converts them into shared contracts."""

    FIELDNAMES = (
        "order_id",
        "symbol",
        "filled_quantity",
        "avg_price",
        "filled_at",
        "source",
        "message",
    )
    EXIT_FIELDNAMES = (
        "order_id",
        "symbol",
        "exited_quantity",
        "avg_price",
        "exited_at",
        "reason",
        "message",
    )

    def __init__(
        self,
        fill_dir: str | Path = DEFAULT_FILL_DIR,
        messages: DomainMessages | None = None,
    ) -> None:
        self._fill_dir = Path(fill_dir)
        self._messages = messages or load_domain_messages()

    def path_for_order(self, order_id: str) -> Path:
        return self._fill_dir / f"{order_id}.csv"

    def exit_path_for_order(self, order_id: str) -> Path:
        return self._fill_dir / f"{order_id}.exit.csv"

    def save_record(self, record: BrokerFillRecord) -> str:
        self._fill_dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for_order(record.order_id)
        with target.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerow(
                {
                    "order_id": record.order_id,
                    "symbol": record.symbol,
                    "filled_quantity": record.filled_quantity,
                    "avg_price": record.avg_price,
                    "filled_at": record.filled_at,
                    "source": record.source,
                    "message": record.message,
                }
            )
        return target.as_posix()

    def save_exit_record(self, record: BrokerExitRecord) -> str:
        self._fill_dir.mkdir(parents=True, exist_ok=True)
        target = self.exit_path_for_order(record.order_id)
        with target.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.EXIT_FIELDNAMES)
            writer.writeheader()
            writer.writerow(
                {
                    "order_id": record.order_id,
                    "symbol": record.symbol,
                    "exited_quantity": record.exited_quantity,
                    "avg_price": record.avg_price,
                    "exited_at": record.exited_at,
                    "reason": record.reason,
                    "message": record.message,
                }
            )
        return target.as_posix()

    def import_for_order(
        self,
        ticket: OrderTicket,
        fill_path: str | Path | None = None,
    ) -> FillExecution | None:
        path = Path(fill_path) if fill_path else self.path_for_order(ticket.order_id)
        if not path.exists():
            return None

        with path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("order_id") != ticket.order_id:
                    continue
                avg_price = float(row.get("avg_price") or 0)
                return FillExecution(
                    fill_id=f"fill-{ticket.order_id}",
                    order_id=ticket.order_id,
                    symbol=row.get("symbol") or ticket.symbol,
                    filled_quantity=int(row.get("filled_quantity") or 0),
                    avg_price=avg_price,
                    target_price=ticket.limit_price,
                    slippage_pct=self._slippage_pct(avg_price, ticket.limit_price),
                    filled_at=row.get("filled_at") or "",
                    source=row.get("source") or "broker_csv",
                    message=row.get("message") or self._messages.text("broker_import", "entry_fill_default"),
                )
        return None

    def import_exit_for_order(
        self,
        entry_fill: FillExecution,
        exit_path: str | Path | None = None,
    ) -> ExitExecution | None:
        path = (
            Path(exit_path)
            if exit_path
            else self.exit_path_for_order(entry_fill.order_id)
        )
        if not path.exists():
            return None

        with path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("order_id") != entry_fill.order_id:
                    continue
                avg_price = float(row.get("avg_price") or 0)
                quantity = int(row.get("exited_quantity") or 0)
                realized_pnl = round(
                    (avg_price - entry_fill.avg_price) * quantity,
                    2,
                )
                realized_pnl_pct = self._slippage_pct(
                    avg_price,
                    entry_fill.avg_price,
                )
                return ExitExecution(
                    exit_id=f"exit-{entry_fill.order_id}",
                    order_id=entry_fill.order_id,
                    symbol=row.get("symbol") or entry_fill.symbol,
                    exited_quantity=quantity,
                    avg_price=avg_price,
                    entry_avg_price=entry_fill.avg_price,
                    realized_pnl=realized_pnl,
                    realized_pnl_pct=realized_pnl_pct,
                    exited_at=row.get("exited_at") or "",
                    reason=row.get("reason") or "manual_exit",
                    message=row.get("message") or self._messages.text("broker_import", "exit_fill_default"),
                )
        return None

    def _slippage_pct(self, avg_price: float, target_price: float) -> float:
        if target_price <= 0:
            return 0
        return round((avg_price - target_price) / target_price, 4)
