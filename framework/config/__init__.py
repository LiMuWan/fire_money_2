"""Generic configuration loading helpers."""

from __future__ import annotations

import json
import os
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping


def load_json_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON object config, returning an empty object for missing files."""

    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_env_overrides(
    payload: Mapping[str, Any],
    mapping: Mapping[str, str],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Merge selected environment variables into a config payload."""

    source = os.environ if environ is None else environ
    merged = dict(payload)
    for key, env_name in mapping.items():
        if env_name in source:
            merged[key] = source[env_name]
    return merged


def require_config_keys(payload: Mapping[str, Any], required_keys: tuple[str, ...]) -> None:
    """Raise a clear error when a config object is missing required keys."""

    missing = tuple(key for key in required_keys if key not in payload)
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")


__all__ = [
    "load_json_config",
    "merge_env_overrides",
    "require_config_keys",
]
