"""Client adapter for obtaining workflow snapshots."""

from __future__ import annotations

from server.firemoney_server import MainChainService
from shared.contracts import MainChainSnapshot


class LocalMainChainAdapter:
    """Local adapter; replace with HTTP/RPC later without changing UI code."""

    def __init__(self, service: MainChainService | None = None) -> None:
        self._service = service or MainChainService()

    def load_snapshot(
        self,
        user_confirmed: bool = False,
        broker_submitted: bool = False,
        fill_received: bool = False,
        exit_received: bool = False,
        adjustments_confirmed: bool = False,
    ) -> MainChainSnapshot:
        return self._service.build_first_slice_snapshot(
            user_confirmed=user_confirmed,
            broker_submitted=broker_submitted,
            fill_received=fill_received,
            exit_received=exit_received,
            adjustments_confirmed=adjustments_confirmed,
        )

    def reset_strategy_config(self) -> bool:
        return self._service.reset_strategy_config()
