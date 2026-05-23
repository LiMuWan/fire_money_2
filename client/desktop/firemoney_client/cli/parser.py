"""Argument parser for the FireMoney one-to-two command line entry."""

from __future__ import annotations

import argparse


def build_one_to_two_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without importing service or infrastructure layers."""
    parser = argparse.ArgumentParser(description="Run FireMoney one-to-two workflow.")
    parser.add_argument(
        "mode",
        choices=(
            "morning",
            "watch",
            "eod",
            "backtest",
            "backtest-audit",
            "replay",
            "board-shadow",
            "board-shadow-record",
            "board-shadow-stability",
            "board-shadow-system",
            "paper-backtest",
            "missed-opportunities",
            "strategy-decision",
            "k92-emotion",
            "k92-backtest",
            "paper-decision",
            "paper-db",
            "execution-quality",
            "stability",
            "doctor",
            "beta-check",
            "beta-plan",
            "beta-rehearsal",
            "beta-start",
            "feishu-test",
            "schedule",
            "scheduler-runs",
            "schedule-health",
            "notifications",
        ),
        help="Workflow mode to run.",
    )
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--symbol", default="600001")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--max-trade-days", type=int, default=30)
    parser.add_argument(
        "--holding-days",
        type=int,
        default=5,
        help="Maximum future trading days used by replay mode for exit accounting.",
    )
    parser.add_argument("--at", default=None, help="schedule mode clock time, HH:MM.")
    parser.add_argument("--paper-store", default=None, help="Optional paper ledger path.")
    parser.add_argument("--paper-db", default=None, help="Optional paper SQLite database path.")
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Optional research daily-bar cache path for board-shadow.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Refresh research daily-bar cache before paper-backtest reports.",
    )
    parser.add_argument(
        "--report-cache",
        default=None,
        help="Optional JSON path to write a report snapshot for preview reuse.",
    )
    parser.add_argument(
        "--board-shadow-store",
        default=None,
        help="Optional limit-up board shadow sample store path.",
    )
    parser.add_argument(
        "--notification-store",
        default=None,
        help="Optional notification record path.",
    )
    parser.add_argument("--scheduler-state", default=None, help="Optional scheduler state path.")
    parser.add_argument(
        "--scheduler-runs",
        default=None,
        help="Optional scheduler run audit path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum local records to print.",
    )
    parser.add_argument(
        "--workflow",
        default=None,
        help="Filter notification records by workflow, for example watch:open.",
    )
    parser.add_argument(
        "--status",
        choices=("disabled", "prepared", "sent", "failed"),
        default=None,
        help="Filter notification records by delivery status.",
    )
    parser.add_argument(
        "--action-only",
        action="store_true",
        help="Show only morning, real paper buy, real paper sell, and end-of-day notifications.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep schedule mode running until Ctrl+C.",
    )
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument(
        "--market-data-timeout-seconds",
        type=float,
        default=20.0,
        help="Maximum seconds for doctor/beta market data readiness checks.",
    )
    parser.add_argument(
        "--phase",
        choices=("scan", "auction", "open", "risk"),
        default="scan",
        help="watch mode phase.",
    )
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Use deterministic sample rows instead of AkShare.",
    )
    parser.add_argument(
        "--beta",
        action="store_true",
        help="Use stricter readiness checks for simulated Beta watch mode.",
    )
    parser.add_argument(
        "--allow-market-data-timeout",
        action="store_true",
        help="Allow beta-start to enter limited watch mode when market data is the only blocked check.",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Print a compact human-readable summary for report modes.",
    )
    return parser


__all__ = ["build_one_to_two_parser"]
