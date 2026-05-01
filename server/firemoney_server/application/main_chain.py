"""Application workflow for the first FireMoney vertical slice."""

from __future__ import annotations

from server.firemoney_server.domain.execution import ExecutionPolicy
from server.firemoney_server.domain.opportunity import OpportunityRanker
from server.firemoney_server.domain.recap import RecapPolicy
from server.firemoney_server.domain.risk import RiskReviewPolicy
from server.firemoney_server.infrastructure.sample_data import (
    sample_market_context,
    sample_opportunity_candidates,
    sample_strategy_config,
)
from shared.contracts import MainChainSnapshot, WorkflowStage


class MainChainService:
    """Orchestrates the product's core chain without owning UI concerns."""

    def __init__(
        self,
        opportunity_ranker: OpportunityRanker | None = None,
        risk_policy: RiskReviewPolicy | None = None,
        execution_policy: ExecutionPolicy | None = None,
        recap_policy: RecapPolicy | None = None,
    ) -> None:
        self._opportunity_ranker = opportunity_ranker or OpportunityRanker()
        self._risk_policy = risk_policy or RiskReviewPolicy()
        self._execution_policy = execution_policy or ExecutionPolicy()
        self._recap_policy = recap_policy or RecapPolicy()

    def build_first_slice_snapshot(self) -> MainChainSnapshot:
        """Build a deterministic snapshot for scan -> review -> receipt -> recap."""

        market_context = sample_market_context()
        strategy_config = sample_strategy_config()
        opportunities = self._opportunity_ranker.rank(sample_opportunity_candidates())
        selected = opportunities[0] if opportunities else None
        risk_review = self._risk_policy.review(selected) if selected else None
        order_ticket = self._execution_policy.draft_order(risk_review) if risk_review else None
        receipt = self._execution_policy.prepare_receipt(order_ticket) if order_ticket else None
        recap = self._recap_policy.build_recap(receipt) if receipt else None

        next_stage = (
            WorkflowStage.STRATEGY_IMPROVEMENT
            if recap
            else WorkflowStage.SIGNAL_SCAN
        )

        return MainChainSnapshot(
            market_context=market_context,
            opportunities=opportunities,
            selected_opportunity=selected,
            risk_review=risk_review,
            order_ticket=order_ticket,
            execution_receipt=receipt,
            recap=recap,
            strategy_config=strategy_config,
            next_stage=next_stage,
        )
