# FireMoney Client Architecture

## 1. Goal

The client keeps the user on the one-to-two validation line. It renders service-owned state and avoids making trusted trading decisions.

Core line:

```text
早盘判断 -> 盘中模拟 -> 尾盘复盘 -> 稳定性观察
```

## 2. Current Skeleton

```text
client/desktop/firemoney_client/
  adapter.py        adapter from client to the one-to-two service
  one_to_two_cli.py local command entry for morning/watch/eod/backtest/stability/doctor/schedule/notifications
  preview.py        local HTML preview generator
  renderer.py       one-to-two HTML renderer
  static/           CSS for the interface preview
```

## 3. Client Responsibilities

- Render candidate pool, position labels, stop loss, strict T+1 risk notes, runtime doctor checks, paper-account state, local schedule state, Feishu notification status, notification records, end-of-day review with stability guidance, and stability observation with recent closed samples.
- Capture view/run intent and call the adapter.
- Consume shared contracts without recomputing score, risk, P/L, or notification state.
- Keep old demos, CSV order flows, receipt import screens, and generic dashboards out of the default product surface.

## 4. UI Rules

- One screen answers one job: can this one-to-two setup be observed and simulated safely?
- Risk, stop loss, position limit, and T+1 warning stay near the candidate and paper position.
- Feishu delivery is shown as state, not as a blocker for strategy execution.
- Local schedule status is shown as one-to-two workflow progress, not as a generic job console.
- The preview and default entry point show only the current one-to-two line.
