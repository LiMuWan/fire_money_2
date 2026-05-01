"""Trading workflow contracts shared across FireMoney layers.

These dataclasses are intentionally small and JSON-friendly. They define the
language shared by client display code, server workflows, tests, and docs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any


class WorkflowStage(str, Enum):
    MARKET_OVERVIEW = "market_overview"
    SIGNAL_SCAN = "signal_scan"
    OPPORTUNITY_POOL = "opportunity_pool"
    RISK_REVIEW = "risk_review"
    ORDER_DRAFT = "order_draft"
    EXECUTION_RECEIPT = "execution_receipt"
    RECAP = "recap"
    STRATEGY_IMPROVEMENT = "strategy_improvement"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ReviewDecision(str, Enum):
    APPROVE_FOR_CONFIRMATION = "approve_for_confirmation"
    NEEDS_REVIEW = "needs_review"
    BLOCK = "block"


class ConfirmationStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    WAITING_USER = "waiting_user"
    CONFIRMED = "confirmed"
    BLOCKED = "blocked"


class AdjustmentStatus(str, Enum):
    NOT_AVAILABLE = "not_available"
    WAITING_USER = "waiting_user"
    APPLIED = "applied"


class ExecutionRoute(str, Enum):
    CSV_EXPORT = "csv_export"
    BROKER_BRIDGE = "broker_bridge"


class ExecutionReceiptStatus(str, Enum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    FAILED = "failed"


class ArchiveReviewQuality(str, Enum):
    EMPTY = "empty"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    REVIEWABLE = "reviewable"


class StrategyBoundaryAction(str, Enum):
    COLLECT_MORE_SAMPLES = "collect_more_samples"
    REVIEW_LOSSES_FIRST = "review_losses_first"
    KEEP_CURRENT_BOUNDARY = "keep_current_boundary"


@dataclass(frozen=True)
class MarketContext:
    trade_date: str
    market_temperature: int
    trend: str
    risk_level: RiskLevel
    summary: str
    next_action: str


@dataclass(frozen=True)
class SignalScanReport:
    report_id: str
    stage: WorkflowStage
    universe_size: int
    candidate_count: int
    ranked_opportunities: tuple[Opportunity, ...]
    focus_opportunities: tuple[Opportunity, ...]
    focus_opportunity: Opportunity | None
    summary: str
    watch_notes: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    name: str
    score: float
    confidence: float
    source_stage: WorkflowStage
    strategy_tags: tuple[str, ...]
    entry_price: float
    stop_loss: float
    target_price: float
    risk_flags: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class RiskReview:
    review_id: str
    opportunity: Opportunity
    decision: ReviewDecision
    risk_level: RiskLevel
    position_limit_pct: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class OrderTicket:
    order_id: str
    review_id: str
    symbol: str
    name: str
    side: str
    quantity: int
    limit_price: float
    route: str
    requires_confirmation: bool
    confirmation_status: ConfirmationStatus
    confirmation_message: str
    status: str


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    order_id: str
    accepted: bool
    status: ExecutionReceiptStatus
    route: ExecutionRoute
    message: str
    prepared_at: str
    submitted_at: str | None
    confirmed_by_user: bool
    failure_reason: str | None
    next_action: str
    exported_path: str | None = None


@dataclass(frozen=True)
class FillExecution:
    fill_id: str
    order_id: str
    symbol: str
    filled_quantity: int
    avg_price: float
    target_price: float
    slippage_pct: float
    filled_at: str
    source: str
    message: str


@dataclass(frozen=True)
class ExitExecution:
    exit_id: str
    order_id: str
    symbol: str
    exited_quantity: int
    avg_price: float
    entry_avg_price: float
    realized_pnl: float
    realized_pnl_pct: float
    exited_at: str
    reason: str
    message: str


@dataclass(frozen=True)
class OutcomeCard:
    outcome_id: str
    order_id: str
    symbol: str
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float | None
    realized_pnl_pct: float | None
    stop_loss: float
    stop_discipline: str
    next_action: str
    summary: str


@dataclass(frozen=True)
class TradeArchiveRecord:
    archive_id: str
    order_id: str
    symbol: str
    name: str
    trade_date: str
    opened_at: str
    closed_at: str
    realized_pnl: float
    realized_pnl_pct: float
    outcome: str
    signal_summary: str
    risk_summary: str
    execution_summary: str
    recap_summary: str
    next_action: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class TradeArchiveReview:
    review_id: str
    record_count: int
    profit_count: int
    loss_count: int
    flat_count: int
    sample_quality: ArchiveReviewQuality
    win_rate: float
    total_realized_pnl: float
    average_realized_pnl_pct: float
    best_archive_id: str | None
    worst_archive_id: str | None
    sample_quality_note: str
    strategy_boundary_action: StrategyBoundaryAction
    strategy_boundary_note: str
    summary: str
    focus_points: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class StrategyAdjustment:
    key: str
    label: str
    current_value: float | int | str
    suggested_value: float | int | str
    reason: str
    impact: str


@dataclass(frozen=True)
class StrategyChangeRecord:
    record_id: str
    action: str
    strategy_id: str
    from_version: str
    to_version: str
    changes: tuple[str, ...]
    reason: str
    created_at: str


@dataclass(frozen=True)
class Recap:
    recap_id: str
    order_id: str
    conclusion: str
    execution_deviation: str
    lessons: tuple[str, ...]
    strategy_adjustments: tuple[StrategyAdjustment, ...]
    next_strategy_action: str


@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str
    name: str
    version: str
    risk_profile: str
    parameters: dict[str, float | int | str]
    impact_summary: str
    adjustment_status: AdjustmentStatus = AdjustmentStatus.NOT_AVAILABLE
    adjustment_message: str = "not_available"
    source: str = "default"
    recent_changes: tuple[StrategyChangeRecord, ...] = ()


@dataclass(frozen=True)
class MainChainSnapshot:
    market_context: MarketContext
    signal_scan: SignalScanReport
    opportunities: tuple[Opportunity, ...]
    selected_opportunity: Opportunity | None
    risk_review: RiskReview | None
    order_ticket: OrderTicket | None
    execution_receipt: ExecutionReceipt | None
    fill_execution: FillExecution | None
    exit_execution: ExitExecution | None
    outcome_card: OutcomeCard | None
    archive_record: TradeArchiveRecord | None
    recent_archives: tuple[TradeArchiveRecord, ...]
    recap: Recap | None
    strategy_config: StrategyConfig
    next_stage: WorkflowStage


def contract_to_dict(value: Any) -> Any:
    """Convert a shared contract into a JSON-friendly dictionary."""

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
