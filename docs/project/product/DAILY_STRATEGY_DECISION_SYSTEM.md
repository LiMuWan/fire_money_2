# FireMoney Daily Strategy Decision System

## Purpose

The daily decision entry is:

```text
python -m client.desktop.firemoney_client.one_to_two_cli strategy-decision --brief
```

The paper-trading command-sheet entry is:

```text
python -m client.desktop.firemoney_client.one_to_two_cli paper-decision --brief
```

Its job is not to force a trade every day. Its job is to choose whether the only validated operating line deserves capital today, or whether the system should stay in cash.

The command sheet then turns that daily strategy choice into one simulated trading decision: buy one qualified candidate, keep managing an existing position, or stand aside.

## Current Rule

- Actual operating line: `board-shadow-system`.
- Fallback line: `cash`.

`board-shadow-system` stays the only actual operating line because it has the strongest 2024+ point-in-time backtest evidence in the current codebase. Research lines remain offline-only until they prove cross-year stability, realistic execution, and lower drawdown than the main line.

## Selection Discipline

- Use one actual operating strategy per day to avoid overlapping drawdowns.
- If the main line has no executable signal or its data check fails, stand aside.
- Do not promote a research strategy because one day looks attractive.
- Remove a strategy from the daily operating path when it cannot prove long-term profitability.
- Re-run point-in-time backtests from `2024-01-01` after every material buy/sell rule change.
- Treat `cash` as an intentional risk-control state, not as missed profit.

## Paper-Trading Command Sheet

- `paper-decision` reads `strategy-decision` first; it does not choose a different strategy locally.
- It reads the morning candidate pool and the current paper account, then outputs at most one simulated buy plan.
- A buy plan includes symbol, entry window, trigger, entry price, stop loss, first take-profit price, planned stop-risk percentage, first-target return percentage, reward/risk ratio, drawdown budget, position budget, quantity, cancellation rules, sell rules, and next check time.
- If there is an existing position, a used daily trade slot, unavailable data, or no `ready` candidate, the command sheet explicitly chooses no new buy.
- The command sheet is read-only. Only `watch --phase open` can write a simulated buy event to the paper ledger.
- The command sheet is local-only by default: it shows the candidate buy point, cancellation rules, sell-point discipline, holding sell triggers, or the explicit no-buy reason in CLI/page output, but it does not push Feishu. Feishu is reserved for morning review, actual simulated buy events, actual simulated sell events, and end-of-day review.
- Non-profitable research strategies do not enter the daily command-sheet buy route.
- The buy gate now requires a high-quality positive-expectancy setup: strong score, sealing, mainline, leader recognition, effective turnover-leader quality, healthy volume ratio, non-overheated RSI, sufficient 60-day position percentile, at least `2.0R` reward/risk, and planned stop risk that is smaller than the first-target return and inside the profit-covered drawdown budget.
- The effective turnover-leader gate is a daily-proxy rule for 换手龙买点. It scores turnover rate, sealed amount / turnover amount, first limit-up time, auction amount ratio, market temperature, volume ratio, RSI, and position structure. Candidates below `72/100` are blocked before paper buying, and candidates above the floor are still shown with notes so the morning review explains whether the buy point is strong or merely passing.
- The paper-trading profit guard reads recent closed trades before every new entry. It blocks new entries after consecutive losses, consecutive quality failures, or excessive recent drawdown, and it reduces position size when recent win rate or average return is below the configured threshold.
- The paper-trading profit-quality guard reviews every closed trade by `profit_drawdown_ratio`. A loss or flat close is a quality failure, and a profitable sample also fails if it earned less than its maximum intratrade adverse move (`profit_drawdown_ratio < 1.0R`). One weak profitable sample reduces the next entry; two consecutive quality failures pause new entries until newer samples prove that profits are covering process drawdown.
- The entry guard also checks the recent closed-trade risk-quality pass rate and average profit/drawdown ratio. If the recent sample cannot prove that profits consistently cover intratrade drawdown, the next buy is reduced even when raw average return is positive.
- Before a new paper buy, the guard also compares the candidate's turnover-dragon quality bucket with closed trades from the same bucket. A weak bucket can reduce the next position, and consecutive quality failures in the same bucket can block the new entry even if unrelated buckets look healthy.
- The sell gate locks profit only after T+1 is available and the position has cleared the higher of the base `+3%` floating-return line or the intratrade drawdown quality line. In practice, the close must satisfy `realized profit > max_adverse_pct * positive_lock_min_profit_drawdown_ratio`, so a small profit after a large pullback is not treated as high-quality locked profit.
- Strong positions can enter the main-rise runner mode when entry turnover quality, opening score, and mainline continuity all clear the configured high bars. These positions skip the ordinary `+3%` lock, use a `+6%` peak / `2%` trailing lock plus a `+1.5%` profit floor, and still obey the original `+10%` strong trailing rule and `+12%` first-target take profit.
- A losing close is not hidden as success. It stays in SQLite with its exit reason and must be reviewed as a strategy-quality accident before loosening buy rules.

## Paper-Trading Database

- `paper-db --brief` reads the SQLite paper-trading mirror and summarizes equity, cash, open positions, closed trades, realized P/L, win rate, recent events, average profit/drawdown ratio, the rate at which realized profit covered intratrade drawdown, the planned entry risk/reward, the entry turnover-dragon quality, and the entry guard decision carried from the original buy plan.
- `PaperTradeStore.save()` syncs the JSON ledger into SQLite after each simulated state change, so existing buy, stop-warning, T+1 sell, take-profit, fade-exit, and discipline-exit paths all persist trading data.
- Each open and closed paper trade stores planned stop-risk percentage, first-target return percentage, planned reward/risk ratio, drawdown budget, entry turnover-dragon quality score/label/notes, entry guard status/action/suggested position/quality-bucket stats, `max_favorable_pct`, `max_adverse_pct`, and `profit_drawdown_ratio`. This keeps the review focused on whether the system is making enough money for both the planned risk, the buy-point quality it trusted, the guard decision it accepted, and the risk it actually had to absorb.
- Closed trades are also grouped into quality buckets: strong turnover dragon (`>=86`), valid turnover dragon (`>=72`), weak turnover quality (`>0`), and unscored legacy samples. The bucket review reports count, win rate, average return, profit/drawdown ratio, risk-quality pass rate, and whether the segment should keep observing or be downgraded.
- Closed trades are also grouped by entry guard action, such as full-size allow, reduced-size allow, and unscored legacy samples. This guard review reports count, average suggested position, win rate, average return, profit/drawdown ratio, risk-quality pass rate, and whether full-size entries should stay open, be downgraded, or be paused.
- The JSON ledger remains the compatibility store for current workflows; SQLite is the query and review store for operating metrics.
- Custom test or rehearsal ledgers keep their own sibling `.sqlite3` file, avoiding accidental pollution of the live `.firemoney/paper_trades.sqlite3`.

## Current Validation Snapshot

- Main line: balanced low-drawdown v2 uses a 20-day gain cap of `20%`, ordinary take profit of `6%`, and strong-market take profit of `8%`. 2024+ dynamic 8%/12% compound return is around `+100.32%`; 2026 validation is around `+11.17%`.
- `paper-backtest --start-date 2020-01-01 --brief` now includes execution-friction stress. With fixed round-trip friction raised from `0.15%` to `1.00%`, the 2020-2026 dynamic compound remains positive at about `+182.30%`, but the weakest year, 2021, falls to about `+1.71%`, so the stress row is marked `warning`.
- Research lines remain offline-only until they prove long-term profitability and weaker-drawdown performance than `board-shadow-system`.

These are research and simulation metrics, not a guarantee of future profit. The product objective is stable risk-adjusted compounding, so the decision layer optimizes for expected return only after the drawdown and data-validity gates pass.
