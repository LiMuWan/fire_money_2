"""FireMoney scheduler state persistence."""

from __future__ import annotations

from pathlib import Path

from framework.scheduler import CompletedTaskStateStore


DEFAULT_SCHEDULER_STATE_PATH = Path(".firemoney") / "scheduler_state.json"


class SchedulerStateStore(CompletedTaskStateStore):
    """Persists completed scheduler task keys to prevent duplicate runs."""

    def __init__(self, path: str | Path = DEFAULT_SCHEDULER_STATE_PATH) -> None:
        super().__init__(path, key="completed")
