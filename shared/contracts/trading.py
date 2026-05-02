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


class OneToTwoEventType(str, Enum):
    MORNING_SCAN = "morning_scan"
    CANDIDATE_SELECTED = "candidate_selected"
    AUCTION_CONFIRMED = "auction_confirmed"
    PAPER_BUY = "paper_buy"
    STOP_WARNING = "stop_warning"
    T1_SELL = "t1_sell"
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
    summary: str
    focus_points: tuple[str, ...]
    account: PaperAccount
    notification: FeishuNotificationResult
    next_action: str


@dataclass(frozen=True)
class OneToTwoStabilityReport:
    report_id: str
    sample_count: int
    success_rate: float
    average_return_pct: float
    max_drawdown: float
    stop_warning_rate: float
    low_breakout_success_rate: float
    position_label_distribution: dict[str, int]
    exit_reason_distribution: dict[str, int]
    status: str
    summary: str
    next_action: str


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
