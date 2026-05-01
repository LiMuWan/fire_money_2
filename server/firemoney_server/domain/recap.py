"""Recap policy for execution feedback."""

from __future__ import annotations

from shared.contracts import (
    ExecutionReceipt,
    ExitExecution,
    FillExecution,
    OutcomeCard,
    Recap,
    RiskLevel,
    RiskReview,
    StrategyAdjustment,
    StrategyConfig,
)

from .message_catalog import DomainMessages, load_domain_messages


class RecapPolicy:
    """Builds recap guidance from execution receipts."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_recap(
        self,
        receipt: ExecutionReceipt,
        risk_review: RiskReview,
        strategy_config: StrategyConfig,
        fill_execution: FillExecution | None = None,
        exit_execution: ExitExecution | None = None,
        outcome_card: OutcomeCard | None = None,
    ) -> Recap:
        adjustments = self._build_strategy_adjustments(
            risk_review=risk_review,
            strategy_config=strategy_config,
            fill_execution=fill_execution,
        )
        conclusion = self._conclusion(fill_execution, exit_execution)
        execution_deviation = (
            self._fill_deviation(fill_execution)
            if fill_execution
            else self._messages.text("recap", "deviation_waiting_fill")
        )
        lessons = (
            (
                fill_execution.message,
                exit_execution.message if exit_execution else "",
                self._fill_lesson(fill_execution),
                outcome_card.summary if outcome_card else "",
                outcome_card.next_action if outcome_card else "",
            )
            if fill_execution
            else (
                self._messages.text("recap", "lesson_keep_confirmation"),
                self._messages.text("recap", "lesson_wait_real_submission"),
            )
        )
        return Recap(
            recap_id=f"recap-{receipt.order_id}",
            order_id=receipt.order_id,
            conclusion=conclusion,
            execution_deviation=execution_deviation,
            lessons=lessons,
            strategy_adjustments=adjustments,
            next_strategy_action=self._next_strategy_action(adjustments),
        )

    def _build_strategy_adjustments(
        self,
        risk_review: RiskReview,
        strategy_config: StrategyConfig,
        fill_execution: FillExecution | None = None,
    ) -> tuple[StrategyAdjustment, ...]:
        parameters = strategy_config.parameters
        adjustments: list[StrategyAdjustment] = []

        current_position = parameters.get("max_position_pct", 0.12)
        if risk_review.risk_level is RiskLevel.MEDIUM or risk_review.warnings:
            suggested_position = min(float(current_position), risk_review.position_limit_pct)
            adjustments.append(
                StrategyAdjustment(
                    key="max_position_pct",
                    label=self._messages.text("recap", "adjustment_position_label"),
                    current_value=current_position,
                    suggested_value=round(suggested_position, 2),
                    reason=self._messages.text("recap", "adjustment_position_reason"),
                    impact=self._messages.text("recap", "adjustment_position_impact"),
                )
            )

        current_min_score = parameters.get("min_score", 70)
        if risk_review.opportunity.risk_flags:
            adjustments.append(
                StrategyAdjustment(
                    key="min_score",
                    label=self._messages.text("recap", "adjustment_min_score_label"),
                    current_value=current_min_score,
                    suggested_value=max(int(current_min_score), 75),
                    reason=self._messages.text("recap", "adjustment_min_score_reason"),
                    impact=self._messages.text("recap", "adjustment_min_score_impact"),
                )
            )

        if fill_execution and fill_execution.slippage_pct > 0.005:
            current_slippage = parameters.get("max_slippage_pct", 0.01)
            adjustments.append(
                StrategyAdjustment(
                    key="max_slippage_pct",
                    label=self._messages.text("recap", "adjustment_slippage_label"),
                    current_value=current_slippage,
                    suggested_value=min(float(current_slippage), 0.005),
                    reason=self._messages.text("recap", "adjustment_slippage_reason"),
                    impact=self._messages.text("recap", "adjustment_slippage_impact"),
                )
            )

        return tuple(adjustments)

    def _conclusion(
        self,
        fill_execution: FillExecution | None,
        exit_execution: ExitExecution | None,
    ) -> str:
        if exit_execution:
            return self._messages.text("recap", "conclusion_closed")
        if fill_execution:
            return self._messages.text("recap", "conclusion_filled")
        return self._messages.text("recap", "conclusion_prepared")

    def _next_strategy_action(
        self,
        adjustments: tuple[StrategyAdjustment, ...],
    ) -> str:
        if not adjustments:
            return self._messages.text("recap", "next_strategy_keep")
        return self._messages.text("recap", "next_strategy_review")

    def _fill_deviation(self, fill_execution: FillExecution) -> str:
        return self._messages.format(
            "recap",
            "fill_deviation",
            avg_price=fill_execution.avg_price,
            target_price=fill_execution.target_price,
            slippage_pct=fill_execution.slippage_pct,
        )

    def _fill_lesson(self, fill_execution: FillExecution) -> str:
        if fill_execution.slippage_pct > 0.005:
            return self._messages.text("recap", "fill_lesson_high_slippage")
        return self._messages.text("recap", "fill_lesson_acceptable")
