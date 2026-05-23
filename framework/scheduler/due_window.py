"""Generic wall-clock due-window helpers for local schedulers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DueWindow:
    """A simple HH:MM execution window."""

    start_time: str
    end_time: str | None = None


def is_due_in_window(requested_time: str, window: DueWindow) -> bool:
    """Return whether a HH:MM time is inside a scheduler due window."""

    if requested_time < window.start_time:
        return False
    if window.end_time is None:
        return True
    return requested_time <= window.end_time


__all__ = ["DueWindow", "is_due_in_window"]
