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
    expires_at: str | None = None


DEFAULT_ONE_TO_TWO_SCHEDULE: tuple[ScheduledOneToTwoJob, ...] = (
    ScheduledOneToTwoJob(
        "strategy-decision",
        "strategy-decision",
        "08:45",
        expires_at="09:31",
    ),
    ScheduledOneToTwoJob("morning", "morning", "08:50", expires_at="09:31"),
    ScheduledOneToTwoJob("paper-decision", "paper-decision", "09:00", expires_at="09:31"),
    ScheduledOneToTwoJob("watch-scan", "watch", "09:20", "scan", "09:31"),
    ScheduledOneToTwoJob("watch-auction", "watch", "09:25", "auction", "09:31"),
    ScheduledOneToTwoJob("watch-open", "watch", "09:31", "open", "09:45"),
    ScheduledOneToTwoJob("watch-risk-1000", "watch", "10:00", "risk", "10:59"),
    ScheduledOneToTwoJob("watch-risk-1100", "watch", "11:00", "risk", "11:30"),
    ScheduledOneToTwoJob("watch-risk-1400", "watch", "14:00", "risk", "14:49"),
    ScheduledOneToTwoJob("watch-risk-1450", "watch", "14:50", "risk", "15:00"),
    ScheduledOneToTwoJob("eod", "eod", "15:10", expires_at="16:00"),
    ScheduledOneToTwoJob(
        "board-shadow-record",
        "board-shadow-record",
        "15:20",
        "shadow",
        "16:00",
    ),
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
        market_data_timeout_seconds: float | None = None,
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
                if _requires_sent_notification(job, notify) and not _is_expired(
                    job,
                    requested_time,
                ):
                    latest_notification = self._latest_notification_status(
                        job.mode,
                        trade_context.trade_date,
                    )
                    if latest_notification != NotificationStatus.SENT:
                        task_results.append(
                            _task_contract(
                                job,
                                status="retrying",
                                message=(
                                    "required notification was previously marked done "
                                    "without sent confirmation; retrying inside window"
                                ),
                                notification_status=(
                                    latest_notification
                                    or NotificationStatus.PREPARED
                                ),
                            )
                        )
                    else:
                        skipped_count += 1
                        task_results.append(
                            _task_contract(job, status="skipped", message="already completed")
                        )
                        continue
                else:
                    skipped_count += 1
                    task_results.append(
                        _task_contract(job, status="skipped", message="already completed")
                    )
                    continue
            if task_results and task_results[-1].task_id == job.task_id and task_results[-1].status == "retrying":
                task_results.pop()
            elif self._state_store.is_done(task_key):
                skipped_count += 1
                task_results.append(
                    _task_contract(job, status="skipped", message="already completed")
                )
                continue
            if _is_expired(job, requested_time):
                self._state_store.mark_done(task_key)
                skipped_count += 1
                task_results.append(
                    _task_contract(
                        job,
                        status="expired",
                        message="missed execution window; not backfilled",
                    )
                )
                continue
            try:
                result = self._run_job(
                    job,
                    trade_context.trade_date,
                    notify,
                    market_data_timeout_seconds,
                )
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
            notification_status = getattr(
                getattr(result, "notification", None),
                "status",
                NotificationStatus.PREPARED,
            )
            notification_ready = (
                not _requires_sent_notification(job, notify)
                or notification_status == NotificationStatus.SENT
            )
            if notification_status != NotificationStatus.FAILED and notification_ready:
                self._state_store.mark_done(task_key)
            executed_count += 1
            task_results.append(
                _task_contract(
                    job,
                    status="completed",
                    message=getattr(result, "next_action", "completed"),
                    notification_status=notification_status,
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

    def _run_job(
        self,
        job: ScheduledOneToTwoJob,
        trade_date: str,
        notify: bool,
        market_data_timeout_seconds: float | None,
    ):
        if job.mode == "strategy-decision":
            return self._service.build_strategy_decision_report(
                trade_date=trade_date,
            )
        if job.mode == "paper-decision":
            return self._service.build_paper_trading_decision_report(
                trade_date=trade_date,
                notify=False,
                market_data_timeout_seconds=(
                    market_data_timeout_seconds
                    if market_data_timeout_seconds is not None
                    else 8.0
                ),
            )
        if job.mode == "morning":
            return self._service.build_one_to_two_morning_report(
                trade_date=trade_date,
                notify=notify,
                market_data_timeout_seconds=market_data_timeout_seconds,
            )
        if job.mode == "watch":
            return self._service.run_one_to_two_watch(
                trade_date=trade_date,
                phase=job.phase or "scan",
                notify=notify,
                market_data_timeout_seconds=market_data_timeout_seconds,
            )
        if job.mode == "eod":
            return self._service.build_one_to_two_end_of_day_review(
                trade_date=trade_date,
                notify=notify,
                market_data_timeout_seconds=market_data_timeout_seconds,
            )
        if job.mode == "board-shadow-record":
            return self._service.run_scheduled_limit_up_board_shadow_record(
                trade_date=trade_date,
                notify=False,
            )
        raise ValueError(f"unsupported scheduler mode: {job.mode}")

    def _latest_notification_status(
        self,
        workflow: str,
        trade_date: str,
    ) -> NotificationStatus | None:
        records = self._service.load_notification_records(
            workflow=workflow,
            limit=20,
        )
        for record in records:
            if record.trade_date == trade_date:
                return record.status
        return None


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


def _requires_sent_notification(job: ScheduledOneToTwoJob, notify: bool) -> bool:
    if not notify:
        return False
    return job.mode in {"morning", "eod"}


def _is_expired(job: ScheduledOneToTwoJob, requested_time: str) -> bool:
    return bool(job.expires_at and requested_time > job.expires_at)


def _normalize_time(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%H:%M")
    return parsed.strftime("%H:%M")
