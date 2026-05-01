"""Application workflow for the first FireMoney vertical slice."""

from __future__ import annotations

from pathlib import Path

from server.firemoney_server.domain.archive import TradeArchivePolicy
from server.firemoney_server.domain.execution import ExecutionPolicy
from server.firemoney_server.domain.opportunity import OpportunityRanker
from server.firemoney_server.domain.outcome import OutcomePolicy
from server.firemoney_server.domain.recap import RecapPolicy
from server.firemoney_server.domain.risk import RiskReviewPolicy
from server.firemoney_server.domain.signal_scan import SignalScanPolicy
from server.firemoney_server.domain.strategy_config import StrategyConfigPolicy
from server.firemoney_server.infrastructure.sample_data import (
    sample_market_context,
    sample_current_price,
    sample_opportunity_candidates,
    sample_strategy_config,
    sample_universe_size,
)
from server.firemoney_server.infrastructure.archive_store import TradeArchiveStore
from server.firemoney_server.infrastructure.broker_adapter import (
    BrokerExecutionAdapter,
    LocalCsvBrokerAdapter,
)
from server.firemoney_server.infrastructure.fill_import import BrokerFillImporter
from server.firemoney_server.infrastructure.order_export import CsvOrderExporter
from server.firemoney_server.infrastructure.receipt_import import BrokerReceiptImporter
from server.firemoney_server.infrastructure.strategy_store import StrategyConfigStore
from shared.contracts import MainChainSnapshot, WorkflowStage


class MainChainService:
    """Orchestrates the product's core chain without owning UI concerns."""

    def __init__(
        self,
        opportunity_ranker: OpportunityRanker | None = None,
        risk_policy: RiskReviewPolicy | None = None,
        archive_policy: TradeArchivePolicy | None = None,
        execution_policy: ExecutionPolicy | None = None,
        outcome_policy: OutcomePolicy | None = None,
        recap_policy: RecapPolicy | None = None,
        signal_scan_policy: SignalScanPolicy | None = None,
        strategy_config_policy: StrategyConfigPolicy | None = None,
        strategy_store: StrategyConfigStore | None = None,
        archive_store: TradeArchiveStore | None = None,
        broker_adapter: BrokerExecutionAdapter | None = None,
        order_exporter: CsvOrderExporter | None = None,
        receipt_importer: BrokerReceiptImporter | None = None,
        fill_importer: BrokerFillImporter | None = None,
    ) -> None:
        self._opportunity_ranker = opportunity_ranker or OpportunityRanker()
        self._risk_policy = risk_policy or RiskReviewPolicy()
        self._archive_policy = archive_policy or TradeArchivePolicy()
        self._execution_policy = execution_policy or ExecutionPolicy()
        self._outcome_policy = outcome_policy or OutcomePolicy()
        self._recap_policy = recap_policy or RecapPolicy()
        self._signal_scan_policy = signal_scan_policy or SignalScanPolicy()
        self._strategy_config_policy = strategy_config_policy or StrategyConfigPolicy()
        self._strategy_store = strategy_store or StrategyConfigStore()
        self._archive_store = archive_store or TradeArchiveStore()
        self._broker_adapter = broker_adapter or LocalCsvBrokerAdapter(
            order_exporter=order_exporter,
            receipt_importer=receipt_importer,
            fill_importer=fill_importer,
        )

    def reset_strategy_config(self) -> bool:
        """Restore default strategy boundaries by clearing local overrides."""

        return self._strategy_store.reset(sample_strategy_config()) is not None

    def export_trade_archives(
        self,
        target_path: str | Path | None = None,
        format: str = "json",
        limit: int = 50,
    ) -> Path:
        """Export compact completed-trade archives through the service boundary."""

        return self._archive_store.export_recent(
            target_path=target_path,
            format=format,
            limit=limit,
        )

    def clear_trade_archives(self) -> bool:
        """Clear local completed-trade archives through the service boundary."""

        return self._archive_store.clear()

    def build_first_slice_snapshot(
        self,
        user_confirmed: bool = False,
        broker_submitted: bool = False,
        fill_received: bool = False,
        exit_received: bool = False,
        adjustments_confirmed: bool = False,
    ) -> MainChainSnapshot:
        """Build a deterministic snapshot for scan -> review -> confirmation."""

        market_context = sample_market_context()
        default_strategy_config = sample_strategy_config()
        base_strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        strategy_config = base_strategy_config
        opportunities = self._opportunity_ranker.rank(sample_opportunity_candidates())
        signal_scan = self._signal_scan_policy.build_report(
            opportunities=opportunities,
            strategy_config=strategy_config,
            universe_size=sample_universe_size(),
            report_id=f"scan-{market_context.trade_date}-001",
        )
        selected = signal_scan.focus_opportunity
        risk_review = self._risk_policy.review(selected) if selected else None
        order_ticket = (
            self._execution_policy.draft_order(
                risk_review,
                user_confirmed=user_confirmed,
            )
            if risk_review
            else None
        )
        export_result = (
            self._broker_adapter.export_order(order_ticket)
            if order_ticket and user_confirmed
            else None
        )
        receipt = (
            self._execution_policy.prepare_receipt(
                order_ticket,
                exported_path=export_result.path,
            )
            if order_ticket and export_result
            else None
        )
        if receipt and broker_submitted:
            imported_receipt = self._broker_adapter.import_receipt(
                receipt.order_id,
            )
            if imported_receipt:
                receipt = self._execution_policy.reconcile_receipt(
                    receipt=receipt,
                    status=imported_receipt.status,
                    submitted_at=imported_receipt.submitted_at,
                    message=imported_receipt.message,
                    next_action=imported_receipt.next_action,
                    failure_reason=imported_receipt.failure_reason,
                )
        fill_execution = (
            self._broker_adapter.import_entry_fill(order_ticket)
            if order_ticket and receipt and receipt.accepted and fill_received
            else None
        )
        exit_execution = (
            self._broker_adapter.import_exit_fill(fill_execution)
            if fill_execution and exit_received
            else None
        )
        outcome_card = (
            self._outcome_policy.build_outcome(
                fill_execution=fill_execution,
                risk_review=risk_review,
                current_price=sample_current_price(fill_execution.symbol),
                exit_execution=exit_execution,
            )
            if fill_execution and risk_review
            else None
        )
        recap = (
            self._recap_policy.build_recap(
                receipt=receipt,
                risk_review=risk_review,
                strategy_config=strategy_config,
                fill_execution=fill_execution,
                exit_execution=exit_execution,
                outcome_card=outcome_card,
            )
            if receipt and risk_review
            else None
        )
        archive_record = (
            self._archive_policy.build_record(
                market_context=market_context,
                signal_scan=signal_scan,
                risk_review=risk_review,
                fill_execution=fill_execution,
                exit_execution=exit_execution,
                outcome_card=outcome_card,
                recap=recap,
            )
            if fill_execution and exit_execution and outcome_card and recap and risk_review
            else None
        )
        recent_archives = (
            self._archive_store.save(archive_record)
            if archive_record
            else self._archive_store.load_recent(limit=3)
        )
        if recap and adjustments_confirmed:
            strategy_config = self._strategy_config_policy.apply_adjustments(
                strategy_config=base_strategy_config,
                adjustments=recap.strategy_adjustments,
            )
            strategy_config = self._strategy_store.save(
                strategy_config,
                previous_config=base_strategy_config,
            )
        else:
            strategy_config = self._strategy_config_policy.mark_waiting_adjustment(
                strategy_config=base_strategy_config,
                recap=recap,
            )

        next_stage = (
            WorkflowStage.STRATEGY_IMPROVEMENT
            if recap and not adjustments_confirmed
            else WorkflowStage.SIGNAL_SCAN
            if recap and adjustments_confirmed
            else WorkflowStage.ORDER_DRAFT
            if order_ticket
            else WorkflowStage.SIGNAL_SCAN
        )

        return MainChainSnapshot(
            market_context=market_context,
            signal_scan=signal_scan,
            opportunities=opportunities,
            selected_opportunity=selected,
            risk_review=risk_review,
            order_ticket=order_ticket,
            execution_receipt=receipt,
            fill_execution=fill_execution,
            exit_execution=exit_execution,
            outcome_card=outcome_card,
            archive_record=archive_record,
            recent_archives=recent_archives,
            recap=recap,
            strategy_config=strategy_config,
            next_stage=next_stage,
        )
