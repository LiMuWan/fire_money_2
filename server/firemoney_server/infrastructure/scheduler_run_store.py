"""Local scheduler run audit persistence for the one-to-two workflow."""

from __future__ import annotations

from pathlib import Path
from time import strftime
from typing import Any, Callable

from framework.storage import AppendOnlyJsonRecordStore
from shared.contracts import OneToTwoScheduleRun, contract_to_dict


DEFAULT_SCHEDULER_RUN_STORE_PATH = Path(".firemoney") / "scheduler_runs.json"
SCHEDULER_RUN_STORE_LIMIT = 2000
OBSERVED_RUN_RETAIN_LIMIT = 240
IMPORTANT_TASK_STATUSES = frozenset({"completed", "failed", "expired", "retrying"})


class SchedulerRunStore:
    """Stores scheduler run results so Beta watch mode is auditable."""

    def __init__(
        self,
        path: str | Path = DEFAULT_SCHEDULER_RUN_STORE_PATH,
        created_at_provider: Callable[[], str] | None = None,
    ) -> None:
        self._store = AppendOnlyJsonRecordStore(
            path,
            key="records",
            limit=SCHEDULER_RUN_STORE_LIMIT,
        )
        self._created_at_provider = created_at_provider

    @property
    def path(self) -> Path:
        return self._store.path

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
        records = self._store.prepend(record)
        self._prune_observed_noise(records)
        return record

    def load(self, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        return self._store.load(limit)

    def _prune_observed_noise(self, records: tuple[dict[str, Any], ...]) -> None:
        observed_count = 0
        kept: list[dict[str, Any]] = []
        for record in records:
            if _is_important_run(record):
                kept.append(record)
                continue
            observed_count += 1
            if observed_count <= OBSERVED_RUN_RETAIN_LIMIT:
                kept.append(record)
        if len(kept) != len(records):
            self._store.replace(kept)


def _is_important_run(record: dict[str, Any]) -> bool:
    if record.get("status") == "executed":
        return True
    run = record.get("run")
    if not isinstance(run, dict):
        return False
    for task in run.get("tasks", ()) or ():
        if not isinstance(task, dict):
            continue
        if str(task.get("status", "")) in IMPORTANT_TASK_STATUSES:
            return True
    return False
