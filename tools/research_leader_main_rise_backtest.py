"""Research backtest for a daily-bar approximation of leader main-rise tactics.

"Leader main-rise" is not fully observable from daily bars because true leader
status depends on theme heat, board ranking, market memory, order book behavior,
and trader attention. This script therefore tests three measurable proxies:

- leader_main_rise_base: recent strong mover, at least one non-one-word board,
  bullish averages, volume expansion, and close near 20-day high.
- leader_main_rise_strong: stricter strength/volume/position requirements.
- leader_main_rise_trailing_exit: same strong entry, then exits on a trailing
  stop, 5-day moving-average break, or max holding days.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any


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
DEFAULT_OUTPUT = Path("exports") / "leader_main_rise_backtest_recent_3y.json"
LIMIT_UP_THRESHOLD = 0.095
ABNORMAL_LIMIT_CEILING = 0.115


@dataclass(frozen=True)
class LeaderTrade:
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
    exit_reason: str
    recent_gain_20_pct: float
    board_count_10: int
    close_to_high20_pct: float
    volume_ratio_20: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a daily-bar research backtest for leader main-rise tactics."
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END_DATE.isoformat())
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-turnover-amount", type=float, default=80_000_000.0)
    parser.add_argument("--roundtrip-cost-pct", type=float, default=0.0015)
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

    base: list[LeaderTrade] = []
    strong_fixed: list[LeaderTrade] = []
    strong_trailing: list[LeaderTrade] = []
    for stock in universe:
        bars = histories.get(stock.code)
        if not bars:
            continue
        base.extend(
            scan_leader_main_rise(
                stock=stock,
                bars=bars,
                start=start,
                end=end,
                min_turnover_amount=args.min_turnover_amount,
                cost_pct=args.roundtrip_cost_pct,
                strong=False,
                trailing=False,
            )
        )
        strong_fixed.extend(
            scan_leader_main_rise(
                stock=stock,
                bars=bars,
                start=start,
                end=end,
                min_turnover_amount=args.min_turnover_amount,
                cost_pct=args.roundtrip_cost_pct,
                strong=True,
                trailing=False,
            )
        )
        strong_trailing.extend(
            scan_leader_main_rise(
                stock=stock,
                bars=bars,
                start=start,
                end=end,
                min_turnover_amount=args.min_turnover_amount,
                cost_pct=args.roundtrip_cost_pct,
                strong=True,
                trailing=True,
            )
        )

    result = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "universe": "A-share mainboard 10cm, current listed non-ST/non-delisting names",
        "cost_model": {
            "roundtrip_cost_pct": args.roundtrip_cost_pct,
            "note": "Every trade deducts this fixed round-trip cost from gross return.",
        },
        "data_quality": {
            "universe_count": len(universe),
            "loaded_symbol_count": len(histories),
            "failed_symbol_count": len(failed),
            "failed_symbols_preview": failed[:50],
        },
        "limitations": [
            "daily bars cannot identify true theme leader or board-rank leader",
            "entry uses next-day open, so intraday chase/fill quality is approximated",
            "current listed universe introduces survivorship bias",
        ],
        "strategies": {
            "leader_main_rise_base": strategy_payload(
                "龙头主升-基础版",
                "20 日涨幅强、近 10 日有非一字封板、均线多头、放量、靠近 20 日高点，次日开盘买入，持有 5 日。",
                base,
                args.sample_preview,
            ),
            "leader_main_rise_strong": strategy_payload(
                "龙头主升-强势版",
                "更高 20 日涨幅、更强放量、近高位收盘且不追过度乖离，次日开盘买入，持有 5 日。",
                strong_fixed,
                args.sample_preview,
            ),
            "leader_main_rise_trailing_exit": strategy_payload(
                "龙头主升-强势移动退出",
                "强势版入场，跌破 5 日线/从持仓高点回撤 8%/最多 8 日退出。",
                strong_trailing,
                args.sample_preview,
            ),
        },
    }
    result["ranked"] = [
        {
            "strategy_id": strategy_id,
            "name": payload["name"],
            **payload["summary"],
        }
        for strategy_id, payload in result["strategies"].items()
    ]
    result["ranked"].sort(
        key=lambda item: (
            item["average_net_return_pct"] if item["average_net_return_pct"] is not None else -999,
            item["win_rate"] if item["win_rate"] is not None else -1,
        ),
        reverse=True,
    )

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(result)
    print(f"output={output_path}", flush=True)
    return 0


def scan_leader_main_rise(
    stock: StockMeta,
    bars: list[DailyBar],
    start: date,
    end: date,
    min_turnover_amount: float,
    cost_pct: float,
    strong: bool,
    trailing: bool,
) -> list[LeaderTrade]:
    trades: list[LeaderTrade] = []
    last_exit_index = -1
    for index in range(80, len(bars) - 8):
        current = bars[index]
        current_date = parse_iso_date(current.trade_date)
        if current_date < start or current_date > end:
            continue
        if index <= last_exit_index:
            continue
        if stock.listing_date:
            listing = parse_iso_date(stock.listing_date)
            if (current_date - listing).days <= 60:
                continue
        signal = leader_signal(
            bars=bars,
            index=index,
            min_turnover_amount=min_turnover_amount,
            strong=strong,
        )
        if not signal:
            continue
        entry_index = index + 1
        if is_one_word_limit_up(bars, entry_index):
            continue
        if trailing:
            exit_index, exit_reason = resolve_trailing_exit(bars, entry_index)
            strategy_id = "leader_main_rise_trailing_exit"
            strategy_name = "龙头主升-强势移动退出"
        else:
            exit_index = min(entry_index + 5, len(bars) - 1)
            exit_reason = "fixed_5_day_exit"
            strategy_id = "leader_main_rise_strong" if strong else "leader_main_rise_base"
            strategy_name = "龙头主升-强势版" if strong else "龙头主升-基础版"
        trade = make_trade(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock=stock,
            bars=bars,
            signal_index=index,
            entry_index=entry_index,
            exit_index=exit_index,
            exit_reason=exit_reason,
            cost_pct=cost_pct,
            signal=signal,
        )
        if trade:
            trades.append(trade)
            last_exit_index = exit_index
    return trades


def leader_signal(
    bars: list[DailyBar],
    index: int,
    min_turnover_amount: float,
    strong: bool,
) -> dict[str, float] | None:
    current = bars[index]
    recent_gain_20 = pct_change(current.close, bars[index - 20].close)
    recent_gain_10 = pct_change(current.close, bars[index - 10].close)
    board_count_10 = sum(
        1
        for item in range(index - 9, index + 1)
        if is_closed_limit_up(bars, item) and not is_one_word_limit_up(bars, item)
    )
    high20 = max(item.high for item in bars[index - 19 : index + 1])
    close_to_high20 = pct_change(current.close, high20)
    volume_ratio_20 = volume_ratio(bars, index, 20)
    ma5 = average_close(bars[index - 4 : index + 1])
    ma10 = average_close(bars[index - 9 : index + 1])
    ma20 = average_close(bars[index - 19 : index + 1])
    ma60 = average_close(bars[index - 59 : index + 1])
    ma20_deviation = pct_change(current.close, ma20)
    turnover = estimated_turnover_amount(current)

    if turnover < min_turnover_amount:
        return None
    if not (ma5 >= ma10 >= ma20 >= ma60):
        return None
    if board_count_10 < 1:
        return None
    if current.close < current.open:
        return None
    if close_to_high20 < -0.05:
        return None
    if ma20_deviation > 0.55:
        return None
    if strong:
        if recent_gain_20 < 0.22 or recent_gain_10 < 0.08:
            return None
        if board_count_10 < 2:
            return None
        if volume_ratio_20 < 1.2:
            return None
        if close_to_high20 < -0.025:
            return None
        if ma20_deviation > 0.42:
            return None
    else:
        if recent_gain_20 < 0.15 or recent_gain_10 < 0.04:
            return None
        if volume_ratio_20 < 1.0:
            return None
    return {
        "recent_gain_20_pct": recent_gain_20,
        "board_count_10": float(board_count_10),
        "close_to_high20_pct": close_to_high20,
        "volume_ratio_20": volume_ratio_20,
    }


def resolve_trailing_exit(bars: list[DailyBar], entry_index: int) -> tuple[int, str]:
    entry_price = bars[entry_index].open
    peak = max(entry_price, bars[entry_index].high)
    max_exit = min(entry_index + 8, len(bars) - 1)
    for index in range(entry_index, max_exit + 1):
        peak = max(peak, bars[index].high)
        ma5 = average_close(bars[max(0, index - 4) : index + 1])
        if bars[index].close < ma5 and index > entry_index:
            return index, "break_ma5"
        if bars[index].close <= peak * 0.92:
            return index, "trailing_8pct"
    return max_exit, "max_8_day_exit"


def make_trade(
    strategy_id: str,
    strategy_name: str,
    stock: StockMeta,
    bars: list[DailyBar],
    signal_index: int,
    entry_index: int,
    exit_index: int,
    exit_reason: str,
    cost_pct: float,
    signal: dict[str, float],
) -> LeaderTrade | None:
    if entry_index >= len(bars) or exit_index >= len(bars):
        return None
    entry_price = bars[entry_index].open
    exit_price = bars[exit_index].close
    if entry_price <= 0:
        return None
    gross = pct_change(exit_price, entry_price)
    return LeaderTrade(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        symbol=stock.code,
        name=stock.name,
        signal_date=bars[signal_index].trade_date,
        entry_date=bars[entry_index].trade_date,
        exit_date=bars[exit_index].trade_date,
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        gross_return_pct=round(gross, 4),
        net_return_pct=round(gross - cost_pct, 4),
        hold_days=max(1, exit_index - entry_index + 1),
        exit_reason=exit_reason,
        recent_gain_20_pct=round(signal["recent_gain_20_pct"], 4),
        board_count_10=int(signal["board_count_10"]),
        close_to_high20_pct=round(signal["close_to_high20_pct"], 4),
        volume_ratio_20=round(signal["volume_ratio_20"], 4),
    )


def strategy_payload(
    name: str,
    description: str,
    trades: list[LeaderTrade],
    sample_preview: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "summary": summarize_trades(trades),
        "yearly": summarize_by_year(trades),
        "exit_reasons": summarize_exit_reasons(trades),
        "recent_samples": [asdict(item) for item in trades[-sample_preview:]],
    }


def summarize_trades(trades: list[LeaderTrade]) -> dict[str, Any]:
    if not trades:
        return {
            "sample_count": 0,
            "unique_symbol_count": 0,
            "win_count": 0,
            "win_rate": None,
            "average_net_return_pct": None,
            "median_net_return_pct": None,
            "best_net_return_pct": None,
            "worst_net_return_pct": None,
            "signal_day_compound_return_pct": None,
            "max_drawdown_pct": None,
            "average_hold_days": None,
        }
    net_returns = [item.net_return_pct for item in trades]
    compound, max_drawdown = signal_day_equity_stats(trades)
    return {
        "sample_count": len(trades),
        "unique_symbol_count": len({item.symbol for item in trades}),
        "win_count": sum(1 for item in trades if item.net_return_pct > 0),
        "win_rate": ratio(sum(1 for item in trades if item.net_return_pct > 0), len(trades)),
        "average_net_return_pct": round(mean(net_returns), 4),
        "median_net_return_pct": round(median(net_returns), 4),
        "best_net_return_pct": round(max(net_returns), 4),
        "worst_net_return_pct": round(min(net_returns), 4),
        "signal_day_compound_return_pct": round(compound, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
        "average_hold_days": round(mean(item.hold_days for item in trades), 2),
    }


def summarize_by_year(trades: list[LeaderTrade]) -> dict[str, Any]:
    years = sorted({item.entry_date[:4] for item in trades})
    return {
        year: summarize_trades([item for item in trades if item.entry_date.startswith(year)])
        for year in years
    }


def summarize_exit_reasons(trades: list[LeaderTrade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in trades:
        counts[trade.exit_reason] = counts.get(trade.exit_reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def signal_day_equity_stats(trades: list[LeaderTrade]) -> tuple[float, float]:
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


def estimated_turnover_amount(bar: DailyBar) -> float:
    return bar.volume_hands * 100 * bar.close


def volume_ratio(bars: list[DailyBar], index: int, window: int) -> float:
    start = max(0, index - window)
    base = average_volume(bars[start:index])
    if base <= 0:
        return 0.0
    return bars[index].volume_hands / base


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
            "max_dd={max_drawdown_pct}".format(**item),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
