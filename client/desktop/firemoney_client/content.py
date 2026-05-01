"""Content catalog for the FireMoney desktop client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


_CONTENT_DIR = Path(__file__).with_name("content")


@dataclass(frozen=True)
class ClientContent:
    workspaces: tuple[dict[str, str], ...]
    labels: dict[str, str]
    sections: dict[str, str]
    empty_states: dict[str, str]
    templates: dict[str, str]


@lru_cache(maxsize=8)
def load_client_content(locale: str = "zh_CN") -> ClientContent:
    """Load localizable client text from a structured content file."""

    content_path = _CONTENT_DIR / f"{locale}.json"
    with content_path.open("r", encoding="utf-8") as file:
        payload: dict[str, Any] = json.load(file)

    return ClientContent(
        workspaces=tuple(payload["workspaces"]),
        labels=dict(payload["labels"]),
        sections=dict(payload["sections"]),
        empty_states=dict(payload["empty_states"]),
        templates=dict(payload.get("templates", {})),
    )
