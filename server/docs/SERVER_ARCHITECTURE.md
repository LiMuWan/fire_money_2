# FireMoney Server Architecture

## 1. Goal

The server/business layer owns deterministic one-to-two policy, state transitions, and external adaptation. It is the authority for scoring, blockers, paper-trading events, notification results, and review output.

## 2. Current Skeleton

```text
server/firemoney_server/
  application/
    main_chain.py          one-to-two workflow orchestration
  domain/
    one_to_two.py          mainboard 10cm one-to-two scoring and blocker policy
  infrastructure/
    feishu_notifier.py     Feishu group robot webhook adapter
    market_data.py         MarketDataProvider boundary and AkShare adapter
    one_to_two_config.py   one-to-two strategy config loader
    paper_store.py         local event-driven paper-trading account
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
- Hard blockers include ST, delisting, new stock, non-mainboard markets, high deviation, nearby pressure, low liquidity, weak market temperature, and one-word unreachable boards.
- Same-day stop loss breaches create warning events only; T+1 sell events are allowed only after the position rolls to the next day.
- Trading dates are resolved before market data and paper trading. Closed dates use the previous A-share trading day so weekends and holidays do not generate false scans.
- `watch` supports `scan`, `auction`, `open`, and `risk` phases. Only the `open` phase can create a paper buy; `risk` handles stop-warning and T+1 sell events.
- Completed exits create `PaperTradeRecord` samples. Stability metrics use these closed trade records, not raw event counts.
- Feishu reads only `FEISHU_ENABLED`, `FEISHU_WEBHOOK_URL`, and optional `FEISHU_WEBHOOK_SECRET`.
- Notification failures return structured results and do not stop strategy execution.
- Local entry modes are exposed by `client.desktop.firemoney_client.one_to_two_cli`: `morning`, `watch`, `eod`, and `backtest`.
