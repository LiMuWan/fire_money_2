# FireMoney Shared Contracts V1

## 1. Purpose

Shared contracts define the stable language between the client and the service layer.
V1 covers the first smoke path:

```text
market overview -> signal scan -> opportunity pool -> risk review -> order draft -> execution receipt -> recap
```

Code entry point:

- `shared/contracts/trading.py`

## 2. Core Contracts

### `MarketContext`

Describes the current market state and answers: "Is there an opportunity now, what is the risk, and what should we look at next?"

Key fields:

- `trade_date`
- `market_temperature`
- `trend`
- `risk_level`
- `summary`
- `next_action`

### `SignalScanReport`

Describes the signal scan result and answers: "What did the scan find, who is in front, and what should we inspect next?"

The first domain policy filters candidates by strategy score, confidence, and liquidity before exposing `focus_opportunities` to the execution line.

Key fields:

- `report_id`
- `stage`
- `universe_size`
- `candidate_count`
- `ranked_opportunities`
- `focus_opportunities`
- `focus_opportunity`
- `summary`
- `watch_notes`
- `next_action`

### `Opportunity`

Describes a candidate opportunity and answers: "Why is this one worth looking at?"

Key fields:

- `symbol`
- `name`
- `score`
- `confidence`
- `strategy_tags`
- `entry_price`
- `stop_loss`
- `target_price`
- `risk_flags`
- `rationale`

### `RiskReview`

Describes the pre-execution review outcome and answers: "Can this trade be done and what is the risk?"

Key fields:

- `review_id`
- `decision`
- `risk_level`
- `position_limit_pct`
- `blockers`
- `warnings`
- `next_action`

### `OrderTicket`

Describes the draft order and answers: "What is ready to confirm?"

Key fields:

- `order_id`
- `review_id`
- `symbol`
- `side`
- `quantity`
- `limit_price`
- `route`
- `requires_confirmation`
- `confirmation_status`
- `confirmation_message`
- `status`

### `ExecutionReceipt`

Describes the execution receipt and answers: "What happened after submission?"

V1 uses a semi-automatic receipt. `prepared` means the CSV export is ready for user review; it does not mean the broker accepted the order.
`exported_path` points to the generated local CSV file for the confirmed order draft.
`accepted` means a broker-side receipt has been imported and reconciled into the workflow.

Key fields:

- `receipt_id`
- `order_id`
- `accepted`
- `status`
- `route`
- `message`
- `prepared_at`
- `submitted_at`
- `confirmed_by_user`
- `failure_reason`
- `next_action`
- `exported_path`

### `FillExecution`

Describes the broker-side fill detail and answers: "What actually traded, at what price, and how far did it deviate from the plan?"

Key fields:

- `fill_id`
- `order_id`
- `symbol`
- `filled_quantity`
- `avg_price`
- `target_price`
- `slippage_pct`
- `filled_at`
- `source`
- `message`

### `ExitExecution`

Describes the broker-side exit fill and answers: "How did the trade close and what P/L was realized?"

Key fields:

- `exit_id`
- `order_id`
- `symbol`
- `exited_quantity`
- `avg_price`
- `entry_avg_price`
- `realized_pnl`
- `realized_pnl_pct`
- `exited_at`
- `reason`
- `message`

### `OutcomeCard`

Describes the post-fill result card and answers: "What is the current outcome, is stop discipline intact, and what should happen next?"

Key fields:

- `outcome_id`
- `order_id`
- `symbol`
- `current_price`
- `unrealized_pnl`
- `unrealized_pnl_pct`
- `realized_pnl`
- `realized_pnl_pct`
- `stop_loss`
- `stop_discipline`
- `next_action`
- `summary`

### `TradeArchiveRecord`

Describes one completed round trip and answers: "What happened in this trade, why, and what should we inspect later?"

Key fields:

- `archive_id`
- `order_id`
- `symbol`
- `name`
- `trade_date`
- `opened_at`
- `closed_at`
- `realized_pnl`
- `realized_pnl_pct`
- `outcome`
- `signal_summary`
- `risk_summary`
- `execution_summary`
- `recap_summary`
- `next_action`
- `tags`

### `TradeArchiveReview`

Describes a lightweight review over recent completed archives and answers: "What pattern is visible now, which samples deserve inspection, and what is the next safe action?"

It is a service-owned summary, not a client-side history dashboard.

Key fields:

- `review_id`
- `record_count`
- `profit_count`
- `loss_count`
- `flat_count`
- `win_rate`
- `total_realized_pnl`
- `average_realized_pnl_pct`
- `best_archive_id`
- `worst_archive_id`
- `summary`
- `focus_points`
- `next_action`

### `Recap`

Describes the execution recap and answers: "How should this execution improve future strategy?"

Key fields:

- `recap_id`
- `order_id`
- `conclusion`
- `execution_deviation`
- `lessons`
- `strategy_adjustments`
- `next_strategy_action`

### `StrategyAdjustment`

Describes one proposed strategy-boundary change. The service layer may propose it, but the UI must present it as a suggestion, not an automatic configuration write.

Key fields:

- `key`
- `label`
- `current_value`
- `suggested_value`
- `reason`
- `impact`

### `StrategyConfig`

Describes the strategy boundary used for the next scan and execution cycle.

Additional adjustment fields:

- `adjustment_status`
- `adjustment_message`

Strategy adjustments become effective only after the user explicitly confirms applying them.
The local service can persist confirmed boundaries and mark `source` as `local`.
Resetting local strategy boundaries restores the default strategy config and source.
Before a local strategy config enters the next scan, the service validates known parameter types and ranges and falls back to default boundaries for invalid values.

### `StrategyChangeRecord`

Describes a lightweight local strategy-boundary change record.

Key fields:

- `record_id`
- `action`
- `strategy_id`
- `from_version`
- `to_version`
- `changes`
- `reason`
- `created_at`

### `MainChainSnapshot`

Aggregated main-chain snapshot. The client consumes this structure to render the main workflow state and does not re-judge business conclusions in the UI.
When a closed trade has been archived, `recent_archives` carries the compact local archive records for review context.

## 3. State Enums

- `WorkflowStage`: main workflow stages
- `RiskLevel`: risk severity
- `ReviewDecision`: execution review decision
- `ConfirmationStatus`: order confirmation state before receipt generation

## 4. Rules

- New cross-layer fields must be added to the shared contract and this document first.
- The client must not infer trusted business outcomes from private fields.
- The service layer must return enough `summary`, `next_action`, `status`, or equivalent fields to support UI display.
- Trading-related contracts default to semi-automatic confirmation, not unattended automatic trading.
- An order draft can become an execution receipt only after `confirmation_status` is `confirmed`.
- Fill execution data can enter recap only after an accepted broker receipt has been imported.
- Exit execution data can enter outcome only after an entry fill has been imported.
- Outcome cards are service-owned outputs; the client must not calculate P/L or stop discipline itself.
- Trade archive records are compact service-owned summaries; local storage, export, and cleanup are owned by infrastructure/service boundaries, not the client.
- Trade archive reviews are service-owned outputs; clients may display them or trigger export, but must not calculate win rate, best/worst archive, or follow-up action.
- Strategy parameters are service-validated before scanning; clients must not apply strategy-boundary changes directly.
