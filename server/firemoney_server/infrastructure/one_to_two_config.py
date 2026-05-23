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
    max_execution_score: float
    max_position_pct: float
    max_daily_trades: int
    initial_cash: float
    paper_entry_mainboard_only: bool
    small_account_mode_enabled: bool
    small_account_min_lot_shares: int
    small_account_target_position_pct: float
    small_account_reduced_target_position_pct: float
    small_account_max_position_pct: float
    small_account_reduced_max_position_pct: float
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
    hard_max_holding_trade_days: int
    discipline_exit_min_gain_pct: float
    positive_lock_profit_pct: float
    minimum_reward_risk_ratio: float
    positive_lock_min_profit_drawdown_ratio: float
    paper_guard_review_sample: int
    paper_guard_min_win_rate: float
    paper_guard_min_average_return_pct: float
    paper_guard_max_consecutive_losses: int
    paper_guard_max_consecutive_quality_failures: int
    paper_guard_max_drawdown_pct: float
    paper_guard_reduced_position_pct: float
    reversal_repair_max_position_pct: float
    paper_guard_min_profit_drawdown_ratio: float
    paper_guard_min_quality_bucket_samples: int
    paper_guard_quality_bucket_block_losses: int
    first_take_profit_pct: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    main_rise_runner_min_quality_score: float
    main_rise_runner_min_opened_score: float
    main_rise_runner_min_mainline_score: float
    main_rise_runner_trailing_start_pct: float
    main_rise_runner_trailing_stop_pct: float
    main_rise_runner_profit_floor_pct: float
    mainline_fade_score: float
    minimum_sample_for_stability: int
    min_sealed_amount_ratio: float
    min_leader_score: float
    min_mainline_score: float
    min_turnover_dragon_score: float
    min_turnover_dragon_turnover_rate: float
    max_turnover_dragon_turnover_rate: float
    min_turnover_dragon_sealed_ratio: float
    min_turnover_dragon_auction_ratio: float
    min_volume_ratio_5: float
    min_rsi_14: float
    max_rsi_14: float
    min_position_percentile_60: float
    min_breakout_structure_score: float
    max_breakout_entry_distance_pct: float
    min_breakout_volume_ratio: float
    min_low_breakout_first_board_count: int
    min_low_breakout_ready_candidates: int
    max_ready_candidates: int
    min_market_cap: float
    max_market_cap: float
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
        max_execution_score=float(
            parameters.get(
                "max_execution_score",
                parameters.get("max_score", 90),
            )
        ),
        max_position_pct=float(parameters["max_position_pct"]),
        max_daily_trades=int(parameters["max_daily_trades"]),
        initial_cash=float(parameters["initial_cash"]),
        paper_entry_mainboard_only=bool(
            parameters.get("paper_entry_mainboard_only", True)
        ),
        small_account_mode_enabled=bool(
            parameters.get("small_account_mode_enabled", False)
        ),
        small_account_min_lot_shares=int(
            parameters.get("small_account_min_lot_shares", 100)
        ),
        small_account_target_position_pct=float(
            parameters.get("small_account_target_position_pct", 0.18)
        ),
        small_account_reduced_target_position_pct=float(
            parameters.get("small_account_reduced_target_position_pct", 0.12)
        ),
        small_account_max_position_pct=float(
            parameters.get("small_account_max_position_pct", 0.35)
        ),
        small_account_reduced_max_position_pct=float(
            parameters.get("small_account_reduced_max_position_pct", 0.2)
        ),
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
        hard_max_holding_trade_days=int(
            parameters.get(
                "hard_max_holding_trade_days",
                min(5, int(parameters["max_holding_trade_days"])),
            )
        ),
        discipline_exit_min_gain_pct=float(parameters["discipline_exit_min_gain_pct"]),
        positive_lock_profit_pct=float(parameters.get("positive_lock_profit_pct", 0.03)),
        minimum_reward_risk_ratio=float(parameters.get("minimum_reward_risk_ratio", 2.0)),
        positive_lock_min_profit_drawdown_ratio=float(
            parameters.get("positive_lock_min_profit_drawdown_ratio", 1.0)
        ),
        paper_guard_review_sample=int(parameters.get("paper_guard_review_sample", 5)),
        paper_guard_min_win_rate=float(parameters.get("paper_guard_min_win_rate", 0.6)),
        paper_guard_min_average_return_pct=float(
            parameters.get("paper_guard_min_average_return_pct", 0.005)
        ),
        paper_guard_max_consecutive_losses=int(
            parameters.get("paper_guard_max_consecutive_losses", 2)
        ),
        paper_guard_max_consecutive_quality_failures=int(
            parameters.get("paper_guard_max_consecutive_quality_failures", 2)
        ),
        paper_guard_max_drawdown_pct=float(
            parameters.get("paper_guard_max_drawdown_pct", 0.03)
        ),
        paper_guard_reduced_position_pct=float(
            parameters.get(
                "paper_guard_reduced_position_pct",
                min(float(parameters["max_position_pct"]), 0.04),
            )
        ),
        reversal_repair_max_position_pct=float(
            parameters.get(
                "reversal_repair_max_position_pct",
                parameters.get(
                    "paper_guard_reduced_position_pct",
                    min(float(parameters["max_position_pct"]), 0.04),
                ),
            )
        ),
        paper_guard_min_profit_drawdown_ratio=float(
            parameters.get("paper_guard_min_profit_drawdown_ratio", 1.0)
        ),
        paper_guard_min_quality_bucket_samples=int(
            parameters.get("paper_guard_min_quality_bucket_samples", 3)
        ),
        paper_guard_quality_bucket_block_losses=int(
            parameters.get("paper_guard_quality_bucket_block_losses", 2)
        ),
        first_take_profit_pct=float(parameters.get("first_take_profit_pct", 0.32)),
        strong_take_profit_pct=float(parameters.get("strong_take_profit_pct", 0.0825)),
        trailing_stop_pct=float(parameters.get("trailing_stop_pct", 0.001)),
        main_rise_runner_min_quality_score=float(
            parameters.get("main_rise_runner_min_quality_score", 86)
        ),
        main_rise_runner_min_opened_score=float(
            parameters.get("main_rise_runner_min_opened_score", 90)
        ),
        main_rise_runner_min_mainline_score=float(
            parameters.get("main_rise_runner_min_mainline_score", 75)
        ),
        main_rise_runner_trailing_start_pct=float(
            parameters.get("main_rise_runner_trailing_start_pct", 0.06)
        ),
        main_rise_runner_trailing_stop_pct=float(
            parameters.get("main_rise_runner_trailing_stop_pct", 0.02)
        ),
        main_rise_runner_profit_floor_pct=float(
            parameters.get("main_rise_runner_profit_floor_pct", 0.015)
        ),
        mainline_fade_score=float(parameters.get("mainline_fade_score", 45)),
        minimum_sample_for_stability=int(parameters["minimum_sample_for_stability"]),
        min_sealed_amount_ratio=float(parameters.get("min_sealed_amount_ratio", 0.08)),
        min_leader_score=float(parameters.get("min_leader_score", 16)),
        min_mainline_score=float(parameters.get("min_mainline_score", 14)),
        min_turnover_dragon_score=float(parameters.get("min_turnover_dragon_score", 70)),
        min_turnover_dragon_turnover_rate=float(
            parameters.get("min_turnover_dragon_turnover_rate", 3.0)
        ),
        max_turnover_dragon_turnover_rate=float(
            parameters.get("max_turnover_dragon_turnover_rate", 18.0)
        ),
        min_turnover_dragon_sealed_ratio=float(
            parameters.get("min_turnover_dragon_sealed_ratio", 0.1)
        ),
        min_turnover_dragon_auction_ratio=float(
            parameters.get("min_turnover_dragon_auction_ratio", 0.025)
        ),
        min_volume_ratio_5=float(parameters.get("min_volume_ratio_5", 1.0)),
        min_rsi_14=float(parameters.get("min_rsi_14", 55)),
        max_rsi_14=float(parameters.get("max_rsi_14", 85)),
        min_position_percentile_60=float(
            parameters.get("min_position_percentile_60", 0.55)
        ),
        min_breakout_structure_score=float(
            parameters.get("min_breakout_structure_score", 70)
        ),
        max_breakout_entry_distance_pct=float(
            parameters.get("max_breakout_entry_distance_pct", 0.08)
        ),
        min_breakout_volume_ratio=float(
            parameters.get(
                "min_breakout_volume_ratio",
                max(1.2, float(parameters.get("min_volume_ratio_5", 1.0))),
            )
        ),
        min_low_breakout_first_board_count=int(
            parameters.get("min_low_breakout_first_board_count", 0)
        ),
        min_low_breakout_ready_candidates=int(
            parameters.get("min_low_breakout_ready_candidates", 0)
        ),
        max_ready_candidates=int(parameters.get("max_ready_candidates", 0)),
        min_market_cap=float(parameters.get("min_market_cap", 5_000_000_000)),
        max_market_cap=float(parameters.get("max_market_cap", 80_000_000_000)),
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
