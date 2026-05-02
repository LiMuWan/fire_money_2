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
- completed exits are stored as `PaperTradeRecord` samples with entry, exit, P/L, holding days, exit reason, position label, and warning count

### `FeishuNotificationResult`

Describes notification outcome without making notification delivery a blocker for strategy execution.

Key fields:

- `status`
- `title`
- `message`
- `webhook_configured`
- `error`

### `OneToTwoMorningReport`

Describes the 08:50 one-to-two report: trading-day context, market temperature, yesterday first-board candidates, paper-account state, notification result, and next action.

### `OneToTwoEndOfDayReview`

Describes the 15:10 one-to-two review: trading-day context, closed sample count, warning count, realized P/L observation, focus points, paper-account state, notification result, and next action.

### `OneToTwoStabilityReport`

Describes the strategy stability observation. Fewer than 30 samples must remain `observation` and must not automatically produce strategy-boundary conclusions.

### `OneToTwoScheduleRun`, `OneToTwoScheduleTask`

Describe one local scheduler tick for the one-to-two loop.

Rules represented by the contracts:

- scheduler output is still part of the one-to-two product line, not a generic job dashboard
- due tasks are visible with `completed`, `skipped`, `pending`, `failed`, or `closed` status
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
- One-to-two candidates, risk notes, stop loss, paper-trading state, and Feishu notification results are shared contracts; clients must not recompute them from raw AkShare fields.
- Stability reports must use closed `PaperTradeRecord` samples. Samples below 30 remain observation-only.
- Backtest output reuses `OneToTwoStabilityReport`; it does not introduce a separate product surface or write live paper-account state.
- AkShare and Feishu details stay behind infrastructure adapters. Shared contracts use project-owned field names only.
- One-to-two paper trading is simulation only; these contracts do not represent real account orders or unattended live trading.
