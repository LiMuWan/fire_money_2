"""Project-owned broker execution adapter boundary."""

from __future__ import annotations

from typing import Protocol

from shared.contracts import ExitExecution, FillExecution, OrderTicket

from .fill_import import BrokerFillImporter
from .order_export import CsvOrderExporter, OrderExportResult
from .receipt_import import BrokerReceiptImporter, BrokerReceiptRecord


class BrokerExecutionAdapter(Protocol):
    """Boundary for broker execution infrastructure."""

    def export_order(self, ticket: OrderTicket) -> OrderExportResult:
        """Prepare an order for user-side broker submission."""
        ...

    def import_receipt(self, order_id: str) -> BrokerReceiptRecord | None:
        """Import broker submission status for an order."""
        ...

    def import_entry_fill(self, ticket: OrderTicket) -> FillExecution | None:
        """Import broker-side entry fill detail."""
        ...

    def import_exit_fill(self, entry_fill: FillExecution) -> ExitExecution | None:
        """Import broker-side exit fill detail."""
        ...


class LocalCsvBrokerAdapter:
    """Local CSV implementation of the broker execution boundary."""

    def __init__(
        self,
        order_exporter: CsvOrderExporter | None = None,
        receipt_importer: BrokerReceiptImporter | None = None,
        fill_importer: BrokerFillImporter | None = None,
    ) -> None:
        self._order_exporter = order_exporter or CsvOrderExporter()
        self._receipt_importer = receipt_importer or BrokerReceiptImporter()
        self._fill_importer = fill_importer or BrokerFillImporter()

    def export_order(self, ticket: OrderTicket) -> OrderExportResult:
        return self._order_exporter.export(ticket)

    def import_receipt(self, order_id: str) -> BrokerReceiptRecord | None:
        return self._receipt_importer.import_for_order(order_id)

    def import_entry_fill(self, ticket: OrderTicket) -> FillExecution | None:
        return self._fill_importer.import_for_order(ticket)

    def import_exit_fill(self, entry_fill: FillExecution) -> ExitExecution | None:
        return self._fill_importer.import_exit_for_order(entry_fill)
