"""Generate a local preview of the one-to-two FireMoney interface."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .adapter import LocalMainChainAdapter
from .renderer import render_one_to_two_workflow_html
from server.firemoney_server import MainChainService
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider


def build_preview(output_path: str | Path) -> Path:
    """Write the current one-to-two workflow interface to an HTML file."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        preview_root = Path(temp_dir)
        paper_store = PaperTradeStore(preview_root / "paper_trades.json")
        adapter = LocalMainChainAdapter(
            MainChainService(
                paper_store=paper_store,
                market_data_provider=SampleMarketDataProvider(),
            )
        )
        one_to_two_report = adapter.build_one_to_two_morning_report(notify=False)
        adapter.run_one_to_two_watch(phase="scan", notify=False)
        adapter.run_one_to_two_watch(phase="auction", notify=False)
        one_to_two_watch_report = adapter.run_one_to_two_watch(
            phase="open",
            notify=False,
        )
        one_to_two_eod_review = adapter.build_one_to_two_end_of_day_review(notify=False)
        one_to_two_stability_report = adapter.build_one_to_two_stability_report()
        target.write_text(
            render_one_to_two_workflow_html(
                report=one_to_two_report,
                watch_report=one_to_two_watch_report,
                eod_review=one_to_two_eod_review,
                stability_report=one_to_two_stability_report,
            ),
            encoding="utf-8",
        )
    return target


if __name__ == "__main__":
    build_preview(Path("client") / "desktop" / "preview" / "core_workflow.html")
