"""Markdown export for local strategy-boundary change audits."""

from __future__ import annotations

from pathlib import Path

from shared.contracts import StrategyChangeRecord, StrategyConfig


DEFAULT_STRATEGY_EXPORT_DIR = Path("exports") / "strategy"


class MarkdownStrategyAuditExporter:
    """Writes recent strategy-boundary changes for review before rollback."""

    def __init__(self, export_dir: str | Path = DEFAULT_STRATEGY_EXPORT_DIR) -> None:
        self._export_dir = Path(export_dir)

    @property
    def export_dir(self) -> Path:
        return self._export_dir

    def export(
        self,
        strategy_config: StrategyConfig,
        target_path: str | Path | None = None,
        actions: tuple[str, ...] | None = None,
    ) -> Path:
        action_filter = self._normalize_actions(actions)
        target = (
            Path(target_path)
            if target_path
            else self._default_target(action_filter)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            self._render_markdown(strategy_config, action_filter),
            encoding="utf-8",
        )
        return target

    def _default_target(self, action_filter: tuple[str, ...]) -> Path:
        if not action_filter:
            return self._export_dir / "strategy_boundary_audit.md"
        suffix = "_".join(self._filename_token(action) for action in action_filter)
        return self._export_dir / f"strategy_boundary_audit_{suffix}.md"

    def _render_markdown(
        self,
        strategy_config: StrategyConfig,
        action_filter: tuple[str, ...],
    ) -> str:
        records = self._matching_records(strategy_config, action_filter)
        lines = [
            "# Strategy Boundary Audit",
            "",
            f"- Strategy ID: {strategy_config.strategy_id}",
            f"- Version: {strategy_config.version}",
            f"- Source: {strategy_config.source}",
            f"- Adjustment status: {strategy_config.adjustment_status.value}",
            f"- Action filter: {', '.join(action_filter) if action_filter else 'all'}",
            "",
            "## Impact",
            "",
            strategy_config.impact_summary,
            "",
            "## Recent Changes",
            "",
        ]
        if records:
            lines.extend(
                [
                    "| Record | Action | Version | Reason | Changes | Created At |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            lines.extend(self._render_record(record) for record in records)
        elif action_filter:
            lines.append("No strategy-boundary changes matched the selected audit filter.")
        else:
            lines.append("No local strategy-boundary changes recorded yet.")
        lines.append("")
        return "\n".join(lines)

    def _normalize_actions(self, actions: tuple[str, ...] | None) -> tuple[str, ...]:
        if not actions:
            return ()
        normalized: list[str] = []
        for action in actions:
            value = str(action).strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    def _matching_records(
        self,
        strategy_config: StrategyConfig,
        action_filter: tuple[str, ...],
    ) -> tuple[StrategyChangeRecord, ...]:
        if not action_filter:
            return strategy_config.recent_changes
        return tuple(
            record
            for record in strategy_config.recent_changes
            if record.action.lower() in action_filter
        )

    def _filename_token(self, action: str) -> str:
        token = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in action
        ).strip("_")
        return token or "action"

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
