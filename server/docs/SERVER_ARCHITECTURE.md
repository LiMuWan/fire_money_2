# FireMoney Server Architecture

## 1. Goal

The server/business layer owns deterministic workflow policy, state transitions, and external adaptation. The first release may run in-process locally, but the boundary is designed as a server boundary.

## 2. Current Skeleton

```text
server/firemoney_server/
  application/
    main_chain.py       main workflow orchestration
  domain/
    archive.py          completed trade archive record policy
    archive_review.py   lightweight completed-archive review policy
    one_to_two.py       mainboard 10cm one-to-two scoring and blocker policy
    strategy_boundary_review.py  archive-review-driven boundary guidance
    strategy_reset_review.py  confirmable local boundary reset guidance
    strategy_config.py  confirmed strategy-boundary validation/application
  infrastructure/
    archive_store.py    local completed trade archive persistence/export/cleanup
    archive_review_export.py  Markdown export for lightweight archive reviews
    export_cleanup.py   retention cleanup for service-owned export files
    feishu_notifier.py  Feishu group robot webhook notification adapter
    market_data.py      MarketDataProvider boundary and AkShare adapter
    one_to_two_config.py  one-to-two strategy config loader
    paper_store.py      local event-driven paper-trading account
    config/             deterministic local input data
    strategy_audit_export.py  Markdown export for strategy-boundary audit records
    strategy_store.py   local strategy config persistence
```

## 3. Layer Rules

- `application` orchestrates use cases and does not own UI concerns.
- `domain` owns business rules and must not depend on UI, SDKs, or window objects.
- `infrastructure` owns data sources, files, webhook adapters, caches, and external bridges.
- `shared/contracts` is the stable public language for the client.

## 4. First-Slice Chain

The current product workflow flows through:

```text
AkShare/market data -> one-to-two candidate scoring
-> event-driven paper account -> Feishu notification result
-> end-of-day review -> stability observation
```

The legacy first-slice execution prototype remains in code for regression coverage, but it is no longer rendered in the current product preview.

## 5. Follow-up Rules

- Risk, position limits, blockers, paper-account events, notification results, and review output should all be authoritative server/business-layer outputs.
- Sample data may provide local preview inputs, but it must not own business decisions.
- Completed trade archive records are built by `domain/archive.py`; they summarize closed samples without introducing a separate history surface yet.
- Completed trade archive records are persisted by `infrastructure/archive_store.py` under `.firemoney/trade_archives.json`.
- Recent archive records can be exported through `MainChainService.export_trade_archives()` as JSON under `exports/archives/`.
- Recent archive records can produce `TradeArchiveReview` through `MainChainService.build_trade_archive_review()` and Markdown through `MainChainService.export_trade_archive_review()`.
- Archive review metrics are built by `domain/archive_review.py`; `infrastructure/archive_review_export.py` only formats the already-approved service output.
- Archive export cleanup goes through `MainChainService.cleanup_archive_exports(retention_count=...)`; it only deletes service-owned archive export filenames and keeps unmatched files.
- Archive review uses a minimum 3-record sample-quality gate before recommending strategy-boundary review; smaller samples are observation-only.
- Archive-review-driven strategy boundary guidance is built by `domain/strategy_boundary_review.py` and exposed through `MainChainService.build_strategy_boundary_review()`; it returns confirmable `StrategyAdjustment` items but does not write config.
- Confirmed archive-review-driven boundary guidance is applied through `MainChainService.apply_strategy_boundary_review(confirm=True)`, which reuses `StrategyConfigPolicy.apply_adjustments()` and `StrategyConfigStore.save()`.
- Local archive cleanup goes through `MainChainService.clear_trade_archives()`; client code must not delete `.firemoney` files directly.
- Invalid local archive JSON is treated as empty local state so the main workflow can continue.
- Recap may propose strategy adjustments, but it must not write new strategy config automatically.
- Strategy config changes require explicit adjustment confirmation before they affect the next scan cycle.
- Strategy config parameters are validated by `domain/strategy_config.py` before they enter the next signal scan.
- Invalid local strategy JSON falls back to default config; unknown, malformed, or out-of-range parameters are corrected from default boundaries.
- Confirmed strategy boundaries are stored locally under `.firemoney/strategy_config.json`.
- Local strategy-boundary reset guidance is built by `domain/strategy_reset_review.py` and exposed through `MainChainService.build_strategy_reset_review()`; it returns blockers, recent changes, and the default target version without deleting files.
- Local strategy boundaries are reset only through `MainChainService.apply_strategy_reset_review(confirm=True)` or the legacy service reset helper; UI must not delete files directly.
- Strategy boundary apply/reset actions keep a lightweight local change record for user trust and recovery context.
- Strategy boundary change records can be exported through `MainChainService.export_strategy_boundary_audit()` as Markdown under `exports/strategy/`.
- Strategy boundary audit export can filter records by action through `actions=("apply",)` or `actions=("reset",)`; filtering stays in infrastructure/service code, not the client.
- Strategy export cleanup goes through `MainChainService.cleanup_strategy_exports(retention_count=...)`; it only deletes service-owned strategy audit filenames and returns an `ExportCleanupResult`.
- One-to-two strategy settings are loaded from `infrastructure/config/one_to_two_strategy.zh_CN.json`; default capital is 100000, single position cap is 8%, and daily paper buys are capped at 1.
- One-to-two market data enters through `MarketDataProvider`; the first real implementation is `AkshareMarketDataProvider`. AkShare fields are normalized into project-owned DTOs before domain scoring.
- AkShare raw snapshots are cached under `.firemoney/market_data/`. If AkShare is unavailable and no explicit fallback is supplied, `MarketDataUnavailable` is raised inside infrastructure, the service converts it into a blocked morning report, and no paper buy can be generated.
- One-to-two scoring lives in `domain/one_to_two.py`: first-board quality, auction/open strength, position structure, theme/market context, and liquidity. ST, delisting, new stocks, non-mainboard markets, high deviation, nearby pressure, low liquidity, weak market temperature, and one-word unreachable boards are hard blockers.
- Paper trading lives in `infrastructure/paper_store.py` under `.firemoney/paper_trades.json`. Same-day stop loss breaches create warning events only; T+1 sell events are allowed only after the position rolls to the next day.
- Feishu notification lives in `infrastructure/feishu_notifier.py` and reads only `FEISHU_ENABLED`, `FEISHU_WEBHOOK_URL`, and optional `FEISHU_WEBHOOK_SECRET`. Notification failures return structured results and do not stop strategy execution.
- Local entry modes are exposed by `client.desktop.firemoney_client.one_to_two_cli`: `morning`, `watch`, `eod`, and `backtest`.

## 6. Configuration Entry Points

- `domain/messages/zh_CN.json` owns domain-facing business messages, review notes, blocker labels, receipt defaults, and strategy adjustment reasons.
- `infrastructure/config/sample_trading_data.zh_CN.json` owns deterministic local market, opportunity, price, and default strategy data for the first runnable slice.
- `infrastructure/config/one_to_two_strategy.zh_CN.json` owns one-to-two product defaults, exclusion rules, position/risk limits, and notification environment variable names.
- Domain and infrastructure modules should load these files through project-owned loaders, then return structured contracts to the client.
- New user-visible business text should enter the domain message catalog first whenever practical; code should keep policies and state transitions, not locale text.
