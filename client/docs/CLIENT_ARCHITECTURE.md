# FireMoney Client Architecture

## 1. Goal

The client owns user experience and interaction closure. It must keep the user on the shortest core line, render workflow state, and avoid making trusted business decisions.

## 2. Current Skeleton

```text
client/desktop/firemoney_client/
  adapter.py     adapter from client to business layer
  content.py     localizable content loader
  content/       locale-specific UI text
  one_to_two_cli.py  local command entry for one-to-two morning/watch/eod/backtest
  renderer.py    HTML renderer for the simplified core interface
  static/        CSS for the interface preview
  view_model.py  display-only view model derived from contracts
  shell.py       workspace definitions and main snapshot rendering
```

## 3. Client Responsibilities

- Render the three core user workspaces: market judgment, execution control, and recap improvement.
- Keep one-to-two candidate review, position score, and pressure/stop notes inside market judgment.
- Keep paper-trading risk discipline and T+1 status inside execution control.
- Keep end-of-day review and stability observation inside recap improvement.
- Capture user confirmations, cancellations, refresh intent, and navigation intent.
- Consume `MainChainSnapshot` without re-computing business conclusions.
- Load display text from content files when practical.

## 4. Workspaces

First release workspaces:

- `市场判断`
- `执行中控`
- `复盘改进`

Removed as first-class entries:

- `信号扫描`: supporting section of `市场判断`
- `机会池`: supporting section of `市场判断`
- `单票复盘`: supporting section of `复盘改进`
- `策略配置`: supporting section of `复盘改进`

## 5. UI Rules

- Each workspace should carry one main chain.
- Helper information defaults to lower density.
- Execution actions must show confirmation, status feedback, and recap entry points.
- The client should use the service-layer adapter instead of calling SDKs directly.
- Strategy-boundary apply/reset actions must go through service review and confirmation methods; the client must not edit `.firemoney` files directly.
- Strategy-boundary audit filtering is requested through the adapter, not by reading or parsing local history files in UI code.
- Export cleanup is requested through the adapter and displayed from `ExportCleanupResult`; UI code must not delete `exports/` files directly.
- One screen should answer one dominant user question.
- Repeated summaries should be folded or hidden when they do not change the next action.

## 6. Core Interface Layout

The first interface is a restrained three-part workspace:

- Top: product name, core path, and only three workspace switches.
- Main column: `市场判断 -> 执行审查 -> 复盘改进` as stacked decision steps.
- Current preview: one-to-two specialty page only.

Design constraints:

- No decorative dashboard blocks.
- No first-class message center, AI center, or complex statistics page.
- Risk, position limit, price, route, and confirmation stay close together.
- The UI may render an order draft, but it must not turn it into a receipt or recap before user confirmation.
- The preview includes both confirmation states: before confirmation and after confirmation.
- The one-to-two specialty page displays server-owned candidates, position labels, stop loss, strict T+1 risk notes, paper-account state, Feishu notification status, and end-of-day/stability summaries.
- Visible text should come from `content/*.json` when practical.

## 7. Content Configuration

- `client/desktop/firemoney_client/content/zh_CN.json` owns visible client text, workspace labels, section titles, empty states, buttons, and shell templates.
- The current local preview uses one-to-two sample market data from the service boundary and renders only candidate, risk, paper-account, notification, and review state.
- `content.py` loads content into typed client structures; UI modules consume these structures instead of embedding display text.
- New visible text should be added to locale content first whenever practical, so future localization can reuse the same interface code.
