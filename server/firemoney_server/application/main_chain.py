"""Application workflow for the FireMoney one-to-two product line."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from datetime import date
from pathlib import Path

from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.board_shadow_store import (
    LimitUpBoardShadowStore,
)
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    MarketDataProvider,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
    load_one_to_two_settings,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.paper_database import PaperTradeDatabase
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import (
    AkshareTradingCalendar,
    TradingCalendar,
)
from server.firemoney_server.application.paper_trading_guard import (
    PaperTradingGuard,
    PaperTradingGuardSettings,
)
from server.firemoney_server.application.paper_entry_policy import PaperEntryPolicy
from server.firemoney_server.application.paper_exit_policy import PaperExitPolicy
from server.firemoney_server.application.paper_decision_service import (
    PaperTradingDecisionService,
)
from server.firemoney_server.application.paper_backtest_service import (
    PaperBacktestService,
)
from server.firemoney_server.application.paper_instruction_builder import (
    PaperInstructionBuilder,
)
from server.firemoney_server.application.paper_runtime_service import (
    PaperRuntimeService,
)
from server.firemoney_server.application.beta_readiness_service import (
    BetaReadinessService,
)
from server.firemoney_server.application.commercial_readiness_service import (
    CommercialReadinessService,
)
from server.firemoney_server.application.end_of_day_review_service import (
    EndOfDayReviewService,
)
from server.firemoney_server.application.doctor_review_service import (
    DoctorReviewService,
)
from server.firemoney_server.application.execution_quality_service import (
    ExecutionQualityService,
)
from server.firemoney_server.application.historical_replay_service import (
    HistoricalReplayService,
)
from server.firemoney_server.application.board_shadow_execution_service import (
    BoardShadowExecutionService,
)
from server.firemoney_server.application.board_shadow_review_service import (
    BoardShadowReviewService,
)
from server.firemoney_server.application.watch_phase_service import (
    WatchPhaseService,
)
from server.firemoney_server.application.watch_report_service import (
    WatchReportService,
)
from server.firemoney_server.application.morning_report_service import (
    MorningReportService,
)
from server.firemoney_server.application.mainline_continuity_service import (
    MainlineContinuityService,
)
from server.firemoney_server.application.mainline_trend_watch_service import (
    MainlineTrendWatchService,
)
from server.firemoney_server.application.stability_review_service import (
    StabilityReviewService,
)
from server.firemoney_server.application.schedule_health_service import (
    ScheduleHealthService,
)
from server.firemoney_server.application.notification_orchestrator import (
    OneToTwoNotificationOrchestrator,
)
from server.firemoney_server.application.strategy_decision_service import (
    StrategyDecisionService,
)
from server.firemoney_server.application.k92_emotion_liquidity_service import (
    K92EmotionLiquidityService,
)
from server.firemoney_server.application.k92_emotion_liquidity_backtest_service import (
    K92EmotionLiquidityBacktestService,
)
from server.firemoney_server.application.missed_opportunity_service import (
    MissedOpportunityService,
)
from shared.contracts import (
    FeishuNotificationResult,
    CommercialReadinessReport,
    K92EmotionLiquidityReport,
    LimitUpBoardShadowReport,
    LimitUpBoardShadowStabilityReport,
    LimitUpBoardShadowSystemReport,
    MainlineTrendWatchReport,
    NotificationStatus,
    NotificationRecord,
    MissedOpportunityReport,
    OneToTwoExecutionQualityReport,
    OneToTwoBetaReadinessReport,
    OneToTwoBacktestAuditReport,
    OneToTwoCandidate,
    OneToTwoDoctorReport,
    OneToTwoEventType,
    OneToTwoEndOfDayReview,
    OneToTwoHistoricalReplayReport,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    OneToTwoStabilityReport,
    PaperBacktestReport,
    PaperBacktestYearlyMetric,
    PaperTradingDecisionReport,
    PaperTradeDatabaseReport,
    PaperAccount,
    StrategyDecisionReport,
    TradingDayContext,
)
from tools import research_limit_up_board_profit_matrix as board_matrix


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


class MainChainService:
    """Orchestrates only the mainboard 10cm one-to-two validation loop."""

    def __init__(
        self,
        one_to_two_settings: OneToTwoStrategySettings | None = None,
        market_data_provider: MarketDataProvider | None = None,
        paper_store: PaperTradeStore | None = None,
        feishu_notifier: FeishuNotifier | None = None,
        notification_store: NotificationRecordStore | None = None,
        scheduler_state_store: SchedulerStateStore | None = None,
        scheduler_run_store: SchedulerRunStore | None = None,
        trading_calendar: TradingCalendar | None = None,
        board_shadow_store: LimitUpBoardShadowStore | None = None,
    ) -> None:
        self._one_to_two_settings = one_to_two_settings or load_one_to_two_settings()
        self._one_to_two_policy = OneToTwoPolicy(self._one_to_two_settings)
        self._paper_entry_policy = PaperEntryPolicy(self._one_to_two_settings)
        self._paper_exit_policy = PaperExitPolicy(self._one_to_two_settings)
        self._paper_trading_guard = PaperTradingGuard(
            PaperTradingGuardSettings(
                review_sample=self._one_to_two_settings.paper_guard_review_sample,
                min_win_rate=self._one_to_two_settings.paper_guard_min_win_rate,
                min_average_return_pct=(
                    self._one_to_two_settings.paper_guard_min_average_return_pct
                ),
                max_consecutive_losses=(
                    self._one_to_two_settings.paper_guard_max_consecutive_losses
                ),
                max_consecutive_quality_failures=(
                    self._one_to_two_settings.paper_guard_max_consecutive_quality_failures
                ),
                max_drawdown_pct=self._one_to_two_settings.paper_guard_max_drawdown_pct,
                max_position_pct=self._one_to_two_settings.max_position_pct,
                reduced_position_pct=(
                    self._one_to_two_settings.paper_guard_reduced_position_pct
                ),
                min_profit_drawdown_ratio=(
                    self._one_to_two_settings.paper_guard_min_profit_drawdown_ratio
                ),
                min_quality_bucket_samples=(
                    self._one_to_two_settings.paper_guard_min_quality_bucket_samples
                ),
                quality_bucket_block_losses=(
                    self._one_to_two_settings.paper_guard_quality_bucket_block_losses
                ),
            )
        )
        self._market_data_provider = market_data_provider or AkshareMarketDataProvider()
        self._paper_store = paper_store or PaperTradeStore(
            initial_cash=self._one_to_two_settings.initial_cash,
            max_position_pct=self._one_to_two_settings.max_position_pct,
            max_daily_trades=self._one_to_two_settings.max_daily_trades,
        )
        self._feishu_notifier = feishu_notifier or FeishuNotifier()
        self._notification_store = notification_store or NotificationRecordStore()
        self._scheduler_state_store = scheduler_state_store or SchedulerStateStore()
        self._scheduler_run_store = scheduler_run_store or SchedulerRunStore()
        self._trading_calendar = trading_calendar or AkshareTradingCalendar()
        self._board_shadow_store = board_shadow_store or LimitUpBoardShadowStore()
        self._notification_orchestrator = OneToTwoNotificationOrchestrator(
            sender=self._feishu_notifier,
            store=self._notification_store,
        )
        self._strategy_decision_service = StrategyDecisionService(
            default_trade_date=self._default_trade_date,
        )
        self._paper_backtest_service = PaperBacktestService(
            default_trade_date=self._default_trade_date,
            settings=self._one_to_two_settings,
        )
        self._board_shadow_execution_service = BoardShadowExecutionService(
            settings=self._one_to_two_settings,
            policy=self._one_to_two_policy,
        )
        self._paper_runtime_service = PaperRuntimeService(
            settings=self._one_to_two_settings,
            trading_calendar=self._trading_calendar,
            paper_store=self._paper_store,
            entry_policy=self._paper_entry_policy,
        )
        self._mainline_continuity_service = MainlineContinuityService(
            settings=self._one_to_two_settings,
            market_data_provider=self._market_data_provider,
        )
        self._mainline_trend_watch_service = MainlineTrendWatchService(
            market_data_provider=self._market_data_provider,
        )
        self._paper_instruction_builder = PaperInstructionBuilder(
            settings=self._one_to_two_settings,
            entry_policy=self._paper_entry_policy,
            exit_policy=self._paper_exit_policy,
            holding_trade_days=self._paper_runtime_service.holding_trade_days,
        )
        self._k92_emotion_liquidity_service = K92EmotionLiquidityService()
        self._k92_emotion_liquidity_backtest_service = (
            K92EmotionLiquidityBacktestService()
        )
        self._missed_opportunity_service = MissedOpportunityService(
            settings=self._one_to_two_settings,
            paper_store=self._paper_store,
            notification_store=self._notification_store,
            scheduler_run_store=self._scheduler_run_store,
        )
        self._paper_decision_service = PaperTradingDecisionService(
            settings=self._one_to_two_settings,
            guard=self._paper_trading_guard,
            notify_or_prepare=self._notify_or_prepare,
            record_notification=self._record_notification,
            format_pct=self._paper_runtime_service.format_pct,
            build_holding_instruction=(
                self._paper_instruction_builder.build_holding_instruction
            ),
            positive_expectancy_candidates=(
                self._paper_runtime_service.positive_expectancy_candidates
            ),
            with_live_mainline_continuity=(
                self._mainline_continuity_service.with_live_mainline_continuity
            ),
            paper_guard_contract=self._paper_runtime_service.guard_contract,
            candidate_with_guard_position_limit=(
                self._paper_runtime_service.candidate_with_guard_position_limit
            ),
            build_trading_instruction=(
                self._paper_instruction_builder.build_trading_instruction
            ),
        )
        self._stability_review_service = StabilityReviewService(
            self._one_to_two_settings,
        )
        self._schedule_health_service = ScheduleHealthService(
            trading_calendar=self._trading_calendar,
            notification_store=self._notification_store,
            scheduler_run_store=self._scheduler_run_store,
        )
        self._end_of_day_review_service = EndOfDayReviewService(
            notify_or_prepare=self._notify_or_prepare,
            record_notification=self._record_notification,
            build_stability_report=self._stability_review_service.build_report,
            board_shadow_hint=self._board_shadow_system_hint,
            regime_label=self._market_regime_label,
        )
        self._doctor_review_service = DoctorReviewService(
            settings=self._one_to_two_settings,
            market_data_provider=self._market_data_provider,
            paper_store=self._paper_store,
            notification_store=self._notification_store,
            scheduler_state_store=self._scheduler_state_store,
            scheduler_run_store=self._scheduler_run_store,
        )
        self._beta_readiness_service = BetaReadinessService(
            build_doctor_report=self._build_beta_doctor_report,
            build_feishu_check=self._build_beta_feishu_check,
            has_feishu_delivery_config=(
                self._doctor_review_service.has_feishu_delivery_config
            ),
            send_feishu_test=self._send_beta_feishu_test,
        )
        self._commercial_readiness_service = CommercialReadinessService()
        self._execution_quality_service = ExecutionQualityService(
            market_data_provider=self._market_data_provider,
        )
        self._historical_replay_service = HistoricalReplayService(
            settings=self._one_to_two_settings,
            market_data_provider=self._market_data_provider,
            trading_calendar=self._trading_calendar,
            paper_store_factory=self._historical_paper_store,
            build_stability_report=self._stability_review_service.build_report,
            candidate_for_position=self._paper_runtime_service.candidate_for_position,
            holding_trade_days=self._paper_runtime_service.holding_trade_days,
            default_trade_date=self._default_trade_date,
            pit_data_warning=isinstance(
                self._market_data_provider,
                AkshareMarketDataProvider,
            ),
        )
        self._board_shadow_review_service = BoardShadowReviewService(
            settings=self._one_to_two_settings,
            board_shadow_store=self._board_shadow_store,
            default_trade_date=self._default_trade_date,
            notify_or_prepare=self._notify_or_prepare,
            record_notification=self._record_notification,
        )
        self._watch_phase_service = WatchPhaseService(
            paper_store=self._paper_store,
            market_data_provider=self._market_data_provider,
            policy=self._one_to_two_policy,
            guard=self._paper_trading_guard,
            positive_expectancy_candidates=(
                self._paper_runtime_service.positive_expectancy_candidates
            ),
            with_live_mainline_continuity=(
                self._mainline_continuity_service.with_live_mainline_continuity
            ),
            exit_if_discipline_requires=self._exit_if_discipline_requires,
            candidate_for_position=self._paper_runtime_service.candidate_for_position,
            candidate_with_guard_position_limit=(
                self._paper_runtime_service.candidate_with_guard_position_limit
            ),
            guard_contract=self._paper_runtime_service.guard_contract,
        )
        self._morning_report_service = MorningReportService(
            trading_calendar=self._trading_calendar,
            paper_store=self._paper_store,
            market_data_provider=self._market_data_provider,
            load_market_rows_with_timeout=self._load_market_rows_with_timeout,
            build_strategy_decision_report=self.build_strategy_decision_report,
            board_shadow_execution_candidates=self._board_shadow_execution_candidates,
            with_live_mainline_continuity=(
                self._mainline_continuity_service.with_live_mainline_continuity
            ),
            notify_or_prepare=self._notify_or_prepare,
            record_notification=self._record_notification,
            market_regime_label=self._market_regime_label,
            default_trade_date=self._default_trade_date,
        )
        self._watch_report_service = WatchReportService(
            watch_phase_service=self._watch_phase_service,
            notification_orchestrator=self._notification_orchestrator,
            build_morning_report=self.build_one_to_two_morning_report,
            build_strategy_decision_report=self.build_strategy_decision_report,
            notify_or_prepare=self._notify_or_prepare,
            record_notification=self._record_notification,
            watch_sell_event_types=self._watch_sell_event_types,
        )

    def resolve_trading_day(self, trade_date: str | None = None) -> TradingDayContext:
        """Resolve a requested date with the same calendar used by workflows."""

        return self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        ).to_contract()

    def build_schedule_health_report(
        self,
        trade_date: str | None = None,
    ) -> OneToTwoScheduleHealthReport:
        """Explain required morning/eod notification coverage."""

        return self._schedule_health_service.build_report(trade_date=trade_date)

    def build_mainline_trend_watch_report(
        self,
        trade_date: str | None = None,
        limit: int = 12,
        timeout_seconds: float | None = None,
        fast_snapshot: bool = False,
    ) -> MainlineTrendWatchReport:
        """Build a watch-only whole-market mainline trend-root report."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        resolved_limit = max(1, limit)
        scan_limit = max(8, min(resolved_limit * 2, 24))
        if timeout_seconds is None:
            return self._mainline_trend_watch_service.build_report(
                trade_date=trade_context.trade_date,
                limit=resolved_limit,
                scan_limit=scan_limit,
                fast_snapshot=fast_snapshot,
            )
        return self._build_mainline_trend_watch_report_with_timeout(
            trade_date=trade_context.trade_date,
            limit=resolved_limit,
            scan_limit=scan_limit,
            timeout_seconds=timeout_seconds,
            fast_snapshot=fast_snapshot,
        )

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        record_notification: bool = True,
        market_data_timeout_seconds: float | None = None,
        allow_cached_on_timeout: bool = True,
    ) -> OneToTwoMorningReport:
        """Build the 08:50 one-to-two report and optional Feishu notice."""

        return self._morning_report_service.build_report(
            trade_date=trade_date,
            notify=notify,
            record_notification=record_notification,
            market_data_timeout_seconds=market_data_timeout_seconds,
            allow_cached_on_timeout=allow_cached_on_timeout,
        )

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        phase: str = "scan",
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
    ) -> OneToTwoMorningReport:
        """Advance one-to-two watch events and paper-trading state."""

        return self._watch_report_service.run(
            trade_date=trade_date,
            phase=phase,
            notify=notify,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def _exit_if_discipline_requires(
        self,
        candidate: OneToTwoCandidate,
    ) -> PaperAccount:
        account = self._paper_store.load()
        if not account.positions:
            return account
        position = account.positions[0]
        if not position.can_sell_today:
            return account
        holding_trade_days = self._paper_runtime_service.holding_trade_days(
            opened_at=position.opened_at,
            trade_date=candidate.trade_date,
        )
        decision = self._paper_exit_policy.decide(position, candidate.latest_price)
        if decision is None:
            decision = self._paper_exit_policy.time_exit_decision(
                position,
                holding_trade_days,
            )
        if decision is None:
            return account
        return self._paper_store.exit_position(
            candidate,
            exit_reason=decision.exit_reason,
            message=decision.message,
            event_type=decision.event_type,
            holding_trade_days=holding_trade_days,
        )

    def _watch_sell_event_types(self) -> frozenset[OneToTwoEventType]:
        return self._notification_orchestrator.watch_sell_event_types

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
        record_notification: bool = True,
    ) -> OneToTwoEndOfDayReview:
        """Build the 15:10 one-to-two review and optional Feishu notice."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        account = self._paper_store.prepare_for_trade_date(report_date)
        try:
            rows = (
                self._load_market_rows_with_timeout(
                    report_date,
                    timeout_seconds=market_data_timeout_seconds,
                    allow_cached_on_timeout=True,
                )
                if market_data_timeout_seconds is not None
                else self._market_data_provider.load_one_to_two_rows(report_date)
            )
            data_unavailable = False
        except Exception:
            rows = ()
            data_unavailable = True
        strategy_report = self.build_strategy_decision_report(
            trade_date=report_date,
            market_rows=rows,
            data_unavailable=data_unavailable,
        )
        return self._end_of_day_review_service.build_review(
            report_date=report_date,
            trade_context=trade_context.to_contract(),
            account=account,
            data_unavailable=data_unavailable,
            regime_label=self._market_regime_label(strategy_report.market_regime),
            notify=notify and trade_context.is_trading_day,
            record_notification=record_notification,
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        """Summarize current paper-trading stability observations."""

        account = self._paper_store.load()
        return self._stability_review_service.build_report(account)

    def build_paper_trade_database_report(
        self,
        database_path: str | Path | None = None,
        limit: int = 10,
    ) -> PaperTradeDatabaseReport:
        """Read persisted paper-trading metrics from the SQLite mirror."""

        path = (
            Path(database_path)
            if database_path is not None
            else self._paper_store.path.with_suffix(".sqlite3")
        )
        if database_path is None:
            self._paper_store.save(self._paper_store.load())
        return PaperTradeDatabase(path).build_report(limit=limit)

    def send_one_to_two_feishu_test(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> FeishuNotificationResult:
        """Send or prepare a Feishu connectivity test for the one-to-two loop."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        message = "\n".join(
            (
                "今日动作：飞书链路测试，不是交易信号",
                f"交易日：{trade_context.trade_date}",
                "用途：确认早评、模拟买入、模拟卖出、尾盘复盘能送达飞书。",
                "说明：不触发模拟买入或卖出，不代表今日可以买。",
                "下一步：链路正常后保持值守常驻，到点只接收交易指挥通知。",
            )
        )
        result = self._notify_or_prepare(
            notify=notify,
            title=f"FireMoney 链路测试 | 非交易信号 | {trade_context.trade_date}",
            message=message,
        )
        self._record_notification("feishu:test", trade_context.trade_date, result)
        return result

    def build_one_to_two_beta_readiness_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoBetaReadinessReport:
        """Run the non-trading Beta readiness gate for the one-to-two loop."""

        requested_date = trade_date or self._default_trade_date()
        trade_context = self._trading_calendar.resolve(requested_date)
        return self._beta_readiness_service.build_report(
            requested_date=requested_date,
            trade_date=trade_context.trade_date,
            is_trading_day=trade_context.is_trading_day,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def _build_beta_doctor_report(
        self,
        requested_date: str,
        beta: bool,
        market_data_timeout_seconds: float,
    ) -> OneToTwoDoctorReport:
        return self.build_one_to_two_doctor_report(
            trade_date=requested_date,
            beta=beta,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def _build_beta_feishu_check(
        self,
        trade_date: str,
        beta: bool,
    ):
        return self._doctor_review_service.build_feishu_check(
            trade_date=trade_date,
            beta=beta,
        )

    def _send_beta_feishu_test(
        self,
        trade_date: str,
        notify: bool,
    ) -> FeishuNotificationResult:
        return self.send_one_to_two_feishu_test(
            trade_date=trade_date,
            notify=notify,
        )

    def build_one_to_two_doctor_report(
        self,
        trade_date: str | None = None,
        beta: bool = False,
        skip_market_data: bool = False,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoDoctorReport:
        """Check whether the one-to-two loop is ready to run locally."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        return self._doctor_review_service.build_report(
            trade_context=trade_context.to_contract(),
            beta=beta,
            skip_market_data=skip_market_data,
            market_data_timeout_seconds=market_data_timeout_seconds,
        )

    def load_notification_records(
        self,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
        action_only: bool = False,
    ) -> tuple[NotificationRecord, ...]:
        """Return recent one-to-two notification delivery records."""

        return self._notification_orchestrator.load_records(
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
        """Evaluate commercial launch gates from service-owned evidence."""

        return self._commercial_readiness_service.build_report(
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
        """Replay one-to-two samples over historical dates in an isolated ledger."""

        return self._historical_replay_service.run_backtest(
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
        """Run the backtest and wrap it with data-quality admission checks."""

        return self._historical_replay_service.build_backtest_audit(
            start_date=start_date,
            end_date=end_date,
            max_trade_days=max_trade_days,
        )

    def run_one_to_two_historical_replay(
        self,
        as_of_date: str | None = None,
        holding_days: int = 5,
    ) -> OneToTwoHistoricalReplayReport:
        """Replay one historical decision without using future bars for selection."""

        return self._historical_replay_service.run_historical_replay(
            as_of_date=as_of_date,
            holding_days=holding_days,
        )

    def build_limit_up_board_shadow_report(
        self,
        as_of_date: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> LimitUpBoardShadowReport:
        """Build a shadow report for the limit-up board validation line."""

        trade_context = self._trading_calendar.resolve(
            as_of_date or self._default_trade_date()
        )
        return self._board_shadow_review_service.build_report(
            as_of_date=trade_context.trade_date,
            cache_dir=cache_dir,
        )

    def record_limit_up_board_shadow_sample(
        self,
        as_of_date: str | None = None,
        cache_dir: str | Path | None = None,
        notify: bool = False,
    ) -> LimitUpBoardShadowReport:
        """Build and persist one limit-up board shadow sample when tradable."""

        trade_context = self._trading_calendar.resolve(
            as_of_date or self._default_trade_date()
        )
        return self._board_shadow_review_service.record_sample(
            as_of_date=trade_context.trade_date,
            cache_dir=cache_dir,
            notify=notify,
        )

    def build_limit_up_board_shadow_stability_report(
        self,
    ) -> LimitUpBoardShadowStabilityReport:
        return self._board_shadow_review_service.build_stability_report()

    def build_limit_up_board_shadow_system_report(
        self,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> LimitUpBoardShadowSystemReport:
        return self._board_shadow_review_service.build_system_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
        )

    def build_paper_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
        refresh_cache: bool = False,
    ) -> PaperBacktestReport:
        return self._paper_backtest_service.build_report(
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
        )

    def build_missed_opportunity_report(
        self,
        start_date: str,
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
        limit: int = 20,
    ) -> MissedOpportunityReport:
        return self._missed_opportunity_service.build_report(
            start_date=start_date,
            end_date=end_date or self._default_trade_date(),
            cache_dir=cache_dir,
            limit=limit,
        )

    def build_strategy_decision_report(
        self,
        trade_date: str | None = None,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
        market_data_timeout_seconds: float | None = None,
        market_rows: tuple[OneToTwoMarketRow, ...] | None = None,
        data_unavailable: bool = False,
        candidates: tuple[OneToTwoCandidate, ...] | None = None,
        market_temperature: int | None = None,
    ) -> StrategyDecisionReport:
        resolved_trade_date = trade_date or self._default_trade_date()
        resolved_data_unavailable = data_unavailable
        if resolved_data_unavailable:
            rows = ()
        elif market_rows is not None:
            rows = market_rows
        elif candidates is not None and market_temperature is not None:
            rows = ()
        else:
            try:
                rows = (
                    self._load_market_rows_with_timeout(
                        resolved_trade_date,
                        timeout_seconds=market_data_timeout_seconds,
                        allow_cached_on_timeout=True,
                    )
                    if market_data_timeout_seconds is not None
                    else self._market_data_provider.load_one_to_two_rows(resolved_trade_date)
                )
            except Exception:
                rows = ()
                resolved_data_unavailable = True
        candidates = candidates if candidates is not None else (
            self._board_shadow_execution_candidates(
                resolved_trade_date,
                rows=rows,
                include_blocked=True,
            )
            if rows
            else ()
        )
        ready_candidates = tuple(item for item in candidates if item.status == "ready")
        average_mainline_score = (
            round(
                sum(item.mainline_score for item in ready_candidates) / len(ready_candidates),
                2,
            )
            if ready_candidates
            else 0.0
        )
        average_turnover_quality_score = (
            round(
                sum(item.turnover_quality_score for item in ready_candidates)
                / len(ready_candidates),
                2,
            )
            if ready_candidates
            else 0.0
        )
        resolved_market_temperature = (
            market_temperature
            if market_temperature is not None
            else rows[0].market_temperature
            if rows
            else 0
        )
        k92_report = self._k92_emotion_liquidity_service.build_report(
            trade_date=resolved_trade_date,
            market_temperature=resolved_market_temperature,
            candidates=candidates,
        )
        return self._strategy_decision_service.build_report(
            trade_date=resolved_trade_date,
            start_date=start_date,
            end_date=end_date,
            cache_dir=cache_dir,
            market_temperature=resolved_market_temperature,
            ready_candidate_count=len(ready_candidates),
            average_mainline_score=average_mainline_score,
            average_turnover_quality_score=average_turnover_quality_score,
            k92_regime=k92_report.regime,
            k92_action=k92_report.action,
            k92_summary=k92_report.summary,
            data_unavailable=resolved_data_unavailable,
        )

    def build_k92_emotion_liquidity_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float | None = None,
    ) -> K92EmotionLiquidityReport:
        """Build a read-only K92 emotion-liquidity research report."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        try:
            rows = (
                self._load_market_rows_with_timeout(
                    report_date,
                    timeout_seconds=market_data_timeout_seconds,
                    allow_cached_on_timeout=True,
                )
                if market_data_timeout_seconds is not None
                else self._market_data_provider.load_one_to_two_rows(report_date)
            )
        except Exception:
            rows = ()
        candidates = (
            self._board_shadow_execution_candidates(
                report_date,
                rows=rows,
                include_blocked=True,
            )
            if rows
            else ()
        )
        return self._k92_emotion_liquidity_service.build_report(
            trade_date=report_date,
            market_temperature=rows[0].market_temperature if rows else 0,
            candidates=candidates,
        )

    def build_k92_emotion_liquidity_backtest_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> PaperBacktestReport:
        """Backtest K92 emotion-liquidity as a read-only research line."""

        end = end_date or self._default_trade_date()
        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        start_parsed = board_matrix.sm.parse_iso_date(start_date)
        end_parsed = board_matrix.sm.parse_iso_date(end)
        if end_parsed < start_parsed:
            raise ValueError("end_date must be on or after start_date")
        universe, histories = board_matrix.load_cached_research_data(
            cache_path,
            start_parsed,
            end_parsed,
        )
        candidates = board_matrix.build_board_candidates(
            universe,
            histories,
            start_parsed,
            end_parsed,
        )
        return self._k92_emotion_liquidity_backtest_service.build_report(
            start_date=start_date,
            end_date=end,
            candidates=candidates,
            histories=histories,
        )

    def build_paper_trading_decision_report(
        self,
        trade_date: str | None = None,
        market_data_timeout_seconds: float = 8.0,
        notify: bool = False,
        record_notification: bool = False,
    ) -> PaperTradingDecisionReport:
        """Build the daily paper-trading command sheet without mutating positions."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        try:
            rows = self._load_market_rows_with_timeout(
                report_date,
                timeout_seconds=market_data_timeout_seconds,
                allow_cached_on_timeout=True,
            )
            data_unavailable = False
        except Exception:
            rows = ()
            data_unavailable = True
        strategy_report = self.build_strategy_decision_report(
            trade_date=report_date,
            market_rows=rows,
            data_unavailable=data_unavailable,
        )
        candidates = (
            self._board_shadow_execution_candidates(
                report_date,
                rows=rows,
                include_blocked=True,
            )
            if rows and not data_unavailable
            else ()
        )
        account = self._paper_runtime_service.account_view_for_trade_date(report_date)
        return self._paper_decision_service.build_report(
            report_date=report_date,
            strategy_report=strategy_report,
            candidates=candidates,
            account=account,
            data_unavailable=data_unavailable,
            notify=notify,
            record_notification=record_notification,
        )

    def _board_shadow_execution_candidates(
        self,
        report_date: str,
        rows: tuple[OneToTwoMarketRow, ...] = (),
        cache_dir: str | Path | None = None,
        include_blocked: bool = False,
    ) -> tuple[OneToTwoCandidate, ...]:
        return self._board_shadow_execution_service.build_candidates(
            report_date=report_date,
            rows=rows,
            cache_dir=cache_dir,
            include_blocked=include_blocked,
        )

    def build_one_to_two_execution_quality_report(
        self,
        symbol: str = "600001",
        trade_date: str | None = None,
    ) -> OneToTwoExecutionQualityReport:
        resolved_trade_date = trade_date or self._default_trade_date()
        return self._execution_quality_service.build_report(
            symbol=symbol,
            trade_date=resolved_trade_date,
        )

    def run_scheduled_limit_up_board_shadow_record(
        self,
        trade_date: str | None = None,
        cache_dir: str | Path | None = None,
        notify: bool = True,
    ) -> LimitUpBoardShadowReport:
        """Record the previous trading day's board-shadow sample after T+1 data exists."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        return self.record_limit_up_board_shadow_sample(
            as_of_date=trade_context.previous_trade_date,
            cache_dir=cache_dir,
            notify=notify,
        )

    def _board_shadow_system_hint(self) -> str:
        return self._board_shadow_review_service.board_shadow_system_hint()

    @staticmethod
    def _market_regime_label(regime: str) -> str:
        return BoardShadowReviewService.market_regime_label(regime)

    @staticmethod
    def _to_paper_backtest_yearly_metric(
        year: str,
        summary: dict[str, object],
    ) -> PaperBacktestYearlyMetric:
        return PaperBacktestService._to_paper_backtest_yearly_metric(year, summary)

    def _load_market_rows_with_timeout(
        self,
        trade_date: str,
        timeout_seconds: float,
        timeout_label: str = "AkShare 行情读取",
        allow_cached_on_timeout: bool = True,
    ):
        result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

        def load_rows() -> None:
            try:
                result_queue.put(
                    (
                        "ready",
                        self._market_data_provider.load_one_to_two_rows(trade_date),
                    )
                )
            except Exception as exc:
                result_queue.put(("blocked", exc))

        worker = Thread(target=load_rows, daemon=True)
        worker.start()
        try:
            status, payload = result_queue.get(timeout=max(0.1, timeout_seconds))
        except Empty as exc:
            cached_rows = (
                self._cached_market_rows_for_timeout(trade_date)
                if allow_cached_on_timeout
                else None
            )
            if cached_rows is not None:
                return cached_rows
            raise TimeoutError(f"{timeout_label}超过 {timeout_seconds:.0f} 秒未返回") from exc
        if status == "blocked":
            cached_rows = (
                self._cached_market_rows_for_timeout(trade_date)
                if allow_cached_on_timeout
                else None
            )
            if cached_rows is not None:
                return cached_rows
            if isinstance(payload, Exception):
                raise payload
            raise RuntimeError(str(payload))
        return payload

    def _cached_market_rows_for_timeout(
        self,
        trade_date: str,
    ) -> tuple[OneToTwoMarketRow, ...] | None:
        cached_loader = getattr(
            self._market_data_provider,
            "load_cached_one_to_two_rows",
            None,
        )
        if cached_loader is None:
            return None
        try:
            return cached_loader(trade_date, allow_stale=True)
        except Exception:
            return None

    def _build_mainline_trend_watch_report_with_timeout(
        self,
        *,
        trade_date: str,
        limit: int,
        scan_limit: int,
        timeout_seconds: float,
        fast_snapshot: bool,
    ) -> MainlineTrendWatchReport:
        result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

        def build_report() -> None:
            try:
                result_queue.put(
                    (
                        "ready",
                        self._mainline_trend_watch_service.build_report(
                            trade_date=trade_date,
                            limit=limit,
                            scan_limit=scan_limit,
                            fast_snapshot=fast_snapshot,
                        ),
                    )
                )
            except Exception as exc:
                result_queue.put(("blocked", exc))

        worker = Thread(target=build_report, daemon=True)
        worker.start()
        try:
            status, payload = result_queue.get(timeout=max(0.1, timeout_seconds))
        except Empty:
            return self._mainline_trend_watch_service.build_unavailable_report(
                trade_date=trade_date,
                status="timeout",
                reason=f"全市场行情源 {timeout_seconds:.0f} 秒内未返回",
                next_action=(
                    "页面先保持真实降级状态；后台下一轮刷新或手动运行 "
                    "mainline-trend --brief 复核行情源。"
                ),
            )
        if status == "ready" and isinstance(payload, MainlineTrendWatchReport):
            return payload
        reason = str(payload) if payload else "全市场行情源异常"
        return self._mainline_trend_watch_service.build_unavailable_report(
            trade_date=trade_date,
            status="error",
            reason=reason,
            next_action="先恢复全市场行情源，再输出主升候选；本次不生成买点。",
        )

    def _historical_paper_store(self, path: Path) -> PaperTradeStore:
        return PaperTradeStore(
            path,
            initial_cash=self._one_to_two_settings.initial_cash,
            max_position_pct=self._one_to_two_settings.max_position_pct,
            max_daily_trades=self._one_to_two_settings.max_daily_trades,
        )

    def _notify_or_prepare(
        self,
        notify: bool,
        title: str,
        message: str,
    ) -> FeishuNotificationResult:
        return self._notification_orchestrator.notify_or_prepare(
            notify=notify,
            title=title,
            message=message,
        )

    def _record_notification(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
    ) -> None:
        self._notification_orchestrator.record(
            workflow=workflow,
            trade_date=trade_date,
            result=result,
        )

    def _default_trade_date(self) -> str:
        return date.today().isoformat()
