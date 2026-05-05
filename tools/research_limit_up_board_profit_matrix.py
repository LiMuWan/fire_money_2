"""Profit matrix for the FireMoney limit-up board validation line.

This research utility stays outside the runtime product path. It compares
same-day sealed-board entry filters and exit disciplines with a no-future-
leakage selection rule: entry filters and daily ranking use only board-day
visible fields, while later bars are used only for exits and PnL.

Daily bars still cannot prove queue fills, seal amount, cancellation pressure,
or intraday order sequence. Treat the output as validation evidence for the
next product line, not as a live-trading claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools import research_strategy_matrix_backtest as sm  # noqa: E402
from tools.research_one_to_two_profit_matrix import (  # noqa: E402
    load_cached_research_data,
)


DEFAULT_OUTPUT = Path("exports") / "limit_up_board_profit_matrix_2024_to_now.json"
DEFAULT_CACHE_DIR = Path(".firemoney") / "research_cache" / "one_to_two_daily"
TRAIN_END_DATE = "2025-12-31"


@dataclass(frozen=True)
class BoardCandidate:
    symbol: str
    name: str
    board_date: str
    index: int
    entry_price: float
    previous_close: float
    close_pct: float
    high_pct: float
    estimated_turnover_amount: float
    volume_ratio_20: float
    recent_gain_pct: float
    ma20_deviation_pct: float
    position_percentile_60: float
    first_board: bool
    ma_bullish: bool
    rank_score: float
    market_seal_count: int = 0
    market_touch_count: int = 0
    market_advance_ratio: float = 0.0


@dataclass(frozen=True)
class EntryCase:
    case_id: str
    require_first_board: bool
    min_turnover_amount: float
    max_recent_gain_pct: float | None
    max_ma20_deviation_pct: float | None
    min_volume_ratio_20: float
    require_ma_bullish: bool
    min_position_percentile_60: float
    min_market_seal_count: int = 0
    max_market_seal_count: int | None = None


@dataclass(frozen=True)
class ExitCase:
    case_id: str
    stop_loss_pct: float
    take_profit_pct: float
    max_hold_days: int
    weak_next_open_exit_pct: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a cached profit matrix for the limit-up board validation line."
    )
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2026-05-03")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--position-pct", type=float, default=0.08)
    parser.add_argument("--roundtrip-cost-pct", type=float, default=0.0015)
    parser.add_argument(
        "--wide",
        action="store_true",
        help="Run a broader exploratory matrix. Default stays focused and faster.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = sm.parse_iso_date(args.start_date)
    end = sm.parse_iso_date(args.end_date)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    universe, histories = load_cached_research_data(Path(args.cache_dir), start, end)
    if args.limit:
        universe = universe[: args.limit]
        histories = {stock.code: histories[stock.code] for stock in universe}
    candidates = build_board_candidates(universe, histories, start, end)
    entry_cases = build_entry_cases(wide=args.wide)
    exit_cases = build_exit_cases(wide=args.wide)
    rank_cases = build_rank_cases(wide=args.wide)
    baseline = evaluate_case(
        candidates=candidates,
        histories=histories,
        entry_case=baseline_entry_case(),
        exit_case=baseline_exit_case(),
        rank_case="score",
        position_pct=args.position_pct,
        roundtrip_cost_pct=args.roundtrip_cost_pct,
    )
    print(
        "matrix "
        f"candidates={len(candidates)} "
        f"entry_cases={len(entry_cases)} "
        f"exit_cases={len(exit_cases)} "
        f"rank_cases={len(rank_cases)}",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    for entry_case in entry_cases:
        filtered = [item for item in candidates if entry_case_allows(entry_case, item)]
        if len(filtered) < 120:
            continue
        for rank_case in rank_cases:
            daily_candidates = select_daily_top_candidates(filtered, rank_case)
            if len(daily_candidates) < 80:
                continue
            for exit_case in exit_cases:
                result = evaluate_preselected(
                    daily_candidates=daily_candidates,
                    histories=histories,
                    entry_case=entry_case,
                    exit_case=exit_case,
                    rank_case=rank_case,
                    position_pct=args.position_pct,
                    roundtrip_cost_pct=args.roundtrip_cost_pct,
                )
                if not qualifies_result(result):
                    continue
                result["score"] = score_result(result)
                results.append(result)

    results.sort(
        key=lambda item: (
            item["score"],
            item["validation_summary"]["position_weighted_return_pct"] or -9,
            item["summary"]["position_weighted_return_pct"] or -9,
            item["summary"]["win_rate"] or -1,
        ),
        reverse=True,
    )
    report = {
        "note": (
            "Entry filters and ranking use only board-day visible fields. "
            "Future bars are used only for T+1 exits and PnL."
        ),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "train_validate_split": {
            "train_end": TRAIN_END_DATE,
            "validation_start": "2026-01-01",
        },
        "universe_count": len(universe),
        "raw_candidate_count": len(candidates),
        "baseline": baseline,
        "top": results[: max(1, args.top)],
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_summary(report, output_path)
    return 0


def build_board_candidates(
    universe: list[sm.StockMeta],
    histories: dict[str, list[sm.DailyBar]],
    start: date,
    end: date,
) -> list[BoardCandidate]:
    result: list[BoardCandidate] = []
    market_stats = build_market_stats(histories, start, end)
    for stock in universe:
        bars = histories.get(stock.code)
        if not bars or len(bars) < 80:
            continue
        for index in range(60, len(bars) - 1):
            current = bars[index]
            trade_date = sm.parse_iso_date(current.trade_date)
            if trade_date < start or trade_date > end:
                continue
            if stock.listing_date:
                listing = sm.parse_iso_date(stock.listing_date)
                if (trade_date - listing).days <= 5:
                    continue
            if not sm.is_touched_limit_up(bars, index):
                continue
            if not sm.is_closed_limit_up(bars, index):
                continue
            if sm.is_one_word_limit_up(bars, index):
                continue
            candidate = build_candidate(stock, bars, index, market_stats)
            if candidate:
                result.append(candidate)
    return result


def build_candidate(
    stock: sm.StockMeta,
    bars: list[sm.DailyBar],
    index: int,
    market_stats: dict[str, dict[str, float]],
) -> BoardCandidate | None:
    current = bars[index]
    previous = bars[index - 1]
    prior20 = bars[index - 20 : index]
    lookback20 = bars[index - 19 : index + 1]
    lookback60 = bars[index - 59 : index + 1]
    if not prior20 or not lookback20 or not lookback60:
        return None
    low60 = min(item.low for item in lookback60)
    high60 = max(item.high for item in lookback60)
    if low60 <= 0 or high60 <= low60:
        return None
    ma20 = sm.average_close(lookback20)
    day_stats = market_stats.get(current.trade_date, {})
    candidate = BoardCandidate(
        symbol=stock.code,
        name=stock.name,
        board_date=current.trade_date,
        index=index,
        entry_price=round(current.high, 2),
        previous_close=round(previous.close, 2),
        close_pct=round(sm.pct_change(current.close, previous.close), 4),
        high_pct=round(sm.pct_change(current.high, previous.close), 4),
        estimated_turnover_amount=round(sm.estimated_turnover_amount(current), 2),
        volume_ratio_20=round(sm.volume_ratio(bars, index, 20), 4),
        recent_gain_pct=round(sm.pct_change(previous.close, prior20[0].close), 4),
        ma20_deviation_pct=round(sm.pct_change(current.close, ma20), 4),
        position_percentile_60=round((current.close - low60) / (high60 - low60), 4),
        first_board=sm.is_first_board(bars, index),
        ma_bullish=sm.ma_bullish(bars, index),
        rank_score=0.0,
        market_seal_count=int(day_stats.get("seal_count", 0)),
        market_touch_count=int(day_stats.get("touch_count", 0)),
        market_advance_ratio=round(day_stats.get("advance_ratio", 0.0), 4),
    )
    return replace_rank_score(candidate)


def replace_rank_score(candidate: BoardCandidate) -> BoardCandidate:
    score = candidate.close_pct * 100
    if candidate.first_board:
        score += 2.5
    if candidate.volume_ratio_20 >= 1.5:
        score += 1.5
    if candidate.estimated_turnover_amount >= 300_000_000:
        score += 1.5
    if candidate.ma_bullish:
        score += 1.0
    if candidate.recent_gain_pct <= 0.35:
        score += 1.0
    if candidate.ma20_deviation_pct <= 0.35:
        score += 1.0
    return BoardCandidate(
        **{
            **asdict(candidate),
            "rank_score": round(score, 4),
        }
    )


def build_market_stats(
    histories: dict[str, list[sm.DailyBar]],
    start: date,
    end: date,
) -> dict[str, dict[str, float]]:
    raw: dict[str, dict[str, float]] = {}
    for bars in histories.values():
        for index in range(1, len(bars)):
            current = bars[index]
            trade_date = sm.parse_iso_date(current.trade_date)
            if trade_date < start or trade_date > end:
                continue
            stats = raw.setdefault(
                current.trade_date,
                {
                    "available_count": 0.0,
                    "up_count": 0.0,
                    "seal_count": 0.0,
                    "touch_count": 0.0,
                },
            )
            stats["available_count"] += 1
            if sm.pct_change(current.close, bars[index - 1].close) > 0:
                stats["up_count"] += 1
            if sm.is_closed_limit_up(bars, index):
                stats["seal_count"] += 1
            if sm.is_touched_limit_up(bars, index):
                stats["touch_count"] += 1

    for stats in raw.values():
        available_count = stats["available_count"]
        stats["advance_ratio"] = (
            stats["up_count"] / available_count if available_count else 0.0
        )
    return raw


def baseline_entry_case() -> EntryCase:
    return EntryCase(
        case_id="baseline_all_sealed_turnover80m",
        require_first_board=False,
        min_turnover_amount=80_000_000.0,
        max_recent_gain_pct=None,
        max_ma20_deviation_pct=None,
        min_volume_ratio_20=0.0,
        require_ma_bullish=False,
        min_position_percentile_60=0.0,
        min_market_seal_count=0,
        max_market_seal_count=None,
    )


def baseline_exit_case() -> ExitCase:
    return ExitCase(
        case_id="next_close_no_stop_no_target",
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        max_hold_days=1,
        weak_next_open_exit_pct=None,
    )


def build_entry_cases(wide: bool) -> list[EntryCase]:
    first_board_options = (True, False)
    turnover_options = (80_000_000.0, 200_000_000.0, 500_000_000.0)
    recent_gain_options: tuple[float | None, ...] = (0.35, 0.55, None)
    ma20_deviation_options: tuple[float | None, ...] = (0.35, None)
    volume_ratio_options = (1.0, 1.3)
    ma_bullish_options = (False, True)
    position_options = (0.0, 0.45)
    market_seal_options: tuple[tuple[int, int | None], ...] = ((0, None), (20, 150))
    if wide:
        turnover_options = (80_000_000.0, 200_000_000.0, 500_000_000.0, 1_000_000_000.0)
        ma20_deviation_options = (0.25, 0.35, 0.55, None)
        position_options = (0.0, 0.35, 0.55, 0.75)
        market_seal_options = ((0, None), (10, None), (20, 150), (30, 120), (40, None))

    cases: list[EntryCase] = [baseline_entry_case()]
    for require_first_board in first_board_options:
        for min_turnover in turnover_options:
            for max_recent_gain in recent_gain_options:
                for max_ma20_dev in ma20_deviation_options:
                    for min_volume_ratio in volume_ratio_options:
                        for require_ma_bullish in ma_bullish_options:
                            for min_position in position_options:
                                for min_seal, max_seal in market_seal_options:
                                    heat_label = (
                                        "heatany"
                                        if min_seal == 0 and max_seal is None
                                        else f"heat{min_seal}-{max_seal or 'any'}"
                                    )
                                    case_id = (
                                        f"{'first' if require_first_board else 'sealed'}"
                                        f"_to{int(min_turnover / 10_000)}w"
                                        f"_gain{label_optional_pct(max_recent_gain)}"
                                        f"_dev{label_optional_pct(max_ma20_dev)}"
                                        f"_vr{min_volume_ratio:g}"
                                        f"_{'ma' if require_ma_bullish else 'nomafilter'}"
                                        f"_pos{min_position:g}"
                                        f"_{heat_label}"
                                    )
                                    cases.append(
                                        EntryCase(
                                            case_id=case_id,
                                            require_first_board=require_first_board,
                                            min_turnover_amount=min_turnover,
                                            max_recent_gain_pct=max_recent_gain,
                                            max_ma20_deviation_pct=max_ma20_dev,
                                            min_volume_ratio_20=min_volume_ratio,
                                            require_ma_bullish=require_ma_bullish,
                                            min_position_percentile_60=min_position,
                                            min_market_seal_count=min_seal,
                                            max_market_seal_count=max_seal,
                                        )
                                    )
    return deduplicate_entry_cases(cases)


def build_exit_cases(wide: bool) -> list[ExitCase]:
    cases = [baseline_exit_case()]
    stop_options = (0.04, 0.05, 0.06)
    take_options = (0.05, 0.08, 0.12)
    hold_options = (1, 2, 3)
    weak_options: tuple[float | None, ...] = (None, 0.0)
    if wide:
        take_options = (0.04, 0.05, 0.08, 0.12, 0.16)
        hold_options = (1, 2, 3, 5)
        weak_options = (None, -0.02, 0.0, 0.02)

    for stop_loss in stop_options:
        for take_profit in take_options:
            for hold_days in hold_options:
                for weak_open in weak_options:
                    weak_label = "none" if weak_open is None else f"{int(weak_open * 1000)}bp"
                    cases.append(
                        ExitCase(
                            case_id=(
                                f"stop{int(stop_loss * 100)}"
                                f"_target{int(take_profit * 100)}"
                                f"_hold{hold_days}"
                                f"_weak{weak_label}"
                            ),
                            stop_loss_pct=stop_loss,
                            take_profit_pct=take_profit,
                            max_hold_days=hold_days,
                            weak_next_open_exit_pct=weak_open,
                        )
                    )
    return deduplicate_exit_cases(cases)


def build_rank_cases(wide: bool) -> tuple[str, ...]:
    if wide:
        return ("score", "turnover", "first_turnover", "low_deviation", "volume_ratio")
    return ("score", "turnover", "first_turnover")


def entry_case_allows(case: EntryCase, candidate: BoardCandidate) -> bool:
    if case.require_first_board and not candidate.first_board:
        return False
    if candidate.estimated_turnover_amount < case.min_turnover_amount:
        return False
    if (
        case.max_recent_gain_pct is not None
        and candidate.recent_gain_pct > case.max_recent_gain_pct
    ):
        return False
    if (
        case.max_ma20_deviation_pct is not None
        and candidate.ma20_deviation_pct > case.max_ma20_deviation_pct
    ):
        return False
    if candidate.volume_ratio_20 < case.min_volume_ratio_20:
        return False
    if case.require_ma_bullish and not candidate.ma_bullish:
        return False
    if candidate.position_percentile_60 < case.min_position_percentile_60:
        return False
    if candidate.market_seal_count < case.min_market_seal_count:
        return False
    if (
        case.max_market_seal_count is not None
        and candidate.market_seal_count > case.max_market_seal_count
    ):
        return False
    return True


def evaluate_case(
    candidates: list[BoardCandidate],
    histories: dict[str, list[sm.DailyBar]],
    entry_case: EntryCase,
    exit_case: ExitCase,
    rank_case: str,
    position_pct: float,
    roundtrip_cost_pct: float,
) -> dict[str, Any]:
    filtered = [item for item in candidates if entry_case_allows(entry_case, item)]
    daily_candidates = select_daily_top_candidates(filtered, rank_case)
    return evaluate_preselected(
        daily_candidates=daily_candidates,
        histories=histories,
        entry_case=entry_case,
        exit_case=exit_case,
        rank_case=rank_case,
        position_pct=position_pct,
        roundtrip_cost_pct=roundtrip_cost_pct,
    )


def evaluate_preselected(
    daily_candidates: list[BoardCandidate],
    histories: dict[str, list[sm.DailyBar]],
    entry_case: EntryCase,
    exit_case: ExitCase,
    rank_case: str,
    position_pct: float,
    roundtrip_cost_pct: float,
) -> dict[str, Any]:
    trades = [
        trade
        for trade in (
            simulate_board_trade(
                candidate=item,
                bars=histories[item.symbol],
                exit_case=exit_case,
                roundtrip_cost_pct=roundtrip_cost_pct,
            )
            for item in daily_candidates
        )
        if trade is not None
    ]
    one_position_trades = sm.select_one_position_trades(trades)
    summary = sm.summarize_position_trades(one_position_trades, position_pct)
    yearly = sm.summarize_position_by_year(one_position_trades, position_pct)
    train_trades = [
        item for item in one_position_trades if item.entry_date <= TRAIN_END_DATE
    ]
    validation_trades = [
        item for item in one_position_trades if item.entry_date > TRAIN_END_DATE
    ]
    return {
        "entry_case": asdict(entry_case),
        "exit_case": asdict(exit_case),
        "rank_case": rank_case,
        "summary": summary,
        "train_summary": sm.summarize_position_trades(train_trades, position_pct),
        "validation_summary": sm.summarize_position_trades(
            validation_trades,
            position_pct,
        ),
        "yearly": yearly,
        "exit_reasons": summarize_exit_reasons(one_position_trades),
        "recent_samples": [asdict(item) for item in one_position_trades[-5:]],
    }


def simulate_board_trade(
    candidate: BoardCandidate,
    bars: list[sm.DailyBar],
    exit_case: ExitCase,
    roundtrip_cost_pct: float,
) -> sm.Trade | None:
    entry_index = candidate.index
    if entry_index + 1 >= len(bars) or candidate.entry_price <= 0:
        return None
    entry_price = candidate.entry_price
    stop_price = entry_price * (1 - exit_case.stop_loss_pct)
    target_price = entry_price * (1 + exit_case.take_profit_pct)
    last_index = min(len(bars) - 1, entry_index + max(1, exit_case.max_hold_days))
    for exit_index in range(entry_index + 1, last_index + 1):
        bar = bars[exit_index]
        if (
            exit_index == entry_index + 1
            and exit_case.weak_next_open_exit_pct is not None
            and sm.pct_change(bar.open, entry_price)
            <= exit_case.weak_next_open_exit_pct
        ):
            return make_trade(
                candidate,
                bars,
                exit_index,
                bar.open,
                roundtrip_cost_pct,
                "weak_next_open_exit",
            )
        if exit_case.stop_loss_pct > 0:
            if bar.open <= stop_price:
                return make_trade(
                    candidate,
                    bars,
                    exit_index,
                    bar.open,
                    roundtrip_cost_pct,
                    "stop_loss_open",
                )
            if bar.low <= stop_price:
                return make_trade(
                    candidate,
                    bars,
                    exit_index,
                    stop_price,
                    roundtrip_cost_pct,
                    "stop_loss",
                )
        if exit_case.take_profit_pct > 0:
            if bar.open >= target_price:
                return make_trade(
                    candidate,
                    bars,
                    exit_index,
                    bar.open,
                    roundtrip_cost_pct,
                    "take_profit_open",
                )
            if bar.high >= target_price:
                return make_trade(
                    candidate,
                    bars,
                    exit_index,
                    target_price,
                    roundtrip_cost_pct,
                    "take_profit",
                )
    return make_trade(
        candidate,
        bars,
        last_index,
        bars[last_index].close,
        roundtrip_cost_pct,
        "max_hold_close",
    )


def make_trade(
    candidate: BoardCandidate,
    bars: list[sm.DailyBar],
    exit_index: int,
    exit_price: float,
    roundtrip_cost_pct: float,
    reason: str,
) -> sm.Trade:
    gross = sm.pct_change(exit_price, candidate.entry_price)
    return sm.Trade(
        strategy_id="limit_up_board_validation",
        strategy_name="limit_up_board_validation",
        symbol=candidate.symbol,
        name=candidate.name,
        signal_date=candidate.board_date,
        entry_date=candidate.board_date,
        exit_date=bars[exit_index].trade_date,
        entry_price=round(candidate.entry_price, 2),
        exit_price=round(exit_price, 2),
        gross_return_pct=round(gross, 4),
        net_return_pct=round(gross - roundtrip_cost_pct, 4),
        hold_days=max(1, exit_index - candidate.index),
        reason=reason,
        rank_score=candidate.rank_score,
        rank_turnover_amount=candidate.estimated_turnover_amount,
    )


def select_daily_top_candidates(
    candidates: list[BoardCandidate],
    rank_case: str,
) -> list[BoardCandidate]:
    by_day: dict[str, list[BoardCandidate]] = {}
    for candidate in candidates:
        by_day.setdefault(candidate.board_date, []).append(candidate)
    return [
        sorted(items, key=lambda item: candidate_rank_key(item, rank_case), reverse=True)[0]
        for _, items in sorted(by_day.items())
    ]


def candidate_rank_key(
    candidate: BoardCandidate,
    rank_case: str,
) -> tuple[float, float, float, float]:
    if rank_case == "turnover":
        return (
            candidate.estimated_turnover_amount,
            candidate.rank_score,
            candidate.volume_ratio_20,
            -candidate.entry_price,
        )
    if rank_case == "first_turnover":
        return (
            1.0 if candidate.first_board else 0.0,
            candidate.estimated_turnover_amount,
            candidate.rank_score,
            -candidate.entry_price,
        )
    if rank_case == "low_deviation":
        return (
            -candidate.ma20_deviation_pct,
            -candidate.recent_gain_pct,
            candidate.estimated_turnover_amount,
            candidate.rank_score,
        )
    if rank_case == "volume_ratio":
        return (
            candidate.volume_ratio_20,
            candidate.estimated_turnover_amount,
            candidate.rank_score,
            -candidate.entry_price,
        )
    return (
        candidate.rank_score,
        candidate.estimated_turnover_amount,
        candidate.volume_ratio_20,
        -candidate.entry_price,
    )


def score_result(result: dict[str, Any]) -> float:
    train = result["train_summary"]
    validation = result["validation_summary"]
    summary = result["summary"]
    train_return = train["position_weighted_return_pct"] or -1.0
    validation_return = validation["position_weighted_return_pct"] or -1.0
    summary_return = summary["position_weighted_return_pct"] or -1.0
    win_rate = summary["win_rate"] or 0.0
    max_drawdown = abs(summary["max_drawdown_pct"] or 0.0)
    stability_return = min(train_return, validation_return)
    return round(
        stability_return * 130
        + summary_return * 45
        + win_rate * 10
        - max_drawdown * 12,
        4,
    )


def qualifies_result(result: dict[str, Any]) -> bool:
    summary = result["summary"]
    train = result["train_summary"]
    validation = result["validation_summary"]
    yearly = result["yearly"]
    if summary["sample_count"] < 80:
        return False
    if train["sample_count"] < 60 or validation["sample_count"] < 15:
        return False
    if (summary["win_rate"] or 0.0) < 0.45:
        return False
    if (train["position_weighted_return_pct"] or 0.0) <= 0:
        return False
    if (validation["position_weighted_return_pct"] or 0.0) <= 0:
        return False
    if (summary["max_drawdown_pct"] or 0.0) < -0.08:
        return False
    positive_years = sum(
        1
        for item in yearly.values()
        if item["sample_count"] > 0 and (item["position_weighted_return_pct"] or 0.0) > 0
    )
    return positive_years >= 3


def summarize_exit_reasons(trades: list[sm.Trade]) -> dict[str, int]:
    result: dict[str, int] = {}
    for trade in trades:
        result[trade.reason] = result.get(trade.reason, 0) + 1
    return dict(sorted(result.items()))


def deduplicate_entry_cases(cases: list[EntryCase]) -> list[EntryCase]:
    result: dict[str, EntryCase] = {}
    for case in cases:
        result[case.case_id] = case
    return list(result.values())


def deduplicate_exit_cases(cases: list[ExitCase]) -> list[ExitCase]:
    result: dict[str, ExitCase] = {}
    for case in cases:
        result[case.case_id] = case
    return list(result.values())


def label_optional_pct(value: float | None) -> str:
    if value is None:
        return "any"
    return str(int(value * 100))


def print_summary(report: dict[str, Any], output_path: Path) -> None:
    baseline = report["baseline"]
    print(
        "baseline "
        f"trades={baseline['summary']['sample_count']} "
        f"win={baseline['summary']['win_rate']} "
        f"return={baseline['summary']['position_weighted_return_pct']} "
        f"dd={baseline['summary']['max_drawdown_pct']}",
        flush=True,
    )
    print("top:", flush=True)
    for item in report["top"][:10]:
        print(
            "  {entry} {exit} rank={rank} trades={trades} win={win} "
            "return={ret} dd={dd} train={train_ret} validation={val_ret}".format(
                entry=item["entry_case"]["case_id"],
                exit=item["exit_case"]["case_id"],
                rank=item["rank_case"],
                trades=item["summary"]["sample_count"],
                win=item["summary"]["win_rate"],
                ret=item["summary"]["position_weighted_return_pct"],
                dd=item["summary"]["max_drawdown_pct"],
                train_ret=item["train_summary"]["position_weighted_return_pct"],
                val_ret=item["validation_summary"]["position_weighted_return_pct"],
            ),
            flush=True,
        )
    print(f"output={output_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
