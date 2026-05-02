"""Local command entry point for the one-to-two strategy workflow."""

from __future__ import annotations

import argparse
import json
import time

from shared.contracts import contract_to_dict

from .adapter import LocalMainChainAdapter
from server.firemoney_server import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    SampleMarketDataProvider,
)
from server.firemoney_server.infrastructure.local_env import load_local_feishu_env
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FireMoney one-to-two workflow.")
    parser.add_argument(
        "mode",
        choices=(
            "morning",
            "watch",
            "eod",
            "backtest",
            "stability",
            "doctor",
            "beta-check",
            "beta-start",
            "feishu-test",
            "schedule",
            "scheduler-runs",
            "notifications",
        ),
        help="Workflow mode to run.",
    )
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--max-trade-days", type=int, default=30)
    parser.add_argument("--at", default=None, help="schedule mode clock time, HH:MM.")
    parser.add_argument("--paper-store", default=None, help="Optional paper ledger path.")
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
        "--loop",
        action="store_true",
        help="Keep schedule mode running until Ctrl+C.",
    )
    parser.add_argument("--interval-seconds", type=int, default=60)
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
    args = parser.parse_args()
    load_local_feishu_env()
    if args.mode == "beta-start" and args.no_notify:
        result = {
            "mode": "beta-start",
            "status": "blocked",
            "summary": "beta-start å¿…é¡»å‘é€é£žä¹¦é€šçŸ¥ï¼Œä¸èƒ½ä½¿ç”¨ --no-notifyã€‚",
            "next_action": "ç§»é™¤ --no-notifyï¼Œå¹¶å…ˆç”¨ beta-check éªŒè¯é£žä¹¦ sent è®°å½•ã€‚",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.beta and args.mode == "schedule" and args.no_notify:
        result = {
            "mode": "schedule",
            "status": "blocked",
            "summary": "模拟盘 Beta 值守必须发送飞书通知，不能同时使用 --no-notify。",
            "next_action": "移除 --no-notify，或先运行 doctor --beta 修复阻断项。",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    provider = SampleMarketDataProvider() if args.sample_data else AkshareMarketDataProvider()
    paper_store = PaperTradeStore(args.paper_store) if args.paper_store else None
    notification_store = (
        NotificationRecordStore(args.notification_store)
        if args.notification_store
        else None
    )
    scheduler_run_store = (
        SchedulerRunStore(args.scheduler_runs)
        if args.scheduler_runs
        else SchedulerRunStore()
    )
    scheduler_state_store = (
        SchedulerStateStore(args.scheduler_state)
        if args.scheduler_state
        else SchedulerStateStore()
    )
    service = MainChainService(
        market_data_provider=provider,
        paper_store=paper_store,
        notification_store=notification_store,
        scheduler_state_store=scheduler_state_store,
        scheduler_run_store=scheduler_run_store,
    )
    adapter = LocalMainChainAdapter(service)
    if args.mode == "morning":
        result = adapter.build_one_to_two_morning_report(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    elif args.mode == "watch":
        result = adapter.run_one_to_two_watch(
            trade_date=args.trade_date,
            phase=args.phase,
            notify=not args.no_notify,
        )
    elif args.mode == "eod":
        result = adapter.build_one_to_two_end_of_day_review(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    elif args.mode == "backtest":
        result = adapter.run_one_to_two_backtest(
            start_date=args.start_date,
            end_date=args.end_date or args.trade_date,
            max_trade_days=args.max_trade_days,
        )
    elif args.mode == "stability":
        result = adapter.build_one_to_two_stability_report()
    elif args.mode == "doctor":
        result = adapter.build_one_to_two_doctor_report(
            trade_date=args.trade_date,
            beta=args.beta,
        )
    elif args.mode == "beta-check":
        if args.no_notify:
            result = {
                "mode": "beta-check",
                "status": "blocked",
                "summary": "beta-check 必须真实发送飞书测试，不能使用 --no-notify。",
                "next_action": "移除 --no-notify，并确认飞书 webhook 或应用机器人已配置。",
            }
        else:
            result = adapter.build_one_to_two_beta_readiness_report(
                trade_date=args.trade_date,
            )
    elif args.mode == "beta-start":
        readiness = adapter.build_one_to_two_doctor_report(
            trade_date=args.trade_date,
            beta=True,
        )
        if readiness.status != "ready":
            print(json.dumps(contract_to_dict(readiness), ensure_ascii=False, indent=2))
            return
        scheduler = OneToTwoScheduler(
            service=service,
            state_store=scheduler_state_store,
        )
        result = scheduler.run_due(
            trade_date=args.trade_date,
            at_time=args.at,
            notify=True,
        )
        scheduler_run_store.append(result)
        if args.loop:
            print(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))
            while True:
                time.sleep(max(1, args.interval_seconds))
                result = scheduler.run_due(
                    trade_date=args.trade_date,
                    at_time=args.at,
                    notify=True,
                )
                scheduler_run_store.append(result)
                print(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))
            return
    elif args.mode == "feishu-test":
        result = adapter.send_one_to_two_feishu_test(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    elif args.mode == "notifications":
        records = adapter.load_notification_records(
            workflow=args.workflow,
            status=args.status,
            limit=max(0, args.limit),
        )
        result = {
            "mode": "notifications",
            "record_count": len(records),
            "records": records,
            "next_action": (
                "No notification records yet; run morning, watch, eod, or schedule first."
                if not records
                else "Review failed or prepared records before trusting Feishu delivery."
            ),
        }
    elif args.mode == "scheduler-runs":
        records = scheduler_run_store.load(limit=max(0, args.limit))
        result = {
            "mode": "scheduler-runs",
            "record_count": len(records),
            "records": records,
            "next_action": (
                "No scheduler run records yet; run schedule first."
                if not records
                else "Review executed, skipped, expired, and failed tasks before trusting Beta watch coverage."
            ),
        }
    else:
        if args.beta:
            readiness = adapter.build_one_to_two_doctor_report(
                trade_date=args.trade_date,
                beta=True,
            )
            if readiness.status != "ready":
                print(json.dumps(contract_to_dict(readiness), ensure_ascii=False, indent=2))
                return
        scheduler = OneToTwoScheduler(
            service=service,
            state_store=scheduler_state_store,
        )
        if args.loop:
            while True:
                result = scheduler.run_due(
                    trade_date=args.trade_date,
                    at_time=args.at,
                    notify=not args.no_notify,
                )
                scheduler_run_store.append(result)
                print(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))
                time.sleep(max(1, args.interval_seconds))
            return
        result = scheduler.run_due(
            trade_date=args.trade_date,
            at_time=args.at,
            notify=not args.no_notify,
        )
        scheduler_run_store.append(result)
    print(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
