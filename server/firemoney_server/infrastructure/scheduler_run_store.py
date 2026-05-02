"""Local scheduler run audit persistence for the one-to-two workflow."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any, Callable

from shared.contracts import OneToTwoScheduleRun, contract_to_dict


DEFAULT_SCHEDULER_RUN_STORE_PATH = Path(".firemoney") / "scheduler_runs.json"


class SchedulerRunStore:
    """Stores scheduler run results so Beta watch mode is auditable."""

    def __init__(
        self,
        path: str | Path = DEFAULT_SCHEDULER_RUN_STORE_PATH,
        created_at_provider: Callable[[], str] | None = None,
    ) -> None:
        self._path = Path(path)
        self._created_at_provider = created_at_provider

    @property
    def path(self) -> Path:
        return self._path

    def append(self, run: OneToTwoScheduleRun) -> dict[str, Any]:
        created_at = (
            self._created_at_provider()
            if self._created_at_provider
            else strftime("%Y%m%d%H%M%S")
        )
        record = {
            "record_id": f"schedule-{run.trade_date}-{run.requested_time}-{created_at}",
            "created_at": created_at,
            "trade_date": run.trade_date,
            "requested_time": run.requested_time,
            "status": "executed" if run.executed_count else "observed",
            "run": contract_to_dict(run),
        }
        records = (record, *self.load())[:200]
        self._save(records)
        return record

    def load(self, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        if not self._path.exists():
            return ()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return ()
        raw_records = payload.get("records", ())
        if not isinstance(raw_records, list):
            return ()
        records = tuple(item for item in raw_records if isinstance(item, dict))
        if limit is None:
            return records
        return records[: max(0, limit)]

    def _save(self, records: tuple[dict[str, Any], ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"records": list(records)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
