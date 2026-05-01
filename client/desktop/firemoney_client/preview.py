"""Generate a local preview of the core FireMoney interface."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .adapter import LocalMainChainAdapter
from .renderer import render_core_workflow_html
from server.firemoney_server import MainChainService
from server.firemoney_server.infrastructure.archive_store import TradeArchiveStore
from server.firemoney_server.infrastructure.fill_import import (
    BrokerExitRecord,
    BrokerFillImporter,
    BrokerFillRecord,
)
from server.firemoney_server.infrastructure.order_export import CsvOrderExporter
from server.firemoney_server.infrastructure.receipt_import import (
    BrokerReceiptImporter,
    BrokerReceiptRecord,
)
from server.firemoney_server.infrastructure.strategy_store import StrategyConfigStore
from shared.contracts import ExecutionReceiptStatus


_CONTENT_DIR = Path(__file__).with_name("content")


def load_preview_seed(locale: str = "zh_CN") -> dict:
    """Load local preview broker samples from content config."""

    with (_CONTENT_DIR / f"preview_seed.{locale}.json").open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def seed_preview_execution_files(
    order_id: str,
    symbol: str,
    receipt_importer: BrokerReceiptImporter,
    fill_importer: BrokerFillImporter,
) -> None:
    """Create local receipt/fill samples used by the static preview states."""

    seed = load_preview_seed()
    receipt_seed = seed["receipt"]
    receipt_importer.save_record(
        BrokerReceiptRecord(
            order_id=order_id,
            status=ExecutionReceiptStatus.ACCEPTED,
            submitted_at=receipt_seed["submitted_at"],
            message=receipt_seed["message"],
            next_action=receipt_seed["next_action"],
        )
    )
    entry_seed = seed["entry_fill"]
    fill_importer.save_record(
        BrokerFillRecord(
            order_id=order_id,
            symbol=symbol,
            filled_quantity=int(entry_seed["filled_quantity"]),
            avg_price=float(entry_seed["avg_price"]),
            filled_at=entry_seed["filled_at"],
            message=entry_seed["message"],
        )
    )
    exit_seed = seed["exit_fill"]
    fill_importer.save_exit_record(
        BrokerExitRecord(
            order_id=order_id,
            symbol=symbol,
            exited_quantity=int(exit_seed["exited_quantity"]),
            avg_price=float(exit_seed["avg_price"]),
            exited_at=exit_seed["exited_at"],
            reason=exit_seed["reason"],
            message=exit_seed["message"],
        )
    )


def build_preview(output_path: str | Path) -> Path:
    """Write the current core workflow interface to an HTML file."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        preview_root = Path(temp_dir)
        store = StrategyConfigStore(preview_root / "strategy_config.json")
        receipt_importer = BrokerReceiptImporter(preview_root / "receipts")
        fill_importer = BrokerFillImporter(preview_root / "fills")
        adapter = LocalMainChainAdapter(
            MainChainService(
                strategy_store=store,
                archive_store=TradeArchiveStore(preview_root / "trade_archives.json"),
                order_exporter=CsvOrderExporter(preview_root / "orders"),
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
            )
        )
        snapshot = adapter.load_snapshot()
        confirmed_snapshot = adapter.load_snapshot(user_confirmed=True)
        seed_preview_execution_files(
            order_id=confirmed_snapshot.execution_receipt.order_id,
            symbol=confirmed_snapshot.order_ticket.symbol,
            receipt_importer=receipt_importer,
            fill_importer=fill_importer,
        )
        submitted_snapshot = adapter.load_snapshot(
            user_confirmed=True,
            broker_submitted=True,
        )
        filled_snapshot = adapter.load_snapshot(
            user_confirmed=True,
            broker_submitted=True,
            fill_received=True,
        )
        closed_snapshot = adapter.load_snapshot(
            user_confirmed=True,
            broker_submitted=True,
            fill_received=True,
            exit_received=True,
        )
        adjusted_snapshot = adapter.load_snapshot(
            user_confirmed=True,
            broker_submitted=True,
            fill_received=True,
            exit_received=True,
            adjustments_confirmed=True,
        )
        adapter.reset_strategy_config()
        reset_snapshot = adapter.load_snapshot(
            user_confirmed=True,
            broker_submitted=True,
            fill_received=True,
            exit_received=True,
        )
        target.write_text(
            render_core_workflow_html(
                snapshot,
                confirmed_snapshot=confirmed_snapshot,
                submitted_snapshot=submitted_snapshot,
                filled_snapshot=filled_snapshot,
                closed_snapshot=closed_snapshot,
                adjusted_snapshot=adjusted_snapshot,
                reset_snapshot=reset_snapshot,
            ),
            encoding="utf-8",
        )
    return target


if __name__ == "__main__":
    build_preview(Path("client") / "desktop" / "preview" / "core_workflow.html")
