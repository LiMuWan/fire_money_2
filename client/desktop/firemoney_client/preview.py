"""Generate a local preview of the one-to-two FireMoney interface."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory

from .preview_data import build_preview_workflow_data
from .renderer import render_one_to_two_workflow_html


def build_preview(output_path: str | Path) -> Path:
    """Write the current one-to-two workflow interface to an HTML file."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        data = build_preview_workflow_data(Path(temp_dir))
        _atomic_write_text(
            target,
            render_one_to_two_workflow_html(
                report=data.report,
                watch_report=data.watch_report,
                eod_review=data.eod_review,
                stability_report=data.stability_report,
                board_shadow_system_report=data.board_shadow_system_report,
                paper_backtest_report=data.paper_backtest_report,
                strategy_decision_report=data.strategy_decision_report,
                paper_decision_report=data.paper_decision_report,
                paper_database_report=data.paper_database_report,
                doctor_report=data.doctor_report,
                schedule_run=data.schedule_run,
                schedule_health_report=data.schedule_health_report,
                notification_records=data.notification_records,
                backtest_audit=data.backtest_audit,
                commercial_readiness_report=data.commercial_readiness_report,
            )
        )
    return target


def _atomic_write_text(target: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, target)


if __name__ == "__main__":
    build_preview(Path("client") / "desktop" / "preview" / "core_workflow.html")
