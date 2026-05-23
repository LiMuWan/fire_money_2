"""SQLite schema and small codecs for the paper-trading mirror."""

from __future__ import annotations

import json
import sqlite3


PAPER_TRADE_SCHEMA_SQL = """
create table if not exists account_snapshots (
    account_id text not null,
    last_trade_date text not null,
    cash real not null,
    initial_cash real not null,
    equity real not null,
    max_position_pct real not null,
    max_daily_trades integer not null,
    daily_trade_count integer not null,
    open_position_count integer not null,
    closed_trade_count integer not null,
    event_count integer not null,
    synced_at text not null,
    primary key (account_id, synced_at)
);

create table if not exists positions (
    account_id text not null,
    symbol text not null,
    name text not null,
    quantity integer not null,
    entry_price real not null,
    latest_price real not null,
    stop_loss real not null,
    position_value real not null,
    unrealized_pnl real not null,
    unrealized_pnl_pct real not null,
    opened_at text not null,
    position_label text not null,
    opened_score real not null,
    can_sell_today integer not null,
    status text not null,
    risk_note text not null,
    peak_price real not null,
    trough_price real not null default 0,
    planned_stop_risk_pct real not null default 0,
    planned_first_target_return_pct real not null default 0,
    planned_reward_risk_ratio real not null default 0,
    max_intratrade_drawdown_budget_pct real not null default 0,
    entry_turnover_quality_score real not null default 0,
    entry_turnover_quality_label text not null default '',
    entry_turnover_quality_notes text not null default '[]',
    entry_guard_status text not null default '',
    entry_guard_action text not null default '',
    entry_guard_suggested_position_pct real not null default 0,
    entry_guard_reason text not null default '',
    entry_guard_quality_bucket text not null default '',
    entry_guard_quality_sample_count integer not null default 0,
    entry_guard_quality_win_rate real not null default 0,
    entry_guard_quality_average_return_pct real not null default 0,
    entry_guard_quality_pass_rate real not null default 0,
    primary key (account_id, symbol, opened_at)
);

create table if not exists trade_events (
    event_id text primary key,
    account_id text not null,
    event_type text not null,
    symbol text not null,
    name text not null,
    trade_date text not null,
    price real not null,
    quantity integer not null,
    amount real not null,
    message text not null,
    created_at text not null
);

create table if not exists closed_trades (
    trade_id text primary key,
    account_id text not null,
    symbol text not null,
    name text not null,
    opened_at text not null,
    closed_at text not null,
    entry_price real not null,
    exit_price real not null,
    quantity integer not null,
    entry_amount real not null,
    exit_amount real not null,
    realized_pnl real not null,
    realized_pnl_pct real not null,
    holding_trade_days integer not null,
    exit_reason text not null,
    position_label text not null,
    success integer not null,
    warning_count integer not null,
    max_favorable_pct real not null default 0,
    max_adverse_pct real not null default 0,
    profit_drawdown_ratio real not null default 0,
    planned_stop_risk_pct real not null default 0,
    planned_first_target_return_pct real not null default 0,
    planned_reward_risk_ratio real not null default 0,
    max_intratrade_drawdown_budget_pct real not null default 0,
    entry_turnover_quality_score real not null default 0,
    entry_turnover_quality_label text not null default '',
    entry_turnover_quality_notes text not null default '[]',
    entry_guard_status text not null default '',
    entry_guard_action text not null default '',
    entry_guard_suggested_position_pct real not null default 0,
    entry_guard_reason text not null default '',
    entry_guard_quality_bucket text not null default '',
    entry_guard_quality_sample_count integer not null default 0,
    entry_guard_quality_win_rate real not null default 0,
    entry_guard_quality_average_return_pct real not null default 0,
    entry_guard_quality_pass_rate real not null default 0
);
"""


PAPER_TRADE_LEGACY_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("positions", "trough_price", "real not null default 0"),
    ("closed_trades", "max_favorable_pct", "real not null default 0"),
    ("closed_trades", "max_adverse_pct", "real not null default 0"),
    ("closed_trades", "profit_drawdown_ratio", "real not null default 0"),
)


PAPER_TRADE_SHARED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("planned_stop_risk_pct", "real not null default 0"),
    ("planned_first_target_return_pct", "real not null default 0"),
    ("planned_reward_risk_ratio", "real not null default 0"),
    ("max_intratrade_drawdown_budget_pct", "real not null default 0"),
    ("entry_turnover_quality_score", "real not null default 0"),
    ("entry_turnover_quality_label", "text not null default ''"),
    ("entry_turnover_quality_notes", "text not null default '[]'"),
    ("entry_guard_status", "text not null default ''"),
    ("entry_guard_action", "text not null default ''"),
    ("entry_guard_suggested_position_pct", "real not null default 0"),
    ("entry_guard_reason", "text not null default ''"),
    ("entry_guard_quality_bucket", "text not null default ''"),
    ("entry_guard_quality_sample_count", "integer not null default 0"),
    ("entry_guard_quality_win_rate", "real not null default 0"),
    ("entry_guard_quality_average_return_pct", "real not null default 0"),
    ("entry_guard_quality_pass_rate", "real not null default 0"),
)


def ensure_paper_trade_schema(connection: sqlite3.Connection) -> None:
    """Create and migrate the paper-trading SQLite mirror."""

    connection.executescript(PAPER_TRADE_SCHEMA_SQL)
    for table, column, definition in PAPER_TRADE_LEGACY_COLUMNS:
        add_column_if_missing(connection, table, column, definition)
    for table in ("positions", "closed_trades"):
        for column, definition in PAPER_TRADE_SHARED_COLUMNS:
            add_column_if_missing(connection, table, column, definition)


def add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        str(row[1]) for row in connection.execute(f"pragma table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"alter table {table} add column {column} {definition}")


def encode_notes(notes: tuple[str, ...]) -> str:
    return json.dumps(list(notes), ensure_ascii=False)


def decode_notes(payload: str | None) -> tuple[str, ...]:
    if not payload:
        return ()
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return tuple(line for line in str(payload).splitlines() if line)
    if isinstance(decoded, list):
        return tuple(str(item) for item in decoded if item is not None)
    if isinstance(decoded, str) and decoded:
        return (decoded,)
    return ()


__all__ = [
    "decode_notes",
    "encode_notes",
    "ensure_paper_trade_schema",
]
