"""Broker gateway contracts shared by local CLI and presentation code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    name: str
    quantity: int
    available_quantity: int
    market_value: float
    cost_price: float
    latest_price: float


@dataclass(frozen=True)
class BrokerConnectionReport:
    broker: str
    status: str
    account_id: str
    cash: float
    available_cash: float
    total_asset: float
    market_value: float
    positions: tuple[BrokerPosition, ...]
    message: str
    next_action: str
    dry_run: bool = True
    raw_error: str | None = None


@dataclass(frozen=True)
class BrokerOrderPlan:
    broker: str
    status: str
    dry_run: bool
    trade_date: str
    action: str
    symbol: str
    name: str
    side: str
    quantity: int
    price: float
    price_type: str
    account_id: str
    summary: str
    warnings: tuple[str, ...]
    next_action: str
    submitted: bool = False
    order_id: str = ""


__all__ = ["BrokerConnectionReport", "BrokerOrderPlan", "BrokerPosition"]
