"""HTTP/RPC boundary placeholders for future service adapters."""

from __future__ import annotations

from typing import Any, Protocol


class ServiceGateway(Protocol):
    """Minimal sync gateway boundary for future HTTP/RPC adapters."""

    def request(
        self,
        operation: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a named operation and return a JSON-friendly payload."""


__all__ = ["ServiceGateway"]
