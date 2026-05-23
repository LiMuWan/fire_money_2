"""Local notification result persistence for the one-to-two workflow."""

from __future__ import annotations

from pathlib import Path
from time import strftime
from typing import Any, Callable

from framework.storage import AppendOnlyJsonRecordStore
from shared.contracts import (
    FeishuNotificationResult,
    NotificationRecord,
    NotificationStatus,
)


DEFAULT_NOTIFICATION_STORE_PATH = Path(".firemoney") / "notifications.json"


class NotificationRecordStore:
    """Stores notification results so Feishu delivery is auditable."""

    def __init__(
        self,
        path: str | Path = DEFAULT_NOTIFICATION_STORE_PATH,
        created_at_provider: Callable[[], str] | None = None,
    ) -> None:
        self._store = AppendOnlyJsonRecordStore(path, key="records", limit=200)
        self._created_at_provider = created_at_provider

    @property
    def path(self) -> Path:
        return self._store.path

    def append(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
        channel: str = "feishu",
    ) -> NotificationRecord:
        created_at = (
            self._created_at_provider()
            if self._created_at_provider
            else strftime("%Y%m%d%H%M%S")
        )
        record = NotificationRecord(
            record_id=f"{channel}-{workflow}-{trade_date}-{created_at}",
            channel=channel,
            workflow=workflow,
            trade_date=trade_date,
            status=result.status,
            title=result.title,
            message=result.message,
            created_at=created_at,
            error=result.error,
        )
        self._store.prepend(self._to_payload(record))
        return record

    def load(self) -> tuple[NotificationRecord, ...]:
        records: list[NotificationRecord] = []
        for item in self._store.load():
            try:
                records.append(self._from_payload(item))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(records)

    def _to_payload(self, record: NotificationRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "channel": record.channel,
            "workflow": record.workflow,
            "trade_date": record.trade_date,
            "status": record.status.value,
            "title": record.title,
            "message": record.message,
            "created_at": record.created_at,
            "error": record.error,
        }

    def _from_payload(self, payload: dict[str, Any]) -> NotificationRecord:
        return NotificationRecord(
            record_id=str(payload["record_id"]),
            channel=str(payload["channel"]),
            workflow=str(payload["workflow"]),
            trade_date=str(payload["trade_date"]),
            status=NotificationStatus(str(payload["status"])),
            title=str(payload["title"]),
            message=str(payload["message"]),
            created_at=str(payload["created_at"]),
            error=(None if payload.get("error") is None else str(payload.get("error"))),
        )
