# FireMoney Shared Contracts V1

## 1. Purpose

Shared contracts define the stable language between the client and the one-to-two service layer.

V1 covers only:

```text
morning scan -> candidate scoring -> paper trading event -> end-of-day review -> stability observation
```

Code entry point:

- `shared/contracts/trading.py`

## 2. Core Contracts

### `TradingDayContext`

Describes how the requested date maps to an A-share trading day.

Key fields:

- `requested_date`
- `trade_date`
- `previous_trade_date`
- `next_trade_date`
- `is_trading_day`
- `note`

### `OneToTwoCandidate`

Describes one mainboard 10cm one-to-two candidate and answers: why can this be observed, bought in the paper account, or blocked?

Key fields:

- `symbol`
- `name`
- `score`
- `status`
- `latest_price`
- `entry_price`
- `stop_loss`
- `position_limit_pct`
- `first_board_score`
- `auction_score`
- `position_score`
- `theme_score`
- `liquidity_score`
- `position_profile`
- `blockers`
- `warnings`
- `rationale`
- `next_action`

### `OneToTwoPositionProfile`

Describes the candidate's location and pressure structure.

Key fields:

- `label`
- `low_position_score`
- `breakout_score`
- `pressure_score`
- `moving_average_score`
- `volume_score`
- `summary`
- `risk_notes`

### `PaperAccount`, `PaperPosition`, `PaperTradeEvent`, `PaperTradeRecord`

Describe the local event-driven simulation account.

Rules represented by the contracts:

- initial cash and daily trade limits are visible on `PaperAccount`
- same-day positions carry `can_sell_today=False`
- same-day stop loss breaches are warning events, not sell events
- T+1 exits are represented by `OneToTwoEventType.T1_SELL`
- weak positions that exceed the configured holding window are represented by `OneToTwoEventType.DISCIPLINE_EXIT`
- completed exits are stored as `PaperTradeRecord` samples with entry, exit, P/L, holding days, exit reason, position label, and warning count

### `FeishuNotificationResult`

Describes notification outcome without making notification delivery a blocker for strategy execution.

Key fields:

- `status`
- `title`
- `message`
- `webhook_configured`
- `error`

### `NotificationRecord`

Describes a persisted notification outcome for review and troubleshooting.

Key fields:

- `channel`
- `workflow`
- `trade_date`
- `status`
- `title`
- `message`
- `created_at`
- `error`

### `OneToTwoMorningReport`

Describes the 08:50 one-to-two report: trading-day context, market temperature, yesterday first-board candidates, paper-account state, notification result, and next action.

### `OneToTwoEndOfDayReview`

Describes the 15:10 one-to-two review: trading-day context, closed sample count, warning count, realized P/L observation, stability stage, next sample milestone, service-owned boundary suggestion, focus points, paper-account state, notification result, and next action.

Rules represented by the contract:

- `sample_count`, `success_count`, `realized_pnl`, and `max_drawdown` are calculated from closed `PaperTradeRecord` samples.
- A sell event is not automatically a success; `success_count` only counts closed samples with positive realized P/L.
- `stability_stage`, `next_milestone`, and `strategy_boundary_suggestion` use the same service calculation as `OneToTwoStabilityReport`, so the client and Feishu tail review do not infer their own strategy conclusion.

### `OneToTwoStabilityReport`

Describes the strategy stability observation. Fewer than 30 samples must remain `observation` and must not automatically produce strategy-boundary conclusions.

Key fields include sample count, sample stage, next milestone, success rate, average return, max drawdown, stop-warning rate, low-breakout success rate, position-label distribution, exit-reason distribution, recent closed samples, and strategy-boundary suggestion.

Rules represented by the contract:

- fewer than 30 samples remain observation-only
- 30 samples produce first-review guidance
- 50 samples produce second-review guidance
- 100 samples can enter boundary-setting review
- `recent_samples` exposes the newest closed `PaperTradeRecord` summaries for review, capped by the service so the client does not become a report-export surface
- clients display the service-owned `strategy_boundary_suggestion` and must not infer their own boundary decision

### `OneToTwoDoctorReport`, `OneToTwoDoctorCheck`

Describe runtime readiness for the one-to-two loop before the user starts morning, watch, schedule, or backtest work.

Rules represented by the contracts:

- doctor checks do not send notifications, create paper trades, or mutate scheduler state
- market-data failure is `blocked` because simulated buys must not be generated without trusted rows
- disabled or missing Feishu setup is `warning`, not `blocked`, because notification delivery must not stop strategy observation
- each check includes a human-readable `detail` and `next_action`

### `OneToTwoScheduleRun`, `OneToTwoScheduleTask`

Describe one local scheduler tick for the one-to-two loop.

Rules represented by the contracts:

- scheduler output is still part of the one-to-two product line, not a generic job dashboard
- due tasks are visible with `completed`, `skipped`, `pending`, `expired`, `failed`, or `closed` status
- expired tasks are missed execution windows and must not be backfilled into simulated buys or stale risk checks
- repeated loop ticks can show skipped work without re-triggering paper-trading events
- non-trading requested dates are `closed` and do not generate market scans or simulated trades

## 3. State Enums

- `OneToTwoEventType`: one-to-two morning scan, candidate selected, auction confirmed, paper buy, stop warning, T+1 sell, end-of-day review, and blocked events.
- `NotificationStatus`: disabled, prepared, sent, failed.
- `PaperTradeStatus`: empty, holding, warning, closed.

## 4. Rules

- New cross-layer fields must be added to the shared contract and this document first.
- The client must not infer trusted business outcomes from private fields.
- The service layer must return enough `summary`, `next_action`, `status`, or equivalent fields to support UI display.
- One-to-two candidates, risk notes, stop loss, paper-trading state, Feishu notification results, and notification records are shared contracts; clients must not recompute them from raw AkShare fields.
- Stability reports must use closed `PaperTradeRecord` samples. Samples below 30 remain observation-only.
- Backtest output reuses `OneToTwoStabilityReport`; it does not introduce a separate product surface or write live paper-account state.
- Stability stages and boundary suggestions are calculated by the service layer at 30/50/100 sample gates.
- Doctor output reuses shared one-to-two runtime checks; clients display it but must not use it to infer hidden infrastructure details.
- AkShare and Feishu details stay behind infrastructure adapters. Shared contracts use project-owned field names only.
- One-to-two paper trading is simulation only; these contracts do not represent real account orders or unattended live trading.
