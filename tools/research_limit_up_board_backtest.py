"""Research backtest for the mainboard 10cm limit-up board strategy.

This utility is intentionally separate from the product runtime. It answers:
"From 2024 to now, if we use a daily-bar approximation of the limit-up board
strategy, how often did the matching stocks make money by the next close?"

Daily bars cannot prove queue fill, seal strength, or intraday order book state.
The script therefore reports layered samples:
- touched_board: intraday high touched the 10cm board.
- tradable_touch_board: touched board, not a one-word board, and liquidity passed.
- sealed_board_discipline: touched and closed on the board, not one-word, liquidity passed.
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
    load_histories,
    load_mainboard_universe,
    parse_iso_date,
    pct_change,
)


DEFAULT_START_DATE = "2024-01-01"
DEFAULT_END_DATE = date.today().isoformat()
DEFAULT_CACHE_DIR = Path(".firemoney") / "research_cache" / "one_to_two_daily"
DEFAULT_OUTPUT = Path("exports") / "limit_up_board_backtest_2024_to_now.json"
LIMIT_UP_THRESHOLD = 0.095
ABNORMAL_LIMIT_CEILING = 0.115


@dataclass(frozen=True)
class BoardMatch:
    symbol: str
    name: str
    board_date: str
    next_trade_date: str
    buy_price: float
    previous_close: float
    board_high_pct: float
    board_close_pct: float
    same_day_close_from_buy_pct: float
    next_open_pct: float
    next_high_pct: float
    next_close_pct: float
    estimated_turnover_amount: float
    ma20_deviation_pct: float
    sealed_same_day: bool
    one_word_untradable: bool
    next_open_profitable: bool
    next_high_profitable: bool
    next_close_profitable: bool
    stop_5_touched_next_day: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a daily-bar research backtest for the mainboard 10cm board strategy."
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-turnover-amount", type=float, default=80_000_000.0)
    parser.add_argument("--sample-preview", type=int, default=30)
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
        start_date=start - timedelta(days=80),
        end_date=end,
        cache_dir=cache_dir,
        workers=max(1, args.workers),
        refresh=args.refresh,
    )
    print(f"loaded={len(histories)} failed={len(failed)} analyzing...", flush=True)

    matches: list[BoardMatch] = []
    for stock in universe:
        bars = histories.get(stock.code)
        if not bars:
            continue
        matches.extend(
            analyze_symbol(
                stock=stock,
                bars=bars,
                start_date=start,
                end_date=end,
                min_turnover_amount=args.min_turnover_amount,
            )
        )

    tradable = [
        item
        for item in matches
        if not item.one_word_untradable
        and item.estimated_turnover_amount >= args.min_turnover_amount
    ]
    sealed = [item for item in tradable if item.sealed_same_day]
    unsealed = [item for item in tradable if not item.sealed_same_day]

    result = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": {
            "name": "mainboard_10cm_limit_up_board_daily_research",
            "date_range": {"start": start.isoformat(), "end": end.isoformat()},
            "buy_price": "daily high on the board-touch day",
            "primary_success_definition": "next trading day close is above the board buy price",
            "opportunity_definition": "next trading day high is above the board buy price",
            "limitations": [
                "daily bars only; queue fill, seal strength, opening auction, and intraday order book are approximated",
                "one-word boards are marked untradable because board-buy fill is unlikely",
                "turnover amount is estimated from Tencent volume_hands * 100 * close",
            ],
        },
        "data_quality": {
            "universe_count": len(universe),
            "loaded_symbol_count": len(histories),
            "failed_symbol_count": len(failed),
            "failed_symbols_preview": failed[:50],
        },
        "touched_board": summarize(matches),
        "tradable_touch_board": summarize(tradable),
        "sealed_board_discipline": summarize(sealed),
        "unsealed_failed_board": summarize(unsealed),
        "yearly": {
            "touched_board": summarize_by_year(matches),
            "tradable_touch_board": summarize_by_year(tradable),
            "sealed_board_discipline": summarize_by_year(sealed),
            "unsealed_failed_board": summarize_by_year(unsealed),
        },
        "recent_samples": [asdict(item) for item in sealed[-args.sample_preview :]],
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(result)
    print(f"output={output_path}", flush=True)
    return 0


def analyze_symbol(
    stock: StockMeta,
    bars: list[DailyBar],
    start_date: date,
    end_date: date,
    min_turnover_amount: float,
) -> list[BoardMatch]:
    result: list[BoardMatch] = []
    if len(bars) < 25:
        return result
    for index in range(20, len(bars) - 1):
        current = bars[index]
        current_date = parse_iso_date(current.trade_date)
        if current_date < start_date or current_date > end_date:
            continue
        if stock.listing_date:
            listing = parse_iso_date(stock.listing_date)
            if (current_date - listing).days <= 5:
                continue
        previous = bars[index - 1]
        next_bar = bars[index + 1]
        high_pct = pct_change(current.high, previous.close)
        close_pct = pct_change(current.close, previous.close)
        if high_pct < LIMIT_UP_THRESHOLD:
            continue
        if high_pct > ABNORMAL_LIMIT_CEILING or close_pct > ABNORMAL_LIMIT_CEILING:
            continue
        result.append(
            build_match(
                stock=stock,
                bars=bars,
                index=index,
                previous=previous,
                current=current,
                next_bar=next_bar,
                min_turnover_amount=min_turnover_amount,
            )
        )
    return result


def build_match(
    stock: StockMeta,
    bars: list[DailyBar],
    index: int,
    previous: DailyBar,
    current: DailyBar,
    next_bar: DailyBar,
    min_turnover_amount: float,
) -> BoardMatch:
    buy_price = current.high
    board_high_pct = pct_change(current.high, previous.close)
    board_close_pct = pct_change(current.close, previous.close)
    same_day_close_from_buy_pct = pct_change(current.close, buy_price)
    next_open_pct = pct_change(next_bar.open, buy_price)
    next_high_pct = pct_change(next_bar.high, buy_price)
    next_close_pct = pct_change(next_bar.close, buy_price)
    ma20 = average_close(bars[index - 19 : index + 1])
    estimated_turnover_amount = current.volume_hands * 100 * current.close
    sealed_same_day = board_close_pct >= LIMIT_UP_THRESHOLD
    one_word_untradable = (
        board_high_pct >= LIMIT_UP_THRESHOLD
        and pct_change(current.open, previous.close) >= LIMIT_UP_THRESHOLD
        and pct_change(current.low, previous.close) >= LIMIT_UP_THRESHOLD
        and sealed_same_day
    )
    return BoardMatch(
        symbol=stock.code,
        name=stock.name,
        board_date=current.trade_date,
        next_trade_date=next_bar.trade_date,
        buy_price=round(buy_price, 2),
        previous_close=round(previous.close, 2),
        board_high_pct=round(board_high_pct, 4),
        board_close_pct=round(board_close_pct, 4),
        same_day_close_from_buy_pct=round(same_day_close_from_buy_pct, 4),
        next_open_pct=round(next_open_pct, 4),
        next_high_pct=round(next_high_pct, 4),
        next_close_pct=round(next_close_pct, 4),
        estimated_turnover_amount=round(estimated_turnover_amount, 2),
        ma20_deviation_pct=round(pct_change(current.close, ma20), 4),
        sealed_same_day=sealed_same_day,
        one_word_untradable=one_word_untradable,
        next_open_profitable=next_open_pct > 0,
        next_high_profitable=next_high_pct > 0,
        next_close_profitable=next_close_pct > 0,
        stop_5_touched_next_day=next_bar.low <= buy_price * 0.95,
    )


def summarize(matches: list[BoardMatch]) -> dict[str, Any]:
    unique_symbols = {item.symbol for item in matches}
    if not matches:
        return {
            "sample_count": 0,
            "unique_symbol_count": 0,
            "next_close_win_count": 0,
            "next_close_win_rate": None,
            "next_high_opportunity_count": 0,
            "next_high_opportunity_rate": None,
            "next_open_win_count": 0,
            "next_open_win_rate": None,
            "stop_5_next_day_count": 0,
            "stop_5_next_day_rate": None,
            "average_next_close_pct": None,
            "median_next_close_pct": None,
            "average_same_day_close_from_buy_pct": None,
        }
    return {
        "sample_count": len(matches),
        "unique_symbol_count": len(unique_symbols),
        "next_close_win_count": sum(1 for item in matches if item.next_close_profitable),
        "next_close_win_rate": ratio(
            sum(1 for item in matches if item.next_close_profitable), len(matches)
        ),
        "next_high_opportunity_count": sum(1 for item in matches if item.next_high_profitable),
        "next_high_opportunity_rate": ratio(
            sum(1 for item in matches if item.next_high_profitable), len(matches)
        ),
        "next_open_win_count": sum(1 for item in matches if item.next_open_profitable),
        "next_open_win_rate": ratio(
            sum(1 for item in matches if item.next_open_profitable), len(matches)
        ),
        "stop_5_next_day_count": sum(1 for item in matches if item.stop_5_touched_next_day),
        "stop_5_next_day_rate": ratio(
            sum(1 for item in matches if item.stop_5_touched_next_day), len(matches)
        ),
        "average_next_close_pct": round(mean(item.next_close_pct for item in matches), 4),
        "median_next_close_pct": round(median(item.next_close_pct for item in matches), 4),
        "average_same_day_close_from_buy_pct": round(
            mean(item.same_day_close_from_buy_pct for item in matches),
            4,
        ),
    }


def summarize_by_year(matches: list[BoardMatch]) -> dict[str, dict[str, Any]]:
    years = sorted({item.board_date[:4] for item in matches})
    return {
        year: summarize([item for item in matches if item.board_date.startswith(year)])
        for year in years
    }


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def print_summary(result: dict[str, Any]) -> None:
    print("summary:", flush=True)
    for key in (
        "touched_board",
        "tradable_touch_board",
        "sealed_board_discipline",
        "unsealed_failed_board",
    ):
        stats = result[key]
        print(
            "  {key}: samples={sample_count} symbols={unique_symbol_count} "
            "next_close_win={next_close_win_rate} next_high_opp={next_high_opportunity_rate} "
            "avg_next_close={average_next_close_pct}".format(key=key, **stats),
            flush=True,
        )
    print("  yearly sealed:", flush=True)
    for year, stats in result["yearly"]["sealed_board_discipline"].items():
        print(
            "    {year}: samples={sample_count} next_close_win={next_close_win_rate}".format(
                year=year,
                **stats,
            ),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
