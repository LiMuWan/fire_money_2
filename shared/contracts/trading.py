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


@dataclass(frozen=True)
class MarketContext:
    trade_date: str
    market_temperature: int
    trend: str
    risk_level: RiskLevel
    summary: str
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
    status: str


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    order_id: str
    accepted: bool
    status: str
    message: str
    exported_path: str | None = None


@dataclass(frozen=True)
class Recap:
    recap_id: str
    order_id: str
    conclusion: str
    execution_deviation: str
    lessons: tuple[str, ...]
    next_strategy_action: str


@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str
    name: str
    version: str
    risk_profile: str
    parameters: dict[str, float | int | str]
    impact_summary: str


@dataclass(frozen=True)
class MainChainSnapshot:
    market_context: MarketContext
    opportunities: tuple[Opportunity, ...]
    selected_opportunity: Opportunity | None
    risk_review: RiskReview | None
    order_ticket: OrderTicket | None
    execution_receipt: ExecutionReceipt | None
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
