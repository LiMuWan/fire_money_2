"""Client-facing gateway protocol for FireMoney workflow adapters."""

from __future__ import annotations

from typing import Protocol

from shared.contracts import (
    CommercialReadinessReport,
    FeishuNotificationResult,
    K92EmotionLiquidityReport,
    LimitUpBoardShadowReport,
    LimitUpBoardShadowStabilityReport,
    LimitUpBoardShadowSystemReport,
    MissedOpportunityReport,
    NotificationRecord,
    NotificationStatus,
    OneToTwoBacktestAuditReport,
    OneToTwoBetaReadinessReport,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoExecutionQualityReport,
    OneToTwoHistoricalReplayReport,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    OneToTwoStabilityReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    StrategyDecisionReport,
)


class MainChainGateway(Protocol):
    """Client-facing gateway; local and future HTTP adapters implement this shape."""

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
        record_notification: bool = True,
    ) -> OneToTwoMorningReport: ...

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        phase: str = "scan",
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
    ) -> OneToTwoMorningReport: ...

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
        record_notification: bool = True,
    ) -> OneToTwoEndOfDayReview: ...

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport: ...

    def build_one_to_two_doctor_report(
        self,
        trade_date: str | None = None,
        beta: bool = False,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoDoctorReport: ...

    def build_schedule_health_report(
        self,
        trade_date: str | None = None,
    ) -> OneToTwoScheduleHealthReport: ...

    def send_one_to_two_feishu_test(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> FeishuNotificationResult: ...

    def build_one_to_two_beta_readiness_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoBetaReadinessReport: ...

    def build_commercial_readiness_report(
        self,
        *,
        report: OneToTwoMorningReport,
        schedule_health_report: OneToTwoScheduleHealthReport | None = None,
        paper_database_report: PaperTradeDatabaseReport | None = None,
        paper_backtest_report: PaperBacktestReport | None = None,
        doctor_report: OneToTwoDoctorReport | None = None,
        notification_records: tuple[NotificationRecord, ...] = (),
    ) -> CommercialReadinessReport: ...

    def load_notification_records(
        self,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
        action_only: bool = False,
    ) -> tuple[NotificationRecord, ...]: ...

    def run_one_to_two_backtest(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoStabilityReport: ...

    def build_one_to_two_backtest_audit(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoBacktestAuditReport: ...

    def run_one_to_two_historical_replay(
        self,
        as_of_date: str | None = None,
        holding_days: int = 5,
    ) -> OneToTwoHistoricalReplayReport: ...

    def build_limit_up_board_shadow_report(
        self,
        as_of_date: str | None = None,
        cache_dir: str | None = None,
    ) -> LimitUpBoardShadowReport: ...

    def record_limit_up_board_shadow_sample(
        self,
        as_of_date: str | None = None,
        cache_dir: str | None = None,
        notify: bool = False,
    ) -> LimitUpBoardShadowReport: ...

    def build_limit_up_board_shadow_stability_report(
        self,
    ) -> LimitUpBoardShadowStabilityReport: ...

    def build_limit_up_board_shadow_system_report(
        self,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> LimitUpBoardShadowSystemReport: ...

    def build_paper_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
        refresh_cache: bool = False,
    ) -> PaperBacktestReport: ...

    def build_missed_opportunity_report(
        self,
        start_date: str,
        end_date: str | None = None,
        cache_dir: str | None = None,
        limit: int = 20,
    ) -> MissedOpportunityReport: ...

    def build_strategy_decision_report(
        self,
        trade_date: str | None = None,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> StrategyDecisionReport: ...

    def build_k92_emotion_liquidity_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float | None = None,
    ) -> K92EmotionLiquidityReport: ...

    def build_k92_emotion_liquidity_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> PaperBacktestReport: ...

    def build_paper_trading_decision_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float = 8.0,
        notify: bool = False,
        record_notification: bool = True,
    ) -> PaperTradingDecisionReport: ...

    def build_paper_trade_database_report(
        self,
        database_path: str | None = None,
        limit: int = 10,
    ) -> PaperTradeDatabaseReport: ...

    def build_one_to_two_execution_quality_report(
        self,
        symbol: str = "600001",
        trade_date: str | None = None,
    ) -> OneToTwoExecutionQualityReport: ...


__all__ = ["MainChainGateway"]
