"""Product-agnostic JSON file stores for local tools and schedulers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any


class JsonFileStore:
    """Small safe JSON file helper with tolerant reads."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read_object(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_object(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class AppendOnlyJsonRecordStore:
    """Stores newest-first records under a configurable JSON key."""

    def __init__(
        self,
        path: str | Path,
        *,
        key: str = "records",
        limit: int = 200,
    ) -> None:
        self._file = JsonFileStore(path)
        self._key = key
        self._limit = max(1, limit)

    @property
    def path(self) -> Path:
        return self._file.path

    def load(self, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        raw_records = self._file.read_object().get(self._key, ())
        if not isinstance(raw_records, list):
            return ()
        records = tuple(item for item in raw_records if isinstance(item, dict))
        if limit is None:
            return records
        return records[: max(0, limit)]

    def prepend(self, record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        records = (record, *self.load())[: self._limit]
        self._file.write_object({self._key: list(records)})
        return records

    def replace(self, records: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        normalized = tuple(item for item in records if isinstance(item, dict))[: self._limit]
        self._file.write_object({self._key: list(normalized)})
        return normalized


class JsonSetStore:
    """Persists a string set under a configurable JSON key."""

    def __init__(self, path: str | Path, *, key: str) -> None:
        self._file = JsonFileStore(path)
        self._key = key

    @property
    def path(self) -> Path:
        return self._file.path

    def load(self) -> set[str]:
        values = self._file.read_object().get(self._key, ())
        if not isinstance(values, list):
            return set()
        return {str(item) for item in values}

    def save(self, values: set[str]) -> None:
        self._file.write_object({self._key: sorted(values)})

    def contains(self, value: str) -> bool:
        return value in self.load()

    def add(self, value: str) -> bool:
        values = self.load()
        if value in values:
            return False
        values.add(value)
        self.save(values)
        return True
