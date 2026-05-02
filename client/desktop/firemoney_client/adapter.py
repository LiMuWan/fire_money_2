"""Client adapter for the one-to-two workflow."""

from __future__ import annotations

from server.firemoney_server import MainChainService
from shared.contracts import (
    NotificationRecord,
    NotificationStatus,
    OneToTwoBetaReadinessReport,
    OneToTwoBacktestAuditReport,
    OneToTwoDoctorReport,
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
        phase: str = "scan",
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        return self._service.run_one_to_two_watch(
            trade_date=trade_date,
            phase=phase,
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

    def build_one_to_two_doctor_report(
        self,
        trade_date: str | None = None,
        beta: bool = False,
    ) -> OneToTwoDoctorReport:
        return self._service.build_one_to_two_doctor_report(
            trade_date=trade_date,
            beta=beta,
        )

    def send_one_to_two_feishu_test(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ):
        return self._service.send_one_to_two_feishu_test(
            trade_date=trade_date,
            notify=notify,
        )

    def build_one_to_two_beta_readiness_report(
        self,
        trade_date: str | None = None,
    ) -> OneToTwoBetaReadinessReport:
        return self._service.build_one_to_two_beta_readiness_report(
            trade_date=trade_date,
        )

    def load_notification_records(
        self,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
    ) -> tuple[NotificationRecord, ...]:
        return self._service.load_notification_records(
            workflow=workflow,
            status=status,
            limit=limit,
        )

    def run_one_to_two_backtest(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoStabilityReport:
        return self._service.run_one_to_two_backtest(
            start_date=start_date,
            end_date=end_date,
            max_trade_days=max_trade_days,
        )

    def build_one_to_two_backtest_audit(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoBacktestAuditReport:
        return self._service.build_one_to_two_backtest_audit(
            start_date=start_date,
            end_date=end_date,
            max_trade_days=max_trade_days,
        )
