"""Output helpers for local FireMoney CLI commands."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from shared.contracts import contract_to_dict

from ..presenters.brief_formatters import (
    format_backtest_audit_brief,
    format_beta_plan_brief,
    format_board_shadow_brief,
    format_board_shadow_stability_brief,
    format_board_shadow_system_brief,
    format_doctor_brief,
    format_execution_quality_brief,
    format_historical_replay_brief,
    format_k92_emotion_liquidity_brief,
    format_missed_opportunities_brief,
    format_morning_brief,
    format_notifications_brief,
    format_paper_backtest_brief,
    format_paper_trade_database_brief,
    format_paper_trading_decision_brief,
    format_schedule_health_brief,
    format_scheduler_runs_brief,
    format_strategy_decision_brief,
    format_watch_brief,
)

Printer = Callable[[str], None]


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sanitized = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(sanitized)


def emit_json(result: Any, printer: Printer = safe_print) -> None:
    printer(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))


def emit_result(
    result: Any,
    *,
    mode: str,
    brief: bool,
    printer: Printer = safe_print,
) -> None:
    if brief:
        formatter = _BRIEF_FORMATTERS.get(mode)
        if formatter:
            printer(formatter(result))
            return
        if mode in _HISTORICAL_REPLAY_BRIEF_MODES:
            printer(format_historical_replay_brief(result))
            return
        if mode in _BOARD_SHADOW_BRIEF_MODES:
            printer(format_board_shadow_brief(result))
            return
    emit_json(result, printer)


_BRIEF_FORMATTERS = {
    "backtest-audit": format_backtest_audit_brief,
    "beta-plan": format_beta_plan_brief,
    "board-shadow-stability": format_board_shadow_stability_brief,
    "board-shadow-system": format_board_shadow_system_brief,
    "doctor": format_doctor_brief,
    "execution-quality": format_execution_quality_brief,
    "k92-emotion": format_k92_emotion_liquidity_brief,
    "k92-backtest": format_paper_backtest_brief,
    "missed-opportunities": format_missed_opportunities_brief,
    "morning": format_morning_brief,
    "notifications": format_notifications_brief,
    "paper-backtest": format_paper_backtest_brief,
    "paper-db": format_paper_trade_database_brief,
    "paper-decision": format_paper_trading_decision_brief,
    "schedule-health": format_schedule_health_brief,
    "scheduler-runs": format_scheduler_runs_brief,
    "strategy-decision": format_strategy_decision_brief,
    "watch": format_watch_brief,
}

_HISTORICAL_REPLAY_BRIEF_MODES = {"replay"}
_BOARD_SHADOW_BRIEF_MODES = {"board-shadow", "board-shadow-record"}

__all__ = ["Printer", "emit_json", "emit_result", "safe_print"]
