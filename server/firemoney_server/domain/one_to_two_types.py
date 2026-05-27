"""Typed inputs and settings boundary for the one-to-two domain policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OneToTwoMarketRow:
    symbol: str
    name: str
    trade_date: str
    board: str
    is_st: bool
    is_delisting: bool
    listing_days: int
    latest_price: float
    previous_close: float
    limit_up_price: float
    first_limit_up_time: str
    sealed_amount: float
    turnover_amount: float
    turnover_rate: float
    open_pct: float
    auction_amount: float
    low_20: float
    high_60: float
    pressure_price: float
    ma_5: float
    ma_10: float
    ma_20: float
    recent_gain_pct: float
    theme: str
    market_temperature: int
    first_board_count: int = 0
    volume_ratio_5: float = 1.5
    rsi_14: float = 65.0
    position_percentile_60: float = 0.75
    market_cap: float = 0.0
    float_market_cap: float = 0.0


@dataclass(frozen=True)
class MarketTrendRow:
    symbol: str
    name: str
    trade_date: str
    board: str
    latest_price: float
    previous_close: float
    change_pct: float
    turnover_amount: float
    turnover_rate: float
    market_cap: float
    float_market_cap: float
    industry: str = ""
    theme: str = ""
    is_st: bool = False
    is_delisting: bool = False


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    name: str
    report_date: str
    roe_pct: float = 0.0
    revenue_growth_pct: float = 0.0
    net_profit_growth_pct: float = 0.0
    gross_margin_pct: float = 0.0
    debt_ratio_pct: float = 0.0
    pe_ttm: float = 0.0
    pb: float = 0.0
    dividend_yield_pct: float = 0.0
    summary: str = ""


@dataclass(frozen=True)
class HistoricalPriceBar:
    trade_date: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    amount: float = 0.0


@dataclass(frozen=True)
class IntradayPriceBar:
    trade_date: str
    timestamp: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    amount: float = 0.0


@dataclass(frozen=True)
class TickSnapshot:
    trade_date: str
    timestamp: str
    last_price: float
    volume: float
    amount: float
    side: str = ""
    bid_price_1: float = 0.0
    ask_price_1: float = 0.0
    bid_volume_1: float = 0.0
    ask_volume_1: float = 0.0


class OneToTwoSettings(Protocol):
    min_score: int
    max_execution_score: float
    max_position_pct: float
    initial_cash: float
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
    min_sealed_amount_ratio: float
    min_leader_score: float
    min_mainline_score: float
    mainline_fade_score: float
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
    first_take_profit_pct: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    max_holding_trade_days: int
    hard_max_holding_trade_days: int
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
    paper_guard_min_profit_drawdown_ratio: float
    exclude_st: bool
    exclude_delisting: bool
    exclude_new_stock_days: int
    excluded_boards: tuple[str, ...]


__all__ = [
    "FundamentalSnapshot",
    "HistoricalPriceBar",
    "IntradayPriceBar",
    "MarketTrendRow",
    "OneToTwoMarketRow",
    "OneToTwoSettings",
    "TickSnapshot",
]
