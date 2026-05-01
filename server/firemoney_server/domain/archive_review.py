"""Lightweight review policy for completed trade archives."""

from __future__ import annotations

from shared.contracts import (
    ArchiveReviewQuality,
    StrategyBoundaryAction,
    TradeArchiveRecord,
    TradeArchiveReview,
)

from .message_catalog import DomainMessages, load_domain_messages


class TradeArchiveReviewPolicy:
    """Builds a compact review summary from recent completed trades."""

    MIN_REVIEWABLE_RECORDS = 3

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_review(
        self,
        records: tuple[TradeArchiveRecord, ...],
        review_id: str = "trade-archive-review",
    ) -> TradeArchiveReview:
        if not records:
            return TradeArchiveReview(
                review_id=review_id,
                record_count=0,
                profit_count=0,
                loss_count=0,
                flat_count=0,
                sample_quality=ArchiveReviewQuality.EMPTY,
                win_rate=0.0,
                total_realized_pnl=0.0,
                average_realized_pnl_pct=0.0,
                best_archive_id=None,
                worst_archive_id=None,
                sample_quality_note=self._messages.text(
                    "archive_review",
                    "quality_empty",
                ),
                strategy_boundary_action=StrategyBoundaryAction.COLLECT_MORE_SAMPLES,
                strategy_boundary_note=self._messages.text(
                    "archive_review",
                    "boundary_collect_more",
                ),
                summary=self._messages.text("archive_review", "empty_summary"),
                focus_points=(
                    self._messages.text("archive_review", "empty_focus"),
                ),
                next_action=self._messages.text("archive_review", "empty_next_action"),
            )

        profit_count = sum(1 for record in records if record.realized_pnl > 0)
        loss_count = sum(1 for record in records if record.realized_pnl < 0)
        flat_count = len(records) - profit_count - loss_count
        total_realized_pnl = round(sum(record.realized_pnl for record in records), 2)
        average_realized_pnl_pct = round(
            sum(record.realized_pnl_pct for record in records) / len(records),
            4,
        )
        win_rate = round(profit_count / len(records), 4)
        best_record = max(records, key=lambda record: record.realized_pnl)
        worst_record = min(records, key=lambda record: record.realized_pnl)
        sample_quality = self._sample_quality(len(records))
        boundary_action = self._strategy_boundary_action(
            sample_quality=sample_quality,
            loss_count=loss_count,
        )

        return TradeArchiveReview(
            review_id=review_id,
            record_count=len(records),
            profit_count=profit_count,
            loss_count=loss_count,
            flat_count=flat_count,
            sample_quality=sample_quality,
            win_rate=win_rate,
            total_realized_pnl=total_realized_pnl,
            average_realized_pnl_pct=average_realized_pnl_pct,
            best_archive_id=best_record.archive_id,
            worst_archive_id=worst_record.archive_id,
            sample_quality_note=self._sample_quality_note(sample_quality),
            strategy_boundary_action=boundary_action,
            strategy_boundary_note=self._strategy_boundary_note(boundary_action),
            summary=self._messages.format(
                "archive_review",
                "summary",
                count=len(records),
                total_pnl=total_realized_pnl,
                win_rate=win_rate,
                average_pct=average_realized_pnl_pct,
            ),
            focus_points=self._focus_points(records, best_record, worst_record),
            next_action=self._next_action(loss_count),
        )

    def _sample_quality(self, record_count: int) -> ArchiveReviewQuality:
        if record_count == 0:
            return ArchiveReviewQuality.EMPTY
        if record_count < self.MIN_REVIEWABLE_RECORDS:
            return ArchiveReviewQuality.INSUFFICIENT_SAMPLE
        return ArchiveReviewQuality.REVIEWABLE

    def _strategy_boundary_action(
        self,
        sample_quality: ArchiveReviewQuality,
        loss_count: int,
    ) -> StrategyBoundaryAction:
        if sample_quality is not ArchiveReviewQuality.REVIEWABLE:
            return StrategyBoundaryAction.COLLECT_MORE_SAMPLES
        if loss_count:
            return StrategyBoundaryAction.REVIEW_LOSSES_FIRST
        return StrategyBoundaryAction.KEEP_CURRENT_BOUNDARY

    def _sample_quality_note(self, sample_quality: ArchiveReviewQuality) -> str:
        key_by_quality = {
            ArchiveReviewQuality.EMPTY: "quality_empty",
            ArchiveReviewQuality.INSUFFICIENT_SAMPLE: "quality_insufficient",
            ArchiveReviewQuality.REVIEWABLE: "quality_reviewable",
        }
        return self._messages.text("archive_review", key_by_quality[sample_quality])

    def _strategy_boundary_note(
        self,
        action: StrategyBoundaryAction,
    ) -> str:
        key_by_action = {
            StrategyBoundaryAction.COLLECT_MORE_SAMPLES: "boundary_collect_more",
            StrategyBoundaryAction.REVIEW_LOSSES_FIRST: "boundary_review_losses",
            StrategyBoundaryAction.KEEP_CURRENT_BOUNDARY: "boundary_keep_current",
        }
        return self._messages.text("archive_review", key_by_action[action])

    def _focus_points(
        self,
        records: tuple[TradeArchiveRecord, ...],
        best_record: TradeArchiveRecord,
        worst_record: TradeArchiveRecord,
    ) -> tuple[str, ...]:
        recent_record = records[0]
        return (
            self._messages.format(
                "archive_review",
                "focus_best",
                archive_id=best_record.archive_id,
                symbol=best_record.symbol,
                pnl=best_record.realized_pnl,
            ),
            self._messages.format(
                "archive_review",
                "focus_worst",
                archive_id=worst_record.archive_id,
                symbol=worst_record.symbol,
                pnl=worst_record.realized_pnl,
            ),
            self._messages.format(
                "archive_review",
                "focus_recent",
                archive_id=recent_record.archive_id,
                next_action=recent_record.next_action,
            ),
        )

    def _next_action(self, loss_count: int) -> str:
        if loss_count:
            return self._messages.text("archive_review", "next_action_loss")
        return self._messages.text("archive_review", "next_action_profit")
