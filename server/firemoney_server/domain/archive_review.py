"""Lightweight review policy for completed trade archives."""

from __future__ import annotations

from shared.contracts import TradeArchiveRecord, TradeArchiveReview

from .message_catalog import DomainMessages, load_domain_messages


class TradeArchiveReviewPolicy:
    """Builds a compact review summary from recent completed trades."""

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
                win_rate=0.0,
                total_realized_pnl=0.0,
                average_realized_pnl_pct=0.0,
                best_archive_id=None,
                worst_archive_id=None,
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

        return TradeArchiveReview(
            review_id=review_id,
            record_count=len(records),
            profit_count=profit_count,
            loss_count=loss_count,
            flat_count=flat_count,
            win_rate=win_rate,
            total_realized_pnl=total_realized_pnl,
            average_realized_pnl_pct=average_realized_pnl_pct,
            best_archive_id=best_record.archive_id,
            worst_archive_id=worst_record.archive_id,
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
