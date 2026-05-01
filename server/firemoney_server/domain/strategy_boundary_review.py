"""Strategy-boundary review policy fed by archive review signals."""

from __future__ import annotations

from shared.contracts import (
    AdjustmentStatus,
    ArchiveReviewQuality,
    StrategyAdjustment,
    StrategyBoundaryAction,
    StrategyBoundaryReview,
    StrategyConfig,
    TradeArchiveReview,
)

from .message_catalog import DomainMessages, load_domain_messages


class StrategyBoundaryReviewPolicy:
    """Turns archive-review signals into explicit, confirmable adjustments."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_review(
        self,
        archive_review: TradeArchiveReview,
        strategy_config: StrategyConfig,
    ) -> StrategyBoundaryReview:
        blockers = self._blockers(archive_review)
        adjustments = (
            self._loss_adjustments(archive_review, strategy_config)
            if archive_review.strategy_boundary_action
            is StrategyBoundaryAction.REVIEW_LOSSES_FIRST
            else ()
        )
        adjustment_status = (
            AdjustmentStatus.WAITING_USER
            if adjustments and not blockers
            else AdjustmentStatus.NOT_AVAILABLE
        )
        return StrategyBoundaryReview(
            review_id=f"strategy-boundary-review-{archive_review.review_id}",
            source_review_id=archive_review.review_id,
            strategy_id=strategy_config.strategy_id,
            from_version=strategy_config.version,
            sample_quality=archive_review.sample_quality,
            source_action=archive_review.strategy_boundary_action,
            adjustment_status=adjustment_status,
            adjustments=adjustments,
            blockers=blockers,
            summary=self._summary(adjustment_status, blockers),
            next_action=self._next_action(adjustment_status, blockers),
        )

    def _blockers(self, archive_review: TradeArchiveReview) -> tuple[str, ...]:
        if archive_review.sample_quality is ArchiveReviewQuality.EMPTY:
            return (self._messages.text("strategy_boundary_review", "blocker_empty"),)
        if archive_review.sample_quality is ArchiveReviewQuality.INSUFFICIENT_SAMPLE:
            return (
                self._messages.format(
                    "strategy_boundary_review",
                    "blocker_insufficient",
                    count=archive_review.record_count,
                ),
            )
        return ()

    def _loss_adjustments(
        self,
        archive_review: TradeArchiveReview,
        strategy_config: StrategyConfig,
    ) -> tuple[StrategyAdjustment, ...]:
        parameters = strategy_config.parameters
        current_position = float(parameters.get("max_position_pct", 0.12))
        current_min_score = int(parameters.get("min_score", 70))
        return (
            StrategyAdjustment(
                key="max_position_pct",
                label=self._messages.text(
                    "strategy_boundary_review",
                    "adjustment_position_label",
                ),
                current_value=current_position,
                suggested_value=round(max(0.01, min(current_position, 0.08)), 2),
                reason=self._messages.format(
                    "strategy_boundary_review",
                    "adjustment_position_reason",
                    loss_count=archive_review.loss_count,
                ),
                impact=self._messages.text(
                    "strategy_boundary_review",
                    "adjustment_position_impact",
                ),
            ),
            StrategyAdjustment(
                key="min_score",
                label=self._messages.text(
                    "strategy_boundary_review",
                    "adjustment_min_score_label",
                ),
                current_value=current_min_score,
                suggested_value=max(current_min_score, 75),
                reason=self._messages.format(
                    "strategy_boundary_review",
                    "adjustment_min_score_reason",
                    worst_archive_id=archive_review.worst_archive_id or "n/a",
                ),
                impact=self._messages.text(
                    "strategy_boundary_review",
                    "adjustment_min_score_impact",
                ),
            ),
        )

    def _summary(
        self,
        adjustment_status: AdjustmentStatus,
        blockers: tuple[str, ...],
    ) -> str:
        if adjustment_status is AdjustmentStatus.WAITING_USER:
            return self._messages.text("strategy_boundary_review", "summary_waiting")
        if blockers:
            return self._messages.text("strategy_boundary_review", "summary_blocked")
        return self._messages.text("strategy_boundary_review", "summary_keep")

    def _next_action(
        self,
        adjustment_status: AdjustmentStatus,
        blockers: tuple[str, ...],
    ) -> str:
        if adjustment_status is AdjustmentStatus.WAITING_USER:
            return self._messages.text("strategy_boundary_review", "next_waiting")
        if blockers:
            return self._messages.text("strategy_boundary_review", "next_blocked")
        return self._messages.text("strategy_boundary_review", "next_keep")
