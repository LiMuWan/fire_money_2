"""Markdown export for lightweight trade archive reviews."""

from __future__ import annotations

from pathlib import Path

from shared.contracts import TradeArchiveRecord, TradeArchiveReview

from .archive_store import DEFAULT_ARCHIVE_EXPORT_DIR


class MarkdownArchiveReviewExporter:
    """Writes compact archive review reports for external reading."""

    def __init__(self, export_dir: str | Path = DEFAULT_ARCHIVE_EXPORT_DIR) -> None:
        self._export_dir = Path(export_dir)

    @property
    def export_dir(self) -> Path:
        return self._export_dir

    def export(
        self,
        review: TradeArchiveReview,
        records: tuple[TradeArchiveRecord, ...],
        target_path: str | Path | None = None,
    ) -> Path:
        target = (
            Path(target_path)
            if target_path
            else self._export_dir / "trade_archive_review.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_markdown(review, records), encoding="utf-8")
        return target

    def _render_markdown(
        self,
        review: TradeArchiveReview,
        records: tuple[TradeArchiveRecord, ...],
    ) -> str:
        lines = [
            "# Trade Archive Review",
            "",
            f"- Review ID: {review.review_id}",
            f"- Records: {review.record_count}",
            f"- Sample quality: {review.sample_quality.value}",
            f"- Win rate: {review.win_rate:.2%}",
            f"- Total realized P/L: {review.total_realized_pnl:.2f}",
            f"- Average realized P/L %: {review.average_realized_pnl_pct:.2%}",
            f"- Best archive: {review.best_archive_id or 'n/a'}",
            f"- Worst archive: {review.worst_archive_id or 'n/a'}",
            f"- Strategy boundary action: {review.strategy_boundary_action.value}",
            "",
            "## Summary",
            "",
            review.summary,
            "",
            "## Sample Quality",
            "",
            review.sample_quality_note,
            "",
            "## Strategy Boundary",
            "",
            review.strategy_boundary_note,
            "",
            "## Focus Points",
            "",
            *[f"- {point}" for point in review.focus_points],
            "",
            "## Next Action",
            "",
            review.next_action,
            "",
            "## Recent Records",
            "",
        ]
        if records:
            lines.extend(
                [
                    "| Archive | Symbol | Outcome | Realized P/L | Realized P/L % | Next Action |",
                    "| --- | --- | --- | ---: | ---: | --- |",
                ]
            )
            for record in records:
                lines.append(
                    "| "
                    f"{self._table_cell(record.archive_id)} | "
                    f"{self._table_cell(record.symbol)} | "
                    f"{self._table_cell(record.outcome)} | "
                    f"{record.realized_pnl:.2f} | "
                    f"{record.realized_pnl_pct:.2%} | "
                    f"{self._table_cell(record.next_action)} |"
                )
        else:
            lines.append("No completed archive records yet.")
        lines.append("")
        return "\n".join(lines)

    def _table_cell(self, value: object) -> str:
        return str(value).replace("\n", " ").replace("|", r"\|")
