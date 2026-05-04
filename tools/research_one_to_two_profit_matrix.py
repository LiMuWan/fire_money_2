"""Fast cached profit matrix for the FireMoney one-to-two strategy.

This research tool intentionally stays outside the runtime product path. It
uses cached daily bars only, builds no-future-leakage entry candidates once,
then evaluates visible-field filters, ranking rules, and exit disciplines.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools import research_one_to_two_backtest as bt  # noqa: E402


DEFAULT_OUTPUT = Path("exports") / "one_to_two_profit_matrix_2024_to_now.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a fast cached profit matrix for one-to-two research."
    )
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2026-05-03")
    parser.add_argument(
        "--cache-dir",
        default=str(bt.DEFAULT_CACHE_DIR),
        help="Cached Tencent daily-bar directory. Network is not used.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument(
        "--wide",
        action="store_true",
        help="Run a broader exploratory matrix. The default is a fast focused matrix.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = bt.parse_iso_date(args.start_date)
    end = bt.parse_iso_date(args.end_date)
    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    universe, histories = load_cached_research_data(cache_dir, start, end)
    matches = build_raw_matches(universe, histories, start, end)
    first_board_counts = bt.Counter(item.first_board_date for item in matches)

    baseline = evaluate_case(
        matches=matches,
        histories=histories,
        first_board_counts=first_board_counts,
        case=baseline_case(),
    )
    entry_cases = build_entry_cases(wide=args.wide)
    exit_cases = build_exit_cases(wide=args.wide)
    rank_cases = ("turnover", "default", "pressure", "open-sweet", "low-first")
    print(
        "matrix "
        f"raw_matches={len(matches)} "
        f"entry_cases={len(entry_cases)} "
        f"exit_cases={len(exit_cases)} "
        f"rank_cases={len(rank_cases)}",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    for entry in entry_cases:
        filtered = filter_matches(matches, first_board_counts, entry)
        if len(filtered) < 120:
            continue
        for rank in rank_cases:
            for exit_case in exit_cases:
                result = evaluate_filtered(
                    filtered_matches=filtered,
                    histories=histories,
                    entry=entry,
                    rank=rank,
                    exit_case=exit_case,
                )
                summary = result["summary"]
                yearly = result["yearly"]
                if not qualifies(summary, yearly):
                    continue
                result["score"] = score_result(summary, yearly)
                results.append(result)

    results.sort(
        key=lambda item: (
            item["summary"]["position_weighted_return_pct"] or -9,
            item["score"],
        ),
        reverse=True,
    )
    report = {
        "note": (
            "Entry filters and ranking use only first-board or second-day open "
            "visible fields. Future bars are used only for exits and PnL."
        ),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "universe_count": len(universe),
        "raw_match_count": len(matches),
        "baseline": baseline,
        "top": results[: max(1, args.top)],
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print_summary(report, output_path)
    return 0


def load_cached_research_data(
    cache_dir: Path,
    start,
    end,
) -> tuple[list[bt.StockMeta], dict[str, list[bt.DailyBar]]]:
    if not cache_dir.exists():
        raise SystemExit(f"cache directory does not exist: {cache_dir}")
    universe: list[bt.StockMeta] = []
    histories: dict[str, list[bt.DailyBar]] = {}
    lookback_start = start - timedelta(days=220)
    for cache_file in sorted(cache_dir.glob("*.json")):
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        code = bt.normalize_code(payload.get("symbol") or cache_file.stem)
        name = bt.normalize_name(payload.get("name")) or code
        if not bt.is_mainboard_code(code) or bt.is_blocked_name(name):
            continue
        bars = [
            bt.DailyBar(
                trade_date=str(row["trade_date"]),
                open=bt.safe_float(row["open"]),
                close=bt.safe_float(row["close"]),
                high=bt.safe_float(row["high"]),
                low=bt.safe_float(row["low"]),
                volume_hands=bt.safe_float(row["volume_hands"]),
            )
            for row in payload.get("rows", [])
        ]
        bars = [
            item
            for item in bt.deduplicate_bars(bars)
            if lookback_start <= bt.parse_iso_date(item.trade_date) <= end
        ]
        bars = sorted(bars, key=lambda item: item.trade_date)
        if len(bars) < 65:
            continue
        universe.append(bt.StockMeta(code=code, name=name, listing_date=None))
        histories[code] = bars
    if len(histories) < bt.MIN_COMPLETE_MAINBOARD_UNIVERSE:
        raise SystemExit(
            f"cached universe incomplete: loaded {len(histories)} symbols"
        )
    return universe, histories


def build_raw_matches(
    universe: list[bt.StockMeta],
    histories: dict[str, list[bt.DailyBar]],
    start,
    end,
) -> list[bt.Match]:
    matches: list[bt.Match] = []
    for stock in universe:
        bars = histories.get(stock.code)
        if not bars:
            continue
        matches.extend(
            bt.analyze_symbol(
                stock=stock,
                bars=bars,
                start_date=start,
                end_date=end,
                min_turnover_amount=0,
                liquidity_score_amount=bt.DEFAULT_LIQUIDITY_SCORE_AMOUNT,
                recent_gain_block_pct=9,
                high_deviation_block_pct=9,
                near_pressure_pct=-1,
                min_confirm_open_pct=-1,
                max_confirm_open_pct=1,
                min_volume_ratio_5=0,
                min_rsi_14=0,
                max_rsi_14=100,
                min_position_percentile_60=0,
            )
        )
    return matches


def baseline_case() -> dict[str, Any]:
    return {
        "entry": {
            "min_score": 82,
            "max_score": None,
            "min_open": 0,
            "max_open": 0.035,
            "min_turnover": 200_000_000,
            "max_turnover": None,
            "min_volume_ratio": 1.0,
            "max_volume_ratio": None,
            "min_rsi": 55,
            "max_rsi": 85,
            "min_position_percentile": 0.55,
            "max_position_percentile": None,
            "max_recent_gain": 0.45,
            "max_ma20_deviation": 0.25,
            "near_pressure_pct": 0.05,
            "labels": ("low_breakout", "breakout", "low_position"),
            "min_first_board_count_for_low_breakout": 45,
            "min_ready_for_low_breakout": 6,
            "max_ready_candidates": 18,
        },
        "rank": "turnover",
        "exit": {
            "stop": 0.04,
            "first_tp": 0.12,
            "strong_tp": 0.10,
            "trail": 0.02,
            "weak": 0.04,
            "hold": 2,
        },
    }


def build_entry_cases(wide: bool = False) -> list[dict[str, Any]]:
    base = baseline_case()["entry"]
    cases: list[dict[str, Any]] = [dict(base)]
    if not wide:
        focused_updates = [
            {"min_turnover": 300_000_000},
            {"min_turnover": 300_000_000, "max_turnover": 800_000_000},
            {"min_turnover": 300_000_000, "max_turnover": 1_200_000_000},
            {"max_score": 88},
            {"max_score": 90},
            {"min_score": 80},
            {"min_score": 84},
            {"min_open": 0.005, "max_open": 0.035},
            {"min_open": 0.01, "max_open": 0.035},
            {"min_open": 0, "max_open": 0.045},
            {"min_rsi": 60, "max_rsi": 85},
            {"min_rsi": 65, "max_rsi": 85},
            {"min_rsi": 65, "max_rsi": 80},
            {"min_rsi": 55, "max_rsi": 72},
            {"min_volume_ratio": 1.2},
            {"min_volume_ratio": 1.0, "max_volume_ratio": 3.0},
            {"min_volume_ratio": 1.2, "max_volume_ratio": 3.0},
            {"min_position_percentile": 0.6},
            {"max_recent_gain": 0.35},
            {"max_ma20_deviation": 0.2},
            {"min_turnover": 300_000_000, "min_rsi": 55, "max_rsi": 72},
            {"min_turnover": 300_000_000, "max_score": 90},
            {"min_turnover": 300_000_000, "min_volume_ratio": 1.2},
            {"max_score": 90, "min_rsi": 55, "max_rsi": 72},
            {"min_open": 0.005, "max_open": 0.035, "min_turnover": 300_000_000},
        ]
        for update in focused_updates:
            case = dict(base)
            case.update(update)
            cases.append(case)
        return unique_cases(cases)

    for min_turnover in (200_000_000, 300_000_000):
        for max_turnover in (None, 800_000_000, 1_200_000_000):
            for max_score in (None, 88, 90):
                for min_score in (80, 82, 84):
                    for min_open, max_open in (
                        (0, 0.035),
                        (0.005, 0.035),
                        (0.01, 0.035),
                        (0, 0.045),
                    ):
                        for min_rsi, max_rsi in (
                            (55, 85),
                            (60, 85),
                            (65, 85),
                            (65, 80),
                            (55, 72),
                        ):
                            case = dict(base)
                            case.update(
                                {
                                    "min_score": min_score,
                                    "max_score": max_score,
                                    "min_open": min_open,
                                    "max_open": max_open,
                                    "min_turnover": min_turnover,
                                    "max_turnover": max_turnover,
                                    "min_rsi": min_rsi,
                                    "max_rsi": max_rsi,
                                }
                            )
                            cases.append(case)
    for min_volume_ratio, max_volume_ratio in (
        (1.2, None),
        (1.0, 3.0),
        (1.2, 3.0),
    ):
        case = dict(base)
        case.update(
            {
                "min_volume_ratio": min_volume_ratio,
                "max_volume_ratio": max_volume_ratio,
            }
        )
        cases.append(case)
    return unique_cases(cases)


def build_exit_cases(wide: bool = False) -> list[dict[str, Any]]:
    cases = [baseline_case()["exit"]]
    if not wide:
        focused_updates = [
            {"first_tp": 0.10},
            {"first_tp": 0.08},
            {"strong_tp": 0.12},
            {"trail": 0.03},
            {"weak": 0.03},
            {"stop": 0.05},
            {"first_tp": 0.10, "strong_tp": 0.12},
            {"first_tp": 0.08, "strong_tp": 0.12},
            {"trail": 0.03, "weak": 0.03},
            {"first_tp": 0.10, "trail": 0.03},
        ]
        for update in focused_updates:
            case = dict(cases[0])
            case.update(update)
            cases.append(case)
        return unique_cases(cases)

    for first_tp in (0.10, 0.12):
        for strong_tp in (0.10, 0.12):
            for trail in (0.02, 0.03):
                for weak in (0.03, 0.04):
                    cases.append(
                        {
                            "stop": 0.04,
                            "first_tp": first_tp,
                            "strong_tp": strong_tp,
                            "trail": trail,
                            "weak": weak,
                            "hold": 2,
                        }
                    )
    return unique_cases(cases)


def unique_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for case in cases:
        key = json.dumps(case, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)
    return unique


def filter_matches(
    matches: list[bt.Match],
    first_board_counts: bt.Counter,
    entry: dict[str, Any],
) -> list[bt.Match]:
    labels = set(entry["labels"])
    base: list[bt.Match] = []
    for item in matches:
        pressure_distance = item.pressure_distance_pct
        if item.score < entry["min_score"]:
            continue
        if score_is_overheated(item.score, entry["max_score"]):
            continue
        if item.position_label not in labels:
            continue
        if not entry["min_open"] <= item.second_open_pct <= entry["max_open"]:
            continue
        if item.estimated_turnover_amount < entry["min_turnover"]:
            continue
        if (
            entry["max_turnover"] is not None
            and item.estimated_turnover_amount >= entry["max_turnover"]
        ):
            continue
        if item.volume_ratio_5 < entry["min_volume_ratio"]:
            continue
        if (
            entry["max_volume_ratio"] is not None
            and item.volume_ratio_5 >= entry["max_volume_ratio"]
        ):
            continue
        if not entry["min_rsi"] <= item.rsi_14 <= entry["max_rsi"]:
            continue
        if item.position_percentile_60 < entry["min_position_percentile"]:
            continue
        if (
            entry["max_position_percentile"] is not None
            and item.position_percentile_60 >= entry["max_position_percentile"]
        ):
            continue
        if item.recent_gain_pct >= entry["max_recent_gain"]:
            continue
        if item.ma20_deviation_pct >= entry["max_ma20_deviation"]:
            continue
        if (
            pressure_distance is not None
            and 0 <= pressure_distance <= entry["near_pressure_pct"]
        ):
            continue
        if item.second_day_one_word:
            continue
        base.append(
            replace(
                item,
                first_board_count=first_board_counts[item.first_board_date],
            )
        )

    ready_counts = bt.Counter(item.second_day_date for item in base)
    filtered: list[bt.Match] = []
    for item in base:
        ready_count = ready_counts[item.second_day_date]
        if (
            entry["max_ready_candidates"] > 0
            and ready_count > entry["max_ready_candidates"]
        ):
            continue
        if item.position_label == "low_breakout":
            if (
                entry["min_first_board_count_for_low_breakout"] > 0
                and item.first_board_count
                < entry["min_first_board_count_for_low_breakout"]
            ):
                continue
            if (
                entry["min_ready_for_low_breakout"] > 0
                and ready_count < entry["min_ready_for_low_breakout"]
            ):
                continue
        filtered.append(replace(item, ready_candidate_count=ready_count))
    return filtered


def score_is_overheated(score: float, max_score: float | None) -> bool:
    return max_score is not None and score >= max_score


def evaluate_case(
    matches: list[bt.Match],
    histories: dict[str, list[bt.DailyBar]],
    first_board_counts: bt.Counter,
    case: dict[str, Any],
) -> dict[str, Any]:
    filtered = filter_matches(matches, first_board_counts, case["entry"])
    return evaluate_filtered(
        filtered_matches=filtered,
        histories=histories,
        entry=case["entry"],
        rank=case["rank"],
        exit_case=case["exit"],
    )


def evaluate_filtered(
    filtered_matches: list[bt.Match],
    histories: dict[str, list[bt.DailyBar]],
    entry: dict[str, Any],
    rank: str,
    exit_case: dict[str, Any],
) -> dict[str, Any]:
    portfolio = bt.build_product_portfolio(
        filtered_matches=filtered_matches,
        histories=histories,
        selection_rank=rank,
        position_pct=0.08,
        stop_loss_pct=exit_case["stop"],
        first_take_profit_pct=exit_case["first_tp"],
        strong_take_profit_pct=exit_case["strong_tp"],
        trailing_stop_pct=exit_case["trail"],
        discipline_exit_min_gain_pct=exit_case["weak"],
        max_holding_trade_days=exit_case["hold"],
        max_simulation_trade_days=10,
    )
    return {
        "entry": entry,
        "rank": rank,
        "exit": exit_case,
        "candidate_count": len(filtered_matches),
        "summary": portfolio["one_position_no_overlap"],
        "yearly": portfolio["yearly_one_position_no_overlap"],
        "labels": portfolio["position_labels_one_position_no_overlap"],
        "exit_reasons": portfolio["exit_reasons_one_position_no_overlap"],
    }


def qualifies(summary: dict[str, Any], yearly: dict[str, Any]) -> bool:
    if summary["sample_count"] < 90:
        return False
    if (summary["position_weighted_return_pct"] or 0) <= 0:
        return False
    for item in yearly.values():
        if item["sample_count"] < 10:
            return False
        if (item["position_weighted_return_pct"] or -9) < 0:
            return False
    return True


def score_result(summary: dict[str, Any], yearly: dict[str, Any]) -> float:
    portfolio_return = summary["position_weighted_return_pct"] or 0
    win_rate = summary["win_rate"] or 0
    avg_return = summary["average_return_pct"] or 0
    drawdown = abs(summary["max_drawdown_pct"] or 0)
    yearly_floor = min(
        item["position_weighted_return_pct"] or -9 for item in yearly.values()
    )
    sample_count = min(summary["sample_count"], 180)
    return round(
        portfolio_return * 3
        + yearly_floor * 2
        + win_rate * 0.35
        + avg_return * 5
        - drawdown * 2
        + sample_count / 1000,
        6,
    )


def print_summary(report: dict[str, Any], output_path: Path) -> None:
    baseline = report["baseline"]["summary"]
    print(
        "baseline "
        f"trades={baseline['sample_count']} "
        f"win={baseline['win_rate']} "
        f"return={baseline['position_weighted_return_pct']} "
        f"dd={baseline['max_drawdown_pct']}",
        flush=True,
    )
    print("top results:", flush=True)
    for item in report["top"][:10]:
        summary = item["summary"]
        print(
            json.dumps(
                {
                    "score": item.get("score"),
                    "trades": summary["sample_count"],
                    "win": summary["win_rate"],
                    "return": summary["position_weighted_return_pct"],
                    "dd": summary["max_drawdown_pct"],
                    "yearly": item["yearly"],
                    "entry": item["entry"],
                    "rank": item["rank"],
                    "exit": item["exit"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    print(f"output={output_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
