"""Scheduler command runners for the FireMoney CLI."""

from __future__ import annotations

import time
from argparse import Namespace

from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler

from ..composition import LocalMainChainContext
from .output import Printer, emit_json, emit_result, safe_print

SCHEDULE_MODES = frozenset({"schedule", "beta-start"})


def run_schedule_command(
    args: Namespace,
    context: LocalMainChainContext,
    printer: Printer = safe_print,
) -> None:
    """Run the ordinary scheduler mode and emit its result."""

    adapter = context.adapter
    if args.beta:
        readiness = adapter.build_one_to_two_doctor_report(
            trade_date=args.trade_date,
            beta=True,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
        if readiness.status != "ready":
            emit_json(readiness, printer)
            return
    scheduler = _build_scheduler(context)
    if args.loop:
        while True:
            result = scheduler.run_due(
                trade_date=args.trade_date,
                at_time=args.at,
                notify=not args.no_notify,
                market_data_timeout_seconds=args.market_data_timeout_seconds,
            )
            context.scheduler_run_store.append(result)
            emit_json(result, printer)
            time.sleep(max(1, args.interval_seconds))
        return
    result = scheduler.run_due(
        trade_date=args.trade_date,
        at_time=args.at,
        notify=not args.no_notify,
        market_data_timeout_seconds=args.market_data_timeout_seconds,
    )
    context.scheduler_run_store.append(result)
    emit_result(result, mode=args.mode, brief=args.brief, printer=printer)


def run_beta_start_command(
    args: Namespace,
    context: LocalMainChainContext,
    printer: Printer = safe_print,
) -> None:
    """Verify Beta readiness, then run the scheduler with real notifications."""

    readiness = context.adapter.build_one_to_two_doctor_report(
        trade_date=args.trade_date,
        beta=True,
        market_data_timeout_seconds=args.market_data_timeout_seconds,
    )
    if _should_auto_send_feishu_test(readiness, args):
        context.adapter.send_one_to_two_feishu_test(
            trade_date=args.trade_date,
            notify=True,
        )
        readiness = context.adapter.build_one_to_two_doctor_report(
            trade_date=args.trade_date,
            beta=True,
            market_data_timeout_seconds=args.market_data_timeout_seconds,
        )
    limited_mode = _can_run_limited_beta_start(readiness, args)
    if readiness.status != "ready" and not limited_mode:
        emit_json(readiness, printer)
        return
    scheduler = _build_scheduler(context)
    result = scheduler.run_due(
        trade_date=args.trade_date,
        at_time=args.at,
        notify=True,
        market_data_timeout_seconds=args.market_data_timeout_seconds,
    )
    if limited_mode:
        result = _mark_limited_mode(result)
    context.scheduler_run_store.append(result)
    if args.loop:
        emit_json(result, printer)
        while True:
            time.sleep(max(1, args.interval_seconds))
            result = scheduler.run_due(
                trade_date=args.trade_date,
                at_time=args.at,
                notify=True,
                market_data_timeout_seconds=args.market_data_timeout_seconds,
            )
            if limited_mode:
                result = _mark_limited_mode(result)
            context.scheduler_run_store.append(result)
            emit_json(result, printer)
        return
    emit_result(result, mode=args.mode, brief=args.brief, printer=printer)


def _can_run_limited_beta_start(readiness, args: Namespace) -> bool:
    if not getattr(args, "allow_market_data_timeout", False):
        return False
    checks = getattr(readiness, "checks", ())
    blocked = [check for check in checks if getattr(check, "status", "") == "blocked"]
    if len(blocked) != 1:
        return False
    return getattr(blocked[0], "check_id", "") == "market_data"


def _should_auto_send_feishu_test(readiness, args: Namespace) -> bool:
    if not getattr(args, "allow_market_data_timeout", False):
        return False
    checks = getattr(readiness, "checks", ())
    blocked = {getattr(check, "check_id", ""): check for check in checks if getattr(check, "status", "") == "blocked"}
    if "feishu" not in blocked:
        return False
    detail = str(getattr(blocked["feishu"], "detail", ""))
    return "feishu-test" in detail


def _mark_limited_mode(result):
    from dataclasses import replace

    tasks = tuple(
        replace(
            task,
            message=(
                f"{task.message} [degraded_market_data_mode]"
                if task.status == "completed"
                else task.message
            ),
        )
        for task in result.tasks
    )
    return replace(
        result,
        tasks=tasks,
        next_action=f"{result.next_action} [degraded_market_data_mode]",
    )


def _build_scheduler(context: LocalMainChainContext) -> OneToTwoScheduler:
    return OneToTwoScheduler(
        service=context.service,
        state_store=context.scheduler_state_store,
    )


__all__ = ["SCHEDULE_MODES", "run_beta_start_command", "run_schedule_command"]
