# FireMoney Client Architecture

## 1. Goal

The client keeps the user on the mainline first-board validation line. It renders service-owned state and avoids making trusted trading decisions.

Core line:

```text
今日决策 -> 模拟盘指挥单 -> 盘中买卖纪律 -> 晚评复盘 -> 收益/回撤证据
```

## 2. Current Skeleton

```text
client/desktop/firemoney_client/
  adapter.py        adapter from client to the one-to-two service
  cli/              local CLI parser, handlers, scheduler runner, runtime, and output adapters
  composition.py    local service/adapter composition root
  gateway.py        client-facing gateway protocol for local and future remote adapters
  one_to_two_cli.py local command entry for morning/watch/eod/backtest/stability/doctor/beta-check/beta-start/feishu-test/schedule/notifications/strategy-decision/paper-decision/paper-db
  presenters/       CLI/HTML presentation helpers and summary builders
  preview.py        local HTML preview generator
  preview_data.py   isolated sample data and report assembly for preview generation
  render_helpers.py shared HTML escaping, status labels, translation, and small formatting helpers
  render_sections.py HTML section renderers for the decision cockpit preview
  renderer.py       thin one-to-two HTML page assembler
  static/           CSS for the interface preview
```

## 3. Client Responsibilities

- Render candidate pool, position labels, stop loss, strict T+1 risk notes, runtime doctor checks, paper-account state, paper database metrics, local schedule state, daily strategy decision, paper-trading command sheet, Feishu notification status, notification records, end-of-day review with stability guidance, and stability observation with recent closed samples.
- The decision cockpit summary is normalized in `presenters/decision_presenter.py`; HTML rendering should consume the presenter output instead of recomputing buy/sell/hold labels inline.
- The default preview renders notification records through the same action-only filter used by CLI, so legacy scan/auction/paper-decision noise does not crowd out morning, buy, sell, and end-of-day messages. Notification display names are normalized in `presenters/notification_presenter.py` so CLI and preview use the same buy/sell action wording.
- Notification message lines are semantically highlighted through `shared/notification_highlight.py`: buy points, sell points, stop-loss/risk, profit/drawdown, discipline, and next actions use distinct colors so morning/eod cards can be scanned quickly without changing the service-owned plain text.
- Capture view/run intent and call the adapter.
- Consume shared contracts without recomputing score, risk, P/L, or notification state.
- Build local services through `composition.py`; CLI and preview should not duplicate infrastructure-store/provider wiring.
- Keep command flags in `cli/parser.py`, ordinary mode dispatch in `cli/handlers.py`, scheduler/Beta loop execution in `cli/schedule_runner.py`, local runtime composition in `cli/runtime.py`, terminal output in `cli/output.py`, and reusable command formatting in `presenters/brief_formatters.py`. `one_to_two_cli.py` should stay a thin local entry point that parses args and delegates. Core trading, replay, research, and paper-ledger brief output belongs to the formatter module so strategy wording changes do not disturb command routing.
- Keep `renderer.py` as a thin page assembler; section-level HTML belongs in `render_sections.py` so UI layout changes do not disturb the public preview entry point. Reusable label translation, escaping, status names, and small formatting helpers live in `render_helpers.py`, not inside every panel renderer.
- Keep preview-only service setup and seeded sample data in `preview_data.py`; `preview.py` should only write the rendered HTML file.
- `--sample-data` is always isolated from the live paper ledger by default. CLI sample runs use `.firemoney/sample/` unless the caller explicitly passes `--paper-store`, `--paper-db`, `--notification-store`, or scheduler paths; when a custom sample paper store is provided, its SQLite mirror stays beside that JSON file.
- Future remote execution must go through an adapter/gateway boundary; UI code must not import FireMoney infrastructure stores or vendor adapters directly.
- Keep `gateway.py` server-free and aligned with the full public surface of `LocalMainChainAdapter`; local implementation details belong in `adapter.py` and service wiring belongs in `composition.py`.
- Future minute-bar / Tick / queue-quality outputs still belong to the service layer; the client should render them as evidence, not derive trusted execution judgments locally.
- Keep old demos, CSV order flows, receipt import screens, and generic dashboards out of the default product surface.

## 4. UI Rules

- One screen answers one job: can this one-to-two setup be observed and simulated safely?
- Risk, stop loss, position limit, and T+1 warning stay near the candidate and paper position.
- Low breakout candidates are shown as executable only after service-side market-width confirmation; thin-width setups remain observation records.
- Feishu delivery is shown as state, not as a blocker for strategy execution.
- Notification colors are decision aids, not new trading rules: green means buy/setup, blue means sell/next action, red means risk/stop loss, orange means discipline, and profit/drawdown lines remain visually separate for review.
- Local schedule status is shown as one-to-two workflow progress, not as a generic job console.
- The preview and default entry point show the decision cockpit first: buy / sell / stand aside, next command, strategy line, paper action, sell discipline, and risk guard. The detailed daily strategy decision and paper-trading command sheet stay immediately below as evidence, not as the first thing the user must parse.
- The local preview may seed temporary closed samples to show the review surface, but it never writes those samples to the live `.firemoney/paper_trades.json` ledger.
