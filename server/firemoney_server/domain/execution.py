"""Execution policy for controlled semi-automatic order flow."""

from __future__ import annotations

from shared.contracts import ExecutionReceipt, OrderTicket, ReviewDecision, RiskReview


class ExecutionPolicy:
    """Creates executable drafts but never bypasses confirmation."""

    def draft_order(self, review: RiskReview) -> OrderTicket | None:
        if review.decision is ReviewDecision.BLOCK:
            return None

        quantity = 100 if review.position_limit_pct <= 0.08 else 200
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
            status="draft_waiting_confirmation",
        )

    def prepare_receipt(self, ticket: OrderTicket) -> ExecutionReceipt:
        return ExecutionReceipt(
            receipt_id=f"receipt-{ticket.order_id}",
            order_id=ticket.order_id,
            accepted=True,
            status="prepared_for_manual_confirmation",
            message="委托草稿已生成，等待用户在券商终端或确认弹窗中二次确认",
            exported_path=f"exports/orders/{ticket.order_id}.csv",
        )
