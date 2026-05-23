"""SQLite mirror and report reader for the local paper-trading account."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from server.firemoney_server.infrastructure.paper_database_schema import (
    decode_notes,
    encode_notes,
    ensure_paper_trade_schema,
)

from shared.contracts import (
    PaperAccount,
    PaperTradeDailyAudit,
    PaperTradeDatabaseEvent,
    PaperTradeDatabasePosition,
    PaperTradeDatabaseReport,
    PaperTradeDatabaseTrade,
    PaperTradeGuardBucket,
    PaperTradeQualityBucket,
)


DEFAULT_PAPER_DATABASE_PATH = Path(".firemoney") / "paper_trades.sqlite3"


class PaperTradeDatabase:
    """Persists paper-trading positions, events, and P/L into SQLite."""

    def __init__(self, path: str | Path = DEFAULT_PAPER_DATABASE_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def sync_account(self, account: PaperAccount) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as connection:
            ensure_paper_trade_schema(connection)
            connection.execute(
                """
                insert or replace into account_snapshots (
                    account_id, last_trade_date, cash, initial_cash, equity,
                    max_position_pct, max_daily_trades, daily_trade_count,
                    open_position_count, closed_trade_count, event_count,
                    synced_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    account.account_id,
                    account.last_trade_date,
                    account.cash,
                    account.initial_cash,
                    account.equity,
                    account.max_position_pct,
                    account.max_daily_trades,
                    account.daily_trade_count,
                    len(account.positions),
                    len(account.closed_trades),
                    len(account.events),
                ),
            )
            connection.execute("delete from positions where account_id = ?", (account.account_id,))
            connection.executemany(
                """
                insert or replace into positions (
                    account_id, symbol, name, quantity, entry_price, latest_price,
                    stop_loss, position_value, unrealized_pnl, unrealized_pnl_pct,
                    opened_at, position_label, opened_score, can_sell_today,
                    status, risk_note, peak_price, trough_price,
                    planned_stop_risk_pct, planned_first_target_return_pct,
                    planned_reward_risk_ratio, max_intratrade_drawdown_budget_pct,
                    entry_turnover_quality_score, entry_turnover_quality_label,
                    entry_turnover_quality_notes, entry_guard_status,
                    entry_guard_action, entry_guard_suggested_position_pct,
                    entry_guard_reason, entry_guard_quality_bucket,
                    entry_guard_quality_sample_count, entry_guard_quality_win_rate,
                    entry_guard_quality_average_return_pct,
                    entry_guard_quality_pass_rate
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        account.account_id,
                        position.symbol,
                        position.name,
                        position.quantity,
                        position.entry_price,
                        position.latest_price,
                        position.stop_loss,
                        position.position_value,
                        position.unrealized_pnl,
                        position.unrealized_pnl_pct,
                        position.opened_at,
                        position.position_label,
                        position.opened_score,
                        int(position.can_sell_today),
                        position.status.value,
                        position.risk_note,
                        position.peak_price,
                        position.trough_price,
                        position.planned_stop_risk_pct,
                        position.planned_first_target_return_pct,
                        position.planned_reward_risk_ratio,
                        position.max_intratrade_drawdown_budget_pct,
                        position.entry_turnover_quality_score,
                        position.entry_turnover_quality_label,
                        encode_notes(position.entry_turnover_quality_notes),
                        position.entry_guard_status,
                        position.entry_guard_action,
                        position.entry_guard_suggested_position_pct,
                        position.entry_guard_reason,
                        position.entry_guard_quality_bucket,
                        position.entry_guard_quality_sample_count,
                        position.entry_guard_quality_win_rate,
                        position.entry_guard_quality_average_return_pct,
                        position.entry_guard_quality_pass_rate,
                    )
                    for position in account.positions
                ),
            )
            connection.executemany(
                """
                insert or replace into trade_events (
                    event_id, account_id, event_type, symbol, name, trade_date,
                    price, quantity, amount, message, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        event.event_id,
                        account.account_id,
                        event.event_type.value,
                        event.symbol,
                        event.name,
                        event.trade_date,
                        event.price,
                        event.quantity,
                        event.amount,
                        event.message,
                        event.created_at,
                    )
                    for event in account.events
                ),
            )
            connection.executemany(
                """
                insert or replace into closed_trades (
                    trade_id, account_id, symbol, name, opened_at, closed_at,
                    entry_price, exit_price, quantity, entry_amount, exit_amount,
                    realized_pnl, realized_pnl_pct, holding_trade_days,
                    exit_reason, position_label, success, warning_count,
                    max_favorable_pct, max_adverse_pct, profit_drawdown_ratio,
                    planned_stop_risk_pct, planned_first_target_return_pct,
                    planned_reward_risk_ratio, max_intratrade_drawdown_budget_pct,
                    entry_turnover_quality_score, entry_turnover_quality_label,
                    entry_turnover_quality_notes, entry_guard_status,
                    entry_guard_action, entry_guard_suggested_position_pct,
                    entry_guard_reason, entry_guard_quality_bucket,
                    entry_guard_quality_sample_count, entry_guard_quality_win_rate,
                    entry_guard_quality_average_return_pct,
                    entry_guard_quality_pass_rate
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        trade.trade_id,
                        account.account_id,
                        trade.symbol,
                        trade.name,
                        trade.opened_at,
                        trade.closed_at,
                        trade.entry_price,
                        trade.exit_price,
                        trade.quantity,
                        trade.entry_amount,
                        trade.exit_amount,
                        trade.realized_pnl,
                        trade.realized_pnl_pct,
                        trade.holding_trade_days,
                        trade.exit_reason,
                        trade.position_label,
                        int(trade.success),
                        trade.warning_count,
                        trade.max_favorable_pct,
                        trade.max_adverse_pct,
                        trade.profit_drawdown_ratio,
                        trade.planned_stop_risk_pct,
                        trade.planned_first_target_return_pct,
                        trade.planned_reward_risk_ratio,
                        trade.max_intratrade_drawdown_budget_pct,
                        trade.entry_turnover_quality_score,
                        trade.entry_turnover_quality_label,
                        encode_notes(trade.entry_turnover_quality_notes),
                        trade.entry_guard_status,
                        trade.entry_guard_action,
                        trade.entry_guard_suggested_position_pct,
                        trade.entry_guard_reason,
                        trade.entry_guard_quality_bucket,
                        trade.entry_guard_quality_sample_count,
                        trade.entry_guard_quality_win_rate,
                        trade.entry_guard_quality_average_return_pct,
                        trade.entry_guard_quality_pass_rate,
                    )
                    for trade in account.closed_trades
                ),
            )
            connection.commit()

    def build_report(self, limit: int = 10) -> PaperTradeDatabaseReport:
        if not self._path.exists():
            return PaperTradeDatabaseReport(
                report_id="paper-trade-database",
                database_path=str(self._path),
                status="empty",
                account_id="",
                last_trade_date="",
                cash=0.0,
                equity=0.0,
                total_realized_pnl=0.0,
                total_realized_return_pct=0.0,
                win_rate=0.0,
                average_realized_return_pct=0.0,
                average_profit_drawdown_ratio=0.0,
                risk_quality_pass_rate=0.0,
                snapshot_count=0,
                event_count=0,
                open_position_count=0,
                closed_trade_count=0,
                positions=(),
                recent_events=(),
                recent_trades=(),
                quality_buckets=(),
                guard_buckets=(),
                daily_audits=(),
                next_action="先运行 morning/watch/risk，让模拟盘账本写入买卖事件后再复盘。",
            )
        with closing(sqlite3.connect(self._path)) as connection:
            connection.row_factory = sqlite3.Row
            ensure_paper_trade_schema(connection)
            snapshot = connection.execute(
                """
                select * from account_snapshots
                order by synced_at desc, rowid desc
                limit 1
                """
            ).fetchone()
            if snapshot is None:
                return self.build_report_empty_existing()
            positions = tuple(
                PaperTradeDatabasePosition(
                    symbol=str(row["symbol"]),
                    name=str(row["name"]),
                    quantity=int(row["quantity"]),
                    entry_price=float(row["entry_price"]),
                    latest_price=float(row["latest_price"]),
                    position_value=float(row["position_value"]),
                    unrealized_pnl=float(row["unrealized_pnl"]),
                    unrealized_pnl_pct=float(row["unrealized_pnl_pct"]),
                    opened_at=str(row["opened_at"]),
                    status=str(row["status"]),
                    planned_stop_risk_pct=float(row["planned_stop_risk_pct"]),
                    planned_first_target_return_pct=float(
                        row["planned_first_target_return_pct"]
                    ),
                    planned_reward_risk_ratio=float(
                        row["planned_reward_risk_ratio"]
                    ),
                    max_intratrade_drawdown_budget_pct=float(
                        row["max_intratrade_drawdown_budget_pct"]
                    ),
                    entry_turnover_quality_score=float(
                        row["entry_turnover_quality_score"]
                    ),
                    entry_turnover_quality_label=str(
                        row["entry_turnover_quality_label"]
                    ),
                    entry_turnover_quality_notes=decode_notes(
                        row["entry_turnover_quality_notes"]
                    ),
                    entry_guard_status=str(row["entry_guard_status"]),
                    entry_guard_action=str(row["entry_guard_action"]),
                    entry_guard_suggested_position_pct=float(
                        row["entry_guard_suggested_position_pct"]
                    ),
                    entry_guard_reason=str(row["entry_guard_reason"]),
                    entry_guard_quality_bucket=str(row["entry_guard_quality_bucket"]),
                    entry_guard_quality_sample_count=int(
                        row["entry_guard_quality_sample_count"]
                    ),
                    entry_guard_quality_win_rate=float(
                        row["entry_guard_quality_win_rate"]
                    ),
                    entry_guard_quality_average_return_pct=float(
                        row["entry_guard_quality_average_return_pct"]
                    ),
                    entry_guard_quality_pass_rate=float(
                        row["entry_guard_quality_pass_rate"]
                    ),
                )
                for row in connection.execute(
                    """
                    select * from positions
                    where account_id = ?
                    order by opened_at desc, symbol asc
                    """,
                    (snapshot["account_id"],),
                ).fetchall()
            )
            recent_events = tuple(
                PaperTradeDatabaseEvent(
                    event_type=str(row["event_type"]),
                    symbol=str(row["symbol"]),
                    name=str(row["name"]),
                    trade_date=str(row["trade_date"]),
                    price=float(row["price"]),
                    quantity=int(row["quantity"]),
                    amount=float(row["amount"]),
                    message=str(row["message"]),
                    created_at=str(row["created_at"]),
                )
                for row in connection.execute(
                    """
                    select * from trade_events
                    where account_id = ?
                    order by created_at desc, event_id desc
                    limit ?
                    """,
                    (snapshot["account_id"], max(0, limit)),
                ).fetchall()
            )
            recent_trades = tuple(
                PaperTradeDatabaseTrade(
                    trade_id=str(row["trade_id"]),
                    symbol=str(row["symbol"]),
                    name=str(row["name"]),
                    opened_at=str(row["opened_at"]),
                    closed_at=str(row["closed_at"]),
                    entry_price=float(row["entry_price"]),
                    exit_price=float(row["exit_price"]),
                    quantity=int(row["quantity"]),
                    realized_pnl=float(row["realized_pnl"]),
                    realized_pnl_pct=float(row["realized_pnl_pct"]),
                    exit_reason=str(row["exit_reason"]),
                    success=bool(row["success"]),
                    max_favorable_pct=float(row["max_favorable_pct"]),
                    max_adverse_pct=float(row["max_adverse_pct"]),
                    profit_drawdown_ratio=float(row["profit_drawdown_ratio"]),
                    planned_stop_risk_pct=float(row["planned_stop_risk_pct"]),
                    planned_first_target_return_pct=float(
                        row["planned_first_target_return_pct"]
                    ),
                    planned_reward_risk_ratio=float(
                        row["planned_reward_risk_ratio"]
                    ),
                    max_intratrade_drawdown_budget_pct=float(
                        row["max_intratrade_drawdown_budget_pct"]
                    ),
                    entry_turnover_quality_score=float(
                        row["entry_turnover_quality_score"]
                    ),
                    entry_turnover_quality_label=str(
                        row["entry_turnover_quality_label"]
                    ),
                    entry_turnover_quality_notes=decode_notes(
                        row["entry_turnover_quality_notes"]
                    ),
                    entry_guard_status=str(row["entry_guard_status"]),
                    entry_guard_action=str(row["entry_guard_action"]),
                    entry_guard_suggested_position_pct=float(
                        row["entry_guard_suggested_position_pct"]
                    ),
                    entry_guard_reason=str(row["entry_guard_reason"]),
                    entry_guard_quality_bucket=str(row["entry_guard_quality_bucket"]),
                    entry_guard_quality_sample_count=int(
                        row["entry_guard_quality_sample_count"]
                    ),
                    entry_guard_quality_win_rate=float(
                        row["entry_guard_quality_win_rate"]
                    ),
                    entry_guard_quality_average_return_pct=float(
                        row["entry_guard_quality_average_return_pct"]
                    ),
                    entry_guard_quality_pass_rate=float(
                        row["entry_guard_quality_pass_rate"]
                    ),
                )
                for row in connection.execute(
                    """
                    select * from closed_trades
                    where account_id = ?
                    order by closed_at desc, trade_id desc
                    limit ?
                    """,
                    (snapshot["account_id"], max(0, limit)),
                ).fetchall()
            )
            aggregate = connection.execute(
                """
                select
                    count(*) as closed_count,
                    coalesce(sum(realized_pnl), 0) as total_pnl,
                    coalesce(avg(realized_pnl_pct), 0) as avg_return,
                    coalesce(avg(case when profit_drawdown_ratio > 0 then profit_drawdown_ratio end), 0) as avg_profit_drawdown_ratio,
                    coalesce(sum(case when realized_pnl_pct > max_adverse_pct then 1 else 0 end), 0) as risk_quality_passes,
                    coalesce(sum(case when success = 1 then 1 else 0 end), 0) as wins
                from closed_trades
                where account_id = ?
                """,
                (snapshot["account_id"],),
            ).fetchone()
            quality_buckets = self._build_quality_buckets(
                connection,
                str(snapshot["account_id"]),
            )
            guard_buckets = self._build_guard_buckets(
                connection,
                str(snapshot["account_id"]),
            )
            daily_audits = self._build_daily_audits(
                connection,
                str(snapshot["account_id"]),
                limit,
            )
            snapshot_count = int(
                connection.execute("select count(*) from account_snapshots").fetchone()[0]
            )
            event_count = int(
                connection.execute(
                    "select count(*) from trade_events where account_id = ?",
                    (snapshot["account_id"],),
                ).fetchone()[0]
            )
            closed_count = int(aggregate["closed_count"])
            total_pnl = float(aggregate["total_pnl"])
            initial_cash = float(snapshot["initial_cash"] or 0.0)
            win_rate = float(aggregate["wins"]) / closed_count if closed_count else 0.0
            return PaperTradeDatabaseReport(
                report_id=f"paper-trade-database-{snapshot['account_id']}",
                database_path=str(self._path),
                status="ready",
                account_id=str(snapshot["account_id"]),
                last_trade_date=str(snapshot["last_trade_date"]),
                cash=float(snapshot["cash"]),
                equity=float(snapshot["equity"]),
                total_realized_pnl=round(total_pnl, 2),
                total_realized_return_pct=round(
                    total_pnl / initial_cash,
                    6,
                )
                if initial_cash > 0
                else 0.0,
                win_rate=round(win_rate, 6),
                average_realized_return_pct=round(float(aggregate["avg_return"]), 6),
                average_profit_drawdown_ratio=round(
                    float(aggregate["avg_profit_drawdown_ratio"]),
                    6,
                ),
                risk_quality_pass_rate=round(
                    float(aggregate["risk_quality_passes"]) / closed_count,
                    6,
                )
                if closed_count
                else 0.0,
                snapshot_count=snapshot_count,
                event_count=event_count,
                open_position_count=len(positions),
                closed_trade_count=closed_count,
                positions=positions,
                recent_events=recent_events,
                recent_trades=recent_trades,
                quality_buckets=quality_buckets,
                guard_buckets=guard_buckets,
                daily_audits=daily_audits,
                next_action="每天 schedule 或 watch 跑完后，用 paper-db 复盘买卖动作、收益和回撤质量。",
            )

    def build_report_empty_existing(self) -> PaperTradeDatabaseReport:
        return PaperTradeDatabaseReport(
            report_id="paper-trade-database",
            database_path=str(self._path),
            status="empty",
            account_id="",
            last_trade_date="",
            cash=0.0,
            equity=0.0,
            total_realized_pnl=0.0,
            total_realized_return_pct=0.0,
            win_rate=0.0,
            average_realized_return_pct=0.0,
            average_profit_drawdown_ratio=0.0,
            risk_quality_pass_rate=0.0,
            snapshot_count=0,
            event_count=0,
            open_position_count=0,
            closed_trade_count=0,
            positions=(),
            recent_events=(),
            recent_trades=(),
            quality_buckets=(),
            guard_buckets=(),
            daily_audits=(),
            next_action="SQLite 文件存在但还没有模拟盘快照，先运行一次 morning/watch/risk。",
        )

    def _build_daily_audits(
        self,
        connection: sqlite3.Connection,
        account_id: str,
        limit: int,
    ) -> tuple[PaperTradeDailyAudit, ...]:
        rows = connection.execute(
            """
            with days as (
                select trade_date from trade_events where account_id = ?
                union
                select closed_at as trade_date from closed_trades where account_id = ?
            )
            select trade_date from days
            order by trade_date desc
            limit ?
            """,
            (account_id, account_id, max(0, limit)),
        ).fetchall()
        return tuple(
            self._daily_audit_for_date(
                connection,
                account_id,
                str(row["trade_date"]),
            )
            for row in rows
        )

    def _daily_audit_for_date(
        self,
        connection: sqlite3.Connection,
        account_id: str,
        trade_date: str,
    ) -> PaperTradeDailyAudit:
        events = connection.execute(
            """
            select * from trade_events
            where account_id = ? and trade_date = ?
            order by created_at asc, event_id asc
            """,
            (account_id, trade_date),
        ).fetchall()
        trades = connection.execute(
            """
            select * from closed_trades
            where account_id = ? and closed_at = ?
            order by trade_id asc
            """,
            (account_id, trade_date),
        ).fetchall()
        buy_count = sum(1 for row in events if str(row["event_type"]) == "paper_buy")
        sell_count = sum(
            1
            for row in events
            if str(row["event_type"])
            in {
                "t1_sell",
                "take_profit",
                "mainline_fade_exit",
                "discipline_exit",
            }
        )
        blocked_count = sum(1 for row in events if str(row["event_type"]) == "blocked")
        warning_count = sum(1 for row in events if str(row["event_type"]) == "stop_warning")
        realized_pnl = round(sum(float(row["realized_pnl"]) for row in trades), 2)
        realized_return_pct = round(
            sum(float(row["realized_pnl_pct"]) for row in trades),
            6,
        )
        profit_drawdown_values = [
            float(row["profit_drawdown_ratio"])
            for row in trades
            if float(row["profit_drawdown_ratio"] or 0.0) > 0
        ]
        average_profit_drawdown_ratio = round(
            sum(profit_drawdown_values) / len(profit_drawdown_values),
            6,
        ) if profit_drawdown_values else 0.0
        risk_quality_pass_rate = (
            round(
                sum(
                    1
                    for row in trades
                    if float(row["realized_pnl_pct"]) > float(row["max_adverse_pct"])
                )
                / len(trades),
                6,
            )
            if trades
            else 0.0
        )
        symbols = tuple(
            sorted(
                {
                    self._format_symbol_name(str(row["name"]), str(row["symbol"]))
                    for row in events
                    if str(row["symbol"])
                }
                | {
                    self._format_symbol_name(str(row["name"]), str(row["symbol"]))
                    for row in trades
                    if str(row["symbol"])
                }
            )
        )
        action, action_label = self._daily_action(
            buy_count=buy_count,
            sell_count=sell_count,
            blocked_count=blocked_count,
            warning_count=warning_count,
        )
        return PaperTradeDailyAudit(
            trade_date=trade_date,
            action=action,
            action_label=action_label,
            event_count=len(events),
            buy_count=buy_count,
            sell_count=sell_count,
            blocked_count=blocked_count,
            warning_count=warning_count,
            realized_pnl=realized_pnl,
            realized_return_pct=realized_return_pct,
            average_profit_drawdown_ratio=average_profit_drawdown_ratio,
            risk_quality_pass_rate=risk_quality_pass_rate,
            symbols=symbols,
            summary=self._daily_audit_summary(
                action_label=action_label,
                symbols=symbols,
                realized_pnl=realized_pnl,
                realized_return_pct=realized_return_pct,
                buy_count=buy_count,
                sell_count=sell_count,
                blocked_count=blocked_count,
                warning_count=warning_count,
            ),
            next_action=self._daily_audit_next_action(
                action=action,
                risk_quality_pass_rate=risk_quality_pass_rate,
                average_profit_drawdown_ratio=average_profit_drawdown_ratio,
                trade_count=len(trades),
            ),
        )

    def _build_quality_buckets(
        self,
        connection: sqlite3.Connection,
        account_id: str,
    ) -> tuple[PaperTradeQualityBucket, ...]:
        rows = connection.execute(
            """
            select
                case
                    when entry_turnover_quality_score >= 86 then 'strong_turnover_dragon'
                    when entry_turnover_quality_score >= 72 then 'valid_turnover_dragon'
                    when entry_turnover_quality_score > 0 then 'weak_turnover_quality'
                    else 'unscored_legacy'
                end as bucket,
                min(entry_turnover_quality_score) as min_score,
                max(entry_turnover_quality_score) as max_score,
                count(*) as trade_count,
                coalesce(sum(realized_pnl), 0) as total_pnl,
                coalesce(avg(realized_pnl_pct), 0) as avg_return,
                coalesce(avg(case when profit_drawdown_ratio > 0 then profit_drawdown_ratio end), 0) as avg_profit_drawdown_ratio,
                coalesce(sum(case when success = 1 then 1 else 0 end), 0) as wins,
                coalesce(sum(case when realized_pnl_pct > max_adverse_pct then 1 else 0 end), 0) as risk_quality_passes
            from closed_trades
            where account_id = ?
            group by bucket
            order by max_score desc, trade_count desc
            """,
            (account_id,),
        ).fetchall()
        return tuple(
            PaperTradeQualityBucket(
                bucket=str(row["bucket"]),
                min_score=round(float(row["min_score"] or 0.0), 2),
                max_score=round(float(row["max_score"] or 0.0), 2),
                trade_count=int(row["trade_count"]),
                win_rate=self._safe_rate(row["wins"], row["trade_count"]),
                average_realized_return_pct=round(float(row["avg_return"]), 6),
                average_profit_drawdown_ratio=round(
                    float(row["avg_profit_drawdown_ratio"]),
                    6,
                ),
                total_realized_pnl=round(float(row["total_pnl"]), 2),
                risk_quality_pass_rate=self._safe_rate(
                    row["risk_quality_passes"],
                    row["trade_count"],
                ),
                next_action=self._quality_bucket_action(
                    str(row["bucket"]),
                    int(row["trade_count"]),
                    self._safe_rate(row["wins"], row["trade_count"]),
                    float(row["avg_return"]),
                    self._safe_rate(row["risk_quality_passes"], row["trade_count"]),
                ),
            )
            for row in rows
        )

    def _build_guard_buckets(
        self,
        connection: sqlite3.Connection,
        account_id: str,
    ) -> tuple[PaperTradeGuardBucket, ...]:
        rows = connection.execute(
            """
            select
                case
                    when entry_guard_action = 'allow_full' then 'allow_full'
                    when entry_guard_action = 'allow_reduced' then 'allow_reduced'
                    when entry_guard_action != '' then entry_guard_action
                    else 'unscored_legacy'
                end as bucket,
                count(*) as trade_count,
                coalesce(sum(realized_pnl), 0) as total_pnl,
                coalesce(avg(realized_pnl_pct), 0) as avg_return,
                coalesce(avg(case when profit_drawdown_ratio > 0 then profit_drawdown_ratio end), 0) as avg_profit_drawdown_ratio,
                coalesce(sum(case when success = 1 then 1 else 0 end), 0) as wins,
                coalesce(sum(case when realized_pnl_pct > max_adverse_pct then 1 else 0 end), 0) as risk_quality_passes,
                coalesce(avg(nullif(entry_guard_suggested_position_pct, 0)), 0) as avg_position_pct
            from closed_trades
            where account_id = ?
            group by bucket
            order by
                case bucket
                    when 'allow_full' then 1
                    when 'allow_reduced' then 2
                    when 'stand_aside' then 3
                    when 'unscored_legacy' then 99
                    else 50
                end,
                trade_count desc
            """,
            (account_id,),
        ).fetchall()
        return tuple(
            PaperTradeGuardBucket(
                bucket=str(row["bucket"]),
                trade_count=int(row["trade_count"]),
                win_rate=self._safe_rate(row["wins"], row["trade_count"]),
                average_realized_return_pct=round(float(row["avg_return"]), 6),
                average_profit_drawdown_ratio=round(
                    float(row["avg_profit_drawdown_ratio"]),
                    6,
                ),
                total_realized_pnl=round(float(row["total_pnl"]), 2),
                risk_quality_pass_rate=self._safe_rate(
                    row["risk_quality_passes"],
                    row["trade_count"],
                ),
                average_suggested_position_pct=round(
                    float(row["avg_position_pct"]),
                    6,
                ),
                next_action=self._guard_bucket_action(
                    str(row["bucket"]),
                    int(row["trade_count"]),
                    self._safe_rate(row["wins"], row["trade_count"]),
                    float(row["avg_return"]),
                    self._safe_rate(row["risk_quality_passes"], row["trade_count"]),
                ),
            )
            for row in rows
        )

    @staticmethod
    def _format_symbol_name(name: str, symbol: str) -> str:
        return f"{name}({symbol})" if name else symbol

    @staticmethod
    def _daily_action(
        *,
        buy_count: int,
        sell_count: int,
        blocked_count: int,
        warning_count: int,
    ) -> tuple[str, str]:
        if sell_count:
            return ("sell", "卖出/止盈止损")
        if buy_count:
            return ("buy", "买入")
        if blocked_count:
            return ("stand_aside", "空仓/阻断")
        if warning_count:
            return ("risk_warning", "风险预警")
        return ("observe", "观察")

    @staticmethod
    def _daily_audit_summary(
        *,
        action_label: str,
        symbols: tuple[str, ...],
        realized_pnl: float,
        realized_return_pct: float,
        buy_count: int,
        sell_count: int,
        blocked_count: int,
        warning_count: int,
    ) -> str:
        names = "、".join(symbols[:3]) if symbols else "无具体标的"
        return (
            f"{action_label}：{names}；买入 {buy_count}，卖出 {sell_count}，"
            f"阻断 {blocked_count}，预警 {warning_count}；"
            f"当日闭环收益 {realized_pnl:.2f} / {realized_return_pct:.2%}。"
        )

    @staticmethod
    def _daily_audit_next_action(
        *,
        action: str,
        risk_quality_pass_rate: float,
        average_profit_drawdown_ratio: float,
        trade_count: int,
    ) -> str:
        if action == "buy":
            return "买入已入库，下一步只盯 T+1、止损预警和主升保护，不临盘加仓。"
        if action == "sell":
            if trade_count and (
                risk_quality_pass_rate < 1.0 or average_profit_drawdown_ratio < 1.0
            ):
                return "卖出已闭环但收益质量不够，后续应复盘买点或卖点是否过早/过晚。"
            return "卖出已闭环，继续观察该类买点是否能稳定贡献正收益和低回撤。"
        if action == "stand_aside":
            return "今天空仓是有效动作，记录阻断原因，避免为了交易频率硬做。"
        if action == "risk_warning":
            return "风险预警日不加仓，下一交易日按 T+1 卖点纪律处理。"
        return "继续观察，等待策略决策和模拟盘指挥单给出明确买卖点。"

    @staticmethod
    def _safe_rate(numerator: object, denominator: object) -> float:
        denominator_float = float(denominator or 0.0)
        if denominator_float <= 0:
            return 0.0
        return round(float(numerator or 0.0) / denominator_float, 6)

    @staticmethod
    def _quality_bucket_action(
        bucket: str,
        trade_count: int,
        win_rate: float,
        average_return: float,
        risk_quality_pass_rate: float,
    ) -> str:
        if bucket == "unscored_legacy":
            return "历史未评分样本只作参考，不用于放宽买点。"
        if trade_count < 3:
            return "样本不足，继续模拟盘观察，不急着提高仓位。"
        if win_rate >= 0.6 and average_return > 0 and risk_quality_pass_rate >= 0.6:
            return "质量段表现合格，可维持当前买点规则。"
        return "质量段表现偏弱，后续应降权或加入硬拦截。"

    @staticmethod
    def _guard_bucket_action(
        bucket: str,
        trade_count: int,
        win_rate: float,
        average_return: float,
        risk_quality_pass_rate: float,
    ) -> str:
        if bucket == "unscored_legacy":
            return "历史未记录守门动作，只作对照，不用于放宽仓位。"
        if trade_count < 3:
            return "守门样本不足，继续小样本跟踪，不急着放大仓位。"
        if win_rate >= 0.6 and average_return > 0 and risk_quality_pass_rate >= 0.6:
            if bucket == "allow_reduced":
                return "降仓后的收益质量合格，可继续用作防守档位。"
            if bucket == "allow_full":
                return "满仓放行表现合格，可维持当前仓位规则。"
            return "该守门动作表现合格，可继续观察。"
        if bucket == "allow_full":
            return "满仓放行表现偏弱，后续应提高门槛或自动降仓。"
        if bucket == "allow_reduced":
            return "降仓后仍偏弱，说明该类买点应暂停而不是试错。"
        return "该守门动作收益质量偏弱，后续应收紧。"
