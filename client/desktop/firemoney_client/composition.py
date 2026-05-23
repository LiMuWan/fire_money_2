"""Local composition root for FireMoney desktop tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.firemoney_server import MainChainService
from server.firemoney_server.infrastructure.board_shadow_store import (
    LimitUpBoardShadowStore,
)
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    SampleMarketDataProvider,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore

from .adapter import LocalMainChainAdapter

SAMPLE_STATE_ROOT = Path(".firemoney") / "sample"


@dataclass(frozen=True)
class LocalMainChainContext:
    service: MainChainService
    adapter: LocalMainChainAdapter
    scheduler_state_store: SchedulerStateStore
    scheduler_run_store: SchedulerRunStore


def build_local_main_chain_context(
    *,
    sample_data: bool = False,
    paper_store_path: str | Path | None = None,
    paper_database_path: str | Path | None = None,
    notification_store_path: str | Path | None = None,
    scheduler_state_path: str | Path | None = None,
    scheduler_runs_path: str | Path | None = None,
    board_shadow_store_path: str | Path | None = None,
    market_data_provider: Any | None = None,
    paper_store: PaperTradeStore | None = None,
    notification_store: NotificationRecordStore | None = None,
    scheduler_state_store: SchedulerStateStore | None = None,
    scheduler_run_store: SchedulerRunStore | None = None,
    board_shadow_store: LimitUpBoardShadowStore | None = None,
    trading_calendar: Any | None = None,
) -> LocalMainChainContext:
    """Build the local service/adapter graph used by CLI and preview tools."""

    provider = market_data_provider
    if provider is None:
        provider = SampleMarketDataProvider() if sample_data else AkshareMarketDataProvider()
    if sample_data:
        paper_store_path = paper_store_path or SAMPLE_STATE_ROOT / "paper_trades.json"
        paper_database_path = paper_database_path or Path(paper_store_path).with_suffix(
            ".sqlite3"
        )
        notification_store_path = (
            notification_store_path or SAMPLE_STATE_ROOT / "notifications.json"
        )
        scheduler_state_path = scheduler_state_path or SAMPLE_STATE_ROOT / "scheduler_state.json"
        scheduler_runs_path = scheduler_runs_path or SAMPLE_STATE_ROOT / "scheduler_runs.json"
        board_shadow_store_path = (
            board_shadow_store_path or SAMPLE_STATE_ROOT / "board_shadow_records.json"
        )
    resolved_paper_store = paper_store
    if resolved_paper_store is None and (paper_store_path or paper_database_path):
        resolved_paper_store = PaperTradeStore(
            paper_store_path or PaperTradeStore().path,
            database_path=paper_database_path,
        )
    resolved_notification_store = notification_store
    if resolved_notification_store is None and notification_store_path:
        resolved_notification_store = NotificationRecordStore(notification_store_path)
    resolved_scheduler_run_store = scheduler_run_store or (
        SchedulerRunStore(scheduler_runs_path)
        if scheduler_runs_path
        else SchedulerRunStore()
    )
    resolved_scheduler_state_store = scheduler_state_store or (
        SchedulerStateStore(scheduler_state_path)
        if scheduler_state_path
        else SchedulerStateStore()
    )
    resolved_board_shadow_store = board_shadow_store
    if resolved_board_shadow_store is None and board_shadow_store_path:
        resolved_board_shadow_store = LimitUpBoardShadowStore(board_shadow_store_path)
    service = MainChainService(
        market_data_provider=provider,
        paper_store=resolved_paper_store,
        notification_store=resolved_notification_store,
        scheduler_state_store=resolved_scheduler_state_store,
        scheduler_run_store=resolved_scheduler_run_store,
        board_shadow_store=resolved_board_shadow_store,
        trading_calendar=trading_calendar,
    )
    return LocalMainChainContext(
        service=service,
        adapter=LocalMainChainAdapter(service),
        scheduler_state_store=resolved_scheduler_state_store,
        scheduler_run_store=resolved_scheduler_run_store,
    )


__all__ = ["LocalMainChainContext", "build_local_main_chain_context"]
