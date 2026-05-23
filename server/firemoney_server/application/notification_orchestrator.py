"""Notification delivery and audit orchestration for FireMoney workflows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from shared.contracts import (
    FeishuNotificationResult,
    NotificationRecord,
    NotificationStatus,
    OneToTwoEventType,
)


class NotificationSender(Protocol):
    def notify(self, title: str, message: str) -> FeishuNotificationResult:
        """Send a notification through the configured adapter."""


class NotificationRecordStoreLike(Protocol):
    def append(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
        channel: str = "feishu",
    ) -> NotificationRecord:
        """Persist one notification audit record."""

    def load(self) -> tuple[NotificationRecord, ...]:
        """Load recent notification audit records."""


class PaperTradeEventLike(Protocol):
    event_type: OneToTwoEventType
    trade_date: str


class PaperAccountLike(Protocol):
    events: Sequence[PaperTradeEventLike]


class OneToTwoNotificationOrchestrator:
    """Keeps delivery rules out of the trading decision service."""

    _WATCH_SELL_EVENT_TYPES = frozenset(
        {
            OneToTwoEventType.T1_SELL,
            OneToTwoEventType.TAKE_PROFIT,
            OneToTwoEventType.MAINLINE_FADE_EXIT,
            OneToTwoEventType.DISCIPLINE_EXIT,
        }
    )
    _ACTION_WORKFLOWS = frozenset({"morning", "watch:open", "watch:risk", "eod"})

    def __init__(
        self,
        *,
        sender: NotificationSender,
        store: NotificationRecordStoreLike,
    ) -> None:
        self._sender = sender
        self._store = store

    @property
    def watch_sell_event_types(self) -> frozenset[OneToTwoEventType]:
        return self._WATCH_SELL_EVENT_TYPES

    def notify_or_prepare(
        self,
        *,
        notify: bool,
        title: str,
        message: str,
    ) -> FeishuNotificationResult:
        if notify:
            return self._sender.notify(title, message)
        return FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title=title,
            message=message,
            webhook_configured=False,
            error="notification skipped",
        )

    def record(
        self,
        *,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
    ) -> NotificationRecord:
        return self._store.append(
            workflow=workflow,
            trade_date=trade_date,
            result=result,
        )

    def should_send_watch(
        self,
        *,
        phase: str,
        account: PaperAccountLike,
        trade_date: str,
    ) -> bool:
        if not account.events:
            return False
        latest = account.events[0]
        if latest.trade_date != trade_date:
            return False
        if phase == "open":
            return latest.event_type == OneToTwoEventType.PAPER_BUY
        if phase == "risk":
            return latest.event_type in self._WATCH_SELL_EVENT_TYPES
        return False

    def load_records(
        self,
        *,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
        action_only: bool = False,
    ) -> tuple[NotificationRecord, ...]:
        records = self._store.load()
        if workflow:
            records = tuple(record for record in records if record.workflow == workflow)
        if status:
            expected = status if isinstance(status, NotificationStatus) else NotificationStatus(status)
            records = tuple(record for record in records if record.status == expected)
        if action_only:
            records = tuple(record for record in records if self.is_action_notification(record))
        if limit is not None:
            records = records[: max(0, limit)]
        return records

    def is_action_notification(self, record: NotificationRecord) -> bool:
        return record.workflow in self._ACTION_WORKFLOWS


__all__ = [
    "NotificationRecordStoreLike",
    "NotificationSender",
    "OneToTwoNotificationOrchestrator",
]
