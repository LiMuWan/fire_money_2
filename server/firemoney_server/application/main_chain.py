"""Application workflow for the first FireMoney vertical slice."""

from __future__ import annotations

from pathlib import Path

from server.firemoney_server.domain.archive import TradeArchivePolicy
from server.firemoney_server.domain.archive_review import TradeArchiveReviewPolicy
from server.firemoney_server.domain.execution import ExecutionPolicy
from server.firemoney_server.domain.opportunity import OpportunityRanker
from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.domain.outcome import OutcomePolicy
from server.firemoney_server.domain.recap import RecapPolicy
from server.firemoney_server.domain.risk import RiskReviewPolicy
from server.firemoney_server.domain.signal_scan import SignalScanPolicy
from server.firemoney_server.domain.strategy_boundary_review import (
    StrategyBoundaryReviewPolicy,
)
from server.firemoney_server.domain.strategy_config import StrategyConfigPolicy
from server.firemoney_server.domain.strategy_reset_review import StrategyResetReviewPolicy
from server.firemoney_server.infrastructure.archive_store import TradeArchiveStore
from server.firemoney_server.infrastructure.archive_review_export import (
    MarkdownArchiveReviewExporter,
)
from server.firemoney_server.infrastructure.broker_adapter import (
    BrokerExecutionAdapter,
    LocalCsvBrokerAdapter,
)
from server.firemoney_server.infrastructure.export_cleanup import ExportCleanup
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.fill_import import BrokerFillImporter
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    MarketDataProvider,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
    load_one_to_two_settings,
)
from server.firemoney_server.infrastructure.order_export import CsvOrderExporter
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.receipt_import import BrokerReceiptImporter
from server.firemoney_server.infrastructure.sample_data import (
    sample_market_context,
    sample_current_price,
    sample_opportunity_candidates,
    sample_strategy_config,
    sample_universe_size,
)
from server.firemoney_server.infrastructure.strategy_audit_export import (
    MarkdownStrategyAuditExporter,
)
from server.firemoney_server.infrastructure.strategy_store import StrategyConfigStore
from shared.contracts import (
    AdjustmentStatus,
    ExportCleanupResult,
    FeishuNotificationResult,
    MainChainSnapshot,
    NotificationStatus,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoStabilityReport,
    StrategyBoundaryReview,
    StrategyConfig,
    StrategyResetReview,
    TradeArchiveReview,
    WorkflowStage,
)


class MainChainService:
    """Orchestrates the product's core chain without owning UI concerns."""

    def __init__(
        self,
        opportunity_ranker: OpportunityRanker | None = None,
        risk_policy: RiskReviewPolicy | None = None,
        archive_policy: TradeArchivePolicy | None = None,
        archive_review_policy: TradeArchiveReviewPolicy | None = None,
        execution_policy: ExecutionPolicy | None = None,
        outcome_policy: OutcomePolicy | None = None,
        recap_policy: RecapPolicy | None = None,
        signal_scan_policy: SignalScanPolicy | None = None,
        strategy_boundary_review_policy: StrategyBoundaryReviewPolicy | None = None,
        strategy_config_policy: StrategyConfigPolicy | None = None,
        strategy_reset_review_policy: StrategyResetReviewPolicy | None = None,
        strategy_store: StrategyConfigStore | None = None,
        strategy_audit_exporter: MarkdownStrategyAuditExporter | None = None,
        archive_store: TradeArchiveStore | None = None,
        archive_review_exporter: MarkdownArchiveReviewExporter | None = None,
        export_cleanup: ExportCleanup | None = None,
        one_to_two_settings: OneToTwoStrategySettings | None = None,
        market_data_provider: MarketDataProvider | None = None,
        paper_store: PaperTradeStore | None = None,
        feishu_notifier: FeishuNotifier | None = None,
        broker_adapter: BrokerExecutionAdapter | None = None,
        order_exporter: CsvOrderExporter | None = None,
        receipt_importer: BrokerReceiptImporter | None = None,
        fill_importer: BrokerFillImporter | None = None,
    ) -> None:
        self._opportunity_ranker = opportunity_ranker or OpportunityRanker()
        self._risk_policy = risk_policy or RiskReviewPolicy()
        self._archive_policy = archive_policy or TradeArchivePolicy()
        self._archive_review_policy = archive_review_policy or TradeArchiveReviewPolicy()
        self._execution_policy = execution_policy or ExecutionPolicy()
        self._outcome_policy = outcome_policy or OutcomePolicy()
        self._recap_policy = recap_policy or RecapPolicy()
        self._signal_scan_policy = signal_scan_policy or SignalScanPolicy()
        self._strategy_boundary_review_policy = (
            strategy_boundary_review_policy or StrategyBoundaryReviewPolicy()
        )
        self._strategy_config_policy = strategy_config_policy or StrategyConfigPolicy()
        self._strategy_reset_review_policy = (
            strategy_reset_review_policy or StrategyResetReviewPolicy()
        )
        self._strategy_store = strategy_store or StrategyConfigStore()
        self._strategy_audit_exporter = (
            strategy_audit_exporter or MarkdownStrategyAuditExporter()
        )
        self._archive_store = archive_store or TradeArchiveStore()
        self._archive_review_exporter = (
            archive_review_exporter or MarkdownArchiveReviewExporter()
        )
        self._export_cleanup = export_cleanup or ExportCleanup()
        self._one_to_two_settings = one_to_two_settings or load_one_to_two_settings()
        self._one_to_two_policy = OneToTwoPolicy(self._one_to_two_settings)
        self._market_data_provider = market_data_provider or AkshareMarketDataProvider()
        self._paper_store = paper_store or PaperTradeStore(
            initial_cash=self._one_to_two_settings.initial_cash,
            max_position_pct=self._one_to_two_settings.max_position_pct,
            max_daily_trades=self._one_to_two_settings.max_daily_trades,
        )
        self._feishu_notifier = feishu_notifier or FeishuNotifier()
        self._broker_adapter = broker_adapter or LocalCsvBrokerAdapter(
            order_exporter=order_exporter,
            receipt_importer=receipt_importer,
            fill_importer=fill_importer,
        )

    def reset_strategy_config(self) -> bool:
        """Restore default strategy boundaries by clearing local overrides."""

        return self._strategy_store.reset(sample_strategy_config()) is not None

    def build_strategy_reset_review(self) -> StrategyResetReview:
        """Build confirmable guidance for resetting local strategy boundaries."""

        default_strategy_config = sample_strategy_config()
        strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        return self._strategy_reset_review_policy.build_review(
            strategy_config=strategy_config,
            default_config=default_strategy_config,
            has_local_config=self._strategy_store.path.exists(),
        )

    def apply_strategy_reset_review(self, confirm: bool = False) -> StrategyConfig:
        """Reset local strategy boundaries only after explicit confirmation."""

        default_strategy_config = sample_strategy_config()
        strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        if not confirm:
            return strategy_config

        review = self._strategy_reset_review_policy.build_review(
            strategy_config=strategy_config,
            default_config=default_strategy_config,
            has_local_config=self._strategy_store.path.exists(),
        )
        if review.reset_status is not AdjustmentStatus.WAITING_USER:
            return strategy_config

        reset_config = self._strategy_store.reset(default_strategy_config)
        return reset_config or strategy_config

    def export_trade_archives(
        self,
        target_path: str | Path | None = None,
        format: str = "json",
        limit: int = 50,
    ) -> Path:
        """Export compact completed-trade archives through the service boundary."""

        return self._archive_store.export_recent(
            target_path=target_path,
            format=format,
            limit=limit,
        )

    def build_trade_archive_review(self, limit: int = 50) -> TradeArchiveReview:
        """Build a lightweight review summary from recent completed trades."""

        return self._archive_review_policy.build_review(
            self._archive_store.load_recent(limit=limit)
        )

    def export_trade_archive_review(
        self,
        target_path: str | Path | None = None,
        limit: int = 50,
    ) -> Path:
        """Export a lightweight Markdown review for recent completed trades."""

        records = self._archive_store.load_recent(limit=limit)
        review = self._archive_review_policy.build_review(records)
        return self._archive_review_exporter.export(
            review=review,
            records=records,
            target_path=target_path,
        )

    def build_strategy_boundary_review(
        self,
        limit: int = 50,
    ) -> StrategyBoundaryReview:
        """Build confirmable strategy-boundary guidance from archive review."""

        default_strategy_config = sample_strategy_config()
        strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        archive_review = self.build_trade_archive_review(limit=limit)
        return self._strategy_boundary_review_policy.build_review(
            archive_review=archive_review,
            strategy_config=strategy_config,
        )

    def apply_strategy_boundary_review(
        self,
        confirm: bool = False,
        limit: int = 50,
    ) -> StrategyConfig:
        """Apply archive-driven boundary suggestions only after confirmation."""

        default_strategy_config = sample_strategy_config()
        base_strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        if not confirm:
            return base_strategy_config

        review = self.build_strategy_boundary_review(limit=limit)
        if review.adjustment_status is not AdjustmentStatus.WAITING_USER:
            return base_strategy_config

        strategy_config = self._strategy_config_policy.apply_adjustments(
            strategy_config=base_strategy_config,
            adjustments=review.adjustments,
        )
        return self._strategy_store.save(
            strategy_config,
            previous_config=base_strategy_config,
            reason=review.summary,
        )

    def export_strategy_boundary_audit(
        self,
        target_path: str | Path | None = None,
        actions: tuple[str, ...] | None = None,
    ) -> Path:
        """Export recent local strategy-boundary changes for audit."""

        default_strategy_config = sample_strategy_config()
        strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        return self._strategy_audit_exporter.export(
            strategy_config=strategy_config,
            target_path=target_path,
            actions=actions,
        )

    def clear_trade_archives(self) -> bool:
        """Clear local completed-trade archives through the service boundary."""

        return self._archive_store.clear()

    def cleanup_archive_exports(
        self,
        retention_count: int = 1,
    ) -> ExportCleanupResult:
        """Remove older archive export files while keeping recent reports."""

        return self._export_cleanup.cleanup(
            target="archive_exports",
            directory=self._archive_store.export_dir,
            prefixes=("trade_archives", "trade_archive_review"),
            suffixes=(".json", ".csv", ".md"),
            retention_count=retention_count,
        )

    def cleanup_strategy_exports(
        self,
        retention_count: int = 1,
    ) -> ExportCleanupResult:
        """Remove older strategy audit export files while keeping recent reports."""

        return self._export_cleanup.cleanup(
            target="strategy_exports",
            directory=self._strategy_audit_exporter.export_dir,
            prefixes=("strategy_boundary_audit",),
            suffixes=(".md",),
            retention_count=retention_count,
        )

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Build the one-to-two morning report and optional Feishu notice."""

        report_date = trade_date or sample_market_context().trade_date
        try:
            rows = self._market_data_provider.load_one_to_two_rows(report_date)
            data_unavailable = False
        except Exception:
            rows = ()
            data_unavailable = True
        candidates = self._one_to_two_policy.build_candidates(rows)
        ready_count = sum(1 for item in candidates if item.status == "ready")
        status = "ready" if ready_count else "blocked"
        summary = (
            "一进二早盘：行情数据不可用，禁止生成模拟买入。"
            if data_unavailable
            else (
                f"一进二早盘：{len(candidates)} 个昨日首板样本，"
                f"{ready_count} 个进入模拟盘观察。"
            )
        )
        notification = (
            self._feishu_notifier.notify("FireMoney 一进二早盘", summary)
            if notify
            else self._notification_skipped("FireMoney 一进二早盘", summary)
        )
        return OneToTwoMorningReport(
            report_id=f"one-to-two-morning-{report_date}",
            trade_date=report_date,
            market_temperature=rows[0].market_temperature if rows else 0,
            status=status,
            summary=summary,
            candidates=candidates,
            account=self._paper_store.load(),
            notification=notification,
            next_action=(
                "等待竞价确认和事件驱动模拟盘。"
                if ready_count
                else "今日不触发模拟买入。"
            ),
        )

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Advance one-to-two watch events and paper-trading state."""

        report = self.build_one_to_two_morning_report(
            trade_date=trade_date,
            notify=False,
        )
        ready = tuple(item for item in report.candidates if item.status == "ready")
        account = self._paper_store.load()
        if ready and not account.positions:
            account = self._paper_store.buy_candidate(ready[0])
        elif account.positions:
            matched = next(
                (
                    candidate
                    for candidate in report.candidates
                    if candidate.symbol == account.positions[0].symbol
                ),
                None,
            )
            if matched:
                account = self._paper_store.update_risk(matched)
        latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
        notification = (
            self._feishu_notifier.notify("FireMoney 一进二盘中", latest_event)
            if notify
            else self._notification_skipped("FireMoney 一进二盘中", latest_event)
        )
        return OneToTwoMorningReport(
            report_id=report.report_id,
            trade_date=report.trade_date,
            market_temperature=report.market_temperature,
            status=report.status,
            summary=report.summary,
            candidates=report.candidates,
            account=account,
            notification=notification,
            next_action="继续盯住止损位和 T+1 纪律。",
        )

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoEndOfDayReview:
        """Build one-to-two end-of-day review and optional Feishu notice."""

        report_date = trade_date or sample_market_context().trade_date
        account = self._paper_store.load()
        warning_count = sum(
            1
            for event in account.events
            if event.event_type.value == "stop_warning"
        )
        sell_count = sum(
            1
            for event in account.events
            if event.event_type.value == "t1_sell"
        )
        realized_pnl = round(account.equity - account.initial_cash, 2)
        summary = (
            f"一进二尾盘：权益 {account.equity:.2f}，"
            f"事件 {len(account.events)} 个，风险预警 {warning_count} 个。"
        )
        notification = (
            self._feishu_notifier.notify("FireMoney 一进二尾盘", summary)
            if notify
            else self._notification_skipped("FireMoney 一进二尾盘", summary)
        )
        return OneToTwoEndOfDayReview(
            review_id=f"one-to-two-eod-{report_date}",
            trade_date=report_date,
            sample_count=len(account.events),
            success_count=sell_count,
            warning_count=warning_count,
            realized_pnl=realized_pnl,
            max_drawdown=min(0.0, realized_pnl),
            summary=summary,
            focus_points=(
                "样本少于 30 笔时只观察，不自动调整策略边界。",
                "继续区分低位突破与高位接力样本。",
            ),
            account=account,
            notification=notification,
            next_action="收盘后归档样本，明早继续扫描昨日首板池。",
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        """Summarize current paper-trading stability observations."""

        account = self._paper_store.load()
        sample_count = len(account.events)
        sell_count = sum(
            1
            for event in account.events
            if event.event_type.value == "t1_sell"
        )
        warning_count = sum(
            1
            for event in account.events
            if event.event_type.value == "stop_warning"
        )
        status = (
            "observation"
            if sample_count < self._one_to_two_settings.minimum_sample_for_stability
            else "reviewable"
        )
        return OneToTwoStabilityReport(
            report_id="one-to-two-stability",
            sample_count=sample_count,
            success_rate=round(sell_count / sample_count, 4) if sample_count else 0.0,
            average_return_pct=0.0,
            max_drawdown=min(0.0, account.equity - account.initial_cash),
            stop_warning_rate=round(warning_count / sample_count, 4) if sample_count else 0.0,
            low_breakout_success_rate=0.0,
            status=status,
            summary="样本处于观察期，暂不自动给出策略边界结论。"
            if status == "observation"
            else "样本达到复查门槛，可以进入策略边界评估。",
            next_action="继续积累至少 30 笔一进二样本。",
        )

    def _notification_skipped(
        self,
        title: str,
        message: str,
    ) -> FeishuNotificationResult:
        return FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title=title,
            message=message,
            webhook_configured=False,
            error="notification skipped",
        )

    def build_first_slice_snapshot(
        self,
        user_confirmed: bool = False,
        broker_submitted: bool = False,
        fill_received: bool = False,
        exit_received: bool = False,
        adjustments_confirmed: bool = False,
    ) -> MainChainSnapshot:
        """Build a deterministic snapshot for scan -> review -> confirmation."""

        market_context = sample_market_context()
        default_strategy_config = sample_strategy_config()
        base_strategy_config = self._strategy_config_policy.normalize_config(
            self._strategy_store.load_or_default(default_strategy_config),
            default_strategy_config,
        )
        strategy_config = base_strategy_config
        opportunities = self._opportunity_ranker.rank(sample_opportunity_candidates())
        signal_scan = self._signal_scan_policy.build_report(
            opportunities=opportunities,
            strategy_config=strategy_config,
            universe_size=sample_universe_size(),
            report_id=f"scan-{market_context.trade_date}-001",
        )
        selected = signal_scan.focus_opportunity
        risk_review = self._risk_policy.review(selected) if selected else None
        order_ticket = (
            self._execution_policy.draft_order(
                risk_review,
                user_confirmed=user_confirmed,
            )
            if risk_review
            else None
        )
        export_result = (
            self._broker_adapter.export_order(order_ticket)
            if order_ticket and user_confirmed
            else None
        )
        receipt = (
            self._execution_policy.prepare_receipt(
                order_ticket,
                exported_path=export_result.path,
            )
            if order_ticket and export_result
            else None
        )
        if receipt and broker_submitted:
            imported_receipt = self._broker_adapter.import_receipt(
                receipt.order_id,
            )
            if imported_receipt:
                receipt = self._execution_policy.reconcile_receipt(
                    receipt=receipt,
                    status=imported_receipt.status,
                    submitted_at=imported_receipt.submitted_at,
                    message=imported_receipt.message,
                    next_action=imported_receipt.next_action,
                    failure_reason=imported_receipt.failure_reason,
                )
        fill_execution = (
            self._broker_adapter.import_entry_fill(order_ticket)
            if order_ticket and receipt and receipt.accepted and fill_received
            else None
        )
        exit_execution = (
            self._broker_adapter.import_exit_fill(fill_execution)
            if fill_execution and exit_received
            else None
        )
        outcome_card = (
            self._outcome_policy.build_outcome(
                fill_execution=fill_execution,
                risk_review=risk_review,
                current_price=sample_current_price(fill_execution.symbol),
                exit_execution=exit_execution,
            )
            if fill_execution and risk_review
            else None
        )
        recap = (
            self._recap_policy.build_recap(
                receipt=receipt,
                risk_review=risk_review,
                strategy_config=strategy_config,
                fill_execution=fill_execution,
                exit_execution=exit_execution,
                outcome_card=outcome_card,
            )
            if receipt and risk_review
            else None
        )
        archive_record = (
            self._archive_policy.build_record(
                market_context=market_context,
                signal_scan=signal_scan,
                risk_review=risk_review,
                fill_execution=fill_execution,
                exit_execution=exit_execution,
                outcome_card=outcome_card,
                recap=recap,
            )
            if fill_execution and exit_execution and outcome_card and recap and risk_review
            else None
        )
        recent_archives = (
            self._archive_store.save(archive_record)
            if archive_record
            else self._archive_store.load_recent(limit=3)
        )
        if recap and adjustments_confirmed:
            strategy_config = self._strategy_config_policy.apply_adjustments(
                strategy_config=base_strategy_config,
                adjustments=recap.strategy_adjustments,
            )
            strategy_config = self._strategy_store.save(
                strategy_config,
                previous_config=base_strategy_config,
            )
        else:
            strategy_config = self._strategy_config_policy.mark_waiting_adjustment(
                strategy_config=base_strategy_config,
                recap=recap,
            )

        next_stage = (
            WorkflowStage.STRATEGY_IMPROVEMENT
            if recap and not adjustments_confirmed
            else WorkflowStage.SIGNAL_SCAN
            if recap and adjustments_confirmed
            else WorkflowStage.ORDER_DRAFT
            if order_ticket
            else WorkflowStage.SIGNAL_SCAN
        )

        return MainChainSnapshot(
            market_context=market_context,
            signal_scan=signal_scan,
            opportunities=opportunities,
            selected_opportunity=selected,
            risk_review=risk_review,
            order_ticket=order_ticket,
            execution_receipt=receipt,
            fill_execution=fill_execution,
            exit_execution=exit_execution,
            outcome_card=outcome_card,
            archive_record=archive_record,
            recent_archives=recent_archives,
            recap=recap,
            strategy_config=strategy_config,
            next_stage=next_stage,
        )
