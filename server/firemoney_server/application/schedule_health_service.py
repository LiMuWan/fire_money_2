"""Read-only diagnostics for scheduler coverage and required notifications."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from shared.contracts import (
    NotificationRecord,
    OneToTwoScheduleHealthItem,
    OneToTwoScheduleHealthReport,
    TradingDayContext,
)


class TradingCalendarLike(Protocol):
    def resolve(self, trade_date: str | None = None) -> object:
        """Resolve requested date into a trading-day context-like object."""


class NotificationStoreLike(Protocol):
    def load(self) -> tuple[NotificationRecord, ...]:
        """Load persisted notification records."""


class SchedulerRunStoreLike(Protocol):
    def load(self, limit: int | None = None) -> tuple[dict, ...]:
        """Load persisted scheduler run records."""


_NOTIFICATION_STATUS_ORDER = {
    "disabled": 0,
    "prepared": 1,
    "failed": 2,
    "sent": 3,
}


class ScheduleHealthService:
    """Explains whether morning/eod should have sent and why they did not."""

    REQUIRED_WORKFLOWS = (
        ("morning", "早评", "08:50"),
        ("paper-decision", "模拟盘指挥单", "09:00"),
        ("watch:open", "开盘确认", "09:31"),
        ("eod", "晚评", "15:10"),
    )

    def __init__(
        self,
        *,
        trading_calendar: TradingCalendarLike,
        notification_store: NotificationStoreLike,
        scheduler_run_store: SchedulerRunStoreLike,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._trading_calendar = trading_calendar
        self._notification_store = notification_store
        self._scheduler_run_store = scheduler_run_store
        self._now_provider = now_provider or datetime.now

    def build_report(self, trade_date: str | None = None) -> OneToTwoScheduleHealthReport:
        context = self._trading_calendar.resolve(trade_date).to_contract()
        notifications = self._notification_store.load()
        runs = self._scheduler_run_store.load()
        items = tuple(
            self._health_item(
                trade_context=context,
                workflow=workflow,
                label=label,
                scheduled_time=scheduled_time,
                notifications=notifications,
                runs=runs,
            )
            for workflow, label, scheduled_time in self.REQUIRED_WORKFLOWS
        )
        blocked = tuple(item for item in items if item.status == "blocked")
        warning = tuple(item for item in items if item.status == "warning")
        status = "blocked" if blocked else "warning" if warning else "ready"
        summary = self._summary(context, status, blocked, warning)
        return OneToTwoScheduleHealthReport(
            report_id=f"schedule-health-{context.requested_date}",
            requested_date=context.requested_date,
            trade_date=context.trade_date,
            is_trading_day=context.is_trading_day,
            status=status,
            summary=summary,
            checked_at=self._now_provider().strftime("%Y-%m-%d %H:%M:%S"),
            items=items,
            scheduler_run_count=len(runs),
            notification_record_count=len(notifications),
            next_action=self._next_action(context, status),
        )

    def _health_item(
        self,
        *,
        trade_context: TradingDayContext,
        workflow: str,
        label: str,
        scheduled_time: str,
        notifications: tuple[NotificationRecord, ...],
        runs: tuple[dict, ...],
    ) -> OneToTwoScheduleHealthItem:
        if not trade_context.is_trading_day:
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status="closed",
                notification_status="not_required",
                status="ready",
                summary=f"{label}：{trade_context.requested_date} 非交易日，不需要发送。",
                next_action="非交易日不用补发，下一交易日再检查 schedule-health。",
            )
        notification = self._latest_notification(
            notifications,
            workflow=workflow,
            trade_date=trade_context.trade_date,
        )
        schedule_status = self._latest_task_status(
            runs,
            workflow=workflow,
            trade_date=trade_context.trade_date,
        )
        if workflow == "paper-decision" and schedule_status in {"completed", "skipped"}:
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status=schedule_status,
                notification_status=notification.status.value if notification else "not_required",
                status="ready",
                summary=f"{label}：调度已完成，指挥单已生成或已按纪律空仓。",
                next_action="继续检查 09:31 开盘确认是否执行。",
            )
        if workflow == "watch:open" and schedule_status in {"completed", "skipped"}:
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status=schedule_status,
                notification_status=notification.status.value if notification else "not_required",
                status="ready",
                summary=f"{label}：open 阶段已执行，已覆盖开盘确认窗口。",
                next_action="若回测有机会但未买入，继续用 missed-opportunities 对齐候选映射和守门原因。",
            )
        if workflow in {"paper-decision", "watch:open"} and self._is_before_scheduled_time(
            trade_context,
            scheduled_time,
        ):
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status=schedule_status,
                notification_status="pending",
                status="ready",
                summary=f"{label}：尚未到 {scheduled_time} 执行时间，等待值守触发。",
                next_action="保持 beta-start 或 schedule 常驻。",
            )
        if workflow in {"paper-decision", "watch:open"} and schedule_status == "not_seen":
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status=schedule_status,
                notification_status="not_required",
                status="blocked",
                summary=f"{label}：没有调度审计记录，关键值守链路未覆盖。",
                next_action="启动 beta-start 或 schedule --loop，确保 09:00 指挥单和 09:31 open 阶段被执行。",
            )
        if workflow in {"paper-decision", "watch:open"}:
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=False,
                schedule_status=schedule_status,
                notification_status=notification.status.value if notification else "not_required",
                status="blocked" if schedule_status in {"failed", "expired"} else "warning",
                summary=f"{label}：调度状态 {schedule_status}，未确认完成。",
                next_action="先修复常驻值守，再复核 missed-opportunities 是否仍有错失机会。",
            )
        if notification and notification.status.value == "sent":
            if self._is_market_data_unavailable_notification(notification):
                return OneToTwoScheduleHealthItem(
                    task_id=workflow,
                    workflow=workflow,
                    scheduled_time=scheduled_time,
                    required_notification=True,
                    schedule_status=schedule_status,
                    notification_status="sent_data_unavailable",
                    status="blocked",
                    summary=f"{label}：飞书已发送，但内容是行情异常暂停，不代表覆盖正常。",
                    next_action="先修复行情源超时，再运行 doctor --market-data-timeout-seconds 20 复核。",
                )
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=True,
                schedule_status=schedule_status,
                notification_status="sent",
                status="ready",
                summary=f"{label}：已发送飞书，调度状态 {schedule_status}。",
                next_action="保持 beta-start 或 schedule 常驻，继续检查后续阶段。",
            )
        if notification:
            if notification.status.value == "prepared":
                after_window = not self._is_before_scheduled_time(trade_context, scheduled_time)
                return OneToTwoScheduleHealthItem(
                    task_id=workflow,
                    workflow=workflow,
                    scheduled_time=scheduled_time,
                    required_notification=True,
                    schedule_status=schedule_status,
                    notification_status=notification.status.value,
                    status="blocked" if after_window else "warning",
                    summary=f"{label}：已有记录但只生成未发送，未确认飞书 sent。",
                    next_action=(
                        "使用 beta-start 或 schedule 且不要带 --no-notify；先运行 feishu-test/beta-check 确认 sent，再重启常驻值守。"
                    ),
                )
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=True,
                schedule_status=schedule_status,
                notification_status=notification.status.value,
                status="blocked" if notification.status.value == "failed" else "warning",
                summary=f"{label}：已有记录但状态为 {notification.status.value}，未确认 sent。",
                next_action="先检查飞书 webhook/app 配置，再运行 beta-check 或对应 schedule 窗口。",
            )
        if schedule_status in {"completed", "skipped"}:
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=True,
                schedule_status=schedule_status,
                notification_status="missing",
                status="blocked",
                summary=f"{label}：调度显示 {schedule_status}，但没有飞书通知记录。",
                next_action="检查通知归档和发送配置，必要时运行 feishu-test 后重启 beta-start。",
            )
        if schedule_status == "expired":
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=True,
                schedule_status=schedule_status,
                notification_status="missing",
                status="blocked",
                summary=f"{label}：执行窗口已过期，系统按纪律没有补发。",
                next_action="确认 beta-start 是否开机常驻；不要盘后补发早评，下一交易日前修复自启动。",
            )
        if self._is_before_scheduled_time(trade_context, scheduled_time):
            return OneToTwoScheduleHealthItem(
                task_id=workflow,
                workflow=workflow,
                scheduled_time=scheduled_time,
                required_notification=True,
                schedule_status=schedule_status,
                notification_status="pending",
                status="ready",
                summary=f"{label}：尚未到 {scheduled_time} 执行时间，当前等待值守触发。",
                next_action="保持 beta-start 或 schedule 常驻，到点后再检查 sent 记录。",
            )
        return OneToTwoScheduleHealthItem(
            task_id=workflow,
            workflow=workflow,
            scheduled_time=scheduled_time,
            required_notification=True,
            schedule_status=schedule_status,
            notification_status="missing",
            status="warning",
            summary=f"{label}：还没有 sent 记录，调度状态 {schedule_status}。",
            next_action="若已到执行时间，确认 beta-start/schedule 是否正在运行。",
        )

    @staticmethod
    def _latest_notification(
        notifications: tuple[NotificationRecord, ...],
        *,
        workflow: str,
        trade_date: str,
    ) -> NotificationRecord | None:
        matches = tuple(
            item
            for item in notifications
            if item.workflow == workflow and item.trade_date == trade_date
        )
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                item.created_at,
                _NOTIFICATION_STATUS_ORDER.get(item.status.value, -1),
                item.record_id,
            ),
        )

    @staticmethod
    def _latest_task_status(
        runs: tuple[dict, ...],
        *,
        workflow: str,
        trade_date: str,
    ) -> str:
        completed_key: tuple[str, str] | None = None
        latest_not_skipped_status = "not_seen"
        latest_not_skipped_key: tuple[str, str] | None = None
        latest_status = "not_seen"
        latest_key: tuple[str, str] | None = None
        for record in runs:
            if str(record.get("trade_date", "")) != trade_date:
                continue
            run = record.get("run", {})
            for task in run.get("tasks", ()):
                task_workflow = str(task.get("mode", ""))
                task_phase = task.get("phase")
                if task_phase:
                    task_workflow = f"{task_workflow}:{task_phase}"
                if task_workflow != workflow:
                    continue
                key = (
                    str(record.get("created_at", "")),
                    str(record.get("record_id", "")),
                )
                status = str(task.get("status", "unknown"))
                if latest_key is None or key > latest_key:
                    latest_key = key
                    latest_status = status
                if status == "completed" and (
                    completed_key is None or key > completed_key
                ):
                    completed_key = key
                if status != "skipped" and (
                    latest_not_skipped_key is None or key > latest_not_skipped_key
                ):
                    latest_not_skipped_key = key
                    latest_not_skipped_status = status
        if completed_key is not None:
            return "completed"
        if latest_not_skipped_key is not None:
            return latest_not_skipped_status
        return latest_status

    @staticmethod
    def _is_market_data_unavailable_notification(notification: NotificationRecord) -> bool:
        message = notification.message or ""
        return (
            "行情数据不可用" in message
            or "行情异常暂停" in message
            or "数据异常" in message
        )

    def _is_before_scheduled_time(
        self,
        context: TradingDayContext,
        scheduled_time: str,
    ) -> bool:
        try:
            trade_date = datetime.strptime(context.trade_date, "%Y-%m-%d").date()
            scheduled_clock = datetime.strptime(scheduled_time, "%H:%M").time()
        except ValueError:
            return False
        now = self._now_provider()
        if now.date() < trade_date:
            return True
        if now.date() > trade_date:
            return False
        return now.time() < scheduled_clock

    @staticmethod
    def _summary(
        context: TradingDayContext,
        status: str,
        blocked: tuple[OneToTwoScheduleHealthItem, ...],
        warning: tuple[OneToTwoScheduleHealthItem, ...],
    ) -> str:
        if not context.is_trading_day:
            return f"{context.requested_date} 非交易日，早评/晚评不应发送。"
        if status == "ready":
            return "关键值守覆盖正常，继续保持早评、指挥单、开盘确认和晚评。"
        if blocked:
            names = "、".join(item.workflow for item in blocked)
            return f"关键值守存在阻断：{names}，需要先修复常驻调度或飞书链路。"
        names = "、".join(item.workflow for item in warning)
        return f"通知覆盖存在待确认项：{names}。"

    @staticmethod
    def _next_action(context: TradingDayContext, status: str) -> str:
        if not context.is_trading_day:
            return "今天不需要早评/晚评；下一交易日盘前检查 beta-start 自启动。"
        if status == "ready":
            return "继续保持 beta-start 常驻，并用 missed-opportunities 复核是否仍错失可执行机会。"
        return "先运行 schedule-health --brief 定位缺失阶段，再用 beta-check/feishu-test 修复。"


__all__ = ["ScheduleHealthService"]
