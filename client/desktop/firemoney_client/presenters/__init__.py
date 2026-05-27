"""Presentation helpers for CLI and HTML surfaces."""

from .brief_formatters import (
    format_backtest_audit_brief,
    format_beta_plan_brief,
    format_board_shadow_brief,
    format_board_shadow_stability_brief,
    format_board_shadow_system_brief,
    format_doctor_brief,
    format_execution_quality_brief,
    format_historical_replay_brief,
    format_mainline_trend_watch_brief,
    format_morning_brief,
    format_notifications_brief,
    format_paper_backtest_brief,
    format_paper_trade_database_brief,
    format_paper_trading_decision_brief,
    format_scheduler_runs_brief,
    format_strategy_decision_brief,
    format_watch_brief,
)
from .decision_presenter import DecisionCockpitView, build_decision_cockpit_view
from .notification_presenter import (
    first_notification_detail,
    notification_display_title,
    symbol_name_from_notification_line,
)

__all__ = [
    "DecisionCockpitView",
    "build_decision_cockpit_view",
    "first_notification_detail",
    "format_backtest_audit_brief",
    "format_beta_plan_brief",
    "format_board_shadow_brief",
    "format_board_shadow_stability_brief",
    "format_board_shadow_system_brief",
    "format_doctor_brief",
    "format_execution_quality_brief",
    "format_historical_replay_brief",
    "format_mainline_trend_watch_brief",
    "format_morning_brief",
    "format_notifications_brief",
    "format_paper_backtest_brief",
    "format_paper_trade_database_brief",
    "format_paper_trading_decision_brief",
    "format_scheduler_runs_brief",
    "format_strategy_decision_brief",
    "format_watch_brief",
    "notification_display_title",
    "symbol_name_from_notification_line",
]
