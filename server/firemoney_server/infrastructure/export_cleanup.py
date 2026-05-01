"""Cleanup helpers for service-owned export files."""

from __future__ import annotations

from pathlib import Path

from shared.contracts import ExportCleanupResult


DEFAULT_EXPORT_RETENTION_COUNT = 1


class ExportCleanup:
    """Deletes older exported files while preserving recent service outputs."""

    def cleanup(
        self,
        target: str,
        directory: str | Path,
        prefixes: tuple[str, ...],
        suffixes: tuple[str, ...],
        retention_count: int = DEFAULT_EXPORT_RETENTION_COUNT,
    ) -> ExportCleanupResult:
        export_dir = Path(directory)
        normalized_retention = max(0, int(retention_count))
        matched = self._matching_files(export_dir, prefixes, suffixes)
        kept = matched[:normalized_retention]
        deleted = matched[normalized_retention:]
        for path in deleted:
            path.unlink()
        return ExportCleanupResult(
            target=target,
            directory=str(export_dir),
            retention_count=normalized_retention,
            matched_count=len(matched),
            deleted_count=len(deleted),
            kept_count=len(kept),
            deleted_files=tuple(path.name for path in deleted),
            kept_files=tuple(path.name for path in kept),
        )

    def _matching_files(
        self,
        export_dir: Path,
        prefixes: tuple[str, ...],
        suffixes: tuple[str, ...],
    ) -> tuple[Path, ...]:
        if not export_dir.exists():
            return ()
        normalized_prefixes = tuple(prefix for prefix in prefixes if prefix)
        normalized_suffixes = tuple(suffix.lower() for suffix in suffixes if suffix)
        return tuple(
            sorted(
                (
                    path
                    for path in export_dir.iterdir()
                    if path.is_file()
                    and self._matches(path, normalized_prefixes, normalized_suffixes)
                ),
                key=lambda path: (
                    path.stat().st_mtime,
                    path.name,
                ),
                reverse=True,
            )
        )

    def _matches(
        self,
        path: Path,
        prefixes: tuple[str, ...],
        suffixes: tuple[str, ...],
    ) -> bool:
        if prefixes and not path.name.startswith(prefixes):
            return False
        if suffixes and path.suffix.lower() not in suffixes:
            return False
        return True
