"""Trade archive policy for completed core workflow records."""

from __future__ import annotations

from shared.contracts import (
    ExitExecution,
    FillExecution,
    MarketContext,
    OutcomeCard,
    Recap,
    RiskReview,
    SignalScanReport,
    TradeArchiveRecord,
)


class TradeArchivePolicy:
    """Builds a compact, reviewable record once a trade is closed."""

    def build_record(
        self,
        market_context: MarketContext,
        signal_scan: SignalScanReport,
        risk_review: RiskReview,
        fill_execution: FillExecution,
        exit_execution: ExitExecution,
        outcome_card: OutcomeCard,
        recap: Recap,
    ) -> TradeArchiveRecord:
        return TradeArchiveRecord(
            archive_id=f"archive-{exit_execution.order_id}",
            order_id=exit_execution.order_id,
            symbol=exit_execution.symbol,
            name=risk_review.opportunity.name,
            trade_date=market_context.trade_date,
            opened_at=fill_execution.filled_at,
            closed_at=exit_execution.exited_at,
            realized_pnl=exit_execution.realized_pnl,
            realized_pnl_pct=exit_execution.realized_pnl_pct,
            outcome=self._outcome_label(exit_execution.realized_pnl),
            signal_summary=signal_scan.summary,
            risk_summary=risk_review.next_action,
            execution_summary=outcome_card.summary,
            recap_summary=recap.conclusion,
            next_action=recap.next_strategy_action,
            tags=(
                *risk_review.opportunity.strategy_tags,
                f"risk:{risk_review.risk_level.value}",
                f"decision:{risk_review.decision.value}",
            ),
        )

    def _outcome_label(self, realized_pnl: float) -> str:
        if realized_pnl > 0:
            return "profit"
        if realized_pnl < 0:
            return "loss"
        return "flat"
