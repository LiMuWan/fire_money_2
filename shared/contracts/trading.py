"""One-to-two workflow contracts shared across FireMoney layers.

The product now keeps a single core business line:

    morning scan -> event-driven paper trading -> end-of-day review
    -> stability observation

These dataclasses stay small and JSON-friendly so the client, service layer,
tests, and docs speak the same language without depending on AkShare, Feishu,
or local storage details.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any

from .paper_database import (
    PaperTradeDailyAudit,
    PaperTradeDatabaseEvent,
    PaperTradeDatabasePosition,
    PaperTradeDatabaseReport,
    PaperTradeDatabaseTrade,
    PaperTradeGuardBucket,
    PaperTradeQualityBucket,
)


class OneToTwoEventType(str, Enum):
    MORNING_SCAN = "morning_scan"
    CANDIDATE_SELECTED = "candidate_selected"
    AUCTION_CONFIRMED = "auction_confirmed"
    PAPER_BUY = "paper_buy"
    STOP_WARNING = "stop_warning"
    T1_SELL = "t1_sell"
    TAKE_PROFIT = "take_profit"
    MAINLINE_FADE_EXIT = "mainline_fade_exit"
    DISCIPLINE_EXIT = "discipline_exit"
    END_OF_DAY_REVIEW = "end_of_day_review"
    BLOCKED = "blocked"


class NotificationStatus(str, Enum):
    DISABLED = "disabled"
    PREPARED = "prepared"
    SENT = "sent"
    FAILED = "failed"


class PaperTradeStatus(str, Enum):
    EMPTY = "empty"
    HOLDING = "holding"
    WARNING = "warning"
    CLOSED = "closed"


@dataclass(frozen=True)
class TradingDayContext:
    requested_date: str
    trade_date: str
    previous_trade_date: str
    next_trade_date: str
    is_trading_day: bool
    note: str


@dataclass(frozen=True)
class OneToTwoPositionProfile:
    label: str
    low_position_score: float
    breakout_score: float
    pressure_score: float
    moving_average_score: float
    volume_score: float
    summary: str
    risk_notes: tuple[str, ...]
    volume_ratio: float = 1.5
    rsi_14: float = 65.0
    position_percentile_60: float = 0.75
    capital_style_label: str = ""


@dataclass(frozen=True)
class BreakoutStructureProfile:
    score: float
    label: str
    breakout_line: float
    distance_pct: float
    base_tightness_score: float
    volume_surge_score: float
    overhead_supply_score: float
    relative_strength_score: float
    passed: bool
    summary: str
    risk_notes: tuple[str, ...]


@dataclass(frozen=True)
class OneToTwoExitPlan:
    stop_loss: float
    stop_loss_pct: float
    first_take_profit_price: float
    first_take_profit_pct: float
    strong_take_profit_price: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    max_holding_trade_days: int
    summary: str


@dataclass(frozen=True)
class MainlineNewsItem:
    title: str
    source: str
    published_at: str
    related_symbols: tuple[str, ...]
    url: str = ""


@dataclass(frozen=True)
class MainlineContinuity:
    theme: str
    score: float
    status: str
    hot_stock_count: int
    limit_up_count: int
    news_count: int
    latest_news: tuple[MainlineNewsItem, ...]
    reasons: tuple[str, ...]
    risk_notes: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class OneToTwoCandidate:
    symbol: str
    name: str
    trade_date: str
    score: float
    status: str
    latest_price: float
    limit_up_price: float
    entry_price: float
    stop_loss: float
    position_limit_pct: float
    first_board_score: float
    auction_score: float
    position_score: float
    theme_score: float
    liquidity_score: float
    position_profile: OneToTwoPositionProfile
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    rationale: str
    next_action: str
    mainline_score: float = 0.0
    sealing_score: float = 0.0
    leader_score: float = 0.0
    leader_label: str = ""
    strategy_tags: tuple[str, ...] = ()
    discipline_summary: str = ""
    exit_plan: OneToTwoExitPlan | None = None
    mainline_continuity: MainlineContinuity | None = None
    turnover_quality_score: float = 0.0
    turnover_quality_label: str = ""
    turnover_quality_notes: tuple[str, ...] = ()
    market_cap: float = 0.0
    float_market_cap: float = 0.0
    market_cap_source: str = ""
    breakout_structure: BreakoutStructureProfile | None = None


@dataclass(frozen=True)
class PaperPosition:
    symbol: str
    name: str
    quantity: int
    entry_price: float
    latest_price: float
    stop_loss: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: str
    position_label: str
    opened_score: float
    can_sell_today: bool
    status: PaperTradeStatus
    risk_note: str
    exit_plan: OneToTwoExitPlan | None = None
    mainline_continuity: MainlineContinuity | None = None
    peak_price: float = 0.0
    trough_price: float = 0.0
    planned_stop_risk_pct: float = 0.0
    planned_first_target_return_pct: float = 0.0
    planned_reward_risk_ratio: float = 0.0
    max_intratrade_drawdown_budget_pct: float = 0.0
    entry_turnover_quality_score: float = 0.0
    entry_turnover_quality_label: str = ""
    entry_turnover_quality_notes: tuple[str, ...] = ()
    entry_guard_status: str = ""
    entry_guard_action: str = ""
    entry_guard_suggested_position_pct: float = 0.0
    entry_guard_reason: str = ""
    entry_guard_quality_bucket: str = ""
    entry_guard_quality_sample_count: int = 0
    entry_guard_quality_win_rate: float = 0.0
    entry_guard_quality_average_return_pct: float = 0.0
    entry_guard_quality_pass_rate: float = 0.0


@dataclass(frozen=True)
class PaperTradeEvent:
    event_id: str
    event_type: OneToTwoEventType
    symbol: str
    name: str
    trade_date: str
    price: float
    quantity: int
    amount: float
    message: str
    created_at: str


@dataclass(frozen=True)
class PaperTradeRecord:
    trade_id: str
    symbol: str
    name: str
    opened_at: str
    closed_at: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_amount: float
    exit_amount: float
    realized_pnl: float
    realized_pnl_pct: float
    holding_trade_days: int
    exit_reason: str
    position_label: str
    success: bool
    warning_count: int
    max_favorable_pct: float = 0.0
    max_adverse_pct: float = 0.0
    profit_drawdown_ratio: float = 0.0
    planned_stop_risk_pct: float = 0.0
    planned_first_target_return_pct: float = 0.0
    planned_reward_risk_ratio: float = 0.0
    max_intratrade_drawdown_budget_pct: float = 0.0
    entry_turnover_quality_score: float = 0.0
    entry_turnover_quality_label: str = ""
    entry_turnover_quality_notes: tuple[str, ...] = ()
    entry_guard_status: str = ""
    entry_guard_action: str = ""
    entry_guard_suggested_position_pct: float = 0.0
    entry_guard_reason: str = ""
    entry_guard_quality_bucket: str = ""
    entry_guard_quality_sample_count: int = 0
    entry_guard_quality_win_rate: float = 0.0
    entry_guard_quality_average_return_pct: float = 0.0
    entry_guard_quality_pass_rate: float = 0.0


@dataclass(frozen=True)
class OneToTwoRecentSample:
    trade_id: str
    symbol: str
    name: str
    opened_at: str
    closed_at: str
    realized_pnl: float
    realized_pnl_pct: float
    holding_trade_days: int
    exit_reason: str
    position_label: str
    success: bool
    warning_count: int
    max_favorable_pct: float = 0.0
    max_adverse_pct: float = 0.0
    profit_drawdown_ratio: float = 0.0


@dataclass(frozen=True)
class PaperAccount:
    account_id: str
    last_trade_date: str
    cash: float
    initial_cash: float
    equity: float
    max_position_pct: float
    max_daily_trades: int
    daily_trade_count: int
    positions: tuple[PaperPosition, ...]
    events: tuple[PaperTradeEvent, ...]
    closed_trades: tuple[PaperTradeRecord, ...]


@dataclass(frozen=True)
class FeishuNotificationResult:
    status: NotificationStatus
    title: str
    message: str
    webhook_configured: bool
    error: str | None = None


@dataclass(frozen=True)
class NotificationRecord:
    record_id: str
    channel: str
    workflow: str
    trade_date: str
    status: NotificationStatus
    title: str
    message: str
    created_at: str
    error: str | None = None


@dataclass(frozen=True)
class OneToTwoMorningReport:
    report_id: str
    trade_date: str
    trade_context: TradingDayContext
    market_temperature: int
    status: str
    summary: str
    candidates: tuple[OneToTwoCandidate, ...]
    account: PaperAccount
    notification: FeishuNotificationResult
    next_action: str


@dataclass(frozen=True)
class OneToTwoEndOfDayReview:
    review_id: str
    trade_date: str
    trade_context: TradingDayContext
    sample_count: int
    success_count: int
    warning_count: int
    realized_pnl: float
    max_drawdown: float
    stability_stage: str
    next_milestone: int
    strategy_boundary_suggestion: str
    summary: str
    focus_points: tuple[str, ...]
    account: PaperAccount
    notification: FeishuNotificationResult
    next_action: str


@dataclass(frozen=True)
class OneToTwoStabilityReport:
    report_id: str
    sample_count: int
    sample_stage: str
    next_milestone: int
    success_rate: float
    average_return_pct: float
    max_drawdown: float
    stop_warning_rate: float
    low_breakout_success_rate: float
    position_label_distribution: dict[str, int]
    exit_reason_distribution: dict[str, int]
    recent_samples: tuple[OneToTwoRecentSample, ...]
    status: str
    summary: str
    strategy_boundary_suggestion: str
    next_action: str


@dataclass(frozen=True)
class BacktestDataQualityCheck:
    check_id: str
    label: str
    status: str
    detail: str
    next_action: str


@dataclass(frozen=True)
class OneToTwoBacktestAuditReport:
    report_id: str
    start_date: str
    end_date: str
    requested_trade_days: int
    usable_trade_days: int
    data_quality_checks: tuple[BacktestDataQualityCheck, ...]
    stability_report: OneToTwoStabilityReport
    status: str
    summary: str
    limitations: tuple[str, ...]
    recommended_next_action: str


@dataclass(frozen=True)
class OneToTwoHistoricalReplayTrade:
    symbol: str
    name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_return_pct: float
    realized_pnl: float
    realized_pnl_pct: float
    holding_trade_days: int
    exit_reason: str
    risk_reward_ratio: float
    max_favorable_pct: float
    max_adverse_pct: float
    candidate_score: float
    position_label: str
    evidence_date: str
    data_mode: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class OneToTwoHistoricalReplayReport:
    report_id: str
    as_of_date: str
    entry_date: str
    exit_date: str
    data_mode: str
    status: str
    summary: str
    candidate: OneToTwoCandidate | None
    trade: OneToTwoHistoricalReplayTrade | None
    quality_checks: tuple[BacktestDataQualityCheck, ...]
    no_future_leakage_notes: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class LimitUpBoardShadowCandidate:
    symbol: str
    name: str
    board_date: str
    entry_price: float
    stop_loss: float
    take_profit_price: float
    rank_score: float
    estimated_turnover_amount: float
    volume_ratio_20: float
    recent_gain_pct: float
    ma20_deviation_pct: float
    first_board: bool
    ma_bullish: bool
    risk_notes: tuple[str, ...]
    next_action: str
    market_seal_count: int = 0
    market_touch_count: int = 0
    market_advance_ratio: float = 0.0
    suggested_position_pct: float = 0.08


@dataclass(frozen=True)
class LimitUpBoardShadowTrade:
    symbol: str
    name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    gross_return_pct: float
    realized_pnl_pct: float
    holding_trade_days: int
    exit_reason: str
    data_mode: str


@dataclass(frozen=True)
class LimitUpBoardShadowSample:
    sample_id: str
    as_of_date: str
    status: str
    symbol: str
    name: str
    entry_price: float
    stop_loss: float
    take_profit_price: float
    rank_score: float
    exit_date: str
    exit_price: float
    realized_pnl_pct: float
    holding_trade_days: int
    exit_reason: str
    success: bool
    created_at: str
    limitations: tuple[str, ...]
    market_seal_count: int = 0
    market_touch_count: int = 0
    market_advance_ratio: float = 0.0
    suggested_position_pct: float = 0.08


@dataclass(frozen=True)
class LimitUpBoardShadowReport:
    report_id: str
    as_of_date: str
    status: str
    summary: str
    candidate: LimitUpBoardShadowCandidate | None
    trade: LimitUpBoardShadowTrade | None
    quality_checks: tuple[BacktestDataQualityCheck, ...]
    no_future_leakage_notes: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str
    notification: FeishuNotificationResult | None = None


@dataclass(frozen=True)
class LimitUpBoardShadowStabilityReport:
    report_id: str
    sample_count: int
    sample_stage: str
    next_milestone: int
    success_rate: float
    average_return_pct: float
    max_drawdown: float
    exit_reason_distribution: dict[str, int]
    recent_samples: tuple[LimitUpBoardShadowSample, ...]
    status: str
    summary: str
    strategy_boundary_suggestion: str
    next_action: str


@dataclass(frozen=True)
class LimitUpBoardShadowSystemMetric:
    label: str
    sample_count: int
    win_rate: float
    position_weighted_return_pct: float
    max_drawdown_pct: float


@dataclass(frozen=True)
class PaperBacktestYearlyMetric:
    year: str
    sample_count: int
    win_rate: float
    average_return_pct: float
    median_return_pct: float
    position_weighted_return_pct: float
    max_drawdown_pct: float
    status: str
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestFrictionScenario:
    label: str
    roundtrip_cost_pct: float
    sample_count: int
    win_rate: float
    position_weighted_return_pct: float
    max_drawdown_pct: float
    validation_return_pct: float
    negative_years: tuple[str, ...]
    weakest_year: str
    weakest_year_return_pct: float
    status: str
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestReturnTarget:
    target_annual_return_pct: float
    weakest_year: str
    weakest_year_return_pct: float
    required_linear_position_multiple: float
    projected_max_drawdown_pct: float
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestEfficiencyCandidate:
    label: str
    total_return_pct: float
    max_drawdown_pct: float
    validation_return_pct: float
    weakest_full_year_return_pct: float
    monthly_positive_ratio: float
    worst_month_return_pct: float
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestMonthlyStability:
    total_months: int
    positive_months: int
    positive_month_ratio: float
    worst_month: str
    worst_month_return_pct: float
    longest_losing_streak: int
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestMonthlyMetric:
    month: str
    position_weighted_return_pct: float
    status: str
    conclusion: str


@dataclass(frozen=True)
class PaperBacktestReport:
    report_id: str
    start_date: str
    end_date: str
    status: str
    strategy_id: str
    summary: str
    overall: LimitUpBoardShadowSystemMetric
    train: LimitUpBoardShadowSystemMetric
    validation: LimitUpBoardShadowSystemMetric
    yearly: tuple[PaperBacktestYearlyMetric, ...]
    negative_years: tuple[str, ...]
    weak_years: tuple[str, ...]
    buy_rule_summary: tuple[str, ...]
    improvement_notes: tuple[str, ...]
    no_future_leakage_notes: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str
    data_coverage_start: str = ""
    data_coverage_end: str = ""
    data_coverage_notes: tuple[str, ...] = ()
    friction_scenarios: tuple[PaperBacktestFrictionScenario, ...] = ()
    return_target: PaperBacktestReturnTarget | None = None
    efficiency_candidates: tuple[PaperBacktestEfficiencyCandidate, ...] = ()
    monthly_stability: PaperBacktestMonthlyStability | None = None
    monthly: tuple[PaperBacktestMonthlyMetric, ...] = ()
    current_month_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissedOpportunityItem:
    trade_date: str
    symbol: str
    name: str
    entry_price: float
    net_return_pct: float
    account_return_pct: float
    position_pct: float
    quantity: int
    paper_status: str
    watch_status: str
    notification_status: str
    diagnosis: str
    next_action: str


@dataclass(frozen=True)
class MissedOpportunityReport:
    report_id: str
    start_date: str
    end_date: str
    status: str
    summary: str
    backtest_trade_count: int
    caught_count: int
    missed_count: int
    missed_profit_count: int
    missed_account_return_pct: float
    items: tuple[MissedOpportunityItem, ...]
    next_action: str


@dataclass(frozen=True)
class LimitUpBoardShadowSystemReport:
    report_id: str
    start_date: str
    end_date: str
    status: str
    system_name: str
    summary: str
    buy_rules: tuple[str, ...]
    sell_rules: tuple[str, ...]
    position_rules: tuple[str, ...]
    fixed_position_summary: LimitUpBoardShadowSystemMetric
    fixed_position_validation: LimitUpBoardShadowSystemMetric
    dynamic_position_summary: LimitUpBoardShadowSystemMetric
    dynamic_position_validation: LimitUpBoardShadowSystemMetric
    yearly_dynamic_position_returns: dict[str, float]
    factor_validation_notes: tuple[str, ...]
    no_future_leakage_notes: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class StrategyDecisionOption:
    strategy_id: str
    role: str
    status: str
    action: str
    confidence: str
    expected_return_label: str
    max_drawdown_label: str
    rationale: str


@dataclass(frozen=True)
class StrategyDecisionReport:
    report_id: str
    trade_date: str
    status: str
    evidence_end_date: str
    market_regime: str
    regime_rationale: str
    regime_action: str
    k92_regime: str
    k92_gate: str
    k92_rationale: str
    selected_strategy_id: str
    selected_action: str
    selected_role: str
    summary: str
    options: tuple[StrategyDecisionOption, ...]
    risk_rules: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class K92EmotionLiquidityCandidate:
    symbol: str
    name: str
    bucket: str
    action: str
    status: str
    score: float
    latest_price: float
    entry_price: float
    stop_loss: float
    market_cap: float
    turnover_quality_score: float
    mainline_score: float
    position_percentile_60: float
    rationale: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class K92EmotionLiquidityReport:
    report_id: str
    trade_date: str
    status: str
    market_temperature: int
    regime: str
    regime_label: str
    action: str
    summary: str
    leader_candidates: tuple[K92EmotionLiquidityCandidate, ...]
    supplement_candidates: tuple[K92EmotionLiquidityCandidate, ...]
    switch_candidates: tuple[K92EmotionLiquidityCandidate, ...]
    risk_candidates: tuple[K92EmotionLiquidityCandidate, ...]
    stand_aside_reasons: tuple[str, ...]
    rules: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class PaperTradingInstruction:
    action: str
    strategy_id: str
    symbol: str
    name: str
    timing: str
    entry_window: str
    entry_trigger: str
    entry_price: float
    stop_loss: float
    first_take_profit_price: float
    planned_stop_risk_pct: float
    planned_first_target_return_pct: float
    planned_reward_risk_ratio: float
    max_intratrade_drawdown_budget_pct: float
    position_pct: float
    cash_budget: float
    quantity: int
    confidence: str
    rationale: str
    invalidation_rules: tuple[str, ...]
    sell_rules: tuple[str, ...]
    risk_notes: tuple[str, ...]
    next_check_time: str


@dataclass(frozen=True)
class PaperHoldingInstruction:
    action: str
    symbol: str
    name: str
    opened_at: str
    holding_trade_days: int
    can_sell_today: bool
    quantity: int
    entry_price: float
    latest_price: float
    stop_loss: float
    positive_lock_price: float
    first_take_profit_price: float
    hard_exit_trade_days: int
    unrealized_pnl: float
    unrealized_pnl_pct: float
    status: str
    rationale: str
    sell_triggers: tuple[str, ...]
    next_check_time: str
    next_command: str


@dataclass(frozen=True)
class PaperTradingGuardDecision:
    status: str
    action: str
    review_sample_count: int
    win_rate: float
    average_return_pct: float
    max_drawdown_pct: float
    consecutive_losses: int
    consecutive_quality_failures: int
    average_profit_drawdown_ratio: float
    risk_quality_pass_rate: float
    suggested_position_pct: float
    reasons: tuple[str, ...]
    next_action: str
    candidate_quality_bucket: str = ""
    candidate_quality_sample_count: int = 0
    candidate_quality_win_rate: float = 0.0
    candidate_quality_average_return_pct: float = 0.0
    candidate_quality_risk_quality_pass_rate: float = 0.0


@dataclass(frozen=True)
class PaperTradingDecisionReport:
    report_id: str
    trade_date: str
    status: str
    market_regime: str
    execution_track: str
    selected_strategy_id: str
    selected_action: str
    evidence_end_date: str
    should_buy: bool
    instruction: PaperTradingInstruction | None
    holding_instruction: PaperHoldingInstruction | None
    candidate_count: int
    ready_count: int
    blocked_count: int
    account_equity: float
    account_cash: float
    existing_position_count: int
    guard_decision: PaperTradingGuardDecision
    summary: str
    decision_rules: tuple[str, ...]
    next_action: str
    notification: FeishuNotificationResult | None = None


@dataclass(frozen=True)
class OneToTwoExecutionQualityReport:
    report_id: str
    symbol: str
    trade_date: str
    status: str
    summary: str
    minute_bar_count: int
    tick_snapshot_count: int
    first_minute_range_pct: float
    first_five_minute_range_pct: float
    first_tick_bid_ask_spread_pct: float
    max_bid_queue_volume: float
    max_ask_queue_volume: float
    first_five_minute_buy_amount_pct: float
    first_five_minute_sell_amount_pct: float
    max_single_tick_amount: float
    auction_window_amount: float
    open_window_amount: float
    open_window_price_lift_pct: float
    large_tick_amount_ratio: float
    buy_drive_score: float
    queue_imbalance_score: float
    entry_momentum_score: float
    entry_momentum_signal: str
    entry_momentum_reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class OneToTwoDoctorCheck:
    check_id: str
    label: str
    status: str
    detail: str
    next_action: str


@dataclass(frozen=True)
class OneToTwoDoctorReport:
    report_id: str
    trade_date: str
    status: str
    summary: str
    checks: tuple[OneToTwoDoctorCheck, ...]
    next_action: str


@dataclass(frozen=True)
class OneToTwoBetaReadinessReport:
    report_id: str
    trade_date: str
    status: str
    summary: str
    feishu_test: FeishuNotificationResult
    doctor_report: OneToTwoDoctorReport
    next_action: str


@dataclass(frozen=True)
class OneToTwoBetaRehearsalReport:
    report_id: str
    trade_date: str
    status: str
    summary: str
    doctor_report: OneToTwoDoctorReport
    schedule_runs: tuple["OneToTwoScheduleRun", ...]
    stability_report: OneToTwoStabilityReport
    notification_record_count: int
    paper_event_count: int
    open_position_count: int
    closed_sample_count: int
    next_action: str


@dataclass(frozen=True)
class OneToTwoBetaLaunchPlan:
    report_id: str
    requested_date: str
    trade_date: str
    next_trade_date: str
    status: str
    summary: str
    rehearsal: OneToTwoBetaRehearsalReport
    doctor_report: OneToTwoDoctorReport
    launch_commands: tuple[str, ...]
    blockers: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class CommercialReadinessGate:
    gate_id: str
    title: str
    status: str
    tone: str
    score: float
    detail: str
    metrics: dict[str, str] | None = None


@dataclass(frozen=True)
class CommercialReadinessReport:
    report_id: str
    trade_date: str
    status: str
    headline: str
    stage: str
    score: float
    gates: tuple[CommercialReadinessGate, ...]
    next_actions: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class OneToTwoScheduleTask:
    task_id: str
    mode: str
    phase: str | None
    scheduled_time: str
    status: str
    message: str
    notification_status: NotificationStatus


@dataclass(frozen=True)
class OneToTwoScheduleRun:
    run_id: str
    trade_date: str
    trade_context: TradingDayContext
    requested_time: str
    due_count: int
    executed_count: int
    skipped_count: int
    tasks: tuple[OneToTwoScheduleTask, ...]
    next_action: str


@dataclass(frozen=True)
class OneToTwoScheduleHealthItem:
    task_id: str
    workflow: str
    scheduled_time: str
    required_notification: bool
    schedule_status: str
    notification_status: str
    status: str
    summary: str
    next_action: str


@dataclass(frozen=True)
class OneToTwoScheduleHealthReport:
    report_id: str
    requested_date: str
    trade_date: str
    is_trading_day: bool
    status: str
    summary: str
    checked_at: str
    items: tuple[OneToTwoScheduleHealthItem, ...]
    scheduler_run_count: int
    notification_record_count: int
    next_action: str


def contract_to_dict(value: Any) -> Any:
    """Convert a shared contract into a JSON-friendly value."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: contract_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [contract_to_dict(item) for item in value]
    if isinstance(value, list):
        return [contract_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: contract_to_dict(item) for key, item in value.items()}
    return value
