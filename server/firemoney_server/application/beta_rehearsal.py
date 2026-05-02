"""Isolated Beta rehearsal for the FireMoney core workflow."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from server.firemoney_server.application.main_chain import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import (
    DEFAULT_ONE_TO_TWO_SCHEDULE,
    OneToTwoScheduler,
)
from server.firemoney_server.infrastructure.market_data import (
    MarketDataProvider,
    SampleMarketDataProvider,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
    load_one_to_two_settings,
)
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import (
    TradingCalendar,
    WeekdayTradingCalendar,
)
from shared.contracts import OneToTwoBetaRehearsalReport


REHEARSAL_TIMES: tuple[str, ...] = (
    "08:50",
    "09:20",
    "09:25",
    "09:31",
    "10:00",
    "11:00",
    "14:00",
    "14:50",
    "15:10",
)


def run_one_to_two_beta_rehearsal(
    trade_date: str | None = None,
    one_to_two_settings: OneToTwoStrategySettings | None = None,
    market_data_provider: MarketDataProvider | None = None,
    trading_calendar: TradingCalendar | None = None,
) -> OneToTwoBetaRehearsalReport:
    """Run a full isolated sample-day rehearsal without touching live local state."""

    settings = one_to_two_settings or load_one_to_two_settings()
    provider = market_data_provider or SampleMarketDataProvider()
    calendar = trading_calendar or WeekdayTradingCalendar()
    requested_context = calendar.resolve(trade_date)

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        paper_store = PaperTradeStore(
            root / "paper_trades.json",
            initial_cash=settings.initial_cash,
            max_position_pct=settings.max_position_pct,
            max_daily_trades=settings.max_daily_trades,
        )
        notification_store = NotificationRecordStore(root / "notifications.json")
        scheduler_state_store = SchedulerStateStore(root / "scheduler_state.json")
        scheduler_run_store = SchedulerRunStore(root / "scheduler_runs.json")
        service = MainChainService(
            one_to_two_settings=settings,
            market_data_provider=provider,
            paper_store=paper_store,
            notification_store=notification_store,
            scheduler_state_store=scheduler_state_store,
            scheduler_run_store=scheduler_run_store,
            trading_calendar=calendar,
        )
        doctor_report = service.build_one_to_two_doctor_report(
            trade_date=requested_context.trade_date,
            beta=False,
        )
        scheduler = OneToTwoScheduler(
            service=service,
            state_store=scheduler_state_store,
        )
        schedule_runs = []
        for at_time in REHEARSAL_TIMES:
            run = scheduler.run_due(
                trade_date=requested_context.trade_date,
                at_time=at_time,
                notify=False,
            )
            scheduler_run_store.append(run)
            schedule_runs.append(run)

        account = paper_store.load()
        stability_report = service.build_one_to_two_stability_report()
        notification_records = notification_store.load()
        executed_count = sum(run.executed_count for run in schedule_runs)
        failed_count = sum(
            1
            for run in schedule_runs
            for task in run.tasks
            if task.status == "failed"
        )
        blocked_checks = tuple(
            check for check in doctor_report.checks if check.status == "blocked"
        )
        expected_count = len(DEFAULT_ONE_TO_TWO_SCHEDULE)
        status = (
            "ready"
            if not blocked_checks
            and failed_count == 0
            and executed_count == expected_count
            else "blocked"
        )
        summary = (
            f"Beta 彩排通过：隔离账本跑完 {expected_count} 个调度任务，"
            f"生成 {len(account.events)} 条模拟盘事件和 "
            f"{len(notification_records)} 条通知记录。"
            if status == "ready"
            else "Beta 彩排未通过：请先查看 doctor_report 和 schedule_runs 中的 blocked/failed 项。"
        )
        return OneToTwoBetaRehearsalReport(
            report_id=f"one-to-two-beta-rehearsal-{requested_context.trade_date}",
            trade_date=requested_context.trade_date,
            status=status,
            summary=summary,
            doctor_report=doctor_report,
            schedule_runs=tuple(schedule_runs),
            stability_report=stability_report,
            notification_record_count=len(notification_records),
            paper_event_count=len(account.events),
            open_position_count=len(account.positions),
            closed_sample_count=len(account.closed_trades),
            next_action=(
                "真实交易日先运行 beta-check 验证飞书 sent，再运行 beta-start --loop 值守。"
                if status == "ready"
                else "修复彩排阻断项后重新运行 beta-rehearsal。"
            ),
        )
