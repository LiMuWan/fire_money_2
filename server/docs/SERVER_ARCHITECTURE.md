# FireMoney Server Architecture

## 1. Goal

The server/business layer owns deterministic one-to-two policy, state transitions, and external adaptation. It is the authority for scoring, blockers, paper-trading events, notification results, and review output.

## 2. Current Skeleton

```text
server/firemoney_server/
  application/
    main_chain.py          one-to-two workflow orchestration
    one_to_two_scheduler.py local due-job scheduler for the one-to-two loop
  domain/
    one_to_two.py          mainboard 10cm one-to-two scoring and blocker policy
  infrastructure/
    feishu_notifier.py     Feishu webhook/app robot adapter
    local_env.py           ignored local Feishu secret loader
    market_data.py         MarketDataProvider boundary and AkShare adapter
    notification_store.py  local notification result records
    one_to_two_config.py   one-to-two strategy config loader
    paper_store.py         local event-driven paper-trading account
    scheduler_run_store.py local scheduler run audit records
    scheduler_state.py     completed local scheduler task state
    trading_calendar.py    trading-day context and T+1 date resolution
    config/
      one_to_two_strategy.zh_CN.json
```

## 3. Layer Rules

- `application` orchestrates use cases and does not own UI concerns.
- `domain` owns scoring, blockers, position structure, stop-loss rules, and status decisions.
- `infrastructure` owns data sources, files, webhook adapters, caches, and config loading.
- `shared/contracts` is the stable public language for the client.

## 4. Product Chain

```text
MarketDataProvider/AkShare
-> one-to-two candidate scoring
-> trading-day resolution
-> local due-job scheduler
-> event-driven paper account
-> closed trade records
-> Feishu notification result
-> end-of-day review
-> stability observation
```

## 5. Rules

- One-to-two strategy settings are loaded from `infrastructure/config/one_to_two_strategy.zh_CN.json`.
- Default capital is 100000, single position cap is 8%, and daily paper buys are capped at 1.
- Market data enters through `MarketDataProvider`; AkShare fields are normalized into project-owned DTOs before domain scoring.
- AkShare raw snapshots are cached under `.firemoney/market_data/`.
- If market data is unavailable, the service returns a blocked morning report and no paper buy can be generated.
- Hard blockers include ST, delisting, new stock, non-mainboard markets, high deviation, nearby pressure, low liquidity, weak market temperature, open confirmation above 4.5%, and one-word unreachable boards.
- Low breakout setups must pass a market-width gate before paper buying: yesterday's mainboard first-board count must reach the configured floor and the same-morning executable candidate pool must have at least the configured count. Otherwise the setup stays blocked for observation.
- Same-day stop loss breaches create warning events only; T+1 sell events are allowed only after the position rolls to the next day.
- Sell discipline uses 4.25%/structure stop, 16% first take profit, and 0.10% trailing protection after an 8.25% strong move is reached.
- Positions that have lasted at least `max_holding_trade_days` and still have not reached `discipline_exit_min_gain_pct` are closed through a discipline exit during `risk`.
- Trading dates are resolved before market data and paper trading. Closed dates use the previous A-share trading day so weekends and holidays do not generate false scans.
- `watch` supports `scan`, `auction`, `open`, and `risk` phases. Only the `open` phase can create a paper buy; `risk` handles stop-warning and T+1 sell events.
- Completed exits create `PaperTradeRecord` samples. Stability metrics use these closed trade records, not raw event counts.
- Stability review also reports position-label distribution, exit-reason distribution, and capped recent closed samples so strategy quality can be judged by sample composition, not only headline win rate.
- Stability review exposes 30/50/100 sample stages and service-owned boundary suggestions; below 30 samples remain observation-only.
- End-of-day review uses closed trade records for sample count, success count, realized P/L, drawdown, stability stage, next sample milestone, and boundary suggestion; a T+1 sell event is not counted as success unless the closed sample is profitable.
- `build_one_to_two_doctor_report()` checks strategy config, trading-day readiness, market data, local state storage, Feishu environment, scheduler readiness, and scheduler audit storage without sending notifications or creating paper trades.
- `run_one_to_two_backtest()` replays historical dates into an isolated temporary paper ledger, then returns a stability report without mutating the live `.firemoney/paper_trades.json`.
- Feishu reads only notification environment variables. Webhook mode uses `FEISHU_ENABLED`, `FEISHU_WEBHOOK_URL`, and optional `FEISHU_WEBHOOK_SECRET`; app robot mode uses `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_RECEIVE_ID`, and `FEISHU_RECEIVE_ID_TYPE`.
- `.firemoney/feishu.env` is an ignored local secret file and is loaded by the CLI without overriding process environment variables.
- Application workflows format one-to-two notification content before calling Feishu: morning messages include candidates, blockers, stop loss, and position cap; watch messages include event, position, stop loss, T+1 status, the next-day handling plan for same-day stop warnings, completed sell/discipline-exit sample summaries, and simulation-only warning; end-of-day messages include events, warnings, closed samples, latest sample summary, stability stage, next sample milestone, and service-owned boundary suggestion.
- Notification results are appended to `.firemoney/notifications.json` for review. Internal workflow reuse must not duplicate records, so `watch` suppresses its internal morning-report record.
- Notification failures return structured results and do not stop strategy execution.
- Local entry modes are exposed by `client.desktop.firemoney_client.one_to_two_cli`: `morning`, `watch`, `eod`, `backtest`, `stability`, `doctor`, `beta-check`, `beta-start`, `feishu-test`, `schedule`, `notifications`, and `scheduler-runs`.
- `stability` reads the current `.firemoney/paper_trades.json` closed samples and returns `OneToTwoStabilityReport` without mutating live state.
- `doctor` returns one-to-two runtime readiness checks and treats missing market data as `blocked`; disabled Feishu is only a `warning` because notifications must not block simulation.
- `notifications` reads recent `.firemoney/notifications.json` records with optional workflow/status/limit filters, so Feishu delivery can be audited without opening the preview page.
- `feishu-test` sends or prepares a non-trading connectivity message and records it as `feishu:test`; it must not create paper-trading events.
- `beta-start` runs strict Beta doctor gates before scheduler execution. If readiness is not `ready`, it prints the doctor report and does not mutate scheduler state or paper-trading events.
- `schedule` runs only one-to-two jobs that are due and still inside their execution window. Missed windows are marked `expired` and are not backfilled, so a late afternoon scheduler start cannot create stale open-phase paper buys.
- Completed, skipped, and expired task keys are recorded in `.firemoney/scheduler_state.json` so loop mode does not duplicate same-day notifications or paper-trading events.
- Each scheduler tick is appended to `.firemoney/scheduler_runs.json`; `scheduler-runs` reads recent run records so Beta watch coverage can be audited separately from Feishu delivery.
