"""Local scheduler for the one-to-two validation loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from server.firemoney_server.application.main_chain import MainChainService
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from shared.contracts import (
    NotificationStatus,
    OneToTwoScheduleRun,
    OneToTwoScheduleTask,
)


@dataclass(frozen=True)
class ScheduledOneToTwoJob:
    task_id: str
    mode: str
    scheduled_time: str
    phase: str | None = None


DEFAULT_ONE_TO_TWO_SCHEDULE: tuple[ScheduledOneToTwoJob, ...] = (
    ScheduledOneToTwoJob("morning", "morning", "08:50"),
    ScheduledOneToTwoJob("watch-scan", "watch", "09:20", "scan"),
    ScheduledOneToTwoJob("watch-auction", "watch", "09:25", "auction"),
    ScheduledOneToTwoJob("watch-open", "watch", "09:31", "open"),
    ScheduledOneToTwoJob("watch-risk-1000", "watch", "10:00", "risk"),
    ScheduledOneToTwoJob("watch-risk-1100", "watch", "11:00", "risk"),
    ScheduledOneToTwoJob("watch-risk-1400", "watch", "14:00", "risk"),
    ScheduledOneToTwoJob("watch-risk-1450", "watch", "14:50", "risk"),
    ScheduledOneToTwoJob("eod", "eod", "15:10"),
)


class OneToTwoScheduler:
    """Runs due one-to-two jobs once per trading day and task id."""

    def __init__(
        self,
        service: MainChainService | None = None,
        state_store: SchedulerStateStore | None = None,
        schedule: tuple[ScheduledOneToTwoJob, ...] = DEFAULT_ONE_TO_TWO_SCHEDULE,
    ) -> None:
        self._service = service or MainChainService()
        self._state_store = state_store or SchedulerStateStore()
        self._schedule = schedule

    def run_due(
        self,
        trade_date: str | None = None,
        at_time: str | None = None,
        notify: bool = True,
    ) -> OneToTwoScheduleRun:
        requested_time = _normalize_time(at_time or datetime.now().strftime("%H:%M"))
        trade_context = self._service.resolve_trading_day(trade_date)
        if not trade_context.is_trading_day:
            return OneToTwoScheduleRun(
                run_id=f"one-to-two-schedule-{trade_context.requested_date}-{requested_time}",
                trade_date=trade_context.trade_date,
                trade_context=trade_context,
                requested_time=requested_time,
                due_count=0,
                executed_count=0,
                skipped_count=0,
                tasks=tuple(
                    _task_contract(
                        job,
                        status="closed",
                        message="requested date is not a trading day",
                    )
                    for job in self._schedule
                ),
                next_action="Non-trading day; scheduler did not run one-to-two jobs.",
            )

        due_count = 0
        executed_count = 0
        skipped_count = 0
        task_results: list[OneToTwoScheduleTask] = []
        for job in self._schedule:
            if job.scheduled_time > requested_time:
                task_results.append(
                    _task_contract(job, status="pending", message="waiting for schedule")
                )
                continue
            due_count += 1
            task_key = f"{trade_context.trade_date}:{job.task_id}"
            if self._state_store.is_done(task_key):
                skipped_count += 1
                task_results.append(
                    _task_contract(job, status="skipped", message="already completed")
                )
                continue
            try:
                result = self._run_job(job, trade_context.trade_date, notify)
            except Exception as exc:
                task_results.append(
                    _task_contract(
                        job,
                        status="failed",
                        message=str(exc),
                        notification_status=NotificationStatus.FAILED,
                    )
                )
                continue
            self._state_store.mark_done(task_key)
            executed_count += 1
            task_results.append(
                _task_contract(
                    job,
                    status="completed",
                    message=getattr(result, "next_action", "completed"),
                    notification_status=result.notification.status,
                )
            )

        return OneToTwoScheduleRun(
            run_id=f"one-to-two-schedule-{trade_context.trade_date}-{requested_time}",
            trade_date=trade_context.trade_date,
            trade_context=trade_context,
            requested_time=requested_time,
            due_count=due_count,
            executed_count=executed_count,
            skipped_count=skipped_count,
            tasks=tuple(task_results),
            next_action=_next_action(executed_count, skipped_count, due_count),
        )

    def _run_job(self, job: ScheduledOneToTwoJob, trade_date: str, notify: bool):
        if job.mode == "morning":
            return self._service.build_one_to_two_morning_report(
                trade_date=trade_date,
                notify=notify,
            )
        if job.mode == "watch":
            return self._service.run_one_to_two_watch(
                trade_date=trade_date,
                phase=job.phase or "scan",
                notify=notify,
            )
        if job.mode == "eod":
            return self._service.build_one_to_two_end_of_day_review(
                trade_date=trade_date,
                notify=notify,
            )
        raise ValueError(f"unsupported scheduler mode: {job.mode}")


def _task_contract(
    job: ScheduledOneToTwoJob,
    status: str,
    message: str,
    notification_status: NotificationStatus = NotificationStatus.PREPARED,
) -> OneToTwoScheduleTask:
    return OneToTwoScheduleTask(
        task_id=job.task_id,
        mode=job.mode,
        phase=job.phase,
        scheduled_time=job.scheduled_time,
        status=status,
        message=message,
        notification_status=notification_status,
    )


def _next_action(executed_count: int, skipped_count: int, due_count: int) -> str:
    if executed_count:
        return "Scheduler executed due one-to-two jobs; keep loop running for later phases."
    if skipped_count and skipped_count == due_count:
        return "All due one-to-two jobs were already completed for this trading day."
    return "No one-to-two jobs are due yet."


def _normalize_time(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%H:%M")
    return parsed.strftime("%H:%M")
