"""Post-fill outcome policy for the core trading workflow."""

from __future__ import annotations

from shared.contracts import ExitExecution, FillExecution, OutcomeCard, RiskReview

from .message_catalog import DomainMessages, load_domain_messages


class OutcomePolicy:
    """Builds a compact post-trade result card from trusted server data."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_outcome(
        self,
        fill_execution: FillExecution,
        risk_review: RiskReview,
        current_price: float,
        exit_execution: ExitExecution | None = None,
    ) -> OutcomeCard:
        if exit_execution:
            pnl = 0.0
            pnl_pct = 0.0
            realized_pnl = exit_execution.realized_pnl
            realized_pnl_pct = exit_execution.realized_pnl_pct
        else:
            pnl = round(
                (current_price - fill_execution.avg_price)
                * fill_execution.filled_quantity,
                2,
            )
            pnl_pct = self._pnl_pct(current_price, fill_execution.avg_price)
            realized_pnl = None
            realized_pnl_pct = None
        stop_discipline = self._stop_discipline(current_price, risk_review)
        next_action = (
            self._messages.text("outcome", "closed_next_action")
            if exit_execution
            else self._next_action(current_price, risk_review)
        )
        return OutcomeCard(
            outcome_id=f"outcome-{fill_execution.order_id}",
            order_id=fill_execution.order_id,
            symbol=fill_execution.symbol,
            current_price=current_price,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=pnl_pct,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            stop_loss=risk_review.opportunity.stop_loss,
            stop_discipline=stop_discipline,
            next_action=next_action,
            summary=(
                self._messages.format(
                    "outcome",
                    "closed_summary",
                    avg_price=exit_execution.avg_price,
                    realized_pnl=realized_pnl,
                    realized_pnl_pct=realized_pnl_pct,
                )
                if exit_execution
                else self._messages.format(
                    "outcome",
                    "floating_summary",
                    current_price=current_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
            ),
        )

    def _pnl_pct(self, current_price: float, avg_price: float) -> float:
        if avg_price <= 0:
            return 0
        return round((current_price - avg_price) / avg_price, 4)

    def _stop_discipline(
        self,
        current_price: float,
        risk_review: RiskReview,
    ) -> str:
        if current_price <= risk_review.opportunity.stop_loss:
            return self._messages.text("outcome", "stop_exit")
        if current_price <= risk_review.opportunity.stop_loss * 1.03:
            return self._messages.text("outcome", "stop_reduce")
        return self._messages.text("outcome", "stop_hold")

    def _next_action(
        self,
        current_price: float,
        risk_review: RiskReview,
    ) -> str:
        if current_price <= risk_review.opportunity.stop_loss:
            return self._messages.text("outcome", "next_exit")
        if current_price >= risk_review.opportunity.target_price:
            return self._messages.text("outcome", "next_take_profit")
        return self._messages.text("outcome", "next_hold")
