"""Compare common A-share trading tactics over a recent historical window.

This is a research utility, not a production strategy router. It deliberately
keeps the product runtime focused on the one-to-two line while giving us a
repeatable way to compare common tactics with the same data and cost model.

Daily bars cannot prove Level2 queue position, intraday seal strength, theme
leadership, or real fill quality. Strategies that need those inputs are encoded
as conservative daily-bar approximations and should be treated as screening
evidence, not trading advice.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research_one_to_two_backtest import (  # noqa: E402
    DailyBar,
    StockMeta,
    average_close,
    average_volume,
    load_histories,
    load_mainboard_universe,
    parse_iso_date,
    pct_change,
)


DEFAULT_END_DATE = date.today()
DEFAULT_START_DATE = DEFAULT_END_DATE - timedelta(days=365 * 3)
DEFAULT_CACHE_DIR = Path(".firemoney") / "research_cache" / "one_to_two_daily"
DEFAULT_OUTPUT = Path("exports") / "strategy_matrix_backtest_recent_3y.json"
LIMIT_UP_THRESHOLD = 0.095
ABNORMAL_LIMIT_CEILING = 0.115


@dataclass(frozen=True)
class Trade:
    strategy_id: str
    strategy_name: str
    symbol: str
    name: str
    signal_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    gross_return_pct: float
    net_return_pct: float
    hold_days: int
    reason: str


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    description: str
    generator: Callable[[StockMeta, list[DailyBar], date, date, float, float], list[Trade]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare common daily-bar A-share tactics over the recent three years."
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END_DATE.isoformat())
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-turnover-amount", type=float, default=80_000_000.0)
    parser.add_argument(
        "--roundtrip-cost-pct",
        type=float,
        default=0.0015,
        help="Deducted from every trade return. 0.0015 means 0.15%.",
    )
    parser.add_argument("--sample-preview", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date)
    if end < start:
        raise SystemExit("--end-date must be on or after --start-date")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    universe = load_mainboard_universe()
    if args.limit:
        universe = universe[: args.limit]
    print(f"universe={len(universe)} start={start} end={end}", flush=True)

    histories, failed = load_histories(
        universe=universe,
        start_date=start - timedelta(days=420),
        end_date=end,
        cache_dir=cache_dir,
        workers=max(1, args.workers),
        refresh=args.refresh,
    )
    print(f"loaded={len(histories)} failed={len(failed)} analyzing...", flush=True)

    strategies = strategy_definitions()
    trades_by_strategy: dict[str, list[Trade]] = {item.strategy_id: [] for item in strategies}
    for stock in universe:
        bars = histories.get(stock.code)
        if not bars:
            continue
        for strategy in strategies:
            trades_by_strategy[strategy.strategy_id].extend(
                strategy.generator(
                    stock,
                    bars,
                    start,
                    end,
                    args.min_turnover_amount,
                    args.roundtrip_cost_pct,
                )
            )

    result = build_result(
        start=start,
        end=end,
        universe_count=len(universe),
        loaded_symbol_count=len(histories),
        failed=failed,
        strategies=strategies,
        trades_by_strategy=trades_by_strategy,
        roundtrip_cost_pct=args.roundtrip_cost_pct,
        min_turnover_amount=args.min_turnover_amount,
        sample_preview=args.sample_preview,
    )
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(result)
    print(f"output={output_path}", flush=True)
    return 0


def strategy_definitions() -> list[StrategyDefinition]:
    return [
        StrategyDefinition(
            strategy_id="sealed_limit_up_board",
            name="封板打板",
            description="盘中触及 10cm 涨停且当天收盘封住，排除一字板，按涨停价买入，次日收盘卖出。",
            generator=sealed_limit_up_board_trades,
        ),
        StrategyDefinition(
            strategy_id="touch_limit_up_chase",
            name="摸板追涨",
            description="盘中触及 10cm 涨停但不要求封住，排除一字板，按当天最高价买入，次日收盘卖出。",
            generator=touch_limit_up_chase_trades,
        ),
        StrategyDefinition(
            strategy_id="first_board_next_open",
            name="一进二竞价",
            description="昨日首板，次日 0%-7% 开盘且非一字，开盘买入，再下一交易日收盘卖出。",
            generator=first_board_next_open_trades,
        ),
        StrategyDefinition(
            strategy_id="second_board_relay",
            name="二板接力",
            description="当天为第二个连续封板，次日 0%-7% 开盘且非一字，开盘买入，再下一交易日收盘卖出。",
            generator=second_board_relay_trades,
        ),
        StrategyDefinition(
            strategy_id="low_platform_breakout",
            name="低位平台突破",
            description="60 日窄幅平台上沿突破，均线多头且放量，次日开盘买入，持有 5 日。",
            generator=low_platform_breakout_trades,
        ),
        StrategyDefinition(
            strategy_id="volume_new_high_breakout",
            name="放量新高突破",
            description="突破前 120 日高点且成交放大，收盘靠近高点，次日开盘买入，持有 5 日。",
            generator=volume_new_high_breakout_trades,
        ),
        StrategyDefinition(
            strategy_id="ma10_pullback",
            name="10日线回踩",
            description="均线多头趋势中回踩 10 日线并收回，次日开盘买入，持有 5 日。",
            generator=ma10_pullback_trades,
        ),
        StrategyDefinition(
            strategy_id="leader_first_yin",
            name="龙头首阴",
            description="近 5 日出现封板后首次阴线但未跌破 10 日线，次日开盘买入，持有 3 日。",
            generator=leader_first_yin_trades,
        ),
        StrategyDefinition(
            strategy_id="n_shape_reversal",
            name="N字反包",
            description="近 10 日有封板，回调后阳线反包近 3 日高点，次日开盘买入，持有 3 日。",
            generator=n_shape_reversal_trades,
        ),
        StrategyDefinition(
            strategy_id="oversold_rebound",
            name="超跌反弹",
            description="20 日跌幅超过 20% 后放量阳线反弹，次日开盘买入，持有 3 日。",
            generator=oversold_rebound_trades,
        ),
    ]


def sealed_limit_up_board_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(20, len(bars) - 1):
        if not signal_date_in_range(stock, bars[index], start, end):
            continue
        if not is_touched_limit_up(bars, index) or not is_closed_limit_up(bars, index):
            continue
        if is_one_word_limit_up(bars, index):
            continue
        if estimated_turnover_amount(bars[index]) < min_turnover_amount:
            continue
        trade = make_same_day_entry_trade(
            strategy_id="sealed_limit_up_board",
            strategy_name="封板打板",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_price=bars[index].high,
            exit_index=index + 1,
            cost_pct=cost_pct,
            reason="sealed_limit_up",
        )
        if trade:
            trades.append(trade)
    return trades


def touch_limit_up_chase_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(20, len(bars) - 1):
        if not signal_date_in_range(stock, bars[index], start, end):
            continue
        if not is_touched_limit_up(bars, index):
            continue
        if is_one_word_limit_up(bars, index):
            continue
        if estimated_turnover_amount(bars[index]) < min_turnover_amount:
            continue
        trade = make_same_day_entry_trade(
            strategy_id="touch_limit_up_chase",
            strategy_name="摸板追涨",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_price=bars[index].high,
            exit_index=index + 1,
            cost_pct=cost_pct,
            reason="touched_limit_up",
        )
        if trade:
            trades.append(trade)
    return trades


def first_board_next_open_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(20, len(bars) - 2):
        if not signal_date_in_range(stock, bars[index], start, end):
            continue
        if not is_first_board(bars, index):
            continue
        if is_one_word_limit_up(bars, index):
            continue
        if estimated_turnover_amount(bars[index]) < min_turnover_amount:
            continue
        entry_index = index + 1
        entry_open_pct = pct_change(bars[entry_index].open, bars[index].close)
        if not 0 <= entry_open_pct <= 0.07:
            continue
        if is_one_word_limit_up(bars, entry_index):
            continue
        trade = make_next_open_trade(
            strategy_id="first_board_next_open",
            strategy_name="一进二竞价",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=entry_index,
            exit_index=entry_index + 1,
            cost_pct=cost_pct,
            reason="first_board_open_confirmed",
        )
        if trade:
            trades.append(trade)
    return trades


def second_board_relay_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(25, len(bars) - 2):
        if not signal_date_in_range(stock, bars[index], start, end):
            continue
        if consecutive_limit_up_count(bars, index) != 2:
            continue
        if is_one_word_limit_up(bars, index):
            continue
        if estimated_turnover_amount(bars[index]) < min_turnover_amount:
            continue
        entry_index = index + 1
        entry_open_pct = pct_change(bars[entry_index].open, bars[index].close)
        if not 0 <= entry_open_pct <= 0.07:
            continue
        if is_one_word_limit_up(bars, entry_index):
            continue
        trade = make_next_open_trade(
            strategy_id="second_board_relay",
            strategy_name="二板接力",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=entry_index,
            exit_index=entry_index + 1,
            cost_pct=cost_pct,
            reason="second_board_open_confirmed",
        )
        if trade:
            trades.append(trade)
    return trades


def low_platform_breakout_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(80, len(bars) - 5):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        prior60 = bars[index - 60 : index]
        prev_high60 = max(item.high for item in prior60)
        prev_low60 = min(item.low for item in prior60)
        if prev_low60 <= 0 or prev_high60 / prev_low60 > 1.35:
            continue
        if current.close < prev_high60 * 1.005:
            continue
        if current.close < current.high * 0.97:
            continue
        if not ma_bullish(bars, index):
            continue
        if volume_ratio(bars, index, 20) < 1.4:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        trade = make_next_open_trade(
            strategy_id="low_platform_breakout",
            strategy_name="低位平台突破",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 5,
            cost_pct=cost_pct,
            reason="low_platform_breakout",
        )
        if trade:
            trades.append(trade)
    return trades


def volume_new_high_breakout_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(140, len(bars) - 5):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        prev_high120 = max(item.high for item in bars[index - 120 : index])
        if current.close < prev_high120 * 1.005:
            continue
        if current.close < current.high * 0.965:
            continue
        if volume_ratio(bars, index, 20) < 1.8:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        if is_one_word_limit_up(bars, index):
            continue
        trade = make_next_open_trade(
            strategy_id="volume_new_high_breakout",
            strategy_name="放量新高突破",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 5,
            cost_pct=cost_pct,
            reason="volume_new_high_breakout",
        )
        if trade:
            trades.append(trade)
    return trades


def ma10_pullback_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(60, len(bars) - 5):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        ma10 = average_close(bars[index - 9 : index + 1])
        ma20 = average_close(bars[index - 19 : index + 1])
        if not ma_bullish(bars, index):
            continue
        if pct_change(bars[index - 1].close, bars[index - 21].close) < 0.10:
            continue
        if not (current.low <= ma10 * 1.02 and current.close >= ma10):
            continue
        if current.close <= current.open:
            continue
        if current.close < ma20 * 1.03:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        trade = make_next_open_trade(
            strategy_id="ma10_pullback",
            strategy_name="10日线回踩",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 5,
            cost_pct=cost_pct,
            reason="ma10_pullback",
        )
        if trade:
            trades.append(trade)
    return trades


def leader_first_yin_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(30, len(bars) - 3):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        recent_indices = range(max(1, index - 5), index)
        if not any(is_closed_limit_up(bars, item) and not is_one_word_limit_up(bars, item) for item in recent_indices):
            continue
        if current.close >= current.open:
            continue
        if pct_change(current.close, bars[index - 1].close) < -0.07:
            continue
        ma10 = average_close(bars[index - 9 : index + 1])
        if current.close < ma10:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        trade = make_next_open_trade(
            strategy_id="leader_first_yin",
            strategy_name="龙头首阴",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 3,
            cost_pct=cost_pct,
            reason="leader_first_yin",
        )
        if trade:
            trades.append(trade)
    return trades


def n_shape_reversal_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(40, len(bars) - 3):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        recent_board_indices = [
            item
            for item in range(max(1, index - 10), index - 1)
            if is_closed_limit_up(bars, item) and not is_one_word_limit_up(bars, item)
        ]
        if not recent_board_indices:
            continue
        board_index = recent_board_indices[-1]
        if index - board_index < 3:
            continue
        if current.close <= current.open:
            continue
        if current.close <= max(item.high for item in bars[index - 3 : index]):
            continue
        if current.close < bars[board_index].close * 0.92:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        trade = make_next_open_trade(
            strategy_id="n_shape_reversal",
            strategy_name="N字反包",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 3,
            cost_pct=cost_pct,
            reason="n_shape_reversal",
        )
        if trade:
            trades.append(trade)
    return trades


def oversold_rebound_trades(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
) -> list[Trade]:
    trades: list[Trade] = []
    for index in range(30, len(bars) - 3):
        current = bars[index]
        if not signal_date_in_range(stock, current, start, end):
            continue
        drawdown20 = pct_change(current.close, bars[index - 20].close)
        if drawdown20 > -0.20:
            continue
        if current.close <= current.open:
            continue
        if pct_change(current.close, bars[index - 1].close) < 0.03:
            continue
        if volume_ratio(bars, index, 10) < 1.2:
            continue
        if estimated_turnover_amount(current) < min_turnover_amount:
            continue
        trade = make_next_open_trade(
            strategy_id="oversold_rebound",
            strategy_name="超跌反弹",
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=index + 1,
            exit_index=index + 3,
            cost_pct=cost_pct,
            reason="oversold_rebound",
        )
        if trade:
            trades.append(trade)
    return trades


def make_same_day_entry_trade(
    strategy_id: str,
    strategy_name: str,
    stock: StockMeta,
    bars: list[DailyBar],
    signal_index: int,
    entry_price: float,
    exit_index: int,
    cost_pct: float,
    reason: str,
) -> Trade | None:
    if exit_index >= len(bars) or entry_price <= 0:
        return None
    gross = pct_change(bars[exit_index].close, entry_price)
    return Trade(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        symbol=stock.code,
        name=stock.name,
        signal_date=bars[signal_index].trade_date,
        entry_date=bars[signal_index].trade_date,
        exit_date=bars[exit_index].trade_date,
        entry_price=round(entry_price, 2),
        exit_price=round(bars[exit_index].close, 2),
        gross_return_pct=round(gross, 4),
        net_return_pct=round(gross - cost_pct, 4),
        hold_days=1,
        reason=reason,
    )


def make_next_open_trade(
    strategy_id: str,
    strategy_name: str,
    stock: StockMeta,
    bars: list[DailyBar],
    signal_index: int,
    entry_index: int,
    exit_index: int,
    cost_pct: float,
    reason: str,
) -> Trade | None:
    if exit_index >= len(bars) or entry_index >= len(bars):
        return None
    if is_one_word_limit_up(bars, entry_index):
        return None
    entry_price = bars[entry_index].open
    if entry_price <= 0:
        return None
    gross = pct_change(bars[exit_index].close, entry_price)
    return Trade(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        symbol=stock.code,
        name=stock.name,
        signal_date=bars[signal_index].trade_date,
        entry_date=bars[entry_index].trade_date,
        exit_date=bars[exit_index].trade_date,
        entry_price=round(entry_price, 2),
        exit_price=round(bars[exit_index].close, 2),
        gross_return_pct=round(gross, 4),
        net_return_pct=round(gross - cost_pct, 4),
        hold_days=max(1, exit_index - entry_index + 1),
        reason=reason,
    )


def build_result(
    start: date,
    end: date,
    universe_count: int,
    loaded_symbol_count: int,
    failed: list[str],
    strategies: list[StrategyDefinition],
    trades_by_strategy: dict[str, list[Trade]],
    roundtrip_cost_pct: float,
    min_turnover_amount: float,
    sample_preview: int,
) -> dict[str, Any]:
    strategy_payload: dict[str, Any] = {}
    ranked: list[dict[str, Any]] = []
    for strategy in strategies:
        trades = trades_by_strategy[strategy.strategy_id]
        summary = summarize_trades(trades)
        yearly = summarize_by_year(trades)
        positive_year_count = sum(
            1
            for item in yearly.values()
            if item["sample_count"] > 0 and item["average_net_return_pct"] > 0
        )
        strategy_payload[strategy.strategy_id] = {
            "name": strategy.name,
            "description": strategy.description,
            "summary": summary,
            "yearly": yearly,
            "recent_samples": [asdict(item) for item in trades[-sample_preview:]],
        }
        ranked.append(
            {
                "strategy_id": strategy.strategy_id,
                "name": strategy.name,
                "sample_count": summary["sample_count"],
                "win_rate": summary["win_rate"],
                "average_net_return_pct": summary["average_net_return_pct"],
                "median_net_return_pct": summary["median_net_return_pct"],
                "signal_day_compound_return_pct": summary["signal_day_compound_return_pct"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
                "positive_year_count": positive_year_count,
            }
        )
    ranked.sort(
        key=lambda item: (
            item["positive_year_count"],
            item["average_net_return_pct"] if item["average_net_return_pct"] is not None else -999,
            item["sample_count"],
        ),
        reverse=True,
    )
    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "universe": "A-share mainboard 10cm, current listed non-ST/non-delisting names",
        "cost_model": {
            "roundtrip_cost_pct": roundtrip_cost_pct,
            "note": "Every trade deducts this fixed round-trip cost from gross return.",
        },
        "data_quality": {
            "universe_count": universe_count,
            "loaded_symbol_count": loaded_symbol_count,
            "failed_symbol_count": len(failed),
            "failed_symbols_preview": failed[:50],
        },
        "minimum_turnover_amount": min_turnover_amount,
        "limitations": [
            "current listed universe introduces survivorship bias",
            "daily bars cannot verify Level2 queue fills, seal amount, intraday stops, or topic leadership",
            "strategy definitions are rule-based approximations of common tactics, not exact private trader playbooks",
            "signal-day compound return assumes full capital is split equally across same-day signals and is idle otherwise",
        ],
        "ranked": ranked,
        "strategies": strategy_payload,
    }


def summarize_trades(trades: list[Trade]) -> dict[str, Any]:
    if not trades:
        return {
            "sample_count": 0,
            "unique_symbol_count": 0,
            "win_count": 0,
            "win_rate": None,
            "average_gross_return_pct": None,
            "average_net_return_pct": None,
            "median_net_return_pct": None,
            "best_net_return_pct": None,
            "worst_net_return_pct": None,
            "signal_day_compound_return_pct": None,
            "max_drawdown_pct": None,
        }
    net_returns = [item.net_return_pct for item in trades]
    gross_returns = [item.gross_return_pct for item in trades]
    compound_return, max_drawdown = signal_day_equity_stats(trades)
    return {
        "sample_count": len(trades),
        "unique_symbol_count": len({item.symbol for item in trades}),
        "win_count": sum(1 for item in trades if item.net_return_pct > 0),
        "win_rate": ratio(sum(1 for item in trades if item.net_return_pct > 0), len(trades)),
        "average_gross_return_pct": round(mean(gross_returns), 4),
        "average_net_return_pct": round(mean(net_returns), 4),
        "median_net_return_pct": round(median(net_returns), 4),
        "best_net_return_pct": round(max(net_returns), 4),
        "worst_net_return_pct": round(min(net_returns), 4),
        "signal_day_compound_return_pct": round(compound_return, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
    }


def summarize_by_year(trades: list[Trade]) -> dict[str, Any]:
    years = sorted({item.entry_date[:4] for item in trades})
    return {
        year: summarize_trades([item for item in trades if item.entry_date.startswith(year)])
        for year in years
    }


def signal_day_equity_stats(trades: list[Trade]) -> tuple[float, float]:
    by_day: dict[str, list[float]] = {}
    for trade in trades:
        by_day.setdefault(trade.entry_date, []).append(trade.net_return_pct)
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for day in sorted(by_day):
        day_return = mean(by_day[day])
        equity *= max(0.0, 1 + day_return)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1)
    return equity - 1, max_drawdown


def signal_date_in_range(stock: StockMeta, bar: DailyBar, start: date, end: date) -> bool:
    current = parse_iso_date(bar.trade_date)
    if current < start or current > end:
        return False
    if stock.listing_date:
        listing = parse_iso_date(stock.listing_date)
        if (current - listing).days <= 30:
            return False
    return True


def is_touched_limit_up(bars: list[DailyBar], index: int) -> bool:
    if index <= 0:
        return False
    high_pct = pct_change(bars[index].high, bars[index - 1].close)
    return LIMIT_UP_THRESHOLD <= high_pct <= ABNORMAL_LIMIT_CEILING


def is_closed_limit_up(bars: list[DailyBar], index: int) -> bool:
    if index <= 0:
        return False
    close_pct = pct_change(bars[index].close, bars[index - 1].close)
    return LIMIT_UP_THRESHOLD <= close_pct <= ABNORMAL_LIMIT_CEILING and bars[index].close >= bars[index].high * 0.995


def is_one_word_limit_up(bars: list[DailyBar], index: int) -> bool:
    if index <= 0:
        return False
    previous_close = bars[index - 1].close
    return (
        pct_change(bars[index].open, previous_close) >= LIMIT_UP_THRESHOLD
        and pct_change(bars[index].low, previous_close) >= LIMIT_UP_THRESHOLD
        and is_closed_limit_up(bars, index)
    )


def is_first_board(bars: list[DailyBar], index: int) -> bool:
    return is_closed_limit_up(bars, index) and not is_closed_limit_up(bars, index - 1)


def consecutive_limit_up_count(bars: list[DailyBar], index: int) -> int:
    count = 0
    current = index
    while current > 0 and is_closed_limit_up(bars, current):
        count += 1
        current -= 1
    return count


def estimated_turnover_amount(bar: DailyBar) -> float:
    return bar.volume_hands * 100 * bar.close


def volume_ratio(bars: list[DailyBar], index: int, window: int) -> float:
    start = max(0, index - window)
    base = average_volume(bars[start:index])
    if base <= 0:
        return 0.0
    return bars[index].volume_hands / base


def ma_bullish(bars: list[DailyBar], index: int) -> bool:
    if index < 20:
        return False
    ma5 = average_close(bars[index - 4 : index + 1])
    ma10 = average_close(bars[index - 9 : index + 1])
    ma20 = average_close(bars[index - 19 : index + 1])
    return ma5 >= ma10 >= ma20


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def print_summary(result: dict[str, Any]) -> None:
    print("summary:", flush=True)
    for item in result["ranked"]:
        print(
            "  {name}: samples={sample_count} win={win_rate} avg_net={average_net_return_pct} "
            "median={median_net_return_pct} compound={signal_day_compound_return_pct} "
            "positive_years={positive_year_count}".format(**item),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
