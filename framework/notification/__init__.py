"""Notification abstractions for reusable delivery adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotificationResult:
    """Product-neutral notification delivery result."""

    status: str
    title: str
    message: str
    channel: str
    configured: bool
    error: str | None = None


class NotificationSender(Protocol):
    """Protocol implemented by webhook, app bot, or future queue adapters."""

    def send(self, *, title: str, message: str) -> NotificationResult:
        """Deliver a message and return a normalized result."""


__all__ = ["NotificationResult", "NotificationSender"]
