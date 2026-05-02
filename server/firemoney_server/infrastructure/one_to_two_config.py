"""Config loader for the one-to-two mainboard strategy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


_CONFIG_DIR = Path(__file__).with_name("config")
_DEFAULT_LOCALE = "zh_CN"


@dataclass(frozen=True)
class OneToTwoStrategySettings:
    strategy_id: str
    name: str
    market: str
    description: str
    min_score: float
    max_position_pct: float
    max_daily_trades: int
    initial_cash: float
    stop_loss_pct: float
    min_turnover_amount: float
    market_temperature_floor: int
    high_deviation_block_pct: float
    recent_gain_block_pct: float
    near_pressure_pct: float
    max_holding_trade_days: int
    discipline_exit_min_gain_pct: float
    minimum_sample_for_stability: int
    excluded_boards: tuple[str, ...]
    exclude_st: bool
    exclude_delisting: bool
    exclude_new_stock_days: int
    morning_time: str
    end_of_day_time: str


@lru_cache(maxsize=4)
def load_one_to_two_settings(
    locale: str = _DEFAULT_LOCALE,
) -> OneToTwoStrategySettings:
    path = _CONFIG_DIR / f"one_to_two_strategy.{locale}.json"
    with path.open("r", encoding="utf-8") as file:
        payload: dict[str, Any] = json.load(file)
    parameters = payload["parameters"]
    exclude = payload["exclude"]
    notification = payload["notification"]
    return OneToTwoStrategySettings(
        strategy_id=str(payload["strategy_id"]),
        name=str(payload["name"]),
        market=str(payload["market"]),
        description=str(payload["description"]),
        min_score=float(parameters["min_score"]),
        max_position_pct=float(parameters["max_position_pct"]),
        max_daily_trades=int(parameters["max_daily_trades"]),
        initial_cash=float(parameters["initial_cash"]),
        stop_loss_pct=float(parameters["stop_loss_pct"]),
        min_turnover_amount=float(parameters["min_turnover_amount"]),
        market_temperature_floor=int(parameters["market_temperature_floor"]),
        high_deviation_block_pct=float(parameters["high_deviation_block_pct"]),
        recent_gain_block_pct=float(parameters["recent_gain_block_pct"]),
        near_pressure_pct=float(parameters["near_pressure_pct"]),
        max_holding_trade_days=int(parameters["max_holding_trade_days"]),
        discipline_exit_min_gain_pct=float(parameters["discipline_exit_min_gain_pct"]),
        minimum_sample_for_stability=int(parameters["minimum_sample_for_stability"]),
        excluded_boards=tuple(str(item) for item in exclude["boards"]),
        exclude_st=bool(exclude["st"]),
        exclude_delisting=bool(exclude["delisting"]),
        exclude_new_stock_days=int(exclude["new_stock_days"]),
        morning_time=str(notification["morning_time"]),
        end_of_day_time=str(notification["end_of_day_time"]),
    )
