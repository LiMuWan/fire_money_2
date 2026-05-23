"""Small SQLite migration helper for local-first applications."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SqliteMigration:
    """A numbered SQLite migration made from one or more SQL statements."""

    version: int
    statements: tuple[str, ...]


def apply_sqlite_migrations(
    path: str | Path,
    migrations: Iterable[SqliteMigration],
) -> int:
    """Apply pending migrations and return the current schema version."""

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = tuple(sorted(migrations, key=lambda item: item.version))
    connection = sqlite3.connect(db_path)
    try:
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        for migration in ordered:
            if migration.version <= current_version:
                continue
            with connection:
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {migration.version}")
            current_version = migration.version
        return current_version
    finally:
        connection.close()
