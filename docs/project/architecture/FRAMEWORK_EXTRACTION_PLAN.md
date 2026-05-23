# FireMoney Framework Extraction Plan

## Goal

FireMoney keeps the trading business focused on buy points, sell points,
paper-trading decisions, and drawdown control. Reusable engineering primitives
belong in the product-agnostic `framework/` package so future projects can reuse
them without importing FireMoney strategy code.

## Layer Boundary

```text
client/desktop
  UI rendering, CLI intent capture, local adapter calls

shared/contracts
  Stable DTO/protocol language between client, server, and future HTTP/RPC adapters

server/firemoney_server/application
  FireMoney use cases: strategy decision, paper-trading command sheet, review flow

server/firemoney_server/domain
  FireMoney trading rules: scoring, blockers, buy/sell discipline, risk policy

server/firemoney_server/infrastructure
  FireMoney adapters: AkShare, A-share calendar, Feishu, project stores/config

framework
  Product-agnostic config, storage, scheduler, notification, and HTTP/RPC primitives
```

## Current First Slice

- `framework/storage` owns tolerant JSON file reads, append-only record stores,
  and string-set stores.
- `framework/scheduler` owns generic completed-task persistence.
- FireMoney notification and scheduler stores keep their existing class names and
  paths, but delegate generic persistence to `framework`.
- FireMoney notification delivery rules now live in
  `server/firemoney_server/application/notification_orchestrator.py`, which
  keeps Feishu low-noise policy separate from trading decisions and Feishu
  adapter details.
- Daily operating-line selection now lives in
  `server/firemoney_server/application/strategy_decision_service.py`, so strategy
  module choice is separated from paper-trading ledger mutation.
- Paper-trading command-sheet orchestration now lives in
  `server/firemoney_server/application/paper_decision_service.py`, so daily
  paper decisions are separated from the main workflow entrypoint.
- End-of-day review orchestration now lives in
  `server/firemoney_server/application/end_of_day_review_service.py`, so review
  statistics and eod notification previews are separated from ledger loading and
  scheduler entrypoints.
- Stability review calculation now lives in
  `server/firemoney_server/application/stability_review_service.py`, so closed
  sample quality, 30/50/100-stage guidance, and boundary suggestions are
  reusable by both `stability` and end-of-day review.
- The framework package must not import `server.firemoney_server`,
  `client.desktop`, or `shared.contracts`.

## Next Refactor Targets

- Continue shrinking `MainChainService` into application services for paper
  trading ledger execution and backtest review.
- Split `renderer.py` into section renderers while preserving
  `render_one_to_two_workflow_html()` as the single public entry.
- Split `one_to_two_cli.py` into command parsing, command handlers, and formatters.
- Add a `MainChainGateway` protocol so local and future HTTP/RPC adapters share
  the same UI-facing contract.
