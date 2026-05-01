"""Client adapter for the one-to-two workflow."""

from __future__ import annotations

from server.firemoney_server import MainChainService
from shared.contracts import (
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoStabilityReport,
)


class LocalMainChainAdapter:
    """Local adapter; replace with HTTP/RPC later without changing UI code."""

    def __init__(self, service: MainChainService | None = None) -> None:
        self._service = service or MainChainService()

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        return self._service.build_one_to_two_morning_report(
            trade_date=trade_date,
            notify=notify,
        )

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        return self._service.run_one_to_two_watch(
            trade_date=trade_date,
            notify=notify,
        )

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoEndOfDayReview:
        return self._service.build_one_to_two_end_of_day_review(
            trade_date=trade_date,
            notify=notify,
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        return self._service.build_one_to_two_stability_report()
