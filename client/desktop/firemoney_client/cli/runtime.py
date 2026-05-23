"""Command runtime for the FireMoney one-to-two CLI."""

from __future__ import annotations

from argparse import Namespace

from server.firemoney_server.infrastructure.local_env import load_local_feishu_env

from ..composition import build_local_main_chain_context
from .handlers import UNHANDLED, run_report_command
from .output import Printer, emit_result, safe_print
from .schedule_runner import run_beta_start_command, run_schedule_command


def run_one_to_two_command(args: Namespace, printer: Printer = safe_print) -> None:
    """Execute one parsed CLI command and write the result through ``printer``."""
    load_local_feishu_env()
    if args.mode == "beta-start" and args.no_notify:
        emit_result(
            {
                "mode": "beta-start",
                "status": "blocked",
                "summary": "beta-start 必须发送飞书通知，不能使用 --no-notify。",
                "next_action": "移除 --no-notify，并先用 beta-check 验证飞书 sent 记录。",
            },
            mode=args.mode,
            brief=args.brief,
            printer=printer,
        )
        return
    if args.mode == "beta-start" and args.sample_data:
        emit_result(
            {
                "mode": "beta-start",
                "status": "blocked",
                "summary": "beta-start 是真实值守入口，不能使用 --sample-data 演示行情。",
                "next_action": "演练请用 schedule --sample-data；真实值守请移除 --sample-data 并先运行 beta-check。",
            },
            mode=args.mode,
            brief=args.brief,
            printer=printer,
        )
        return
    if args.beta and args.mode == "schedule" and args.no_notify:
        emit_result(
            {
                "mode": "schedule",
                "status": "blocked",
                "summary": "模拟盘 Beta 值守必须发送飞书通知，不能同时使用 --no-notify。",
                "next_action": "移除 --no-notify，或先运行 doctor --beta 修复阻断项。",
            },
            mode=args.mode,
            brief=args.brief,
            printer=printer,
        )
        return
    context = build_local_main_chain_context(
        sample_data=args.sample_data,
        paper_store_path=args.paper_store,
        paper_database_path=args.paper_db,
        notification_store_path=args.notification_store,
        scheduler_state_path=args.scheduler_state,
        scheduler_runs_path=args.scheduler_runs,
        board_shadow_store_path=args.board_shadow_store,
    )

    if args.mode == "beta-start":
        run_beta_start_command(args, context, printer=printer)
        return
    if args.mode == "schedule":
        run_schedule_command(args, context, printer=printer)
        return

    result = run_report_command(args, context)
    if result is UNHANDLED:
        raise ValueError(f"Unsupported one-to-two CLI mode: {args.mode}")
    emit_result(result, mode=args.mode, brief=args.brief, printer=printer)


__all__ = ["run_one_to_two_command", "safe_print"]
