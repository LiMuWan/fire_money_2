"""Local environment loading for ignored FireMoney runtime secrets."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_LOCAL_FEISHU_ENV_PATH = Path(".firemoney") / "feishu.env"

_ALLOWED_FEISHU_ENV_KEYS = {
    "FEISHU_ENABLED",
    "FEISHU_WEBHOOK_URL",
    "FEISHU_WEBHOOK_SECRET",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_RECEIVE_ID",
    "FEISHU_RECEIVE_ID_TYPE",
    "FEISHU_OPEN_CHAT_ID",
    "FEISHU_API_BASE_URL",
}


def load_local_feishu_env(
    path: str | Path = DEFAULT_LOCAL_FEISHU_ENV_PATH,
) -> tuple[str, ...]:
    """Load ignored local Feishu settings without overriding process env."""

    target = Path(path)
    if not target.exists():
        return ()
    loaded: list[str] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in _ALLOWED_FEISHU_ENV_KEYS or key in os.environ:
            continue
        os.environ[key] = _unquote_env_value(value.strip())
        loaded.append(key)
    return tuple(loaded)


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
