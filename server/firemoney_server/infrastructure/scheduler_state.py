"""Local scheduler state persistence for the one-to-two workflow."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path


DEFAULT_SCHEDULER_STATE_PATH = Path(".firemoney") / "scheduler_state.json"


class SchedulerStateStore:
    """Persists completed scheduler task keys to prevent duplicate runs."""

    def __init__(self, path: str | Path = DEFAULT_SCHEDULER_STATE_PATH) -> None:
        self._path = Path(path)

    def is_done(self, task_key: str) -> bool:
        return task_key in self._load()

    def mark_done(self, task_key: str) -> None:
        done = self._load()
        if task_key in done:
            return
        done.add(task_key)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"completed": sorted(done)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return set()
        completed = payload.get("completed", ())
        if not isinstance(completed, list):
            return set()
        return {str(item) for item in completed}
