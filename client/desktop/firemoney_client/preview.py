"""Generate a local preview of the one-to-two FireMoney interface."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .adapter import LocalMainChainAdapter
from .renderer import render_one_to_two_workflow_html
from server.firemoney_server import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar


PREVIEW_TRADE_DATE = "2026-04-30"


def build_preview(output_path: str | Path) -> Path:
    """Write the current one-to-two workflow interface to an HTML file."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        preview_root = Path(temp_dir)
        paper_store = PaperTradeStore(preview_root / "paper_trades.json")
        service = MainChainService(
            paper_store=paper_store,
            market_data_provider=SampleMarketDataProvider(),
            trading_calendar=WeekdayTradingCalendar(),
        )
        adapter = LocalMainChainAdapter(service)
        one_to_two_report = adapter.build_one_to_two_morning_report(
            trade_date=PREVIEW_TRADE_DATE,
            notify=False,
        )
        adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="scan",
            notify=False,
        )
        adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="auction",
            notify=False,
        )
        one_to_two_watch_report = adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="open",
            notify=False,
        )
        one_to_two_eod_review = adapter.build_one_to_two_end_of_day_review(
            trade_date=PREVIEW_TRADE_DATE,
            notify=False,
        )
        one_to_two_stability_report = adapter.build_one_to_two_stability_report()
        schedule_run = OneToTwoScheduler(
            service=service,
            state_store=SchedulerStateStore(preview_root / "scheduler_state.json"),
        ).run_due(
            trade_date=PREVIEW_TRADE_DATE,
            at_time="09:31",
            notify=False,
        )
        target.write_text(
            render_one_to_two_workflow_html(
                report=one_to_two_report,
                watch_report=one_to_two_watch_report,
                eod_review=one_to_two_eod_review,
                stability_report=one_to_two_stability_report,
                schedule_run=schedule_run,
            ),
            encoding="utf-8",
        )
    return target


if __name__ == "__main__":
    build_preview(Path("client") / "desktop" / "preview" / "core_workflow.html")
