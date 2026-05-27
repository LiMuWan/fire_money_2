"""Preview-only data assembly for the FireMoney one-to-two interface."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.one_to_two_config import load_one_to_two_settings
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar
from shared.contracts import (
    BacktestDataQualityCheck,
    CommercialReadinessReport,
    FeishuNotificationResult,
    LimitUpBoardShadowSystemMetric,
    LimitUpBoardShadowSystemReport,
    MainlineTrendWatchReport,
    NotificationRecord,
    NotificationStatus,
    OneToTwoBacktestAuditReport,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    OneToTwoScheduleRun,
    OneToTwoScheduleTask,
    OneToTwoStabilityReport,
    PaperBacktestEfficiencyCandidate,
    PaperBacktestFrictionScenario,
    PaperBacktestMonthlyMetric,
    PaperBacktestMonthlyStability,
    PaperBacktestReport,
    PaperBacktestReturnTarget,
    PaperBacktestYearlyMetric,
    PaperAccount,
    PaperTradeDatabaseReport,
    PaperTradeRecord,
    PaperTradingDecisionReport,
    StrategyDecisionReport,
    contract_to_dict,
)

from .composition import build_local_main_chain_context


PREVIEW_TRADE_DATE = "2026-04-30"
PREVIEW_CREATED_AT = "20260430093100"
PAPER_BACKTEST_PREVIEW_CACHE_VERSION = 5
BOARD_SHADOW_SYSTEM_PREVIEW_CACHE_VERSION = 1


@dataclass(frozen=True)
class PreviewWorkflowData:
    """All service-owned reports needed by the static preview renderer."""

    report: OneToTwoMorningReport
    watch_report: OneToTwoMorningReport
    eod_review: OneToTwoEndOfDayReview
    stability_report: OneToTwoStabilityReport
    board_shadow_system_report: Any
    paper_backtest_report: PaperBacktestReport
    strategy_decision_report: StrategyDecisionReport
    paper_decision_report: PaperTradingDecisionReport
    paper_database_report: PaperTradeDatabaseReport
    trend_watch_report: MainlineTrendWatchReport
    doctor_report: OneToTwoDoctorReport
    schedule_run: OneToTwoScheduleRun
    schedule_health_report: OneToTwoScheduleHealthReport
    notification_records: tuple[NotificationRecord, ...]
    backtest_audit: OneToTwoBacktestAuditReport
    commercial_readiness_report: CommercialReadinessReport


class ReadOnlyPaperTradeStore(PaperTradeStore):
    """Paper store view used by the public preview so rendering does not trade."""

    def prepare_for_trade_date(self, trade_date: str) -> PaperAccount:
        return _account_view_for_trade_date(self.load(), trade_date)

    def save(self, account: PaperAccount) -> PaperAccount:
        self._database.sync_account(account)
        return account


class PreviewRiskBreakMarketDataProvider:
    """Preview-only snapshot that shows the same-day stop-warning state."""

    def __init__(self, base_provider: SampleMarketDataProvider) -> None:
        self._base_provider = base_provider

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        rows = self._base_provider.load_one_to_two_rows(trade_date)
        if not rows:
            return rows
        warning_row = replace(
            rows[0],
            latest_price=9.8,
            open_pct=0.03,
            ma_5=9.3,
            ma_10=9.2,
            ma_20=9.1,
            recent_gain_pct=0.12,
        )
        return (warning_row, *rows[1:])

    def load_mainline_news(self, theme: str, symbols: tuple[str, ...]):
        return self._base_provider.load_mainline_news(theme, symbols)

    def load_full_market_rows(self, trade_date: str):
        return self._base_provider.load_full_market_rows(trade_date)

    def load_price_bars(self, symbol: str, start_date: str, end_date: str):
        return self._base_provider.load_price_bars(symbol, start_date, end_date)

    def load_fundamental_snapshot(self, symbol: str):
        return self._base_provider.load_fundamental_snapshot(symbol)


def build_preview_workflow_data(preview_root: Path) -> PreviewWorkflowData:
    """Build isolated preview reports without touching the live paper ledger."""

    paper_store = PaperTradeStore(preview_root / "paper_trades.json")
    _seed_preview_closed_sample(paper_store)
    notification_store = NotificationRecordStore(
        preview_root / "notifications.json",
        created_at_provider=lambda: PREVIEW_CREATED_AT,
    )
    trading_calendar = WeekdayTradingCalendar()
    sample_provider = SampleMarketDataProvider()
    context = build_local_main_chain_context(
        paper_store=paper_store,
        market_data_provider=sample_provider,
        notification_store=notification_store,
        trading_calendar=trading_calendar,
    )
    adapter = context.adapter
    one_to_two_report = adapter.build_one_to_two_morning_report(
        trade_date=PREVIEW_TRADE_DATE,
        notify=False,
    )
    paper_decision_report = adapter.build_paper_trading_decision_report(
        trade_date=PREVIEW_TRADE_DATE,
        record_notification=False,
    )
    adapter.run_one_to_two_watch(
        trade_date=PREVIEW_TRADE_DATE,
        phase="scan",
        notify=False,
    )
    adapter.run_one_to_two_watch(
        trade_date=PREVIEW_TRADE_DATE,
        phase="auction",
        notify=False,
    )
    adapter.run_one_to_two_watch(
        trade_date=PREVIEW_TRADE_DATE,
        phase="open",
        notify=False,
    )
    risk_context = build_local_main_chain_context(
        paper_store=paper_store,
        market_data_provider=PreviewRiskBreakMarketDataProvider(sample_provider),
        notification_store=notification_store,
        trading_calendar=trading_calendar,
    )
    risk_adapter = risk_context.adapter
    one_to_two_watch_report = risk_adapter.run_one_to_two_watch(
        trade_date=PREVIEW_TRADE_DATE,
        phase="risk",
        notify=False,
    )
    one_to_two_eod_review = risk_adapter.build_one_to_two_end_of_day_review(
        trade_date=PREVIEW_TRADE_DATE,
        notify=False,
    )
    stability_report = risk_adapter.build_one_to_two_stability_report()
    paper_database_report = risk_adapter.build_paper_trade_database_report()
    doctor_report = risk_adapter.build_one_to_two_doctor_report(
        trade_date=PREVIEW_TRADE_DATE,
    )
    schedule_health_report = risk_adapter.build_schedule_health_report(
        trade_date=PREVIEW_TRADE_DATE,
    )
    notification_records = adapter.load_notification_records(action_only=True)
    paper_backtest_report = _load_or_build_paper_backtest_report(
        risk_adapter,
        start_date="2020-01-01",
        end_date=_preview_backtest_end_date(),
    )
    return PreviewWorkflowData(
        report=one_to_two_report,
        watch_report=one_to_two_watch_report,
        eod_review=one_to_two_eod_review,
        stability_report=stability_report,
        board_shadow_system_report=_load_or_build_board_shadow_system_report(
            risk_adapter,
            start_date="2024-01-01",
            end_date="2026-05-05",
        ),
        paper_backtest_report=paper_backtest_report,
        strategy_decision_report=risk_adapter.build_strategy_decision_report(
            trade_date=PREVIEW_TRADE_DATE,
        ),
        paper_decision_report=paper_decision_report,
        paper_database_report=paper_database_report,
        trend_watch_report=risk_adapter.build_mainline_trend_watch_report(
            trade_date=PREVIEW_TRADE_DATE,
            limit=12,
        ),
        doctor_report=doctor_report,
        schedule_run=_build_preview_schedule_run(one_to_two_report.trade_context),
        schedule_health_report=schedule_health_report,
        notification_records=notification_records,
        backtest_audit=risk_adapter.build_one_to_two_backtest_audit(
            end_date=PREVIEW_TRADE_DATE,
            max_trade_days=30,
        ),
        commercial_readiness_report=risk_adapter.build_commercial_readiness_report(
            report=one_to_two_report,
            schedule_health_report=schedule_health_report,
            paper_database_report=paper_database_report,
            paper_backtest_report=paper_backtest_report,
            doctor_report=doctor_report,
            notification_records=notification_records,
        ),
    )


def build_live_workflow_data() -> PreviewWorkflowData:
    """Build the public server page from real current runtime state."""

    paper_store = ReadOnlyPaperTradeStore()
    context = build_local_main_chain_context(paper_store=paper_store)
    adapter = context.adapter
    trade_context = context.service.resolve_trading_day()
    trade_date = trade_context.trade_date
    morning_report = adapter.build_one_to_two_morning_report(
        trade_date=trade_date,
        notify=False,
        record_notification=False,
        market_data_timeout_seconds=20,
    )
    paper_decision_report = adapter.build_paper_trading_decision_report(
        trade_date=trade_date,
        market_data_timeout_seconds=20,
        notify=False,
        record_notification=False,
    )
    stability_report = adapter.build_one_to_two_stability_report()
    paper_database_report = adapter.build_paper_trade_database_report(limit=20)
    doctor_report = adapter.build_one_to_two_doctor_report(
        trade_date=trade_date,
        market_data_timeout_seconds=20,
    )
    schedule_health_report = adapter.build_schedule_health_report(
        trade_date=trade_date,
    )
    notification_records = tuple(
        record
        for record in adapter.load_notification_records(action_only=True, limit=50)
        if record.trade_date == trade_date
    )
    live_account = _account_view_for_trade_date(paper_store.load(), trade_date)
    paper_database_report = _today_paper_database_report(
        paper_database_report,
        trade_date=trade_date,
    )
    watch_report = _build_live_watch_report(
        report=morning_report,
        account=live_account,
    )
    eod_review = _build_live_eod_review(
        trade_context=trade_context,
        account=live_account,
        stability_report=stability_report,
    )
    paper_backtest_report = _load_cached_or_unavailable_paper_backtest_report(
        start_date="2020-01-01",
        end_date=_preview_backtest_end_date(),
    )
    board_shadow_system_report = _load_cached_or_unavailable_board_shadow_system_report(
        start_date="2024-01-01",
        end_date="2026-05-05",
    )
    return PreviewWorkflowData(
        report=morning_report,
        watch_report=watch_report,
        eod_review=eod_review,
        stability_report=stability_report,
        board_shadow_system_report=board_shadow_system_report,
        paper_backtest_report=paper_backtest_report,
        strategy_decision_report=context.service.build_strategy_decision_report(
            trade_date=trade_date,
            market_data_timeout_seconds=20,
        ),
        paper_decision_report=paper_decision_report,
        paper_database_report=paper_database_report,
        trend_watch_report=adapter.build_mainline_trend_watch_report(
            trade_date=trade_date,
            limit=12,
        ),
        doctor_report=doctor_report,
        schedule_run=_build_live_schedule_run(trade_context, schedule_health_report),
        schedule_health_report=schedule_health_report,
        notification_records=notification_records,
        backtest_audit=_build_live_backtest_audit(paper_backtest_report),
        commercial_readiness_report=adapter.build_commercial_readiness_report(
            report=morning_report,
            schedule_health_report=schedule_health_report,
            paper_database_report=paper_database_report,
            paper_backtest_report=paper_backtest_report,
            doctor_report=doctor_report,
            notification_records=notification_records,
        ),
    )


def _preview_backtest_end_date() -> str:
    return date.today().isoformat()


def _account_view_for_trade_date(account: PaperAccount, trade_date: str) -> PaperAccount:
    if not account.last_trade_date:
        return replace(account, last_trade_date=trade_date, daily_trade_count=0)
    if trade_date <= account.last_trade_date:
        return account
    positions = tuple(
        replace(
            position,
            can_sell_today=True,
            risk_note="已进入下一交易日，若继续跌破止损可模拟卖出。",
        )
        for position in account.positions
    )
    return replace(
        account,
        last_trade_date=trade_date,
        daily_trade_count=0,
        positions=positions,
    )


def _build_live_watch_report(
    *,
    report: OneToTwoMorningReport,
    account: PaperAccount,
) -> OneToTwoMorningReport:
    latest_event = account.events[0].message if account.events else "暂无新的模拟盘事件。"
    ready = tuple(candidate for candidate in report.candidates if candidate.status == "ready")
    if account.positions:
        position = account.positions[0]
        action = f"持仓风控 {position.name}（{position.symbol}）"
        detail = (
            f"持仓成本：{position.entry_price}；当前市值 {position.position_value:.2f}\n"
            f"成本 {position.entry_price}，现价 {position.latest_price}，止损 {position.stop_loss}\n"
            f"纪律状态：{'可按纪律卖出' if position.can_sell_today else 'T+1 未到，只预警不卖出'}"
        )
    elif ready:
        candidate = ready[0]
        action = f"观察 {candidate.name}（{candidate.symbol}）"
        detail = (
            f"观察候选：{candidate.name}（{candidate.symbol}） 分数 {candidate.score}\n"
            f"标签：{candidate.leader_label or candidate.position_profile.label}；"
            f"换手质量 {candidate.turnover_quality_score}/100；"
            f"封板 {candidate.sealing_score}/20；买入参考 {candidate.entry_price}；止损 {candidate.stop_loss}\n"
            f"仓位上限：{candidate.position_limit_pct:.0%}；状态：{candidate.status}"
        )
    else:
        action = "空仓"
        detail = "当前无可执行候选。"
    notification = FeishuNotificationResult(
        status=NotificationStatus.PREPARED,
        title=f"FireMoney 主线首板实时快照 | {report.trade_date}",
        message="\n".join(
            (
                f"今日动作：{action}",
                f"交易日：{report.trade_date}",
                "阶段：公网实时快照",
                detail,
                f"最新事件：{latest_event}",
                "提醒：模拟盘不是实盘，不连接真实账户，不自动下单。",
            )
        ),
        webhook_configured=False,
        error="live preview read-only snapshot",
    )
    return replace(
        report,
        account=account,
        notification=notification,
        next_action="继续读取真实值守和模拟盘账本；页面本身不写入买卖事件。",
    )


def _build_live_eod_review(
    *,
    trade_context,
    account: PaperAccount,
    stability_report: OneToTwoStabilityReport,
) -> OneToTwoEndOfDayReview:
    report_date = trade_context.trade_date
    same_day_closed = tuple(
        record for record in account.closed_trades if record.closed_at == report_date
    )
    warning_count = sum(
        1
        for event in account.events
        if str(getattr(event.event_type, "value", event.event_type)) == "stop_warning"
        and event.trade_date == report_date
    )
    realized_pnl = round(sum(record.realized_pnl for record in same_day_closed), 2)
    latest_today = same_day_closed[0] if same_day_closed else None
    notification = FeishuNotificationResult(
        status=NotificationStatus.PREPARED,
        title=f"FireMoney 尾盘实时快照 | {report_date}",
        message="\n".join(
            (
                f"今日动作：{'持仓观察' if account.positions else '防守空仓'}",
                f"交易日：{report_date}",
                f"交易结果：今日事件 {len(account.events)}，止损预警 {warning_count}，已实现盈亏 {realized_pnl:.2f}",
                f"稳定性：已归档 {len(account.closed_trades)} 笔，阶段 {stability_report.sample_stage}",
                "今日闭环：暂无完成样本，继续按主线首板闭环观察。"
                if latest_today is None
                else (
                    f"今日闭环：{latest_today.name}"
                    f"（{latest_today.symbol}），"
                    f"收益 {latest_today.realized_pnl_pct:.2%}"
                ),
                "纪律：公网页只读展示尾盘状态，不生成尾盘通知记录。",
                "下一步：等待 15:10 值守复盘或查看真实通知记录。",
            )
        ),
        webhook_configured=False,
        error="live preview read-only snapshot",
    )
    return OneToTwoEndOfDayReview(
        review_id=f"live-eod-{report_date}",
        trade_date=report_date,
        trade_context=trade_context,
        sample_count=len(same_day_closed),
        success_count=sum(1 for record in same_day_closed if record.success),
        warning_count=warning_count,
        realized_pnl=realized_pnl,
        max_drawdown=stability_report.max_drawdown,
        stability_stage=stability_report.sample_stage,
        next_milestone=stability_report.next_milestone,
        strategy_boundary_suggestion=stability_report.strategy_boundary_suggestion,
        summary="公网实时页只读展示真实模拟盘状态；尾盘复盘以 15:10 值守结果为准。",
        focus_points=(
            "页面刷新不触发买入、卖出或尾盘通知。",
            "查看通知记录和模拟盘账本确认真实闭环。",
        ),
        account=account,
        notification=notification,
        next_action="等待 15:10 值守复盘或查看真实通知记录。",
    )


def _today_paper_database_report(
    report: PaperTradeDatabaseReport,
    *,
    trade_date: str,
) -> PaperTradeDatabaseReport:
    return replace(
        report,
        recent_events=tuple(
            event for event in report.recent_events if event.trade_date == trade_date
        ),
        daily_audits=tuple(
            audit for audit in report.daily_audits if audit.trade_date == trade_date
        ),
    )


def _build_live_schedule_run(
    trade_context,
    schedule_health_report: OneToTwoScheduleHealthReport,
) -> OneToTwoScheduleRun:
    now = datetime.now()
    requested_time = now.strftime("%H:%M")
    workflow_status = {
        item.workflow: item.schedule_status
        for item in schedule_health_report.items
    }
    tasks = (
        _live_task(
            "strategy-decision",
            "strategy-decision",
            None,
            "08:45",
            workflow_status.get("strategy-decision", "pending"),
        ),
        _live_task("morning", "morning", None, "08:50", workflow_status.get("morning", "pending")),
        _live_task(
            "paper-decision",
            "paper-decision",
            None,
            "09:00",
            workflow_status.get("paper-decision", "pending"),
        ),
        _live_task(
            "watch-open",
            "watch",
            "open",
            "09:31",
            workflow_status.get("watch:open", "pending"),
        ),
        _live_task("eod", "eod", None, "15:10", workflow_status.get("eod", "pending")),
    )
    return OneToTwoScheduleRun(
        run_id=f"live-preview-{trade_context.trade_date}-{requested_time}",
        trade_date=trade_context.trade_date,
        trade_context=trade_context,
        requested_time=requested_time,
        due_count=sum(1 for task in tasks if task.status != "pending"),
        executed_count=sum(1 for task in tasks if task.status == "completed"),
        skipped_count=sum(1 for task in tasks if task.status == "skipped"),
        tasks=tasks,
        next_action="公网页只读展示真实当天状态；交易事件只由 beta-start 值守到点触发。",
    )


def _live_task(
    task_id: str,
    mode: str,
    phase: str | None,
    scheduled_time: str,
    status: str,
) -> OneToTwoScheduleTask:
    return OneToTwoScheduleTask(
        task_id=task_id,
        mode=mode,
        phase=phase,
        scheduled_time=scheduled_time,
        status=status if status != "not_seen" else "pending",
        message="公网实时页：读取调度审计状态，不在页面生成交易事件。",
        notification_status=NotificationStatus.PREPARED,
    )


def _build_preview_schedule_run(trade_context) -> OneToTwoScheduleRun:
    tasks = (
        OneToTwoScheduleTask(
            task_id="preview-morning",
            mode="morning",
            phase=None,
            scheduled_time="08:50",
            status="completed",
            message="预览样例：早评已生成。",
            notification_status=NotificationStatus.PREPARED,
        ),
        OneToTwoScheduleTask(
            task_id="preview-paper-decision",
            mode="paper-decision",
            phase=None,
            scheduled_time="09:20",
            status="completed",
            message="预览样例：模拟盘指挥单已生成。",
            notification_status=NotificationStatus.PREPARED,
        ),
        OneToTwoScheduleTask(
            task_id="preview-watch-open",
            mode="watch",
            phase="open",
            scheduled_time="09:31",
            status="completed",
            message="预览样例：开盘确认已写入模拟买入。",
            notification_status=NotificationStatus.PREPARED,
        ),
        OneToTwoScheduleTask(
            task_id="preview-watch-risk",
            mode="watch",
            phase="risk",
            scheduled_time="14:50",
            status="completed",
            message="预览样例：风险复核已执行。",
            notification_status=NotificationStatus.PREPARED,
        ),
        OneToTwoScheduleTask(
            task_id="preview-eod",
            mode="eod",
            phase=None,
            scheduled_time="15:10",
            status="completed",
            message="预览样例：尾盘复盘已生成。",
            notification_status=NotificationStatus.PREPARED,
        ),
    )
    return OneToTwoScheduleRun(
        run_id=f"preview-schedule-{PREVIEW_TRADE_DATE}-1520",
        trade_date=PREVIEW_TRADE_DATE,
        trade_context=trade_context,
        requested_time="15:20",
        due_count=len(tasks),
        executed_count=len(tasks),
        skipped_count=0,
        tasks=tasks,
        next_action="真实值守请运行 schedule --loop；预览页只展示调度节奏，不重复触发业务。",
    )


def _seed_preview_closed_sample(paper_store: PaperTradeStore) -> None:
    account = paper_store.load()
    settings = load_one_to_two_settings()
    initial_cash = float(settings.initial_cash)
    paper_store.save(
        PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=initial_cash,
            initial_cash=initial_cash,
            equity=initial_cash,
            max_position_pct=float(settings.max_position_pct),
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=account.positions,
            events=account.events,
            closed_trades=(
                PaperTradeRecord(
                    trade_id="preview-600018-20260428-20260429",
                    symbol="600018",
                    name="低位换手样本",
                    opened_at="2026-04-28",
                    closed_at="2026-04-29",
                    entry_price=10.0,
                    exit_price=10.38,
                    quantity=100,
                    entry_amount=1000.0,
                    exit_amount=1038.0,
                    realized_pnl=38.0,
                    realized_pnl_pct=0.038,
                    holding_trade_days=1,
                    exit_reason="discipline_take_profit",
                    position_label="低位平台突破",
                    success=True,
                    warning_count=0,
                    max_favorable_pct=0.042,
                    max_adverse_pct=0.012,
                    profit_drawdown_ratio=3.1667,
                ),
            ),
        )
    )


def _load_or_build_paper_backtest_report(
    adapter,
    *,
    start_date: str,
    end_date: str,
) -> PaperBacktestReport:
    cache_path = (
        Path(".firemoney")
        / "reports"
        / f"paper_backtest_{start_date}_to_{end_date}.json"
    )
    cached = _read_paper_backtest_report(cache_path, requested_end_date=end_date)
    if cached is not None and cached.return_target is not None:
        return cached
    try:
        report = adapter.build_paper_backtest_report(
            start_date=start_date,
            end_date=end_date,
        )
    except BaseException as exc:
        if cached is not None:
            return cached
        return _paper_backtest_unavailable_report(start_date, end_date, exc)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = contract_to_dict(report)
    payload["preview_cache_version"] = PAPER_BACKTEST_PREVIEW_CACHE_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_cached_or_unavailable_paper_backtest_report(
    *,
    start_date: str,
    end_date: str,
) -> PaperBacktestReport:
    cache_path = _paper_backtest_cache_path(start_date=start_date, end_date=end_date)
    cached = _read_paper_backtest_report(cache_path, requested_end_date=end_date)
    if cached is not None:
        return cached
    latest_cached = _read_latest_paper_backtest_report(
        start_date=start_date,
        requested_end_date=end_date,
    )
    if latest_cached is not None:
        return latest_cached
    return _paper_backtest_unavailable_report(
        start_date,
        end_date,
        RuntimeError("live preview uses cached backtest only"),
    )


def _paper_backtest_cache_path(*, start_date: str, end_date: str) -> Path:
    return (
        Path(".firemoney")
        / "reports"
        / f"paper_backtest_{start_date}_to_{end_date}.json"
    )


def _read_latest_paper_backtest_report(
    *,
    start_date: str,
    requested_end_date: str,
) -> PaperBacktestReport | None:
    reports_dir = Path(".firemoney") / "reports"
    prefix = f"paper_backtest_{start_date}_to_"
    candidates = sorted(
        (
            path
            for path in reports_dir.glob(f"{prefix}*.json")
            if "_refreshed" not in path.stem
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for path in candidates:
        cached = _read_paper_backtest_report(
            path,
            requested_end_date=requested_end_date,
            allow_partial_current_month=True,
        )
        if cached is not None:
            return _with_requested_backtest_month_note(
                cached,
                requested_end_date=requested_end_date,
            )
    return None


def _with_requested_backtest_month_note(
    report: PaperBacktestReport,
    *,
    requested_end_date: str,
) -> PaperBacktestReport:
    requested_month = requested_end_date[:7] if len(requested_end_date) >= 7 else ""
    if not requested_month:
        return report
    current_month = next((item for item in report.monthly if item.month == requested_month), None)
    if current_month is not None:
        note = (
            f"本月回测：{current_month.month} 已纳入，收益 "
            f"{current_month.position_weighted_return_pct:.2%}，"
            f"{current_month.conclusion}。"
        )
    else:
        note = (
            f"本月回测：当前读取最近历史缓存 {report.end_date}；"
            f"{requested_month} 尚未完整纳入，历史和本年度曲线仍可参考。"
        )
    return replace(report, current_month_notes=(note,))


def _load_or_build_board_shadow_system_report(
    adapter,
    *,
    start_date: str,
    end_date: str,
) -> LimitUpBoardShadowSystemReport:
    cache_path = (
        Path(".firemoney")
        / "reports"
        / f"board_shadow_system_{start_date}_to_{end_date}.json"
    )
    cached = _read_board_shadow_system_report(cache_path)
    if cached is not None:
        return cached
    try:
        report = adapter.build_limit_up_board_shadow_system_report(
            start_date=start_date,
            end_date=end_date,
        )
    except BaseException as exc:
        return _board_shadow_system_unavailable_report(start_date, end_date, exc)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = contract_to_dict(report)
    payload["preview_cache_version"] = BOARD_SHADOW_SYSTEM_PREVIEW_CACHE_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_cached_or_unavailable_board_shadow_system_report(
    *,
    start_date: str,
    end_date: str,
) -> LimitUpBoardShadowSystemReport:
    cache_path = (
        Path(".firemoney")
        / "reports"
        / f"board_shadow_system_{start_date}_to_{end_date}.json"
    )
    cached = _read_board_shadow_system_report(cache_path)
    if cached is not None:
        return cached
    return _board_shadow_system_unavailable_report(
        start_date,
        end_date,
        RuntimeError("live preview uses cached board-shadow evidence only"),
    )


def _build_live_backtest_audit(
    paper_backtest_report: PaperBacktestReport,
) -> OneToTwoBacktestAuditReport:
    status = "ready" if paper_backtest_report.status == "ready" else "warning"
    check = BacktestDataQualityCheck(
        check_id="live_preview_cached_backtest",
        label="实时页历史证据",
        status=status,
        detail="公网实时页只读取历史回测缓存，不在每分钟刷新时重跑历史回测。",
        next_action="需要刷新历史证据时离线运行 paper-backtest/backtest-audit。",
    )
    return OneToTwoBacktestAuditReport(
        report_id=f"live-backtest-audit-{paper_backtest_report.end_date}",
        start_date=paper_backtest_report.start_date,
        end_date=paper_backtest_report.end_date,
        requested_trade_days=0,
        usable_trade_days=0,
        data_quality_checks=(check,),
        stability_report=_stability_from_paper_backtest(paper_backtest_report),
        status=status,
        summary="实时页未重跑历史回测；历史证据来自缓存，今日运行状态仍实时读取。",
        limitations=(
            "实时刷新优先保证今日行情、飞书、模拟盘账本和调度状态。",
            "历史回测缓存缺失时不阻塞公网页面刷新。",
        ),
        recommended_next_action="离线刷新历史证据后，实时页会读取新的缓存结果。",
    )


def _stability_from_paper_backtest(
    report: PaperBacktestReport,
) -> OneToTwoStabilityReport:
    return OneToTwoStabilityReport(
        report_id=f"live-backtest-stability-{report.end_date}",
        sample_count=report.overall.sample_count,
        sample_stage="历史回测缓存",
        next_milestone=0,
        success_rate=report.overall.win_rate,
        average_return_pct=report.overall.position_weighted_return_pct,
        max_drawdown=report.overall.max_drawdown_pct,
        stop_warning_rate=0.0,
        low_breakout_success_rate=report.overall.win_rate,
        position_label_distribution={},
        exit_reason_distribution={},
        recent_samples=(),
        status=report.status,
        summary=report.summary,
        strategy_boundary_suggestion="实时页不重跑历史回测，避免阻塞当天值守页面。",
        next_action="需要历史样本明细时离线刷新回测缓存。",
    )


def _empty_backtest_metric(label: str) -> LimitUpBoardShadowSystemMetric:
    return LimitUpBoardShadowSystemMetric(
        label=label,
        sample_count=0,
        win_rate=0.0,
        position_weighted_return_pct=0.0,
        max_drawdown_pct=0.0,
    )


def _paper_backtest_unavailable_report(
    start_date: str,
    end_date: str,
    exc: BaseException,
) -> PaperBacktestReport:
    detail = str(exc) or exc.__class__.__name__
    return PaperBacktestReport(
        report_id=f"paper-backtest-{start_date}-to-{end_date}-unavailable",
        start_date=start_date,
        end_date=end_date,
        status="blocked",
        strategy_id="board-shadow-system",
        summary="回测证据暂不可用，预览页仍优先刷新今日值守状态。",
        overall=_empty_backtest_metric("回测证据不可用"),
        train=_empty_backtest_metric("训练段不可用"),
        validation=_empty_backtest_metric("验证段不可用"),
        yearly=(),
        negative_years=(),
        weak_years=(),
        buy_rule_summary=(
            "研究缓存缺失或不可读时，不阻塞首页和值守状态刷新。",
        ),
        improvement_notes=(
            f"回测生成失败：{detail}",
        ),
        no_future_leakage_notes=(
            "当前为降级报告，没有生成新的历史回测结论。",
        ),
        limitations=(
            "证据中心缺少研究缓存时，只能查看今日运行状态和模拟盘指挥，不应解读为回测通过。",
        ),
        next_action="先修复 .firemoney/research_cache/one_to_two_daily 或重新生成回测缓存。",
        data_coverage_start="",
        data_coverage_end="",
        data_coverage_notes=(f"回测证据不可用：{detail}",),
        friction_scenarios=(),
        return_target=None,
        efficiency_candidates=(),
        monthly_stability=None,
        monthly=(),
        current_month_notes=("本月回测暂不可用，等待研究缓存恢复。",),
    )


def _board_shadow_system_unavailable_report(
    start_date: str,
    end_date: str,
    exc: BaseException,
) -> LimitUpBoardShadowSystemReport:
    detail = str(exc) or exc.__class__.__name__
    return LimitUpBoardShadowSystemReport(
        report_id=f"board-shadow-system-{start_date}-to-{end_date}-unavailable",
        start_date=start_date,
        end_date=end_date,
        status="blocked",
        system_name="龙虎榜雷达",
        summary="龙虎榜雷达证据暂不可用，预览页仍优先刷新今日值守状态。",
        buy_rules=("研究缓存缺失或不可读时，不阻塞首页刷新。",),
        sell_rules=(),
        position_rules=(),
        fixed_position_summary=_empty_backtest_metric("固定仓位不可用"),
        fixed_position_validation=_empty_backtest_metric("固定仓位验证不可用"),
        dynamic_position_summary=_empty_backtest_metric("动态仓位不可用"),
        dynamic_position_validation=_empty_backtest_metric("动态仓位验证不可用"),
        yearly_dynamic_position_returns={},
        factor_validation_notes=(f"龙虎榜雷达生成失败：{detail}",),
        no_future_leakage_notes=("当前为降级报告，没有生成新的历史证据结论。",),
        limitations=(
            "证据中心缺少研究缓存时，只能查看今日运行状态和模拟盘指挥，不应解读为证据通过。",
        ),
        next_action="先修复 .firemoney/research_cache/one_to_two_daily 或重新生成龙虎榜雷达缓存。",
    )


def _read_board_shadow_system_report(
    path: Path,
) -> LimitUpBoardShadowSystemReport | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("preview_cache_version")
            != BOARD_SHADOW_SYSTEM_PREVIEW_CACHE_VERSION
        ):
            return None
        return _board_shadow_system_report_from_dict(payload)
    except Exception:
        return None


def _board_shadow_system_report_from_dict(
    payload: dict[str, Any],
) -> LimitUpBoardShadowSystemReport:
    return LimitUpBoardShadowSystemReport(
        report_id=str(payload["report_id"]),
        start_date=str(payload["start_date"]),
        end_date=str(payload["end_date"]),
        status=str(payload["status"]),
        system_name=str(payload["system_name"]),
        summary=str(payload["summary"]),
        buy_rules=tuple(payload.get("buy_rules", ())),
        sell_rules=tuple(payload.get("sell_rules", ())),
        position_rules=tuple(payload.get("position_rules", ())),
        fixed_position_summary=_paper_backtest_metric_from_dict(
            payload["fixed_position_summary"]
        ),
        fixed_position_validation=_paper_backtest_metric_from_dict(
            payload["fixed_position_validation"]
        ),
        dynamic_position_summary=_paper_backtest_metric_from_dict(
            payload["dynamic_position_summary"]
        ),
        dynamic_position_validation=_paper_backtest_metric_from_dict(
            payload["dynamic_position_validation"]
        ),
        yearly_dynamic_position_returns={
            str(key): float(value)
            for key, value in payload.get("yearly_dynamic_position_returns", {}).items()
        },
        factor_validation_notes=tuple(payload.get("factor_validation_notes", ())),
        no_future_leakage_notes=tuple(payload.get("no_future_leakage_notes", ())),
        limitations=tuple(payload.get("limitations", ())),
        next_action=str(payload["next_action"]),
    )


def _read_paper_backtest_report(
    path: Path,
    *,
    requested_end_date: str | None = None,
    allow_partial_current_month: bool = False,
) -> PaperBacktestReport | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("preview_cache_version") != PAPER_BACKTEST_PREVIEW_CACHE_VERSION:
            return None
        current_month_notes = tuple(str(item) for item in payload.get("current_month_notes", ()))
        if (
            not allow_partial_current_month
            and current_month_notes
            and any("尚未完整纳入" in item for item in current_month_notes)
        ):
            return None
        coverage_end = str(payload.get("data_coverage_end") or "")
        if (
            not allow_partial_current_month
            and requested_end_date
            and coverage_end
            and coverage_end[:7] < requested_end_date[:7]
        ):
            return None
        return _paper_backtest_report_from_dict(payload)
    except Exception:
        return None


def _paper_backtest_report_from_dict(payload: dict[str, Any]) -> PaperBacktestReport:
    return PaperBacktestReport(
        report_id=str(payload["report_id"]),
        start_date=str(payload["start_date"]),
        end_date=str(payload["end_date"]),
        status=str(payload["status"]),
        strategy_id=str(payload["strategy_id"]),
        summary=str(payload["summary"]),
        overall=_paper_backtest_metric_from_dict(payload["overall"]),
        train=_paper_backtest_metric_from_dict(payload["train"]),
        validation=_paper_backtest_metric_from_dict(payload["validation"]),
        yearly=tuple(
            _paper_backtest_yearly_from_dict(item)
            for item in payload.get("yearly", [])
        ),
        negative_years=tuple(payload.get("negative_years", ())),
        weak_years=tuple(payload.get("weak_years", ())),
        buy_rule_summary=tuple(payload.get("buy_rule_summary", ())),
        improvement_notes=tuple(payload.get("improvement_notes", ())),
        no_future_leakage_notes=tuple(payload.get("no_future_leakage_notes", ())),
        limitations=tuple(payload.get("limitations", ())),
        next_action=str(payload["next_action"]),
        data_coverage_start=str(payload.get("data_coverage_start", "")),
        data_coverage_end=str(payload.get("data_coverage_end", "")),
        data_coverage_notes=tuple(payload.get("data_coverage_notes", ())),
        friction_scenarios=tuple(
            _paper_backtest_friction_from_dict(item)
            for item in payload.get("friction_scenarios", ())
        ),
        return_target=(
            _paper_backtest_return_target_from_dict(payload["return_target"])
            if payload.get("return_target")
            else None
        ),
        efficiency_candidates=tuple(
            _paper_backtest_efficiency_candidate_from_dict(item)
            for item in payload.get("efficiency_candidates", ())
        ),
        monthly_stability=(
            _paper_backtest_monthly_stability_from_dict(payload["monthly_stability"])
            if payload.get("monthly_stability")
            else None
        ),
        monthly=tuple(
            _paper_backtest_monthly_metric_from_dict(item)
            for item in payload.get("monthly", ())
        ),
        current_month_notes=tuple(payload.get("current_month_notes", ())),
    )


def _paper_backtest_metric_from_dict(
    payload: dict[str, Any],
) -> LimitUpBoardShadowSystemMetric:
    return LimitUpBoardShadowSystemMetric(
        label=str(payload["label"]),
        sample_count=int(payload["sample_count"]),
        win_rate=float(payload["win_rate"]),
        position_weighted_return_pct=float(payload["position_weighted_return_pct"]),
        max_drawdown_pct=float(payload["max_drawdown_pct"]),
    )


def _paper_backtest_yearly_from_dict(payload: dict[str, Any]) -> PaperBacktestYearlyMetric:
    return PaperBacktestYearlyMetric(
        year=str(payload["year"]),
        sample_count=int(payload["sample_count"]),
        win_rate=float(payload["win_rate"]),
        average_return_pct=float(payload["average_return_pct"]),
        median_return_pct=float(payload["median_return_pct"]),
        position_weighted_return_pct=float(payload["position_weighted_return_pct"]),
        max_drawdown_pct=float(payload["max_drawdown_pct"]),
        status=str(payload["status"]),
        conclusion=str(payload["conclusion"]),
    )


def _paper_backtest_friction_from_dict(
    payload: dict[str, Any],
) -> PaperBacktestFrictionScenario:
    return PaperBacktestFrictionScenario(
        label=str(payload["label"]),
        roundtrip_cost_pct=float(payload["roundtrip_cost_pct"]),
        sample_count=int(payload["sample_count"]),
        win_rate=float(payload["win_rate"]),
        position_weighted_return_pct=float(payload["position_weighted_return_pct"]),
        max_drawdown_pct=float(payload["max_drawdown_pct"]),
        validation_return_pct=float(payload["validation_return_pct"]),
        negative_years=tuple(payload.get("negative_years", ())),
        weakest_year=str(payload.get("weakest_year", "")),
        weakest_year_return_pct=float(payload.get("weakest_year_return_pct", 0.0)),
        status=str(payload["status"]),
        conclusion=str(payload["conclusion"]),
    )


def _paper_backtest_return_target_from_dict(
    payload: dict[str, Any],
) -> PaperBacktestReturnTarget:
    return PaperBacktestReturnTarget(
        target_annual_return_pct=float(payload["target_annual_return_pct"]),
        weakest_year=str(payload["weakest_year"]),
        weakest_year_return_pct=float(payload["weakest_year_return_pct"]),
        required_linear_position_multiple=float(
            payload["required_linear_position_multiple"]
        ),
        projected_max_drawdown_pct=float(payload["projected_max_drawdown_pct"]),
        conclusion=str(payload["conclusion"]),
    )


def _paper_backtest_efficiency_candidate_from_dict(
    payload: dict[str, Any],
) -> PaperBacktestEfficiencyCandidate:
    return PaperBacktestEfficiencyCandidate(
        label=str(payload["label"]),
        total_return_pct=float(payload["total_return_pct"]),
        max_drawdown_pct=float(payload["max_drawdown_pct"]),
        validation_return_pct=float(payload["validation_return_pct"]),
        weakest_full_year_return_pct=float(payload["weakest_full_year_return_pct"]),
        monthly_positive_ratio=float(payload.get("monthly_positive_ratio", 0.0)),
        worst_month_return_pct=float(payload.get("worst_month_return_pct", 0.0)),
        conclusion=str(payload["conclusion"]),
    )


def _paper_backtest_monthly_stability_from_dict(
    payload: dict[str, Any],
) -> PaperBacktestMonthlyStability:
    return PaperBacktestMonthlyStability(
        total_months=int(payload["total_months"]),
        positive_months=int(payload["positive_months"]),
        positive_month_ratio=float(payload["positive_month_ratio"]),
        worst_month=str(payload["worst_month"]),
        worst_month_return_pct=float(payload["worst_month_return_pct"]),
        longest_losing_streak=int(payload["longest_losing_streak"]),
        conclusion=str(payload["conclusion"]),
    )


def _paper_backtest_monthly_metric_from_dict(
    payload: dict[str, Any],
) -> PaperBacktestMonthlyMetric:
    return PaperBacktestMonthlyMetric(
        month=str(payload["month"]),
        position_weighted_return_pct=float(payload["position_weighted_return_pct"]),
        status=str(payload["status"]),
        conclusion=str(payload["conclusion"]),
    )


__all__ = [
    "PREVIEW_CREATED_AT",
    "PREVIEW_TRADE_DATE",
    "PreviewRiskBreakMarketDataProvider",
    "PreviewWorkflowData",
    "build_live_workflow_data",
    "build_preview_workflow_data",
]
