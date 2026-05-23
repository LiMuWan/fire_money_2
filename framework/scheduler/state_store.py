"""Product-agnostic scheduler task completion persistence."""

from __future__ import annotations

from pathlib import Path

from framework.storage import JsonSetStore


class CompletedTaskStateStore:
    """Persists completed scheduler task keys to avoid duplicate runs."""

    def __init__(self, path: str | Path, *, key: str = "completed") -> None:
        self._store = JsonSetStore(path, key=key)

    @property
    def path(self) -> Path:
        return self._store.path

    def load(self) -> tuple[str, ...]:
        return tuple(sorted(self._store.load()))

    def is_done(self, task_key: str) -> bool:
        return self._store.contains(task_key)

    def mark_done(self, task_key: str) -> None:
        self._store.add(task_key)

