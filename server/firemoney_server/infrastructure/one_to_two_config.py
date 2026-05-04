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
    min_confirm_open_pct: float
    max_confirm_open_pct: float
    min_turnover_amount: float
    liquidity_score_amount: float
    market_temperature_floor: int
    high_deviation_block_pct: float
    recent_gain_block_pct: float
    near_pressure_pct: float
    max_holding_trade_days: int
    discipline_exit_min_gain_pct: float
    first_take_profit_pct: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    mainline_fade_score: float
    minimum_sample_for_stability: int
    min_sealed_amount_ratio: float
    min_leader_score: float
    min_mainline_score: float
    min_low_breakout_first_board_count: int
    min_low_breakout_ready_candidates: int
    max_ready_candidates: int
    allowed_position_labels: tuple[str, ...]
    selection_rank: str
    board_strategy_enabled: bool
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
        min_confirm_open_pct=float(parameters.get("min_confirm_open_pct", 0.0)),
        max_confirm_open_pct=float(parameters.get("max_confirm_open_pct", 0.07)),
        min_turnover_amount=float(parameters["min_turnover_amount"]),
        liquidity_score_amount=float(
            parameters.get(
                "liquidity_score_amount",
                parameters["min_turnover_amount"],
            )
        ),
        market_temperature_floor=int(parameters["market_temperature_floor"]),
        high_deviation_block_pct=float(parameters["high_deviation_block_pct"]),
        recent_gain_block_pct=float(parameters["recent_gain_block_pct"]),
        near_pressure_pct=float(parameters["near_pressure_pct"]),
        max_holding_trade_days=int(parameters["max_holding_trade_days"]),
        discipline_exit_min_gain_pct=float(parameters["discipline_exit_min_gain_pct"]),
        first_take_profit_pct=float(parameters.get("first_take_profit_pct", 0.32)),
        strong_take_profit_pct=float(parameters.get("strong_take_profit_pct", 0.0825)),
        trailing_stop_pct=float(parameters.get("trailing_stop_pct", 0.001)),
        mainline_fade_score=float(parameters.get("mainline_fade_score", 45)),
        minimum_sample_for_stability=int(parameters["minimum_sample_for_stability"]),
        min_sealed_amount_ratio=float(parameters.get("min_sealed_amount_ratio", 0.08)),
        min_leader_score=float(parameters.get("min_leader_score", 16)),
        min_mainline_score=float(parameters.get("min_mainline_score", 14)),
        min_low_breakout_first_board_count=int(
            parameters.get("min_low_breakout_first_board_count", 0)
        ),
        min_low_breakout_ready_candidates=int(
            parameters.get("min_low_breakout_ready_candidates", 0)
        ),
        max_ready_candidates=int(parameters.get("max_ready_candidates", 0)),
        allowed_position_labels=tuple(
            str(item) for item in parameters.get("allowed_position_labels", ())
        ),
        selection_rank=str(parameters.get("selection_rank", "default")),
        board_strategy_enabled=bool(parameters.get("board_strategy_enabled", True)),
        excluded_boards=tuple(str(item) for item in exclude["boards"]),
        exclude_st=bool(exclude["st"]),
        exclude_delisting=bool(exclude["delisting"]),
        exclude_new_stock_days=int(exclude["new_stock_days"]),
        morning_time=str(notification["morning_time"]),
        end_of_day_time=str(notification["end_of_day_time"]),
    )
