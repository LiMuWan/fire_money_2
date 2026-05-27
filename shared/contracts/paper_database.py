"""Paper-trading SQLite report contracts shared by client and server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperTradeDatabasePosition:
    symbol: str
    name: str
    quantity: int
    entry_price: float
    latest_price: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: str
    status: str
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
class PaperTradeDatabaseEvent:
    event_type: str
    symbol: str
    name: str
    trade_date: str
    price: float
    quantity: int
    amount: float
    message: str
    created_at: str


@dataclass(frozen=True)
class PaperTradeDatabaseTrade:
    trade_id: str
    symbol: str
    name: str
    opened_at: str
    closed_at: str
    entry_price: float
    exit_price: float
    quantity: int
    realized_pnl: float
    realized_pnl_pct: float
    exit_reason: str
    success: bool
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
class PaperTradeQualityBucket:
    bucket: str
    min_score: float
    max_score: float
    trade_count: int
    win_rate: float
    average_realized_return_pct: float
    average_profit_drawdown_ratio: float
    total_realized_pnl: float
    risk_quality_pass_rate: float
    next_action: str


@dataclass(frozen=True)
class PaperTradeGuardBucket:
    bucket: str
    trade_count: int
    win_rate: float
    average_realized_return_pct: float
    average_profit_drawdown_ratio: float
    total_realized_pnl: float
    risk_quality_pass_rate: float
    average_suggested_position_pct: float
    next_action: str


@dataclass(frozen=True)
class PaperTradeDailyAudit:
    trade_date: str
    action: str
    action_label: str
    event_count: int
    buy_count: int
    sell_count: int
    blocked_count: int
    warning_count: int
    realized_pnl: float
    realized_return_pct: float
    average_profit_drawdown_ratio: float
    risk_quality_pass_rate: float
    symbols: tuple[str, ...]
    summary: str
    next_action: str


@dataclass(frozen=True)
class PaperTradePeriodReturn:
    period: str
    trade_count: int
    realized_pnl: float
    realized_return_pct: float
    win_rate: float
    average_trade_return_pct: float


@dataclass(frozen=True)
class PaperTradeDatabaseReport:
    report_id: str
    database_path: str
    status: str
    account_id: str
    last_trade_date: str
    cash: float
    equity: float
    total_realized_pnl: float
    total_realized_return_pct: float
    win_rate: float
    average_realized_return_pct: float
    average_profit_drawdown_ratio: float
    risk_quality_pass_rate: float
    snapshot_count: int
    event_count: int
    open_position_count: int
    closed_trade_count: int
    positions: tuple[PaperTradeDatabasePosition, ...]
    recent_events: tuple[PaperTradeDatabaseEvent, ...]
    recent_trades: tuple[PaperTradeDatabaseTrade, ...]
    quality_buckets: tuple[PaperTradeQualityBucket, ...]
    guard_buckets: tuple[PaperTradeGuardBucket, ...]
    next_action: str
    daily_audits: tuple[PaperTradeDailyAudit, ...] = ()
    monthly_returns: tuple[PaperTradePeriodReturn, ...] = ()
    yearly_returns: tuple[PaperTradePeriodReturn, ...] = ()


__all__ = [
    "PaperTradeDailyAudit",
    "PaperTradeDatabaseEvent",
    "PaperTradeDatabasePosition",
    "PaperTradeDatabaseReport",
    "PaperTradeDatabaseTrade",
    "PaperTradeGuardBucket",
    "PaperTradePeriodReturn",
    "PaperTradeQualityBucket",
]
