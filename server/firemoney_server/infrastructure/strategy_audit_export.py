"""Markdown export for local strategy-boundary change audits."""

from __future__ import annotations

from pathlib import Path

from shared.contracts import StrategyChangeRecord, StrategyConfig


DEFAULT_STRATEGY_EXPORT_DIR = Path("exports") / "strategy"


class MarkdownStrategyAuditExporter:
    """Writes recent strategy-boundary changes for review before rollback."""

    def __init__(self, export_dir: str | Path = DEFAULT_STRATEGY_EXPORT_DIR) -> None:
        self._export_dir = Path(export_dir)

    def export(
        self,
        strategy_config: StrategyConfig,
        target_path: str | Path | None = None,
    ) -> Path:
        target = (
            Path(target_path)
            if target_path
            else self._export_dir / "strategy_boundary_audit.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_markdown(strategy_config), encoding="utf-8")
        return target

    def _render_markdown(self, strategy_config: StrategyConfig) -> str:
        lines = [
            "# Strategy Boundary Audit",
            "",
            f"- Strategy ID: {strategy_config.strategy_id}",
            f"- Version: {strategy_config.version}",
            f"- Source: {strategy_config.source}",
            f"- Adjustment status: {strategy_config.adjustment_status.value}",
            "",
            "## Impact",
            "",
            strategy_config.impact_summary,
            "",
            "## Recent Changes",
            "",
        ]
        if strategy_config.recent_changes:
            lines.extend(
                [
                    "| Record | Action | Version | Reason | Changes | Created At |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            lines.extend(
                self._render_record(record)
                for record in strategy_config.recent_changes
            )
        else:
            lines.append("No local strategy-boundary changes recorded yet.")
        lines.append("")
        return "\n".join(lines)

    def _render_record(self, record: StrategyChangeRecord) -> str:
        return (
            "| "
            f"{self._table_cell(record.record_id)} | "
            f"{self._table_cell(record.action)} | "
            f"{self._table_cell(record.from_version)} -> {self._table_cell(record.to_version)} | "
            f"{self._table_cell(record.reason)} | "
            f"{self._table_cell('; '.join(record.changes))} | "
            f"{self._table_cell(record.created_at)} |"
        )

    def _table_cell(self, value: object) -> str:
        return str(value).replace("\n", " ").replace("|", r"\|")
