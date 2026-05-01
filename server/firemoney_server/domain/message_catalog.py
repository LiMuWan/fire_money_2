"""Domain message catalog for user-visible server guidance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


_MESSAGES_DIR = Path(__file__).with_name("messages")
_DEFAULT_LOCALE = "zh_CN"


@dataclass(frozen=True)
class DomainMessages:
    payload: dict[str, Any]

    def text(self, section: str, key: str) -> str:
        return str(self.payload[section][key])

    def format(self, section: str, key: str, **values: object) -> str:
        return self.text(section, key).format(**values)


@lru_cache(maxsize=4)
def load_domain_messages(locale: str = _DEFAULT_LOCALE) -> DomainMessages:
    path = _MESSAGES_DIR / f"{locale}.json"
    with path.open("r", encoding="utf-8") as file:
        payload: dict[str, Any] = json.load(file)
    return DomainMessages(payload)
