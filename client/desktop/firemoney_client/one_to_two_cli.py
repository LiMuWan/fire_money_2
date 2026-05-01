"""Local command entry point for the one-to-two strategy workflow."""

from __future__ import annotations

import argparse
import json

from shared.contracts import contract_to_dict

from .adapter import LocalMainChainAdapter
from server.firemoney_server import MainChainService
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    SampleMarketDataProvider,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FireMoney one-to-two workflow.")
    parser.add_argument(
        "mode",
        choices=("morning", "watch", "eod", "backtest"),
        help="Workflow mode to run.",
    )
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Use deterministic sample rows instead of AkShare.",
    )
    args = parser.parse_args()

    provider = SampleMarketDataProvider() if args.sample_data else AkshareMarketDataProvider()
    adapter = LocalMainChainAdapter(MainChainService(market_data_provider=provider))
    if args.mode == "morning":
        result = adapter.build_one_to_two_morning_report(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    elif args.mode == "watch":
        result = adapter.run_one_to_two_watch(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    elif args.mode == "eod":
        result = adapter.build_one_to_two_end_of_day_review(
            trade_date=args.trade_date,
            notify=not args.no_notify,
        )
    else:
        result = adapter.build_one_to_two_stability_report()
    print(json.dumps(contract_to_dict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
