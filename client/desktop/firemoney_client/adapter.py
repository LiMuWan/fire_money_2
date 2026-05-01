"""Client adapter for obtaining workflow snapshots."""

from __future__ import annotations

from server.firemoney_server import MainChainService
from shared.contracts import MainChainSnapshot


class LocalMainChainAdapter:
    """Local adapter; replace with HTTP/RPC later without changing UI code."""

    def __init__(self, service: MainChainService | None = None) -> None:
        self._service = service or MainChainService()

    def load_snapshot(self) -> MainChainSnapshot:
        return self._service.build_first_slice_snapshot()
