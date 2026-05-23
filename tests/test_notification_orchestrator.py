from __future__ import annotations

import unittest
from dataclasses import dataclass

from server.firemoney_server.application.notification_orchestrator import (
    OneToTwoNotificationOrchestrator,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationRecord,
    NotificationStatus,
    OneToTwoEventType,
)


@dataclass(frozen=True)
class Event:
    event_type: OneToTwoEventType
    trade_date: str = "2026-05-08"


@dataclass(frozen=True)
class Account:
    events: tuple[Event, ...] = ()


class Sender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> FeishuNotificationResult:
        self.sent.append((title, message))
        return FeishuNotificationResult(
            status=NotificationStatus.SENT,
            title=title,
            message=message,
            webhook_configured=True,
        )


class Store:
    def __init__(self) -> None:
        self.records: list[NotificationRecord] = []

    def append(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
        channel: str = "feishu",
    ) -> NotificationRecord:
        record = NotificationRecord(
            record_id=f"{channel}-{workflow}-{trade_date}",
            channel=channel,
            workflow=workflow,
            trade_date=trade_date,
            status=result.status,
            title=result.title,
            message=result.message,
            created_at="20260508093000",
            error=result.error,
        )
        self.records.insert(0, record)
        return record

    def load(self) -> tuple[NotificationRecord, ...]:
        return tuple(self.records)


class OneToTwoNotificationOrchestratorTest(unittest.TestCase):
    def test_watch_delivery_is_limited_to_real_buy_and_sell_events(self) -> None:
        orchestrator = OneToTwoNotificationOrchestrator(
            sender=Sender(),
            store=Store(),
        )

        self.assertFalse(
            orchestrator.should_send_watch(
                phase="scan",
                account=Account(events=(Event(OneToTwoEventType.CANDIDATE_SELECTED),)),
                trade_date="2026-05-08",
            )
        )
        self.assertFalse(
            orchestrator.should_send_watch(
                phase="auction",
                account=Account(events=(Event(OneToTwoEventType.AUCTION_CONFIRMED),)),
                trade_date="2026-05-08",
            )
        )
        self.assertFalse(
            orchestrator.should_send_watch(
                phase="open",
                account=Account(events=(Event(OneToTwoEventType.BLOCKED),)),
                trade_date="2026-05-08",
            )
        )
        self.assertTrue(
            orchestrator.should_send_watch(
                phase="open",
                account=Account(events=(Event(OneToTwoEventType.PAPER_BUY),)),
                trade_date="2026-05-08",
            )
        )
        self.assertTrue(
            orchestrator.should_send_watch(
                phase="risk",
                account=Account(events=(Event(OneToTwoEventType.TAKE_PROFIT),)),
                trade_date="2026-05-08",
            )
        )
        self.assertFalse(
            orchestrator.should_send_watch(
                phase="risk",
                account=Account(events=(Event(OneToTwoEventType.STOP_WARNING),)),
                trade_date="2026-05-08",
            )
        )

    def test_action_only_filter_uses_workflow_boundary(self) -> None:
        store = Store()
        orchestrator = OneToTwoNotificationOrchestrator(
            sender=Sender(),
            store=store,
        )
        result = FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title="FireMoney",
            message="prepared",
            webhook_configured=False,
        )
        for workflow in (
            "morning",
            "watch:scan",
            "watch:open",
            "paper-decision",
            "watch:risk",
            "eod",
        ):
            orchestrator.record(
                workflow=workflow,
                trade_date="2026-05-08",
                result=result,
            )

        action_records = orchestrator.load_records(action_only=True)

        self.assertEqual(
            {record.workflow for record in action_records},
            {"morning", "watch:open", "watch:risk", "eod"},
        )

    def test_notify_or_prepare_does_not_call_sender_when_prepared(self) -> None:
        sender = Sender()
        orchestrator = OneToTwoNotificationOrchestrator(
            sender=sender,
            store=Store(),
        )

        result = orchestrator.notify_or_prepare(
            notify=False,
            title="FireMoney",
            message="local preview",
        )

        self.assertEqual(result.status, NotificationStatus.PREPARED)
        self.assertEqual(sender.sent, [])


if __name__ == "__main__":
    unittest.main()
