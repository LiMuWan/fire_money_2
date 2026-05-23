"""Audit backtest opportunities that the live paper loop failed to capture."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from shared.contracts import (
    MissedOpportunityItem,
    MissedOpportunityReport,
    NotificationRecord,
    PaperAccount,
)
from server.firemoney_server.domain.paper_position_sizing import (
    simulate_small_account_trades,
)
from tools import research_limit_up_board_profit_matrix as board_matrix


class PaperStoreLike(Protocol):
    def load(self) -> PaperAccount:
        ...


class NotificationStoreLike(Protocol):
    def load(self) -> tuple[NotificationRecord, ...]:
        ...


class SchedulerRunStoreLike(Protocol):
    def load(self, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        ...


class SmallAccountSettingsLike(Protocol):
    initial_cash: float
    small_account_min_lot_shares: int
    small_account_target_position_pct: float
    small_account_max_position_pct: float


class MissedOpportunityService:
    """Compares research opportunities with actual paper-trading execution."""

    def __init__(
        self,
        *,
        settings: SmallAccountSettingsLike,
        paper_store: PaperStoreLike,
        notification_store: NotificationStoreLike,
        scheduler_run_store: SchedulerRunStoreLike,
    ) -> None:
        self._settings = settings
        self._paper_store = paper_store
        self._notification_store = notification_store
        self._scheduler_run_store = scheduler_run_store

    def build_report(
        self,
        *,
        start_date: str,
        end_date: str,
        cache_dir: str | Path | None = None,
        limit: int = 20,
    ) -> MissedOpportunityReport:
        start = board_matrix.sm.parse_iso_date(start_date)
        end = board_matrix.sm.parse_iso_date(end_date)
        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        universe, histories = board_matrix.load_cached_research_data(
            cache_path,
            start,
            end,
        )
        candidates = board_matrix.build_board_candidates(universe, histories, start, end)
        result = board_matrix.evaluate_case(
            candidates=candidates,
            histories=histories,
            entry_case=board_matrix.shadow_default_entry_case(),
            exit_case=board_matrix.shadow_default_exit_case(),
            rank_case="score",
            position_pct=0.08,
            roundtrip_cost_pct=0.0015,
        )
        small_trades, _skipped = simulate_small_account_trades(
            trades=list(result.get("one_position_trades", [])),
            initial_cash=float(self._settings.initial_cash),
            lot_shares=int(self._settings.small_account_min_lot_shares),
            target_position_pct=float(self._settings.small_account_target_position_pct),
            max_position_pct=float(self._settings.small_account_max_position_pct),
        )
        account = self._paper_store.load()
        notifications = self._notification_store.load()
        schedule_runs = self._scheduler_run_store.load(limit=500)
        items = tuple(
            self._build_item(
                trade=trade,
                account=account,
                notifications=notifications,
                schedule_runs=schedule_runs,
            )
            for trade in small_trades
        )
        caught_count = sum(1 for item in items if item.paper_status == "caught")
        missed = tuple(item for item in items if item.paper_status != "caught")
        missed_profit = tuple(item for item in missed if item.account_return_pct > 0)
        missed_account_return_pct = sum(item.account_return_pct for item in missed_profit)
        status = "ready" if not missed_profit else "warning"
        summary = (
            f"回测机会 {len(items)} 笔，真实模拟盘抓到 {caught_count} 笔，"
            f"错失 {len(missed)} 笔；其中错失盈利机会 {len(missed_profit)} 笔，"
            f"按小账户回测口径约少赚 {missed_account_return_pct:.2%}。"
        )
        return MissedOpportunityReport(
            report_id=f"missed-opportunities-{start_date}-to-{end_date}",
            start_date=start_date,
            end_date=end_date,
            status=status,
            summary=summary,
            backtest_trade_count=len(items),
            caught_count=caught_count,
            missed_count=len(missed),
            missed_profit_count=len(missed_profit),
            missed_account_return_pct=round(missed_account_return_pct, 6),
            items=items[: max(0, limit)],
            next_action=(
                "逐日复盘错失盈利机会：优先修 watch/open 候选映射、行情源可用性和调度覆盖。"
                if missed_profit
                else "当前区间没有错失盈利机会，继续保持值守并扩大观察窗口。"
            ),
        )

    def _build_item(
        self,
        *,
        trade: Any,
        account: PaperAccount,
        notifications: tuple[NotificationRecord, ...],
        schedule_runs: tuple[dict[str, Any], ...],
    ) -> MissedOpportunityItem:
        trade_date = str(trade.entry_date)
        symbol = str(trade.symbol)
        paper_status = self._paper_status(account, trade_date, symbol)
        watch_status = self._watch_status(schedule_runs, trade_date)
        notification_status = self._notification_status(notifications, trade_date, symbol)
        diagnosis = self._diagnosis(
            paper_status=paper_status,
            watch_status=watch_status,
            notification_status=notification_status,
            trade=trade,
        )
        return MissedOpportunityItem(
            trade_date=trade_date,
            symbol=symbol,
            name=str(trade.name),
            entry_price=float(trade.entry_price),
            net_return_pct=float(trade.net_return_pct),
            account_return_pct=float(trade.account_return_pct),
            position_pct=float(trade.position_pct),
            quantity=int(trade.quantity),
            paper_status=paper_status,
            watch_status=watch_status,
            notification_status=notification_status,
            diagnosis=diagnosis,
            next_action=self._next_action(paper_status, watch_status, notification_status),
        )

    @staticmethod
    def _paper_status(account: PaperAccount, trade_date: str, symbol: str) -> str:
        for position in account.positions:
            if position.symbol == symbol and position.opened_at == trade_date:
                return "caught"
        for event in account.events:
            if event.symbol == symbol and event.trade_date == trade_date:
                return "caught"
        for closed in account.closed_trades:
            if closed.symbol == symbol and closed.opened_at == trade_date:
                return "caught"
        return "missed"

    @staticmethod
    def _watch_status(schedule_runs: tuple[dict[str, Any], ...], trade_date: str) -> str:
        tasks: list[dict[str, Any]] = []
        for record in schedule_runs:
            if str(record.get("trade_date")) != trade_date:
                continue
            run = record.get("run") or {}
            for task in run.get("tasks", ()) or ():
                if task.get("mode") == "watch":
                    tasks.append(task)
        if not tasks:
            return "no_watch_run"
        open_tasks = [item for item in tasks if item.get("phase") == "open"]
        if not open_tasks:
            return "watch_no_open_phase"
        if any(item.get("status") == "completed" for item in open_tasks):
            return "watch_open_completed"
        if any(item.get("status") == "failed" for item in open_tasks):
            return "watch_open_failed"
        return "watch_open_not_completed"

    @staticmethod
    def _notification_status(
        notifications: tuple[NotificationRecord, ...],
        trade_date: str,
        symbol: str,
    ) -> str:
        same_day = [item for item in notifications if item.trade_date == trade_date]
        if not same_day:
            return "no_notification"
        action_records = [
            item
            for item in same_day
            if symbol in item.message and item.workflow in {"watch:open", "paper-decision"}
        ]
        if action_records:
            best = action_records[0].status
            return best.value if hasattr(best, "value") else str(best)
        if any(item.workflow == "watch:open" for item in same_day):
            return "watch_open_without_symbol"
        return "notification_without_action"

    @staticmethod
    def _diagnosis(
        *,
        paper_status: str,
        watch_status: str,
        notification_status: str,
        trade: Any,
    ) -> str:
        if paper_status == "caught":
            return "真实模拟盘已抓到该机会。"
        if watch_status == "no_watch_run":
            return "该日没有值守审计记录，优先检查 schedule/beta-start 是否常驻。"
        if watch_status == "watch_no_open_phase":
            return "该日有调度记录但缺少 open 阶段，开盘确认链路未覆盖。"
        if watch_status == "watch_open_completed" and notification_status == "watch_open_without_symbol":
            return "open 阶段跑过但未映射到该回测候选，需修复实时候选与日线研究口径差异。"
        if watch_status == "watch_open_completed":
            return "open 阶段跑过但未写模拟买入，需检查守门、持仓、日内数据和候选拦截。"
        if float(getattr(trade, "account_return_pct", 0.0)) > 0:
            return "这是错失盈利机会，应优先复盘运行链路。"
        return "错失机会为亏损或小幅波动，暂不作为放宽买点依据。"

    @staticmethod
    def _next_action(
        paper_status: str,
        watch_status: str,
        notification_status: str,
    ) -> str:
        if paper_status == "caught":
            return "继续用 paper-db 跟踪卖点和收益质量。"
        if watch_status == "no_watch_run":
            return "修复常驻调度和开盘值守覆盖。"
        if watch_status == "watch_open_completed" and notification_status == "watch_open_without_symbol":
            return "对齐 watch/open 实时候选池与 paper-backtest 日线候选池。"
        return "复盘当日守门、持仓、行情源和候选拦截原因。"


__all__ = ["MissedOpportunityService"]
