# FireMoney Core Business Plan

## 1. Goal

FireMoney is being rebuilt around the shortest useful trading-assistant loop for the user:

```text
judge market -> control execution -> improve from recap
```

In product terms, the first version should feel like:

```text
see signal -> check risk -> confirm order -> see receipt -> learn one improvement
```

Everything else is supporting material, not a first-class entry.

## 2. Core Business Line

### P0: Keep

- `市场判断`: market context, signal scan, focus candidate, and only the necessary opportunity pool.
- `执行中控`: risk review, order draft, user confirmation, submission status, and receipt tracking.
- `复盘改进`: execution recap, one clear lesson, and the next strategy-boundary adjustment.

### P1: Fold Into P0

- `信号扫描`: lives inside `市场判断`, not as a separate primary workspace.
- `机会池`: becomes the selected candidate list under `市场判断`, not a standalone destination.
- `策略配置`: appears as strategy boundary and parameter-impact editing inside `复盘改进`.
- `单票复盘`: becomes the main recap state inside `复盘改进`.

### P2: Drop From The First Version

- independent message center
- AI playground or generic AI center
- complex historical-statistics pages
- decorative command-center dashboards
- repeated subpages that restate the same market, risk, or recap summary
- multi-account and vendor-maintenance surfaces until the core chain is trusted

## 3. Layer Split

### Client

- UI and interaction
- tables, charts, state display
- input, confirmation, cancellation
- execution result and recap display
- localizable content loading

### Server / Business Layer

- strategy scan, recommendation, scoring
- risk review and abnormal blocking
- order draft generation
- account, funds, positions, and execution state
- execution logs, recap records, and report generation

### Shared

- DTOs and schemas
- error codes and state enums
- API or local RPC protocol
- documented data dictionary

## 4. First Release Sequence

1. Establish shared contracts: opportunity, risk review, order draft, recap, strategy config, signal scan report.
2. Establish server architecture: application, domain, infrastructure, contracts.
3. Establish client architecture around three primary workspaces: `市场判断`, `执行中控`, `复盘改进`.
4. Strengthen the P0 business chain from the validated core business rules.
5. Add risk controls and semi-automatic execution only after confirmation and recap are clear.
6. Complete tests and docs.

## 5. Current State

- Shared contracts already include the first-slice chain and the new `SignalScanReport`.
- Server now emits a deterministic signal scan report before selecting the first opportunity.
- Signal scan policy now lives in the domain layer and filters by strategy score, confidence, and liquidity constraints.
- Client shell renders the signal scan summary and next action before the opportunity and execution sections.
- Client shell now exposes only the three core workspaces.
- Client text starts from a localizable content catalog.
- Client preview renders a clean three-step interface from the same shared snapshot.
- The default flow now stops at order draft until the user explicitly confirms.
- `OrderTicket` now carries explicit confirmation status and confirmation copy.
- Recap now proposes strategy-boundary adjustments without automatically writing config.
- Strategy-boundary adjustments now require explicit user confirmation before updating the next cycle.
- Confirmed strategy boundaries are persisted locally under `.firemoney/strategy_config.json`.
- Local strategy boundaries are validated before the next scan; invalid local JSON falls back to defaults.
- Unknown, malformed, or out-of-range strategy parameters are corrected from default boundaries.
- Local strategy boundaries can be reset back to defaults through the service layer.
- Strategy boundary apply/reset actions now keep a lightweight local change record.
- Execution receipts now expose route, status, prepared time, export path, and next action as structured fields.
- Confirmed order drafts now generate a real local CSV export through the infrastructure layer.
- Broker execution is now behind a project-owned adapter boundary, with local CSV as the first implementation.
- Broker-side receipt CSV import now reconciles submitted/accepted/failed status back into the main workflow.
- Broker-side fill detail import now feeds成交数量、成交均价和滑点 into recap.
- Post-fill outcome cards now show current price, unrealized P/L, stop discipline, and next action.
- Exit fill import now closes the trade with realized P/L and a final recap state.
- Completed round trips now produce a compact trade archive record for review.
- Completed archive records are persisted locally under `.firemoney/trade_archives.json`.
- Client preview now shows a lightweight recent-archives review strip beside the core workflow.
- Archive records can now be exported as JSON or CSV through the service boundary.
- Local archive cleanup now goes through the service boundary and bad archive JSON is treated as empty local state.
- Recent archive records can now produce a lightweight service-owned review summary and Markdown export without adding a history center.
- Archive review now reports sample quality and prevents fewer than 3 closed archives from driving strategy-boundary action.
- Smoke tests cover the new contract field and the main client rendering path.

## 6. Next TODO

- [x] Define the first version of `shared/contracts`.
- [x] Define server folder structure and module boundaries.
- [x] Define the simplified three-workspace client structure.
- [x] Establish the first end-to-end smoke path: signal scan -> opportunity pool -> risk review -> recap.
- [x] Add explicit user confirmation state before any executable order route.
- [x] Replace deterministic sample scan data with the first domain signal-scan policy.
- [x] Add recap-driven strategy-boundary suggestions.
- [x] Add user confirmation for applying proposed strategy adjustments.
- [x] Persist confirmed strategy boundaries outside sample data.
- [x] Validate local strategy boundaries before the next scan cycle.
- [x] Add a lightweight reset/revert path for local strategy boundaries.
- [x] Add a visible lightweight change trail for strategy boundary changes.
- [x] Add structured execution receipt data for the semi-automatic CSV flow.
- [x] Add real CSV file generation behind the execution route.
- [x] Wrap the CSV execution path behind a broker adapter boundary.
- [x] Add broker receipt import/reconciliation after the CSV file is submitted outside FireMoney.
- [x] Add final fill-price/deal recap after the broker returns成交明细.
- [x] Split the next cycle into a compact post-trade outcome card: unrealized P/L, stop discipline, and follow-up action.
- [x] Add realized P/L after an exit fill is imported.
- [x] Add a compact final trade archive record for the completed round trip.
- [x] Persist completed archive records to local storage after the in-memory contract is stable.
- [x] Add a compact recent-archives review strip without turning it into a full history dashboard.
- [x] Add archive export or cleanup controls only after the core local record format settles.
- [x] Add lightweight archive review summary/export after archive export settles.
- [x] Add an archive-review sample-quality gate before strategy-boundary guidance.

## 7. Validation Entry Points

Run the smoke suite:

```powershell
python -m unittest discover -s tests -v
```

Regenerate the local HTML preview:

```powershell
python -m client.desktop.firemoney_client.preview
```

Open:

```text
client/desktop/preview/core_workflow.html
```
