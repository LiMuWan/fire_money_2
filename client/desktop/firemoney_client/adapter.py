"""Client adapter for obtaining workflow snapshots."""

from __future__ import annotations

from pathlib import Path

from server.firemoney_server import MainChainService
from shared.contracts import (
    ExportCleanupResult,
    MainChainSnapshot,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoStabilityReport,
    StrategyBoundaryReview,
    StrategyConfig,
    StrategyResetReview,
    TradeArchiveReview,
)


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

    def build_strategy_reset_review(self) -> StrategyResetReview:
        return self._service.build_strategy_reset_review()

    def apply_strategy_reset_review(
        self,
        confirm: bool = False,
    ) -> StrategyConfig:
        return self._service.apply_strategy_reset_review(confirm=confirm)

    def export_trade_archives(
        self,
        target_path: str | Path | None = None,
        format: str = "json",
        limit: int = 50,
    ) -> Path:
        return self._service.export_trade_archives(
            target_path=target_path,
            format=format,
            limit=limit,
        )

    def build_trade_archive_review(self, limit: int = 50) -> TradeArchiveReview:
        return self._service.build_trade_archive_review(limit=limit)

    def export_trade_archive_review(
        self,
        target_path: str | Path | None = None,
        limit: int = 50,
    ) -> Path:
        return self._service.export_trade_archive_review(
            target_path=target_path,
            limit=limit,
        )

    def build_strategy_boundary_review(self, limit: int = 50) -> StrategyBoundaryReview:
        return self._service.build_strategy_boundary_review(limit=limit)

    def apply_strategy_boundary_review(
        self,
        confirm: bool = False,
        limit: int = 50,
    ) -> StrategyConfig:
        return self._service.apply_strategy_boundary_review(
            confirm=confirm,
            limit=limit,
        )

    def export_strategy_boundary_audit(
        self,
        target_path: str | Path | None = None,
        actions: tuple[str, ...] | None = None,
    ) -> Path:
        return self._service.export_strategy_boundary_audit(
            target_path=target_path,
            actions=actions,
        )

    def clear_trade_archives(self) -> bool:
        return self._service.clear_trade_archives()

    def cleanup_archive_exports(
        self,
        retention_count: int = 1,
    ) -> ExportCleanupResult:
        return self._service.cleanup_archive_exports(retention_count=retention_count)

    def cleanup_strategy_exports(
        self,
        retention_count: int = 1,
    ) -> ExportCleanupResult:
        return self._service.cleanup_strategy_exports(retention_count=retention_count)

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
