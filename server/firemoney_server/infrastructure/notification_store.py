"""Local notification result persistence for the one-to-two workflow."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any

from shared.contracts import (
    FeishuNotificationResult,
    NotificationRecord,
    NotificationStatus,
)


DEFAULT_NOTIFICATION_STORE_PATH = Path(".firemoney") / "notifications.json"


class NotificationRecordStore:
    """Stores notification results so Feishu delivery is auditable."""

    def __init__(self, path: str | Path = DEFAULT_NOTIFICATION_STORE_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
        channel: str = "feishu",
    ) -> NotificationRecord:
        created_at = strftime("%Y%m%d%H%M%S")
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
        records = (record, *self.load())[:200]
        self._save(records)
        return record

    def load(self) -> tuple[NotificationRecord, ...]:
        if not self._path.exists():
            return ()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return ()
        raw_records = payload.get("records", ())
        if not isinstance(raw_records, list):
            return ()
        records: list[NotificationRecord] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            try:
                records.append(self._from_payload(item))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(records)

    def _save(self, records: tuple[NotificationRecord, ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [self._to_payload(record) for record in records]}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
