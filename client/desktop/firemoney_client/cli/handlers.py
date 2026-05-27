"""Mode handlers for non-scheduler FireMoney CLI commands."""

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
from typing import Any

from server.firemoney_server.application.beta_rehearsal import (
    build_one_to_two_beta_launch_plan,
    run_one_to_two_beta_rehearsal,
)
from shared.contracts import contract_to_dict

from ..broker.qmt_gateway import QmtBrokerGateway
from ..composition import LocalMainChainContext

UNHANDLED = object()
HANDLED_MODES = frozenset(
    {
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
        "mainline-trend",
        "paper-decision",
        "qmt-check",
        "qmt-plan",
        "paper-db",
        "execution-quality",
        "stability",
        "doctor",
        "beta-check",
        "beta-plan",
        "beta-rehearsal",
        "feishu-test",
        "notifications",
        "scheduler-runs",
        "schedule-health",
    }
)


def run_report_command(args: Namespace, context: LocalMainChainContext) -> Any:
    """Return a command result, or ``UNHANDLED`` when schedule runtime should run."""

    adapter = context.adapter
    if args.mode == "morning":
        return adapter.build_one_to_two_morning_report(
            trade_date=args.trade_date,
            notify=not args.no_notify,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
            record_notification=not args.no_notify,
        )
    if args.mode == "watch":
        return adapter.run_one_to_two_watch(
            trade_date=args.trade_date,
            phase=args.phase,
            notify=not args.no_notify,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
    if args.mode == "eod":
        return adapter.build_one_to_two_end_of_day_review(
            trade_date=args.trade_date,
            notify=not args.no_notify,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
            record_notification=not args.no_notify,
        )
    if args.mode == "backtest":
        return adapter.run_one_to_two_backtest(
            start_date=args.start_date,
            end_date=args.end_date or args.trade_date,
            max_trade_days=args.max_trade_days,
        )
    if args.mode == "backtest-audit":
        return adapter.build_one_to_two_backtest_audit(
            start_date=args.start_date,
            end_date=args.end_date or args.trade_date,
            max_trade_days=args.max_trade_days,
        )
    if args.mode == "replay":
        return adapter.run_one_to_two_historical_replay(
            as_of_date=args.trade_date,
            holding_days=args.holding_days,
        )
    if args.mode == "board-shadow":
        return adapter.build_limit_up_board_shadow_report(
            as_of_date=args.trade_date,
            cache_dir=args.cache_dir,
        )
    if args.mode == "board-shadow-record":
        return adapter.record_limit_up_board_shadow_sample(
            as_of_date=args.trade_date,
            cache_dir=args.cache_dir,
            notify=not args.no_notify,
        )
    if args.mode == "board-shadow-stability":
        return adapter.build_limit_up_board_shadow_stability_report()
    if args.mode == "board-shadow-system":
        return adapter.build_limit_up_board_shadow_system_report(
            start_date=args.start_date or "2024-01-01",
            end_date=args.end_date or args.trade_date,
            cache_dir=args.cache_dir,
        )
    if args.mode == "paper-backtest":
        report = adapter.build_paper_backtest_report(
            start_date=args.start_date or "2020-01-01",
            end_date=args.end_date or args.trade_date,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
        )
        _write_report_cache(report, args.report_cache)
        return report
    if args.mode == "missed-opportunities":
        return adapter.build_missed_opportunity_report(
            start_date=args.start_date or "2026-05-01",
            end_date=args.end_date or args.trade_date,
            cache_dir=args.cache_dir,
            limit=max(0, args.limit),
        )
    if args.mode == "strategy-decision":
        return adapter.build_strategy_decision_report(
            trade_date=args.trade_date,
            start_date=args.start_date or "2024-01-01",
            end_date=args.end_date or args.trade_date,
            cache_dir=args.cache_dir,
        )
    if args.mode == "k92-emotion":
        return adapter.build_k92_emotion_liquidity_report(
            trade_date=args.trade_date,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
    if args.mode == "k92-backtest":
        report = adapter.build_k92_emotion_liquidity_backtest_report(
            start_date=args.start_date or "2020-01-01",
            end_date=args.end_date or args.trade_date,
            cache_dir=args.cache_dir,
        )
        _write_report_cache(report, args.report_cache)
        return report
    if args.mode == "mainline-trend":
        return adapter.build_mainline_trend_watch_report(
            trade_date=args.trade_date,
            limit=max(1, args.limit),
        )
    if args.mode == "paper-decision":
        return adapter.build_paper_trading_decision_report(
            trade_date=args.trade_date,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
            notify=False,
        )
    if args.mode == "qmt-check":
        return _build_qmt_gateway(args).check()
    if args.mode == "qmt-plan":
        paper_report = adapter.build_paper_trading_decision_report(
            trade_date=args.trade_date,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
            notify=False,
        )
        return _build_qmt_gateway(args).plan_paper_decision(
            paper_report,
            submit=args.qmt_submit,
        )
    if args.mode == "paper-db":
        return adapter.build_paper_trade_database_report(
            database_path=args.paper_db,
            limit=max(0, args.limit),
        )
    if args.mode == "execution-quality":
        return adapter.build_one_to_two_execution_quality_report(
            symbol=args.symbol,
            trade_date=args.trade_date,
        )
    if args.mode == "stability":
        return adapter.build_one_to_two_stability_report()
    if args.mode == "doctor":
        return adapter.build_one_to_two_doctor_report(
            trade_date=args.trade_date,
            beta=args.beta,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
    if args.mode == "beta-check":
        if args.no_notify:
            return {
                "mode": "beta-check",
                "status": "blocked",
                "summary": "beta-check 必须真实发送飞书测试，不能使用 --no-notify。",
                "next_action": "移除 --no-notify，并确认飞书 webhook 或应用机器人已配置。",
            }
        return adapter.build_one_to_two_beta_readiness_report(
            trade_date=args.trade_date,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
    if args.mode == "beta-plan":
        return build_one_to_two_beta_launch_plan(
            trade_date=args.trade_date,
            service=context.service,
        )
    if args.mode == "beta-rehearsal":
        return run_one_to_two_beta_rehearsal(trade_date=args.trade_date)
    if args.mode == "feishu-test":
        return adapter.send_one_to_two_feishu_test(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    if args.mode == "notifications":
        records = adapter.load_notification_records(
            workflow=args.workflow,
            status=args.status,
            limit=max(0, args.limit),
            action_only=args.action_only,
        )
        return {
            "mode": "notifications",
            "record_count": len(records),
            "records": records,
            "next_action": (
                "No notification records yet; run morning, watch, eod, or schedule first."
                if not records
                else "Review failed or prepared records before trusting Feishu delivery."
            ),
        }
    if args.mode == "scheduler-runs":
        records = context.scheduler_run_store.load(limit=max(0, args.limit))
        return {
            "mode": "scheduler-runs",
            "record_count": len(records),
            "records": records,
            "next_action": (
                "No scheduler run records yet; run schedule first."
                if not records
                else "Review executed, skipped, expired, and failed tasks before trusting Beta watch coverage."
            ),
        }
    if args.mode == "schedule-health":
        return adapter.build_schedule_health_report(trade_date=args.trade_date)
    return UNHANDLED


def _write_report_cache(report: Any, report_cache: str | None) -> None:
    if not report_cache:
        return
    path = Path(report_cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(contract_to_dict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_qmt_gateway(args: Namespace) -> QmtBrokerGateway:
    return QmtBrokerGateway(
        qmt_path=args.qmt_path,
        account_id=args.qmt_account,
        session_id=args.qmt_session_id,
    )


__all__ = ["HANDLED_MODES", "UNHANDLED", "run_report_command"]
