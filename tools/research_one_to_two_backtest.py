"""Research backtest for the mainboard 10cm one-to-two strategy.

This utility is intentionally outside the runtime product path. It answers:
"From 2024 to now, how often did historical mainboard first boards complete
the next-day second board under the one-to-two discipline?"

The scan uses daily bars only, so auction strength, sealed order amount,
intraday fills, and live topic heat are approximations.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


DEFAULT_START_DATE = "2024-01-01"
DEFAULT_END_DATE = date.today().isoformat()
DEFAULT_CACHE_DIR = Path(".firemoney") / "research_cache" / "one_to_two_daily"
DEFAULT_OUTPUT = Path("exports") / "one_to_two_backtest_2024_to_now.json"
TENCENT_KLINE_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
MAINBOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")
LIMIT_UP_THRESHOLD = 0.095
SECOND_BOARD_TOUCH_THRESHOLD = 0.095
DEFAULT_MIN_SCORE = 82.0
DEFAULT_MIN_TURNOVER_AMOUNT = 80_000_000.0
DEFAULT_POSITION_PCT = 0.08
DEFAULT_STOP_LOSS_PCT = 0.0425
DEFAULT_FIRST_TAKE_PROFIT_PCT = 0.28
DEFAULT_STRONG_TAKE_PROFIT_PCT = 0.0825
DEFAULT_TRAILING_STOP_PCT = 0.001
DEFAULT_DISCIPLINE_EXIT_MIN_GAIN_PCT = 0.04
DEFAULT_MAX_HOLDING_TRADE_DAYS = 2
DEFAULT_MAX_SIMULATION_TRADE_DAYS = 10
DEFAULT_MIN_LOW_BREAKOUT_FIRST_BOARD_COUNT = 45
DEFAULT_MIN_LOW_BREAKOUT_READY_CANDIDATES = 6
MIN_COMPLETE_MAINBOARD_UNIVERSE = 2500


@dataclass(frozen=True)
class StockMeta:
    code: str
    name: str
    listing_date: str | None


@dataclass(frozen=True)
class DailyBar:
    trade_date: str
    open: float
    close: float
    high: float
    low: float
    volume_hands: float


@dataclass(frozen=True)
class Match:
    symbol: str
    name: str
    first_board_date: str
    second_day_date: str
    first_board_pct: float
    second_close_pct: float
    second_open_pct: float
    second_high_pct: float
    buy_open_to_close_pct: float
    score: float
    position_label: str
    estimated_turnover_amount: float
    recent_gain_pct: float
    ma20_deviation_pct: float
    pressure_distance_pct: float | None
    first_board_count: int
    ready_candidate_count: int
    second_day_one_word: bool
    blockers: tuple[str, ...]
    second_board_closed: bool
    second_board_touched: bool
    buy_day_positive: bool


@dataclass(frozen=True)
class SimulatedTrade:
    symbol: str
    name: str
    first_board_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    r_multiple: float
    holding_trade_days: int
    exit_reason: str
    score: float
    position_label: str
    second_open_pct: float
    estimated_turnover_amount: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a daily-bar research backtest for the FireMoney one-to-two strategy."
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-turnover-amount", type=float, default=DEFAULT_MIN_TURNOVER_AMOUNT)
    parser.add_argument("--recent-gain-block-pct", type=float, default=0.45)
    parser.add_argument("--high-deviation-block-pct", type=float, default=0.25)
    parser.add_argument("--near-pressure-pct", type=float, default=0.05)
    parser.add_argument("--min-confirm-open-pct", type=float, default=0.0)
    parser.add_argument("--max-confirm-open-pct", type=float, default=0.045)
    parser.add_argument("--position-pct", type=float, default=DEFAULT_POSITION_PCT)
    parser.add_argument("--stop-loss-pct", type=float, default=DEFAULT_STOP_LOSS_PCT)
    parser.add_argument(
        "--first-take-profit-pct",
        type=float,
        default=DEFAULT_FIRST_TAKE_PROFIT_PCT,
    )
    parser.add_argument(
        "--strong-take-profit-pct",
        type=float,
        default=DEFAULT_STRONG_TAKE_PROFIT_PCT,
    )
    parser.add_argument(
        "--trailing-stop-pct",
        type=float,
        default=DEFAULT_TRAILING_STOP_PCT,
    )
    parser.add_argument(
        "--discipline-exit-min-gain-pct",
        type=float,
        default=DEFAULT_DISCIPLINE_EXIT_MIN_GAIN_PCT,
    )
    parser.add_argument(
        "--max-holding-trade-days",
        type=int,
        default=DEFAULT_MAX_HOLDING_TRADE_DAYS,
    )
    parser.add_argument(
        "--max-simulation-trade-days",
        type=int,
        default=DEFAULT_MAX_SIMULATION_TRADE_DAYS,
    )
    parser.add_argument("--sample-preview", type=int, default=30)
    parser.add_argument(
        "--min-low-breakout-first-board-count",
        type=int,
        default=DEFAULT_MIN_LOW_BREAKOUT_FIRST_BOARD_COUNT,
    )
    parser.add_argument(
        "--min-low-breakout-ready-candidates",
        type=int,
        default=DEFAULT_MIN_LOW_BREAKOUT_READY_CANDIDATES,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = parse_iso_date(args.start_date)
    end = parse_iso_date(args.end_date)
    if end < start:
        raise SystemExit("--end-date must be on or after --start-date")

    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    universe = load_mainboard_universe(
        cache_dir=cache_dir,
        minimum_count=0 if args.limit else MIN_COMPLETE_MAINBOARD_UNIVERSE,
    )
    universe_warnings = list(getattr(load_mainboard_universe, "last_warnings", []))
    if args.limit:
        universe = universe[: args.limit]
    print(f"universe={len(universe)} start={start} end={end}", flush=True)

    lookback_start = start - timedelta(days=220)
    histories, failed = load_histories(
        universe=universe,
        start_date=lookback_start,
        end_date=end,
        cache_dir=cache_dir,
        workers=max(1, args.workers),
        refresh=args.refresh,
    )
    print(
        f"loaded={len(histories)} failed={len(failed)} analyzing...",
        flush=True,
    )

    matches: list[Match] = []
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
                recent_gain_block_pct=args.recent_gain_block_pct,
                high_deviation_block_pct=args.high_deviation_block_pct,
                near_pressure_pct=args.near_pressure_pct,
                min_confirm_open_pct=args.min_confirm_open_pct,
                max_confirm_open_pct=args.max_confirm_open_pct,
            )
        )

    filtered = apply_market_width_gate(
        matches=matches,
        min_score=args.min_score,
        min_low_breakout_first_board_count=args.min_low_breakout_first_board_count,
        min_low_breakout_ready_candidates=args.min_low_breakout_ready_candidates,
    )
    result = build_result(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        universe_count=len(universe),
        loaded_symbol_count=len(histories),
        failed_symbol_count=len(failed),
        failed_symbols=failed[:50],
        universe_warnings=universe_warnings,
        basic_matches=matches,
        filtered_matches=filtered,
        histories=histories,
        min_score=args.min_score,
        min_confirm_open_pct=args.min_confirm_open_pct,
        max_confirm_open_pct=args.max_confirm_open_pct,
        position_pct=args.position_pct,
        stop_loss_pct=args.stop_loss_pct,
        first_take_profit_pct=args.first_take_profit_pct,
        strong_take_profit_pct=args.strong_take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        discipline_exit_min_gain_pct=args.discipline_exit_min_gain_pct,
        max_holding_trade_days=args.max_holding_trade_days,
        max_simulation_trade_days=args.max_simulation_trade_days,
        min_low_breakout_first_board_count=args.min_low_breakout_first_board_count,
        min_low_breakout_ready_candidates=args.min_low_breakout_ready_candidates,
        sample_preview=args.sample_preview,
    )
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(result)
    print(f"output={output_path}", flush=True)
    return 0


def load_mainboard_universe(
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
    minimum_count: int = MIN_COMPLETE_MAINBOARD_UNIVERSE,
) -> list[StockMeta]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local environment
        raise SystemExit(f"akshare is required for stock universe loading: {exc}") from exc

    stocks: dict[str, StockMeta] = {}
    warnings: list[str] = []
    sh_loaded = False
    sz_loaded = False

    try:
        sh_df = ak.stock_info_sh_name_code(symbol="\u4e3b\u677fA\u80a1")
        for row in sh_df.to_dict("records"):
            code = normalize_code(row.get("\u8bc1\u5238\u4ee3\u7801"))
            name = normalize_name(row.get("\u8bc1\u5238\u7b80\u79f0"))
            listing_date = normalize_date_value(row.get("\u4e0a\u5e02\u65e5\u671f"))
            add_stock(stocks, code, name, listing_date)
        sh_loaded = True
    except Exception as exc:
        message = f"failed to load Shanghai mainboard universe: {exc}"
        warnings.append(message)
        print(f"warning: {message}", file=sys.stderr)

    try:
        sz_df = ak.stock_info_sz_name_code(symbol="A\u80a1\u5217\u8868")
        for row in sz_df.to_dict("records"):
            if str(row.get("\u677f\u5757", "")).strip() != "\u4e3b\u677f":
                continue
            code = normalize_code(row.get("A\u80a1\u4ee3\u7801"))
            name = normalize_name(row.get("A\u80a1\u7b80\u79f0"))
            listing_date = normalize_date_value(row.get("A\u80a1\u4e0a\u5e02\u65e5\u671f"))
            add_stock(stocks, code, name, listing_date)
        sz_loaded = True
    except Exception as exc:
        message = f"failed to load Shenzhen mainboard universe: {exc}"
        warnings.append(message)
        print(f"warning: {message}", file=sys.stderr)

    if not sh_loaded or not sz_loaded or len(stocks) < minimum_count:
        before_fallback = len(stocks)
        try:
            fallback_df = ak.stock_info_a_code_name()
            for row in fallback_df.to_dict("records"):
                code = normalize_code(row.get("code"))
                name = normalize_name(row.get("name"))
                add_stock(stocks, code, name, None)
            if len(stocks) > before_fallback:
                warnings.append(
                    "filled mainboard universe from AkShare A-code fallback "
                    f"({before_fallback}->{len(stocks)})"
                )
        except Exception as exc:
            message = f"failed to load AkShare A-code fallback universe: {exc}"
            warnings.append(message)
            print(f"warning: {message}", file=sys.stderr)

    if cache_dir is not None and len(stocks) < minimum_count:
        before_cache = len(stocks)
        cached_added = add_cached_universe(stocks, cache_dir)
        if cached_added:
            warnings.append(
                "filled mainboard universe from cached history files "
                f"({before_cache}->{len(stocks)})"
            )

    load_mainboard_universe.last_warnings = warnings
    if minimum_count and len(stocks) < minimum_count:
        raise SystemExit(
            "mainboard universe is incomplete: "
            f"loaded {len(stocks)} symbols, expected at least {minimum_count}. "
            "Retry later, pass --limit for a smoke run, or warm the local history cache."
        )

    return sorted(stocks.values(), key=lambda item: item.code)


load_mainboard_universe.last_warnings = []


def add_stock(
    stocks: dict[str, StockMeta],
    code: str,
    name: str,
    listing_date: str | None,
) -> None:
    if not is_mainboard_code(code):
        return
    if not name or is_blocked_name(name):
        return
    stocks[code] = StockMeta(code=code, name=name, listing_date=listing_date)


def add_cached_universe(stocks: dict[str, StockMeta], cache_dir: Path) -> int:
    if not cache_dir.exists():
        return 0
    added = 0
    for cache_file in cache_dir.glob("*.json"):
        code = normalize_code(cache_file.stem)
        if code in stocks or not is_mainboard_code(code):
            continue
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = normalize_name(payload.get("name")) or code
        if is_blocked_name(name):
            continue
        stocks[code] = StockMeta(code=code, name=name, listing_date=None)
        added += 1
    return added


def load_histories(
    universe: list[StockMeta],
    start_date: date,
    end_date: date,
    cache_dir: Path,
    workers: int,
    refresh: bool,
) -> tuple[dict[str, list[DailyBar]], list[str]]:
    histories: dict[str, list[DailyBar]] = {}
    failed: list[str] = []
    started_at = time.monotonic()
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                load_history,
                stock,
                start_date,
                end_date,
                cache_dir,
                refresh,
            ): stock
            for stock in universe
        }
        for future in concurrent.futures.as_completed(futures):
            stock = futures[future]
            completed += 1
            try:
                bars = future.result()
            except Exception as exc:
                failed.append(f"{stock.code}:{exc}")
            else:
                if bars:
                    histories[stock.code] = bars
                else:
                    failed.append(f"{stock.code}:empty")
            if completed % 100 == 0 or completed == len(universe):
                elapsed = time.monotonic() - started_at
                print(
                    f"progress={completed}/{len(universe)} loaded={len(histories)} "
                    f"failed={len(failed)} elapsed={elapsed:.1f}s",
                    flush=True,
                )
    return histories, failed


def load_history(
    stock: StockMeta,
    start_date: date,
    end_date: date,
    cache_dir: Path,
    refresh: bool,
) -> list[DailyBar]:
    cache_file = cache_dir / f"{stock.code}.json"
    if not refresh:
        cached = read_cached_bars(cache_file, start_date, end_date)
        if cached is not None:
            return cached

    bars = fetch_tencent_daily_bars(stock.code, start_date, end_date)
    cache_payload = {
        "symbol": stock.code,
        "name": stock.name,
        "source": "tencent_newfqkline",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "rows": [asdict(item) for item in bars],
    }
    cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")
    return bars


def read_cached_bars(cache_file: Path, start_date: date, end_date: date) -> list[DailyBar] | None:
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        bars = [DailyBar(**row) for row in rows]
    except Exception:
        return None
    if not bars:
        return None
    dates = [parse_iso_date(item.trade_date) for item in bars]
    if min(dates) > start_date + timedelta(days=10):
        return None
    last_allowed = end_date - timedelta(days=10)
    if max(dates) < last_allowed:
        return None
    return bars


def fetch_tencent_daily_bars(code: str, start_date: date, end_date: date) -> list[DailyBar]:
    tx_symbol = tencent_symbol(code)
    query = urllib.parse.urlencode(
        {
            "_var": f"kline_day_{tx_symbol}",
            "param": (
                f"{tx_symbol},day,{start_date.isoformat()},"
                f"{end_date.isoformat()},1000,"
            ),
            "r": "0.8205512681390605",
        }
    )
    url = f"{TENCENT_KLINE_URL}?{query}"
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                    ),
                    "Referer": "https://gu.qq.com/",
                },
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                text = response.read().decode("utf-8", errors="ignore")
            payload = parse_tencent_payload(text)
            raw_rows = payload["data"][tx_symbol].get("day", [])
            bars = [parse_daily_bar(row) for row in raw_rows if len(row) >= 6]
            filtered = [
                item
                for item in bars
                if start_date <= parse_iso_date(item.trade_date) <= end_date
            ]
            return sorted(deduplicate_bars(filtered), key=lambda item: item.trade_date)
        except Exception as exc:  # pragma: no cover - network dependent
            last_exc = exc
            time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(str(last_exc) if last_exc else "unknown fetch error")


def parse_tencent_payload(text: str) -> dict[str, Any]:
    equals_index = text.find("=")
    if equals_index >= 0:
        text = text[equals_index + 1 :]
    return json.loads(text)


def parse_daily_bar(row: list[Any]) -> DailyBar:
    return DailyBar(
        trade_date=str(row[0]),
        open=safe_float(row[1]),
        close=safe_float(row[2]),
        high=safe_float(row[3]),
        low=safe_float(row[4]),
        volume_hands=safe_float(row[5]),
    )


def deduplicate_bars(bars: Iterable[DailyBar]) -> list[DailyBar]:
    by_date: dict[str, DailyBar] = {}
    for item in bars:
        by_date[item.trade_date] = item
    return list(by_date.values())


def analyze_symbol(
    stock: StockMeta,
    bars: list[DailyBar],
    start_date: date,
    end_date: date,
    min_turnover_amount: float,
    recent_gain_block_pct: float,
    high_deviation_block_pct: float,
    near_pressure_pct: float,
    min_confirm_open_pct: float,
    max_confirm_open_pct: float,
) -> list[Match]:
    result: list[Match] = []
    if len(bars) < 65:
        return result

    for index in range(61, len(bars) - 1):
        current = bars[index]
        current_date = parse_iso_date(current.trade_date)
        if current_date < start_date or current_date > end_date:
            continue
        if stock.listing_date:
            listing = parse_iso_date(stock.listing_date)
            if (current_date - listing).days <= 5:
                continue

        previous = bars[index - 1]
        previous_previous = bars[index - 2]
        first_pct = pct_change(current.close, previous.close)
        previous_pct = pct_change(previous.close, previous_previous.close)
        if first_pct < LIMIT_UP_THRESHOLD or previous_pct >= LIMIT_UP_THRESHOLD:
            continue

        next_bar = bars[index + 1]
        match = build_match(
            stock=stock,
            bars=bars,
            index=index,
            next_bar=next_bar,
            first_pct=first_pct,
            min_turnover_amount=min_turnover_amount,
            recent_gain_block_pct=recent_gain_block_pct,
            high_deviation_block_pct=high_deviation_block_pct,
            near_pressure_pct=near_pressure_pct,
            min_confirm_open_pct=min_confirm_open_pct,
            max_confirm_open_pct=max_confirm_open_pct,
        )
        result.append(match)
    return result


def build_match(
    stock: StockMeta,
    bars: list[DailyBar],
    index: int,
    next_bar: DailyBar,
    first_pct: float,
    min_turnover_amount: float,
    recent_gain_block_pct: float,
    high_deviation_block_pct: float,
    near_pressure_pct: float,
    min_confirm_open_pct: float,
    max_confirm_open_pct: float,
) -> Match:
    current = bars[index]
    previous = bars[index - 1]
    lookback20 = bars[index - 20 : index + 1]
    prior20 = bars[index - 20 : index]
    prior60 = bars[index - 60 : index]
    prior5 = bars[index - 5 : index]

    ma5 = average_close(bars[index - 4 : index + 1])
    ma10 = average_close(bars[index - 9 : index + 1])
    ma20 = average_close(lookback20)
    low20 = min(item.low for item in lookback20)
    previous_high60 = max(item.high for item in prior60)
    prior_pressure = min((item.high for item in prior60 if item.high > current.close), default=0.0)
    pressure_distance = (
        pct_change(prior_pressure, current.close) if prior_pressure > 0 else None
    )
    recent_gain = pct_change(previous.close, prior20[0].close)
    ma20_deviation = pct_change(current.close, ma20)
    estimated_turnover_amount = current.volume_hands * 100 * current.close
    volume_ratio = current.volume_hands / max(average_volume(prior5), 1.0)

    second_close_pct = pct_change(next_bar.close, current.close)
    second_open_pct = pct_change(next_bar.open, current.close)
    second_high_pct = pct_change(next_bar.high, current.close)
    buy_open_to_close_pct = pct_change(next_bar.close, next_bar.open)
    second_day_one_word = second_open_pct >= LIMIT_UP_THRESHOLD

    first_board_score = score_first_board(
        first_pct=first_pct,
        current=current,
        estimated_turnover_amount=estimated_turnover_amount,
        volume_ratio=volume_ratio,
    )
    open_strength_score = score_next_open(second_open_pct)
    position_score, position_label = score_position(
        current=current,
        low20=low20,
        previous_high60=previous_high60,
        pressure_distance=pressure_distance,
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        estimated_turnover_amount=estimated_turnover_amount,
        min_turnover_amount=min_turnover_amount,
    )
    theme_market_score = 9.0
    liquidity_score = score_liquidity(estimated_turnover_amount, min_turnover_amount)
    score = round(
        first_board_score
        + open_strength_score
        + position_score
        + theme_market_score
        + liquidity_score,
        2,
    )

    blockers: list[str] = []
    if estimated_turnover_amount < min_turnover_amount:
        blockers.append("turnover_too_low")
    if second_open_pct < min_confirm_open_pct:
        blockers.append("second_day_not_red_open")
    if second_open_pct > max_confirm_open_pct:
        blockers.append("second_day_open_too_high")
    if recent_gain >= recent_gain_block_pct:
        blockers.append("recent_gain_too_high")
    if ma20_deviation >= high_deviation_block_pct:
        blockers.append("ma20_deviation_too_high")
    if pressure_distance is not None and 0 <= pressure_distance <= near_pressure_pct:
        blockers.append("near_left_pressure")
    if second_day_one_word:
        blockers.append("second_day_one_word_untradable")
    if not math.isfinite(score):
        blockers.append("invalid_score")

    return Match(
        symbol=stock.code,
        name=stock.name,
        first_board_date=current.trade_date,
        second_day_date=next_bar.trade_date,
        first_board_pct=round(first_pct, 4),
        second_close_pct=round(second_close_pct, 4),
        second_open_pct=round(second_open_pct, 4),
        second_high_pct=round(second_high_pct, 4),
        buy_open_to_close_pct=round(buy_open_to_close_pct, 4),
        score=score,
        position_label=position_label,
        estimated_turnover_amount=round(estimated_turnover_amount, 2),
        recent_gain_pct=round(recent_gain, 4),
        ma20_deviation_pct=round(ma20_deviation, 4),
        pressure_distance_pct=round(pressure_distance, 4) if pressure_distance is not None else None,
        first_board_count=0,
        ready_candidate_count=0,
        second_day_one_word=second_day_one_word,
        blockers=tuple(blockers),
        second_board_closed=second_close_pct >= LIMIT_UP_THRESHOLD,
        second_board_touched=second_high_pct >= SECOND_BOARD_TOUCH_THRESHOLD,
        buy_day_positive=buy_open_to_close_pct > 0,
    )


def score_first_board(
    first_pct: float,
    current: DailyBar,
    estimated_turnover_amount: float,
    volume_ratio: float,
) -> float:
    score = 10.0
    if first_pct >= 0.098:
        score += 4.0
    if current.close >= current.high * 0.995:
        score += 4.0
    if estimated_turnover_amount >= 200_000_000:
        score += 4.0
    if 1.2 <= volume_ratio <= 5:
        score += 3.0
    elif volume_ratio > 0:
        score += 1.0
    return min(score, 25.0)


def score_next_open(second_open_pct: float) -> float:
    score = 8.0
    if 0.02 <= second_open_pct <= 0.07:
        score += 7.0
    elif 0 <= second_open_pct < 0.02:
        score += 3.0
    elif 0.07 < second_open_pct < LIMIT_UP_THRESHOLD:
        score += 4.0
    if second_open_pct > 0:
        score += 2.0
    return min(score, 20.0)


def score_position(
    current: DailyBar,
    low20: float,
    previous_high60: float,
    pressure_distance: float | None,
    ma5: float,
    ma10: float,
    ma20: float,
    estimated_turnover_amount: float,
    min_turnover_amount: float,
) -> tuple[float, str]:
    low_score = 8.0 if current.close <= low20 * 1.25 else 4.0
    breakout_score = 7.0 if current.close >= previous_high60 * 0.98 else 3.0
    pressure_score = 5.0 if pressure_distance is None or pressure_distance > 0.08 else 2.0
    ma_score = 3.0 if ma5 >= ma10 >= ma20 else 1.0
    volume_score = 2.0 if estimated_turnover_amount >= min_turnover_amount * 2 else 1.0
    label = "low_breakout" if low_score >= 8 and breakout_score >= 7 else ""
    if not label and breakout_score >= 7:
        label = "breakout"
    if not label and low_score >= 8:
        label = "low_position"
    if not label:
        label = "extended_or_mid"
    return low_score + breakout_score + pressure_score + ma_score + volume_score, label


def score_liquidity(estimated_turnover_amount: float, min_turnover_amount: float) -> float:
    if estimated_turnover_amount >= min_turnover_amount * 3:
        return 15.0
    if estimated_turnover_amount >= min_turnover_amount:
        return 10.0
    return 0.0


def apply_market_width_gate(
    matches: list[Match],
    min_score: float,
    min_low_breakout_first_board_count: int,
    min_low_breakout_ready_candidates: int,
) -> list[Match]:
    first_board_counts = Counter(item.first_board_date for item in matches)
    base_ready = [
        replace(
            item,
            first_board_count=first_board_counts[item.first_board_date],
        )
        for item in matches
        if item.score >= min_score and not item.blockers
    ]
    ready_counts = Counter(item.second_day_date for item in base_ready)
    filtered: list[Match] = []
    for item in base_ready:
        ready_candidate_count = ready_counts[item.second_day_date]
        enriched = replace(
            item,
            ready_candidate_count=ready_candidate_count,
        )
        if item.position_label == "low_breakout":
            if (
                min_low_breakout_first_board_count > 0
                and item.first_board_count < min_low_breakout_first_board_count
            ):
                continue
            if (
                min_low_breakout_ready_candidates > 0
                and ready_candidate_count < min_low_breakout_ready_candidates
            ):
                continue
        filtered.append(enriched)
    return filtered


def build_product_portfolio(
    filtered_matches: list[Match],
    histories: dict[str, list[DailyBar]],
    position_pct: float,
    stop_loss_pct: float,
    first_take_profit_pct: float,
    strong_take_profit_pct: float,
    trailing_stop_pct: float,
    discipline_exit_min_gain_pct: float,
    max_holding_trade_days: int,
    max_simulation_trade_days: int,
) -> dict[str, Any]:
    simulated = [
        trade
        for trade in (
            simulate_trade(
                match=item,
                histories=histories,
                stop_loss_pct=stop_loss_pct,
                first_take_profit_pct=first_take_profit_pct,
                strong_take_profit_pct=strong_take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
                discipline_exit_min_gain_pct=discipline_exit_min_gain_pct,
                max_holding_trade_days=max_holding_trade_days,
                max_simulation_trade_days=max_simulation_trade_days,
            )
            for item in filtered_matches
        )
        if trade is not None
    ]
    daily_top_matches = select_daily_top_matches(filtered_matches)
    daily_top_trades = [
        trade
        for trade in (
            simulate_trade(
                match=item,
                histories=histories,
                stop_loss_pct=stop_loss_pct,
                first_take_profit_pct=first_take_profit_pct,
                strong_take_profit_pct=strong_take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
                discipline_exit_min_gain_pct=discipline_exit_min_gain_pct,
                max_holding_trade_days=max_holding_trade_days,
                max_simulation_trade_days=max_simulation_trade_days,
            )
            for item in daily_top_matches
        )
        if trade is not None
    ]
    one_position_trades = select_one_position_trades(daily_top_trades)
    return {
        "selection_rule": (
            "候选先过硬拦截；低位平台突破必须满足昨日首板宽度和今日可执行候选宽度；"
            "只在次日红盘开且不高于 4.5% 时确认；"
            "每天按当时可见的 score/open/position/turnover 排名最多买 1 笔；"
            "已有持仓时不再开新仓，严格 T+1。"
        ),
        "ranking_no_future_fields": True,
        "position_pct": position_pct,
        "exit_discipline": {
            "stop_loss_pct": stop_loss_pct,
            "first_take_profit_pct": first_take_profit_pct,
            "strong_take_profit_pct": strong_take_profit_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "discipline_exit_min_gain_pct": discipline_exit_min_gain_pct,
            "max_holding_trade_days": max_holding_trade_days,
        },
        "all_filtered_candidates": summarize_trades(simulated, position_pct),
        "daily_top_one_trade_per_day": summarize_trades(daily_top_trades, position_pct),
        "one_position_no_overlap": summarize_trades(one_position_trades, position_pct),
        "yearly_one_position_no_overlap": summarize_trades_by_year(
            one_position_trades,
            position_pct,
        ),
        "position_labels_one_position_no_overlap": summarize_trades_by_label(
            one_position_trades,
            position_pct,
        ),
        "exit_reasons_one_position_no_overlap": summarize_trade_exit_reasons(
            one_position_trades
        ),
    }


def simulate_trade(
    match: Match,
    histories: dict[str, list[DailyBar]],
    stop_loss_pct: float,
    first_take_profit_pct: float,
    strong_take_profit_pct: float,
    trailing_stop_pct: float,
    discipline_exit_min_gain_pct: float,
    max_holding_trade_days: int,
    max_simulation_trade_days: int,
) -> SimulatedTrade | None:
    bars = histories.get(match.symbol)
    if not bars:
        return None
    by_date = {item.trade_date: index for index, item in enumerate(bars)}
    entry_index = by_date.get(match.second_day_date)
    if entry_index is None:
        return None
    entry_bar = bars[entry_index]
    entry_price = entry_bar.open
    if entry_price <= 0:
        return None

    stop_price = round_price_up(entry_price * (1 - stop_loss_pct))
    first_take_profit_price = entry_price * (1 + first_take_profit_pct)
    strong_take_profit_price = entry_price * (1 + strong_take_profit_pct)
    last_index = min(entry_index + max_simulation_trade_days, len(bars) - 1)
    exit_price = entry_bar.close
    exit_date = entry_bar.trade_date
    exit_reason = "same_day_close_fallback"
    holding_trade_days = 0
    peak_price = entry_price

    for index in range(entry_index, last_index + 1):
        bar = bars[index]
        holding_trade_days = index - entry_index
        peak_price = max(peak_price, bar.high)
        if holding_trade_days == 0:
            exit_price = bar.close
            exit_date = bar.trade_date
            continue
        if bar.low <= stop_price:
            exit_price = stop_price
            exit_date = bar.trade_date
            exit_reason = "stop_loss_t1"
            break
        trailing_stop_price = peak_price * (1 - trailing_stop_pct)
        if peak_price >= strong_take_profit_price and bar.low <= trailing_stop_price:
            exit_price = trailing_stop_price
            exit_date = bar.trade_date
            exit_reason = "trailing_take_profit"
            break
        if bar.high >= first_take_profit_price:
            exit_price = first_take_profit_price
            exit_date = bar.trade_date
            exit_reason = "take_profit_first_target"
            break
        if (
            holding_trade_days >= max_holding_trade_days
            and pct_change(bar.close, entry_price) < discipline_exit_min_gain_pct
        ):
            exit_price = bar.close
            exit_date = bar.trade_date
            exit_reason = "discipline_weak_after_2_days"
            break
        exit_price = bar.close
        exit_date = bar.trade_date
        exit_reason = "max_simulation_close"

    return_pct = pct_change(exit_price, entry_price)
    risk_pct = stop_loss_pct if stop_loss_pct > 0 else 1.0
    return SimulatedTrade(
        symbol=match.symbol,
        name=match.name,
        first_board_date=match.first_board_date,
        entry_date=match.second_day_date,
        exit_date=exit_date,
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        return_pct=round(return_pct, 4),
        r_multiple=round(return_pct / risk_pct, 4),
        holding_trade_days=holding_trade_days,
        exit_reason=exit_reason,
        score=match.score,
        position_label=match.position_label,
        second_open_pct=match.second_open_pct,
        estimated_turnover_amount=match.estimated_turnover_amount,
    )


def select_daily_top_matches(matches: list[Match]) -> list[Match]:
    by_date: dict[str, list[Match]] = {}
    for item in matches:
        by_date.setdefault(item.second_day_date, []).append(item)
    return [
        sorted(items, key=selection_rank_key, reverse=True)[0]
        for _, items in sorted(by_date.items())
    ]


def selection_rank_key(match: Match) -> tuple[float, int, int, float, float]:
    open_confirm_bonus = 1 if 0 <= match.second_open_pct <= 0.045 else 0
    position_bonus = 1 if match.position_label in {"low_breakout", "low_position", "breakout"} else 0
    return (
        match.score,
        open_confirm_bonus,
        position_bonus,
        match.second_open_pct,
        match.estimated_turnover_amount,
    )


def select_one_position_trades(trades: list[SimulatedTrade]) -> list[SimulatedTrade]:
    selected: list[SimulatedTrade] = []
    next_available_date = ""
    for trade in sorted(trades, key=lambda item: (item.entry_date, item.symbol)):
        if next_available_date and trade.entry_date <= next_available_date:
            continue
        selected.append(trade)
        next_available_date = trade.exit_date
    return selected


def round_price_up(value: float) -> float:
    return math.ceil(value * 100 - 1e-9) / 100


def build_result(
    start_date: str,
    end_date: str,
    universe_count: int,
    loaded_symbol_count: int,
    failed_symbol_count: int,
    failed_symbols: list[str],
    universe_warnings: list[str],
    basic_matches: list[Match],
    filtered_matches: list[Match],
    histories: dict[str, list[DailyBar]],
    min_score: float,
    min_confirm_open_pct: float,
    max_confirm_open_pct: float,
    position_pct: float,
    stop_loss_pct: float,
    first_take_profit_pct: float,
    strong_take_profit_pct: float,
    trailing_stop_pct: float,
    discipline_exit_min_gain_pct: float,
    max_holding_trade_days: int,
    max_simulation_trade_days: int,
    min_low_breakout_first_board_count: int,
    min_low_breakout_ready_candidates: int,
    sample_preview: int,
) -> dict[str, Any]:
    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": {
            "name": "mainboard_10cm_one_to_two_daily_research",
            "date_range": {"start": start_date, "end": end_date},
            "success_definition": "next trading day close-to-close gain >= 9.5%",
            "touch_definition": "next trading day high-to-close gain >= 9.5%",
            "limitations": [
                "daily bars only; auction amount, sealed orders, intraday fill, and theme heat are approximated",
                "filtered sample excludes untradable next-day one-word limit-up openings",
                "turnover amount is estimated from Tencent volume_hands * 100 * close",
            ],
            "min_score": min_score,
            "confirm_open_window": {
                "min_pct": min_confirm_open_pct,
                "max_pct": max_confirm_open_pct,
            },
            "low_breakout_width_gate": {
                "min_first_board_count": min_low_breakout_first_board_count,
                "min_ready_candidates": min_low_breakout_ready_candidates,
            },
            "product_reliability_note": (
                "The reliability decision should use product_portfolio.one_position_no_overlap, "
                "not all filtered candidates."
            ),
        },
        "data_quality": {
            "universe_count": universe_count,
            "loaded_symbol_count": loaded_symbol_count,
            "failed_symbol_count": failed_symbol_count,
            "failed_symbols_preview": failed_symbols,
            "universe_warnings": universe_warnings,
        },
        "basic_first_board": summarize_matches(basic_matches),
        "filtered_strategy_candidates": summarize_matches(filtered_matches),
        "yearly": {
            "basic_first_board": summarize_by_year(basic_matches),
            "filtered_strategy_candidates": summarize_by_year(filtered_matches),
        },
        "position_labels": summarize_by_label(filtered_matches),
        "product_portfolio": build_product_portfolio(
            filtered_matches=filtered_matches,
            histories=histories,
            position_pct=position_pct,
            stop_loss_pct=stop_loss_pct,
            first_take_profit_pct=first_take_profit_pct,
            strong_take_profit_pct=strong_take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            discipline_exit_min_gain_pct=discipline_exit_min_gain_pct,
            max_holding_trade_days=max_holding_trade_days,
            max_simulation_trade_days=max_simulation_trade_days,
        ),
        "blockers": summarize_blockers(basic_matches),
        "recent_samples": [asdict(item) for item in filtered_matches[-sample_preview:]],
    }


def summarize_matches(matches: list[Match]) -> dict[str, Any]:
    if not matches:
        return {
            "sample_count": 0,
            "second_board_closed_count": 0,
            "second_board_close_win_rate": None,
            "second_board_touched_count": 0,
            "second_board_touch_rate": None,
            "buy_day_positive_count": 0,
            "buy_day_positive_rate": None,
            "average_second_close_pct": None,
            "median_second_close_pct": None,
            "average_buy_open_to_close_pct": None,
        }
    return {
        "sample_count": len(matches),
        "second_board_closed_count": sum(1 for item in matches if item.second_board_closed),
        "second_board_close_win_rate": ratio(
            sum(1 for item in matches if item.second_board_closed), len(matches)
        ),
        "second_board_touched_count": sum(1 for item in matches if item.second_board_touched),
        "second_board_touch_rate": ratio(
            sum(1 for item in matches if item.second_board_touched), len(matches)
        ),
        "buy_day_positive_count": sum(1 for item in matches if item.buy_day_positive),
        "buy_day_positive_rate": ratio(
            sum(1 for item in matches if item.buy_day_positive), len(matches)
        ),
        "average_second_close_pct": round(mean(item.second_close_pct for item in matches), 4),
        "median_second_close_pct": round(median(item.second_close_pct for item in matches), 4),
        "average_buy_open_to_close_pct": round(
            mean(item.buy_open_to_close_pct for item in matches),
            4,
        ),
    }


def summarize_by_year(matches: list[Match]) -> dict[str, dict[str, Any]]:
    years = sorted({item.first_board_date[:4] for item in matches})
    return {
        year: summarize_matches([item for item in matches if item.first_board_date.startswith(year)])
        for year in years
    }


def summarize_by_label(matches: list[Match]) -> dict[str, dict[str, Any]]:
    labels = sorted({item.position_label for item in matches})
    return {
        label: summarize_matches([item for item in matches if item.position_label == label])
        for label in labels
    }


def summarize_blockers(matches: list[Match]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in matches:
        for blocker in item.blockers:
            counts[blocker] = counts.get(blocker, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summarize_trades(trades: list[SimulatedTrade], position_pct: float) -> dict[str, Any]:
    if not trades:
        return {
            "sample_count": 0,
            "win_count": 0,
            "win_rate": None,
            "average_return_pct": None,
            "median_return_pct": None,
            "average_r": None,
            "average_win_pct": None,
            "average_loss_pct": None,
            "payoff_ratio": None,
            "position_weighted_return_pct": None,
            "max_drawdown_pct": None,
        }
    wins = [item for item in trades if item.return_pct > 0]
    losses = [item for item in trades if item.return_pct <= 0]
    avg_win = mean(item.return_pct for item in wins) if wins else 0.0
    avg_loss = mean(item.return_pct for item in losses) if losses else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss < 0 else None
    equity_curve = build_equity_curve(trades, position_pct)
    return {
        "sample_count": len(trades),
        "win_count": len(wins),
        "win_rate": ratio(len(wins), len(trades)),
        "average_return_pct": round(mean(item.return_pct for item in trades), 4),
        "median_return_pct": round(median(item.return_pct for item in trades), 4),
        "average_r": round(mean(item.r_multiple for item in trades), 4),
        "average_win_pct": round(avg_win, 4) if wins else None,
        "average_loss_pct": round(avg_loss, 4) if losses else None,
        "payoff_ratio": round(payoff, 4) if payoff is not None else None,
        "position_weighted_return_pct": equity_curve["total_return_pct"],
        "max_drawdown_pct": equity_curve["max_drawdown_pct"],
    }


def build_equity_curve(trades: list[SimulatedTrade], position_pct: float) -> dict[str, float]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for trade in sorted(trades, key=lambda item: (item.exit_date, item.entry_date, item.symbol)):
        equity *= 1 + trade.return_pct * position_pct
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak if peak else 0.0
        max_drawdown = min(max_drawdown, drawdown)
    return {
        "total_return_pct": round(equity - 1, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
    }


def summarize_trades_by_year(
    trades: list[SimulatedTrade],
    position_pct: float,
) -> dict[str, dict[str, Any]]:
    years = sorted({item.entry_date[:4] for item in trades})
    return {
        year: summarize_trades(
            [item for item in trades if item.entry_date.startswith(year)],
            position_pct,
        )
        for year in years
    }


def summarize_trades_by_label(
    trades: list[SimulatedTrade],
    position_pct: float,
) -> dict[str, dict[str, Any]]:
    labels = sorted({item.position_label for item in trades})
    return {
        label: summarize_trades(
            [item for item in trades if item.position_label == label],
            position_pct,
        )
        for label in labels
    }


def summarize_trade_exit_reasons(trades: list[SimulatedTrade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in trades:
        counts[item.exit_reason] = counts.get(item.exit_reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def print_summary(result: dict[str, Any]) -> None:
    basic = result["basic_first_board"]
    filtered = result["filtered_strategy_candidates"]
    product = result["product_portfolio"]["one_position_no_overlap"]
    print("summary:", flush=True)
    print(
        "  basic samples={sample_count} close_win={second_board_close_win_rate} "
        "touch={second_board_touch_rate}".format(**basic),
        flush=True,
    )
    print(
        "  filtered samples={sample_count} close_win={second_board_close_win_rate} "
        "touch={second_board_touch_rate}".format(**filtered),
        flush=True,
    )
    print("  yearly filtered:", flush=True)
    for year, stats in result["yearly"]["filtered_strategy_candidates"].items():
        print(
            "    {year}: samples={sample_count} close_win={second_board_close_win_rate}".format(
                year=year,
                **stats,
            ),
            flush=True,
        )
    print(
        "  product one-position trades={sample_count} win={win_rate} avg_return={average_return_pct} "
        "portfolio_return={position_weighted_return_pct} max_dd={max_drawdown_pct}".format(
            **product
        ),
        flush=True,
    )
    print("  yearly product one-position:", flush=True)
    for year, stats in result["product_portfolio"]["yearly_one_position_no_overlap"].items():
        print(
            "    {year}: trades={sample_count} win={win_rate} avg_return={average_return_pct} "
            "portfolio_return={position_weighted_return_pct}".format(
                year=year,
                **stats,
            ),
            flush=True,
        )


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def average_close(bars: list[DailyBar]) -> float:
    return mean(item.close for item in bars) if bars else 0.0


def average_volume(bars: list[DailyBar]) -> float:
    return mean(item.volume_hands for item in bars) if bars else 0.0


def pct_change(value: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return (value - base) / base


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def normalize_name(value: Any) -> str:
    return str(value or "").strip()


def normalize_date_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def is_mainboard_code(code: str) -> bool:
    return code.startswith(MAINBOARD_PREFIXES)


def is_blocked_name(name: str) -> bool:
    upper = name.upper()
    return "ST" in upper or "\u9000" in name


def tencent_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith("6") else f"sz{code}"


def safe_float(value: Any) -> float:
    try:
        if value in ("", None):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
