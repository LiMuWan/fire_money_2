"""Local client adapter for the one-to-two workflow."""

from __future__ import annotations

from server.firemoney_server import MainChainService
from shared.contracts import (
    CommercialReadinessReport,
    K92EmotionLiquidityReport,
    LimitUpBoardShadowReport,
    LimitUpBoardShadowStabilityReport,
    LimitUpBoardShadowSystemReport,
    MainlineTrendWatchReport,
    MissedOpportunityReport,
    NotificationRecord,
    NotificationStatus,
    OneToTwoExecutionQualityReport,
    OneToTwoBetaReadinessReport,
    OneToTwoBacktestAuditReport,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoHistoricalReplayReport,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    OneToTwoStabilityReport,
    StrategyDecisionReport,
)


class LocalMainChainAdapter:
    """Local adapter; replace with HTTP/RPC later without changing UI code."""

    def __init__(self, service: MainChainService | None = None) -> None:
        self._service = service or MainChainService()

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
        record_notification: bool = True,
    ) -> OneToTwoMorningReport:
        return self._service.build_one_to_two_morning_report(
            trade_date=trade_date,
            notify=notify,
            market_data_timeout_seconds=market_data_timeout_seconds,
            record_notification=record_notification,
        )

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        phase: str = "scan",
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
    ) -> OneToTwoMorningReport:
        return self._service.run_one_to_two_watch(
            trade_date=trade_date,
            phase=phase,
            notify=notify,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
        record_notification: bool = True,
    ) -> OneToTwoEndOfDayReview:
        return self._service.build_one_to_two_end_of_day_review(
            trade_date=trade_date,
            notify=notify,
            market_data_timeout_seconds=market_data_timeout_seconds,
            record_notification=record_notification,
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        return self._service.build_one_to_two_stability_report()

    def build_one_to_two_doctor_report(
        self,
        trade_date: str | None = None,
        beta: bool = False,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoDoctorReport:
        return self._service.build_one_to_two_doctor_report(
            trade_date=trade_date,
            beta=beta,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def build_schedule_health_report(
        self,
        trade_date: str | None = None,
    ) -> OneToTwoScheduleHealthReport:
        return self._service.build_schedule_health_report(trade_date=trade_date)

    def build_mainline_trend_watch_report(
        self,
        trade_date: str | None = None,
        limit: int = 12,
    ) -> MainlineTrendWatchReport:
        return self._service.build_mainline_trend_watch_report(
            trade_date=trade_date,
            limit=limit,
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
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoBetaReadinessReport:
        return self._service.build_one_to_two_beta_readiness_report(
            trade_date=trade_date,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def load_notification_records(
        self,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
        action_only: bool = False,
    ) -> tuple[NotificationRecord, ...]:
        return self._service.load_notification_records(
            workflow=workflow,
            status=status,
            limit=limit,
            action_only=action_only,
        )

    def build_commercial_readiness_report(
        self,
        *,
        report: OneToTwoMorningReport,
        schedule_health_report: OneToTwoScheduleHealthReport | None = None,
        paper_database_report: PaperTradeDatabaseReport | None = None,
        paper_backtest_report: PaperBacktestReport | None = None,
        doctor_report: OneToTwoDoctorReport | None = None,
        notification_records: tuple[NotificationRecord, ...] = (),
    ) -> CommercialReadinessReport:
        return self._service.build_commercial_readiness_report(
            report=report,
            schedule_health_report=schedule_health_report,
            paper_database_report=paper_database_report,
            paper_backtest_report=paper_backtest_report,
            doctor_report=doctor_report,
            notification_records=notification_records,
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

    def run_one_to_two_historical_replay(
        self,
        as_of_date: str | None = None,
        holding_days: int = 5,
    ) -> OneToTwoHistoricalReplayReport:
        return self._service.run_one_to_two_historical_replay(
            as_of_date=as_of_date,
            holding_days=holding_days,
        )

    def build_limit_up_board_shadow_report(
        self,
        as_of_date: str | None = None,
        cache_dir: str | None = None,
    ) -> LimitUpBoardShadowReport:
        return self._service.build_limit_up_board_shadow_report(
            as_of_date=as_of_date,
            cache_dir=cache_dir,
        )

    def record_limit_up_board_shadow_sample(
        self,
        as_of_date: str | None = None,
        cache_dir: str | None = None,
        notify: bool = False,
    ) -> LimitUpBoardShadowReport:
        return self._service.record_limit_up_board_shadow_sample(
            as_of_date=as_of_date,
            cache_dir=cache_dir,
            notify=notify,
        )

    def build_limit_up_board_shadow_stability_report(
        self,
    ) -> LimitUpBoardShadowStabilityReport:
        return self._service.build_limit_up_board_shadow_stability_report()

    def build_limit_up_board_shadow_system_report(
        self,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> LimitUpBoardShadowSystemReport:
        return self._service.build_limit_up_board_shadow_system_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
        )

    def build_paper_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
        refresh_cache: bool = False,
    ) -> PaperBacktestReport:
        return self._service.build_paper_backtest_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )

    def build_missed_opportunity_report(
        self,
        start_date: str,
        end_date: str | None = None,
        cache_dir: str | None = None,
        limit: int = 20,
    ) -> MissedOpportunityReport:
        return self._service.build_missed_opportunity_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            limit=limit,
        )

    def build_strategy_decision_report(
        self,
        trade_date: str | None = None,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> StrategyDecisionReport:
        return self._service.build_strategy_decision_report(
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
        )

    def build_k92_emotion_liquidity_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float | None = None,
    ) -> K92EmotionLiquidityReport:
        return self._service.build_k92_emotion_liquidity_report(
            trade_date=trade_date,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def build_k92_emotion_liquidity_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | None = None,
    ) -> PaperBacktestReport:
        return self._service.build_k92_emotion_liquidity_backtest_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
        )

    def build_paper_trading_decision_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float = 8.0,
        notify: bool = False,
        record_notification: bool = True,
    ) -> PaperTradingDecisionReport:
        return self._service.build_paper_trading_decision_report(
            trade_date=trade_date,
            market_data_timeout_seconds=market_data_timeout_seconds,
            notify=notify,
            record_notification=record_notification,
        )

    def build_paper_trade_database_report(
        self,
        database_path: str | None = None,
        limit: int = 10,
    ) -> PaperTradeDatabaseReport:
        return self._service.build_paper_trade_database_report(
            database_path=database_path,
            limit=limit,
        )

    def build_one_to_two_execution_quality_report(
        self,
        symbol: str = "600001",
        trade_date: str | None = None,
    ) -> OneToTwoExecutionQualityReport:
        return self._service.build_one_to_two_execution_quality_report(
            symbol=symbol,
            trade_date=trade_date,
        )
