# FireMoney Server Architecture

## 1. Goal

The server/business layer owns deterministic one-to-two policy, state transitions, and external adaptation. It is the authority for scoring, blockers, paper-trading events, notification results, and review output.

## 2. Current Skeleton

```text
server/firemoney_server/
  application/
    main_chain.py          one-to-two workflow orchestration and daily strategy decision
    beta_readiness_service.py beta-check readiness gate and Feishu test orchestration
    board_shadow_execution_service.py board-shadow candidate adaptation for the daily mainline path
    board_shadow_review_service.py board-shadow evidence report and shadow sample orchestration
    doctor_review_service.py local runtime readiness checks for beta/watch startup
    end_of_day_review_service.py 15:10 review orchestration and eod notification preview
    execution_quality_service.py intraday minute/Tick execution-quality evidence
    historical_replay_service.py isolated historical replay, backtest, and data-quality audit
    mainline_continuity_service.py live mainline breadth/news continuity enrichment
    morning_report_service.py morning candidate report and low-noise notification orchestration
    notification_orchestrator.py low-noise delivery rules and notification audit orchestration
    one_to_two_scheduler.py local due-job scheduler for the one-to-two loop
    one_to_two_notification_text.py morning/watch/eod/shadow notification message copy helpers
    paper_backtest_service.py yearly/monthly paper-backtest evidence and friction checks
    paper_decision_service.py read-only paper-trading command-sheet orchestration
    paper_decision_text.py paper-trading command-sheet discipline and message copy helpers
    paper_instruction_builder.py paper buy/holding instruction DTO and wording builder
    paper_runtime_service.py paper-account view, guard DTO, and replay candidate adapters
    paper_entry_policy.py  paper-trading buy eligibility, entry quality, and guard sizing
    paper_exit_policy.py   paper-trading sell discipline and main-rise protection policy
    paper_trading_guard.py paper-trading entry guard and position-size policy
    stability_review_service.py closed-trade stability metrics and boundary suggestions
    strategy_decision_service.py daily operating-line selector from audited evidence snapshots
    watch_phase_service.py scan/auction/open/risk phase state transitions for paper events
    watch_report_service.py watch report, delivery eligibility, and notification recording wrapper
  domain/
    one_to_two.py          mainboard 10cm one-to-two scoring and blocker policy
    one_to_two_types.py    normalized market rows, price bars, tick snapshots, and settings protocol
    paper_position_sizing.py A-share lot sizing and small-account paper position policy
  infrastructure/
    feishu_notifier.py     Feishu webhook/app robot adapter
    local_env.py           ignored local Feishu secret loader
    market_data.py         MarketDataProvider boundary and AkShare adapter
    notification_store.py  local notification result records
    one_to_two_config.py   one-to-two strategy config loader
    paper_database.py      SQLite mirror for paper-trading events, positions, and P/L
    paper_database_schema.py SQLite schema/migration and notes codecs for the paper mirror
    paper_store.py         local event-driven paper-trading account
    paper_store_codec.py   JSON contract codec for the local paper account
    sample_market_data.py  deterministic sample provider for tests and preview
    scheduler_run_store.py local scheduler run audit records
    scheduler_state.py     completed local scheduler task state
    trading_calendar.py    trading-day context and T+1 date resolution
    config/
      one_to_two_strategy.zh_CN.json
```

## 3. Layer Rules

- `framework/` owns reusable config, storage, scheduler, notification, and future HTTP/RPC primitives. It must not import FireMoney strategy, client, or shared trading contracts.
- `application` orchestrates use cases and does not own UI concerns.
- `main_chain.py` is the composition entry point. Daily strategy selection, morning reports, beta readiness, board-shadow-to-mainline candidate adaptation, paper runtime adapters, paper command sheets and instruction building, paper-backtest evidence, historical replay/backtest audit, intraday execution-quality evidence, watch report wrapping, watch phase effects, doctor checks, end-of-day review, stability review, and board-shadow evidence reports each live in their own application service.
- `domain` owns scoring, blockers, position structure, stop-loss rules, and status decisions. Pure input types and the settings protocol live in `domain/one_to_two_types.py` so market-data adapters can depend on DTO shapes without importing the scoring policy.
- `infrastructure` owns data sources, files, webhook adapters, caches, and config loading.
- `shared/contracts` is the stable public language for the client.
- Intraday minute bars and tick/order-book snapshots should enter through the same `MarketDataProvider` boundary instead of leaking new vendor APIs into the domain or client.
- Real broker execution adapters, including QMT/MiniQMT, do not belong in the server strategy layer. The server emits paper-trading command sheets and shared broker-order DTOs only; local client infrastructure owns vendor SDK imports, account connectivity, dry-run order planning, and any explicitly armed live submission.

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
- Default paper capital is 10000. The runtime uses small-account A-share lot sizing: buys must be at least one 100-share lot, normal target exposure is 18%, reduced target exposure is 12%, the single-symbol hard cap is 35%, and reduced-mode hard cap is 20%. If one lot is too expensive for the cap, the system must stand aside instead of inventing a fractional position.
- Market data enters through `MarketDataProvider`; AkShare fields are normalized into project-owned DTOs before domain scoring.
- Normalized market rows, historical bars, intraday bars, and tick snapshots are defined in `domain/one_to_two_types.py`; infrastructure must import these types from the type module, not from the scoring policy module.
- `infrastructure/market_data.py` contains the real AkShare adapter and shared provider protocol; deterministic preview/test data lives in `infrastructure/sample_market_data.py` and is re-exported for backward-compatible imports.
- AkShare raw snapshots are cached under `.firemoney/market_data/`.
- If market data is unavailable, the service returns a blocked morning report and no paper buy can be generated.
- Hard blockers include ST, delisting, new stock, non-mainboard markets, high deviation, nearby pressure, low liquidity, weak market temperature, weak volume-ratio continuity, RSI over-cold/over-hot setups, low 60-day position percentile, generic mid-position setups, weak effective-turnover leader quality, over-wide executable candidate pools, open confirmation above 3.5%, and one-word unreachable boards.
- The domain now exposes `turnover_quality_score`, `turnover_quality_label`, and `turnover_quality_notes` on `OneToTwoCandidate`. This is the daily-proxy buy-point gate for 换手龙: effective turnover range, sealed amount / turnover amount, first limit-up time, auction amount ratio, market temperature, volume ratio, RSI, and position structure must align before a candidate can become an executable paper buy. It intentionally does not use future bars; tick/order-book data can only upgrade this proxy later.
- The domain exposes volume ratio, RSI(14), 60-day position percentile, and a capital-style proxy on `OneToTwoPositionProfile`; the capital style is a turnover proxy only and must not be presented as real hot-money/institution seat attribution until PIT seat or fund-flow data is integrated.
- Low breakout setups must pass a market-width gate before paper buying: yesterday's mainboard first-board count must reach the configured floor and the same-morning executable candidate pool must have at least the configured count. If the executable pool exceeds the configured ceiling, the day is treated as too scattered and stays blocked for observation.
- Same-day stop loss breaches create warning events only; T+1 sell events are allowed only after the position rolls to the next day.
- Before a paper buy is emitted, the application layer records the entry risk budget on `PaperTradingInstruction`: planned stop-risk percentage, first-target return percentage, planned reward/risk ratio, and maximum intratrade drawdown budget. Candidates must have planned reward greater than planned risk and pass the configured turnover-leader quality floor before they can enter the command sheet, and the same planned fields are persisted onto `PaperPosition`, `PaperTradeRecord`, and the SQLite mirror for plan-vs-actual review.
- Paper entries are filtered by `application/paper_entry_policy.py`; it owns positive-expectancy candidate eligibility, planned entry quality, reward/risk calculation, and guard-driven position reduction without writing ledgers, sending Feishu, or loading market data.
- Paper position quantity is resolved by `domain/paper_position_sizing.py` and reused by read-only command sheets, `watch/open` ledger writes, and small-account backtest summaries. This prevents the UI from showing a buy that the ledger cannot execute under one-lot rules.
- Sell discipline uses 4%/structure stop, 12% first take profit, and 2% trailing protection after a 10% strong move is reached.
- Positive-profit locking is quality-gated: after T+1, the position must clear the higher of the configured base profit line and the intratrade adverse-move line (`max_adverse_pct * positive_lock_min_profit_drawdown_ratio`) before `positive_profit_lock` is recorded.
- Paper exits are decided by `application/paper_exit_policy.py`; it returns sell reasons and event types without writing the paper ledger, sending Feishu, or reading market data. `MainChainService` applies the returned decision through `PaperTradeStore`.
- Positions that have lasted at least `max_holding_trade_days` and still have not reached `discipline_exit_min_gain_pct` are closed through a discipline exit during `risk`.
- Trading dates are resolved before market data and paper trading. Closed dates use the previous A-share trading day so weekends and holidays do not generate false scans.
- `watch` supports `scan`, `auction`, `open`, and `risk` phases. Only the `open` phase can create a paper buy; `risk` handles stop-warning and T+1 sell events.
- Watch phase state transitions live in `application/watch_phase_service.py`; it owns scan/auction/open/risk event effects, but does not format Feishu text, decide delivery eligibility, or read/write notification stores.
- `watch/open` must route from the same morning candidate snapshot and market temperature it is about to execute. It must not re-fetch market rows just to decide strategy routing, otherwise the 09:00 command sheet and 09:31 execution can silently diverge when data sources move between calls.
- Morning-report orchestration lives in `application/morning_report_service.py`; it resolves the trading date, prepares the account view, loads market rows, adapts mainline candidates, and prepares/records only the morning notification boundary.
- Watch report wrapping lives in `application/watch_report_service.py`; it delegates state changes to `WatchPhaseService`, asks `notification_orchestrator` whether the event is action-worthy, and records only eligible watch buy/sell notifications.
- Mainline continuity enrichment lives in `application/mainline_continuity_service.py`; it uses live breadth/news evidence to enrich candidates for watch decisions, without writing paper positions or sending notifications.
- Completed exits create `PaperTradeRecord` samples. Stability metrics use these closed trade records, not raw event counts.
- The paper-trading guard treats consecutive low-quality closes as a hard stop: if recent closed trades fail to cover intratrade drawdown for the configured streak, new paper entries are blocked even when the final P/L was slightly positive.
- Stability review also reports position-label distribution, exit-reason distribution, and capped recent closed samples so strategy quality can be judged by sample composition, not only headline win rate.
- Stability review exposes 30/50/100 sample stages and service-owned boundary suggestions; below 30 samples remain observation-only.
- Stability review calculation lives in `application/stability_review_service.py`; it consumes a prepared `PaperAccount`, does not read/write ledgers, and is reused by both `stability` and end-of-day review.
- End-of-day review uses closed trade records for sample count, success count, realized P/L, drawdown, stability stage, next sample milestone, and boundary suggestion; a T+1 sell event is not counted as success unless the closed sample is profitable.
- End-of-day review orchestration lives in `application/end_of_day_review_service.py`; `MainChainService` resolves the trade date and paper account, then delegates review statistics, eod notification preview, and notification audit recording to the review service.
- Runtime readiness checks live in `application/doctor_review_service.py`; `MainChainService.build_one_to_two_doctor_report()` only resolves the trade date and delegates. The doctor service checks strategy config, trading-day readiness, market data, local state storage, Feishu environment, scheduler readiness, and scheduler audit storage without sending notifications or creating paper trades.
- Intraday execution-quality checks live in `application/execution_quality_service.py`; it consumes the `MarketDataProvider` minute/Tick boundary and returns a read-only `OneToTwoExecutionQualityReport` without touching paper positions, notifications, or scheduler state.
- Historical replay and backtest-audit orchestration live in `application/historical_replay_service.py`; it receives an isolated temporary paper-store factory and never mutates the live `.firemoney/paper_trades.json`.
- Feishu reads only notification environment variables. Webhook mode uses `FEISHU_ENABLED`, `FEISHU_WEBHOOK_URL`, and optional `FEISHU_WEBHOOK_SECRET`; app robot mode uses `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_RECEIVE_ID`, and `FEISHU_RECEIVE_ID_TYPE`.
- `.firemoney/feishu.env` is an ignored local secret file and is loaded by the CLI without overriding process environment variables.
- Application workflows format one-to-two notification content before calling Feishu. Feishu delivery is intentionally low-noise: morning messages include candidates, blockers, stop loss, and position cap; watch messages are sent only when a real paper buy or real paper sell event is written; end-of-day messages include events, warnings, closed samples, latest sample summary, stability stage, next sample milestone, and service-owned boundary suggestion. Scan, auction, ordinary risk checks, board-shadow records, and `paper-decision` command sheets stay local unless they produce an actual paper buy/sell event.
- Feishu delivery prefers an interactive message card built from `application/notification_rich_text.py` and shared semantic highlighting rules; webhook/app delivery retries transient DNS/connection/timeout errors before reporting failure, and webhook card delivery automatically falls back to the original text payload if card delivery is rejected. Stored notification records keep the plain text message for auditability.
- Notification delivery rules live in `application/notification_orchestrator.py`; it owns notify-or-prepare, notification audit records, watch-phase send eligibility, and the `--action-only` stream boundary. It must not score candidates, mutate paper positions, or know Feishu webhook details.
- Morning/watch/end-of-day/board-shadow message bodies live in `application/one_to_two_notification_text.py`; this module is presentation copy only and must not import storage, Feishu, market data, or `MainChainService`.
- Board-shadow remains a review and evidence layer, not a second daily operating line. Its report, system evidence summary, and shadow sample recording live in `application/board_shadow_review_service.py`; default paper trading still routes only through the main board-shadow-system operating line or cash.
- Board-shadow execution adaptation lives in `application/board_shadow_execution_service.py`; it converts validated board-shadow evidence and live market rows into `OneToTwoCandidate` command-sheet candidates, including the 50-800 亿市值带、候选池过散闸门、继承硬拦截、换手质量降级和主线 exit plan.
- Paper-backtest evidence lives in `application/paper_backtest_service.py`; it owns yearly/monthly validation, friction scenarios, return-target checks, efficiency challengers, and data-coverage notes. `MainChainService.build_paper_backtest_report()` only delegates, so the live paper ledger and daily watch flow stay separate from historical validation.
- Notification results are appended to `.firemoney/notifications.json` for review. Internal workflow reuse must not duplicate records, so `watch` suppresses its internal morning-report record.
- Notification failures return structured results and do not stop strategy execution.
- Local entry modes are exposed by `client.desktop.firemoney_client.one_to_two_cli`: `morning`, `watch`, `eod`, `backtest`, `stability`, `doctor`, `beta-check`, `beta-start`, `feishu-test`, `schedule`, `notifications`, `scheduler-runs`, `strategy-decision`, `paper-decision`, `qmt-check`, and `qmt-plan`.
- `stability` reads the current `.firemoney/paper_trades.json` closed samples and returns `OneToTwoStabilityReport` without mutating live state.
- `doctor` returns one-to-two runtime readiness checks and treats missing market data as `blocked`; in strict Beta mode, disabled or unverified Feishu is also `blocked` because morning/eod delivery is part of the value-watch contract. Non-Beta diagnostics may still treat notification configuration as a softer local warning.
- Current AkShare integration covers daily bars and news. Minute bars / Tick / queue-quality validation are the next data-layer upgrade required before claiming stable pre-main-rise entries.
- `notifications` reads recent `.firemoney/notifications.json` records with optional workflow/status/limit filters, so Feishu delivery can be audited without opening the preview page. Use `--action-only` to show the low-noise action stream: morning review, real paper buy, real paper sell, and end-of-day review.
- `feishu-test` sends or prepares a non-trading connectivity message and records it as `feishu:test`; it must not create paper-trading events.
- `beta-start` runs strict Beta doctor gates before scheduler execution. If readiness is not `ready`, it prints the doctor report and does not mutate scheduler state or paper-trading events.
- Beta readiness orchestration lives in `application/beta_readiness_service.py`; it decides when beta-check may send the Feishu connectivity test and returns explicit skip reasons for non-trading days, preflight blockers, or Feishu shape failures.
- `strategy-decision` is a lightweight read-only daily selector. It reads the validated evidence snapshot, chooses the main operating line, keeps the research side line in watch-only status, and must not recompute the heavy board-shadow backtest during scheduler ticks.
- Daily strategy selection lives in `application/strategy_decision_service.py`; it turns `exports/strategy_decision_snapshot.json` or the built-in audited fallback into a `StrategyDecisionReport`. `MainChainService` delegates to it so future strategy modules can be swapped without touching paper-trading state transitions.
- `paper-decision` is the read-only paper-trading command sheet. It consumes the daily strategy decision, morning candidates, and paper account state, then emits at most one simulated buy plan with entry, stop, take-profit, cancellation, and sell rules. It stays local and must not mutate `.firemoney/paper_trades.json`; only `watch --phase open` writes a paper buy and triggers a buy notification.
- `qmt-check` and `qmt-plan` are client-side bridge commands. They must consume service-owned reports instead of recomputing buy/sell decisions, and they must keep QMT SDK access behind a local adapter so Tencent Cloud preview and server workflows never depend on a logged-in Windows trading terminal.
- Paper-decision orchestration lives in `application/paper_decision_service.py`; it builds the command-sheet report and notification preview from prepared candidates/account state while delegating ledger mutation to watch/open and watch/risk.
- Paper-decision discipline wording and command-sheet message body live in `application/paper_decision_text.py`; it is presentation copy only and must not import storage, Feishu, market data, or `MainChainService`.
- Paper buy and holding instruction DTO construction lives in `application/paper_instruction_builder.py`; it depends on entry/exit policies and settings, but does not read/write ledgers, send notifications, or decide whether watch may write events.
- Paper runtime adapters live in `application/paper_runtime_service.py`; they own cross-day account views, guard-result contract conversion, replay-position candidate conversion, and shared paper percentage formatting so `MainChainService` does not hand-build trading DTOs.
- Existing-position command sheets classify strong positions into a main-rise runner mode when entry quality, opening score, and mainline continuity are all high. Runner positions skip the ordinary 3% lock and instead show the dynamic trailing/profit-floor sell points.
- The paper-trading guard receives the current candidate's turnover quality score. It can reduce or block the entry when closed trades from the same quality bucket have weak win rate, weak average return, or consecutive profit/drawdown quality failures.
- `paper-db` reads the SQLite mirror of the paper ledger and reports account equity, cash, open positions, recent events, closed trades, realized P/L, win rate, average trade return, monthly/yearly realized return summaries, the entry turnover-dragon quality, the entry guard decision attached to open/closed trades, quality-bucket performance, and guard-action performance for later buy-rule or position-size downgrades.
- `PaperTradeStore.save()` keeps JSON and SQLite in sync, so all existing paper buy/sell/risk paths persist operating data without duplicating trading rules.
- Paper JSON serialization lives in `infrastructure/paper_store_codec.py`; `paper_store.py` owns event-driven account state transitions, not contract parsing minutiae.
- Paper SQLite schema and additive migrations live in `infrastructure/paper_database_schema.py`; `paper_database.py` owns sync/report queries and must not grow migration boilerplate inline again.
- `schedule` runs only one-to-two jobs that are due and still inside their execution window. Missed windows are marked `expired` and are not backfilled, so a late afternoon scheduler start cannot create stale open-phase paper buys.
- Completed, skipped, and expired task keys are recorded in `.firemoney/scheduler_state.json` so loop mode does not duplicate same-day notifications or paper-trading events. Required morning/eod notifications are not marked completed when Feishu delivery fails, allowing the scheduler to retry while the execution window is still open.
- Each scheduler tick is appended to `.firemoney/scheduler_runs.json`; `scheduler-runs` reads run records so Beta watch coverage can be audited separately from Feishu delivery. Important execution evidence (`completed` / `failed` / `expired` / retrying tasks, or any run that executed due work) is retained longer than ordinary observed loop ticks, so month-level missed-opportunity reviews are not drowned out by minute-by-minute idle records.
