"""Execution policy for controlled semi-automatic order flow."""

from __future__ import annotations

from shared.contracts import (
    ConfirmationStatus,
    ExecutionReceipt,
    ExecutionReceiptStatus,
    ExecutionRoute,
    OrderTicket,
    ReviewDecision,
    RiskReview,
)

from .message_catalog import DomainMessages, load_domain_messages


class ExecutionPolicy:
    """Creates executable drafts but never bypasses confirmation."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def draft_order(
        self,
        review: RiskReview,
        user_confirmed: bool = False,
    ) -> OrderTicket | None:
        if review.decision is ReviewDecision.BLOCK:
            return None

        quantity = 100 if review.position_limit_pct <= 0.08 else 200
        confirmation_status = (
            ConfirmationStatus.CONFIRMED
            if user_confirmed
            else ConfirmationStatus.WAITING_USER
        )
        confirmation_message = self._messages.text(
            "execution",
            "confirmation_confirmed" if user_confirmed else "confirmation_waiting",
        )
        status = (
            "confirmed_waiting_receipt"
            if user_confirmed
            else "draft_waiting_confirmation"
        )
        return OrderTicket(
            order_id=f"draft-{review.opportunity.symbol}",
            review_id=review.review_id,
            symbol=review.opportunity.symbol,
            name=review.opportunity.name,
            side="buy",
            quantity=quantity,
            limit_price=review.opportunity.entry_price,
            route="csv_export",
            requires_confirmation=True,
            confirmation_status=confirmation_status,
            confirmation_message=confirmation_message,
            status=status,
        )

    def prepare_receipt(
        self,
        ticket: OrderTicket,
        exported_path: str | None = None,
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            receipt_id=f"receipt-{ticket.order_id}",
            order_id=ticket.order_id,
            accepted=False,
            status=ExecutionReceiptStatus.PREPARED,
            route=ExecutionRoute.CSV_EXPORT,
            message=self._messages.text("execution", "receipt_prepared_message"),
            prepared_at="2026-05-01T09:31:00+08:00",
            submitted_at=None,
            confirmed_by_user=ticket.confirmation_status is ConfirmationStatus.CONFIRMED,
            failure_reason=None,
            next_action=self._messages.text("execution", "receipt_prepared_next_action"),
            exported_path=exported_path or f"exports/orders/{ticket.order_id}.csv",
        )

    def reconcile_receipt(
        self,
        receipt: ExecutionReceipt,
        status: ExecutionReceiptStatus,
        submitted_at: str,
        message: str,
        next_action: str,
        failure_reason: str | None = None,
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            receipt_id=receipt.receipt_id,
            order_id=receipt.order_id,
            accepted=status is ExecutionReceiptStatus.ACCEPTED,
            status=status,
            route=receipt.route,
            message=message,
            prepared_at=receipt.prepared_at,
            submitted_at=submitted_at,
            confirmed_by_user=receipt.confirmed_by_user,
            failure_reason=failure_reason,
            next_action=next_action,
            exported_path=receipt.exported_path,
        )
