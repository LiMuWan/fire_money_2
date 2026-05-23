"""Preview-only data assembly for the FireMoney one-to-two interface."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.one_to_two_config import load_one_to_two_settings
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar
from shared.contracts import (
    CommercialReadinessReport,
    LimitUpBoardShadowSystemMetric,
    LimitUpBoardShadowSystemReport,
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
    doctor_report: OneToTwoDoctorReport
    schedule_run: OneToTwoScheduleRun
    schedule_health_report: OneToTwoScheduleHealthReport
    notification_records: tuple[NotificationRecord, ...]
    backtest_audit: OneToTwoBacktestAuditReport
    commercial_readiness_report: CommercialReadinessReport


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


def _preview_backtest_end_date() -> str:
    return date.today().isoformat()


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
    report = adapter.build_paper_backtest_report(
        start_date=start_date,
        end_date=end_date,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = contract_to_dict(report)
    payload["preview_cache_version"] = PAPER_BACKTEST_PREVIEW_CACHE_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


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
    report = adapter.build_limit_up_board_shadow_system_report(
        start_date=start_date,
        end_date=end_date,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = contract_to_dict(report)
    payload["preview_cache_version"] = BOARD_SHADOW_SYSTEM_PREVIEW_CACHE_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


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
) -> PaperBacktestReport | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("preview_cache_version") != PAPER_BACKTEST_PREVIEW_CACHE_VERSION:
            return None
        current_month_notes = tuple(str(item) for item in payload.get("current_month_notes", ()))
        if current_month_notes and any("尚未完整纳入" in item for item in current_month_notes):
            return None
        coverage_end = str(payload.get("data_coverage_end") or "")
        if requested_end_date and coverage_end and coverage_end[:7] < requested_end_date[:7]:
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
    "build_preview_workflow_data",
]
