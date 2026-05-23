"""Local paper-trading account persistence for one-to-two strategy."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any

from server.firemoney_server.infrastructure.paper_database import PaperTradeDatabase
from server.firemoney_server.infrastructure.paper_store_codec import PaperStoreCodec
from server.firemoney_server.domain.paper_position_sizing import (
    resolve_paper_position_size,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    load_one_to_two_settings,
)
from shared.contracts import (
    OneToTwoCandidate,
    OneToTwoEventType,
    PaperAccount,
    PaperPosition,
    PaperTradeEvent,
    PaperTradeRecord,
    PaperTradingGuardDecision,
    PaperTradeStatus,
)


DEFAULT_PAPER_STORE_PATH = Path(".firemoney") / "paper_trades.json"


class PaperTradeStore:
    """Stores an event-driven paper account in local JSON."""

    def __init__(
        self,
        path: str | Path = DEFAULT_PAPER_STORE_PATH,
        database_path: str | Path | None = None,
        initial_cash: float | None = None,
        max_position_pct: float | None = None,
        max_daily_trades: int = 1,
    ) -> None:
        self._path = Path(path)
        self._database = PaperTradeDatabase(
            database_path or self._path.with_suffix(".sqlite3")
        )
        settings = load_one_to_two_settings()
        self._settings = settings
        self._initial_cash = float(
            settings.initial_cash if initial_cash is None else initial_cash
        )
        self._max_position_pct = float(
            settings.max_position_pct if max_position_pct is None else max_position_pct
        )
        self._max_daily_trades = int(max_daily_trades)
        self._codec = PaperStoreCodec(
            initial_cash=self._initial_cash,
            max_position_pct=self._max_position_pct,
            max_daily_trades=self._max_daily_trades,
        )

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> PaperAccount:
        if not self._path.exists():
            return self._codec.empty_account()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            account = self._codec.from_payload(payload)
            if self._is_stale_empty_account(account):
                return self._codec.empty_account()
            return self._normalize_account_basis(account)
        except (JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            return self._codec.empty_account()

    def _is_stale_empty_account(self, account: PaperAccount) -> bool:
        if account.positions or account.events or account.closed_trades:
            return False
        return (
            abs(float(account.initial_cash) - self._initial_cash) > 0.01
            or abs(float(account.max_position_pct) - self._max_position_pct) > 0.0001
        )

    def _normalize_account_basis(self, account: PaperAccount) -> PaperAccount:
        if account.positions:
            return account
        if (
            abs(float(account.initial_cash) - self._initial_cash) <= 0.01
            and abs(float(account.max_position_pct) - self._max_position_pct) <= 0.0001
        ):
            return account
        realized_pnl = sum(float(trade.realized_pnl) for trade in account.closed_trades)
        normalized_equity = round(max(0.0, self._initial_cash + realized_pnl), 2)
        return PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=normalized_equity,
            initial_cash=self._initial_cash,
            equity=normalized_equity,
            max_position_pct=self._max_position_pct,
            max_daily_trades=self._max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=account.positions,
            events=account.events,
            closed_trades=account.closed_trades,
        )

    def save(self, account: PaperAccount) -> PaperAccount:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._codec.to_payload(account), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self._database is not None:
            self._database.sync_account(account)
        return account

    def prepare_for_trade_date(self, trade_date: str) -> PaperAccount:
        account = self.load()
        if not account.last_trade_date:
            return self.save(
                PaperAccount(
                    account_id=account.account_id,
                    last_trade_date=trade_date,
                    cash=account.cash,
                    initial_cash=account.initial_cash,
                    equity=account.equity,
                    max_position_pct=account.max_position_pct,
                    max_daily_trades=account.max_daily_trades,
                    daily_trade_count=0,
                    positions=account.positions,
                    events=account.events,
                    closed_trades=account.closed_trades,
                )
            )
        if trade_date < account.last_trade_date:
            return account
        if account.last_trade_date == trade_date:
            return account
        positions = tuple(
            PaperPosition(
                symbol=position.symbol,
                name=position.name,
                quantity=position.quantity,
                entry_price=position.entry_price,
                latest_price=position.latest_price,
                stop_loss=position.stop_loss,
                position_value=position.position_value,
                unrealized_pnl=position.unrealized_pnl,
                unrealized_pnl_pct=position.unrealized_pnl_pct,
                opened_at=position.opened_at,
                position_label=position.position_label,
                opened_score=position.opened_score,
                can_sell_today=True,
                status=position.status,
                risk_note="已进入下一交易日，若继续跌破止损可模拟卖出。",
                exit_plan=position.exit_plan,
                mainline_continuity=position.mainline_continuity,
                peak_price=position.peak_price,
                trough_price=position.trough_price,
                **self._planned_position_fields(position),
                **self._entry_evidence_position_fields(position),
            )
            for position in account.positions
        )
        return self.save(
            PaperAccount(
                account_id=account.account_id,
                last_trade_date=trade_date,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.equity,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=0,
                positions=positions,
                events=account.events,
                closed_trades=account.closed_trades,
            )
        )

    def buy_candidate(
        self,
        candidate: OneToTwoCandidate,
        guard_decision: PaperTradingGuardDecision | None = None,
    ) -> PaperAccount:
        account = self.prepare_for_trade_date(candidate.trade_date)
        if candidate.status != "ready":
            return self.save(
                self._append_event(
                    account,
                    OneToTwoEventType.BLOCKED,
                    candidate,
                    candidate.latest_price,
                    0,
                    "候选未达到模拟买入条件",
                )
            )
        if account.daily_trade_count >= account.max_daily_trades or account.positions:
            return self.save(
                self._append_event(
                    account,
                    OneToTwoEventType.BLOCKED,
                    candidate,
                    candidate.latest_price,
                    0,
                    "模拟盘当日交易次数已满或已有持仓",
                )
            )
        position_size = resolve_paper_position_size(
            settings=self._settings,
            account=account,
            candidate=candidate,
        )
        quantity = position_size.quantity
        amount = position_size.cash_budget
        if quantity <= 0 or amount > account.cash:
            return self.save(
                self._append_event(
                    account,
                    OneToTwoEventType.BLOCKED,
                    candidate,
                    candidate.latest_price,
                    0,
                    position_size.note or "模拟资金不足或买入数量不足一手",
                )
            )
        position = PaperPosition(
            symbol=candidate.symbol,
            name=candidate.name,
            quantity=quantity,
            entry_price=candidate.entry_price,
            latest_price=candidate.latest_price,
            stop_loss=candidate.stop_loss,
            position_value=amount,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            opened_at=candidate.trade_date,
            position_label=candidate.position_profile.label,
            opened_score=candidate.score,
            can_sell_today=False,
            status=PaperTradeStatus.HOLDING,
            risk_note=(
                candidate.exit_plan.summary
                if candidate.exit_plan
                else "严格 T+1：当天跌破止损只预警，不模拟卖出。"
            ),
            exit_plan=candidate.exit_plan,
            mainline_continuity=candidate.mainline_continuity,
            peak_price=candidate.latest_price,
            trough_price=candidate.latest_price,
            planned_stop_risk_pct=self._planned_stop_risk_pct(candidate),
            planned_first_target_return_pct=self._planned_first_target_return_pct(
                candidate
            ),
            planned_reward_risk_ratio=self._planned_reward_risk_ratio(candidate),
            max_intratrade_drawdown_budget_pct=(
                self._max_intratrade_drawdown_budget_pct(candidate)
            ),
            entry_turnover_quality_score=round(candidate.turnover_quality_score, 2),
            entry_turnover_quality_label=candidate.turnover_quality_label,
            entry_turnover_quality_notes=candidate.turnover_quality_notes,
            **self._entry_guard_fields(guard_decision),
        )
        account = PaperAccount(
            account_id=account.account_id,
            last_trade_date=candidate.trade_date,
            cash=round(account.cash - amount, 2),
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count + 1,
            positions=(position,),
            events=account.events,
            closed_trades=account.closed_trades,
        )
        account = self._append_event(
            account,
            OneToTwoEventType.PAPER_BUY,
            candidate,
            candidate.entry_price,
            quantity,
            "模拟买入，一进二事件驱动账本已记录。",
        )
        return self.save(self._revalue(account, candidate.latest_price))

    def record_candidate_event(
        self,
        candidate: OneToTwoCandidate,
        message: str,
        event_type: OneToTwoEventType = OneToTwoEventType.CANDIDATE_SELECTED,
    ) -> PaperAccount:
        account = self.prepare_for_trade_date(candidate.trade_date)
        exists = any(
            event.symbol == candidate.symbol
            and event.trade_date == candidate.trade_date
            and event.event_type == event_type
            for event in account.events
        )
        if exists:
            return account
        return self.save(
            self._append_event(
                account,
                event_type,
                candidate,
                candidate.latest_price,
                0,
                message,
            )
        )

    def update_risk(self, candidate: OneToTwoCandidate) -> PaperAccount:
        account = self.prepare_for_trade_date(candidate.trade_date)
        if not account.positions:
            return account
        position = account.positions[0]
        if position.symbol != candidate.symbol:
            return account
        account = self._revalue(account, candidate.latest_price)
        account = self._refresh_position_context(account, candidate)
        position = account.positions[0]
        if candidate.latest_price >= position.stop_loss:
            return self.save(account)
        if not position.can_sell_today:
            already_warned = any(
                event.symbol == position.symbol
                and event.trade_date == candidate.trade_date
                and event.event_type == OneToTwoEventType.STOP_WARNING
                for event in account.events
            )
            warned = PaperPosition(
                symbol=position.symbol,
                name=position.name,
                quantity=position.quantity,
                entry_price=position.entry_price,
                latest_price=candidate.latest_price,
                stop_loss=position.stop_loss,
                position_value=position.position_value,
                unrealized_pnl=position.unrealized_pnl,
                unrealized_pnl_pct=position.unrealized_pnl_pct,
                opened_at=position.opened_at,
                position_label=position.position_label,
                opened_score=position.opened_score,
                can_sell_today=position.can_sell_today,
                status=PaperTradeStatus.WARNING,
                risk_note="跌破止损但受 T+1 约束，次日仍弱再模拟卖出。",
                exit_plan=position.exit_plan,
                mainline_continuity=candidate.mainline_continuity or position.mainline_continuity,
                peak_price=position.peak_price,
                trough_price=position.trough_price,
                **self._planned_position_fields(position),
                **self._entry_evidence_position_fields(position),
            )
            account = PaperAccount(
                account_id=account.account_id,
                last_trade_date=account.last_trade_date,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.equity,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=account.daily_trade_count,
                positions=(warned,),
                events=account.events,
                closed_trades=account.closed_trades,
            )
            if already_warned:
                return self.save(account)
            account = self._append_event(
                account,
                OneToTwoEventType.STOP_WARNING,
                candidate,
                candidate.latest_price,
                position.quantity,
                "跌破止损，已发出 T+1 风险预警。",
            )
            return self.save(account)
        entry_amount = round(position.quantity * position.entry_price, 2)
        proceeds = round(position.quantity * candidate.latest_price, 2)
        realized_pnl = round(proceeds - entry_amount, 2)
        realized_pnl_pct = round(
            (candidate.latest_price - position.entry_price) / position.entry_price,
            4,
        )
        max_favorable_pct, max_adverse_pct, profit_drawdown_ratio = (
            self._trade_excursion_quality(position, candidate.latest_price, realized_pnl_pct)
        )
        warning_count = sum(
            1
            for event in account.events
            if event.symbol == position.symbol and event.event_type == OneToTwoEventType.STOP_WARNING
        )
        closed_trade = PaperTradeRecord(
            trade_id=f"{position.symbol}-{position.opened_at}-{candidate.trade_date}",
            symbol=position.symbol,
            name=position.name,
            opened_at=position.opened_at,
            closed_at=candidate.trade_date,
            entry_price=position.entry_price,
            exit_price=round(candidate.latest_price, 2),
            quantity=position.quantity,
            entry_amount=entry_amount,
            exit_amount=proceeds,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            holding_trade_days=1 if position.opened_at != candidate.trade_date else 0,
            exit_reason="stop_loss_t1",
            position_label=position.position_label,
            success=realized_pnl > 0,
            warning_count=warning_count,
            max_favorable_pct=max_favorable_pct,
            max_adverse_pct=max_adverse_pct,
            profit_drawdown_ratio=profit_drawdown_ratio,
            planned_stop_risk_pct=position.planned_stop_risk_pct,
            planned_first_target_return_pct=position.planned_first_target_return_pct,
            planned_reward_risk_ratio=position.planned_reward_risk_ratio,
            max_intratrade_drawdown_budget_pct=(
                position.max_intratrade_drawdown_budget_pct
            ),
            entry_turnover_quality_score=position.entry_turnover_quality_score,
            entry_turnover_quality_label=position.entry_turnover_quality_label,
            entry_turnover_quality_notes=position.entry_turnover_quality_notes,
            **self._entry_guard_position_fields(position),
        )
        account = PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=round(account.cash + proceeds, 2),
            initial_cash=account.initial_cash,
            equity=round(account.cash + proceeds, 2),
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(),
            events=account.events,
            closed_trades=(closed_trade, *account.closed_trades)[:200],
        )
        account = self._append_event(
            account,
            OneToTwoEventType.T1_SELL,
            candidate,
            candidate.latest_price,
            position.quantity,
            "次日仍低于止损，模拟 T+1 卖出。",
        )
        return self.save(account)

    def _refresh_position_context(
        self,
        account: PaperAccount,
        candidate: OneToTwoCandidate,
    ) -> PaperAccount:
        if not account.positions:
            return account
        position = account.positions[0]
        refreshed = PaperPosition(
            symbol=position.symbol,
            name=position.name,
            quantity=position.quantity,
            entry_price=position.entry_price,
            latest_price=position.latest_price,
            stop_loss=position.stop_loss,
            position_value=position.position_value,
            unrealized_pnl=position.unrealized_pnl,
            unrealized_pnl_pct=position.unrealized_pnl_pct,
            opened_at=position.opened_at,
            position_label=position.position_label,
            opened_score=position.opened_score,
            can_sell_today=position.can_sell_today,
            status=position.status,
            risk_note=position.risk_note,
            exit_plan=position.exit_plan or candidate.exit_plan,
            mainline_continuity=(
                candidate.mainline_continuity or position.mainline_continuity
            ),
            peak_price=position.peak_price,
            trough_price=position.trough_price,
            **self._planned_position_fields(position),
            **self._entry_evidence_position_fields(position),
        )
        return PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(refreshed,),
            events=account.events,
            closed_trades=account.closed_trades,
        )

    def exit_position(
        self,
        candidate: OneToTwoCandidate,
        exit_reason: str,
        message: str,
        event_type: OneToTwoEventType = OneToTwoEventType.DISCIPLINE_EXIT,
        holding_trade_days: int = 0,
    ) -> PaperAccount:
        account = self.prepare_for_trade_date(candidate.trade_date)
        if not account.positions:
            return account
        position = account.positions[0]
        if position.symbol != candidate.symbol or not position.can_sell_today:
            return account
        entry_amount = round(position.quantity * position.entry_price, 2)
        proceeds = round(position.quantity * candidate.latest_price, 2)
        realized_pnl = round(proceeds - entry_amount, 2)
        realized_pnl_pct = round(
            (candidate.latest_price - position.entry_price) / position.entry_price,
            4,
        )
        max_favorable_pct, max_adverse_pct, profit_drawdown_ratio = (
            self._trade_excursion_quality(position, candidate.latest_price, realized_pnl_pct)
        )
        warning_count = sum(
            1
            for event in account.events
            if event.symbol == position.symbol
            and event.event_type == OneToTwoEventType.STOP_WARNING
        )
        closed_trade = PaperTradeRecord(
            trade_id=f"{position.symbol}-{position.opened_at}-{candidate.trade_date}-{exit_reason}",
            symbol=position.symbol,
            name=position.name,
            opened_at=position.opened_at,
            closed_at=candidate.trade_date,
            entry_price=position.entry_price,
            exit_price=round(candidate.latest_price, 2),
            quantity=position.quantity,
            entry_amount=entry_amount,
            exit_amount=proceeds,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            holding_trade_days=holding_trade_days,
            exit_reason=exit_reason,
            position_label=position.position_label,
            success=realized_pnl > 0,
            warning_count=warning_count,
            max_favorable_pct=max_favorable_pct,
            max_adverse_pct=max_adverse_pct,
            profit_drawdown_ratio=profit_drawdown_ratio,
            planned_stop_risk_pct=position.planned_stop_risk_pct,
            planned_first_target_return_pct=position.planned_first_target_return_pct,
            planned_reward_risk_ratio=position.planned_reward_risk_ratio,
            max_intratrade_drawdown_budget_pct=(
                position.max_intratrade_drawdown_budget_pct
            ),
            entry_turnover_quality_score=position.entry_turnover_quality_score,
            entry_turnover_quality_label=position.entry_turnover_quality_label,
            entry_turnover_quality_notes=position.entry_turnover_quality_notes,
            **self._entry_guard_position_fields(position),
        )
        account = PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=round(account.cash + proceeds, 2),
            initial_cash=account.initial_cash,
            equity=round(account.cash + proceeds, 2),
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(),
            events=account.events,
            closed_trades=(closed_trade, *account.closed_trades)[:200],
        )
        account = self._append_event(
            account,
            event_type,
            candidate,
            candidate.latest_price,
            position.quantity,
            message,
        )
        return self.save(account)

    def roll_to_next_day(self) -> PaperAccount:
        account = self.load()
        positions = tuple(
            PaperPosition(
                symbol=position.symbol,
                name=position.name,
                quantity=position.quantity,
                entry_price=position.entry_price,
                latest_price=position.latest_price,
                stop_loss=position.stop_loss,
                position_value=position.position_value,
                unrealized_pnl=position.unrealized_pnl,
                unrealized_pnl_pct=position.unrealized_pnl_pct,
                opened_at=position.opened_at,
                position_label=position.position_label,
                opened_score=position.opened_score,
                can_sell_today=True,
                status=position.status,
                risk_note="已过买入日，若继续跌破止损可模拟卖出。",
                exit_plan=position.exit_plan,
                mainline_continuity=position.mainline_continuity,
                peak_price=position.peak_price,
                trough_price=position.trough_price,
                **self._planned_position_fields(position),
                **self._entry_evidence_position_fields(position),
            )
            for position in account.positions
        )
        return self.save(
            PaperAccount(
                account_id=account.account_id,
                last_trade_date=account.last_trade_date,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.equity,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=0,
                positions=positions,
                events=account.events,
                closed_trades=account.closed_trades,
            )
        )

    def _append_event(
        self,
        account: PaperAccount,
        event_type: OneToTwoEventType,
        candidate: OneToTwoCandidate,
        price: float,
        quantity: int,
        message: str,
    ) -> PaperAccount:
        event = PaperTradeEvent(
            event_id=f"{event_type.value}-{strftime('%Y%m%d%H%M%S')}",
            event_type=event_type,
            symbol=candidate.symbol,
            name=candidate.name,
            trade_date=candidate.trade_date,
            price=round(price, 2),
            quantity=quantity,
            amount=round(price * quantity, 2),
            message=message,
            created_at=strftime("%Y%m%d%H%M%S"),
        )
        return PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=account.positions,
            events=(event, *account.events)[:50],
            closed_trades=account.closed_trades,
        )

    def _revalue(self, account: PaperAccount, latest_price: float) -> PaperAccount:
        if not account.positions:
            return PaperAccount(
                account_id=account.account_id,
                last_trade_date=account.last_trade_date,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.cash,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=account.daily_trade_count,
                positions=(),
                events=account.events,
                closed_trades=account.closed_trades,
            )
        position = account.positions[0]
        peak_price = max(position.peak_price or position.entry_price, latest_price)
        trough_price = min(position.trough_price or position.entry_price, latest_price)
        value = round(position.quantity * latest_price, 2)
        pnl = round((latest_price - position.entry_price) * position.quantity, 2)
        pnl_pct = round((latest_price - position.entry_price) / position.entry_price, 4)
        updated = PaperPosition(
            symbol=position.symbol,
            name=position.name,
            quantity=position.quantity,
            entry_price=position.entry_price,
            latest_price=round(latest_price, 2),
            stop_loss=position.stop_loss,
            position_value=value,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=pnl_pct,
            opened_at=position.opened_at,
            position_label=position.position_label,
            opened_score=position.opened_score,
            can_sell_today=position.can_sell_today,
            status=position.status,
            risk_note=position.risk_note,
            exit_plan=position.exit_plan,
            mainline_continuity=position.mainline_continuity,
            peak_price=round(peak_price, 2),
            trough_price=round(trough_price, 2),
            planned_stop_risk_pct=position.planned_stop_risk_pct,
            planned_first_target_return_pct=position.planned_first_target_return_pct,
            planned_reward_risk_ratio=position.planned_reward_risk_ratio,
            max_intratrade_drawdown_budget_pct=(
                position.max_intratrade_drawdown_budget_pct
            ),
            **self._entry_evidence_position_fields(position),
        )
        return PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=round(account.cash + value, 2),
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(updated,),
            events=account.events,
            closed_trades=account.closed_trades,
        )

    def _trade_excursion_quality(
        self,
        position: PaperPosition,
        exit_price: float,
        realized_pnl_pct: float,
    ) -> tuple[float, float, float]:
        peak_price = max(position.peak_price or position.entry_price, exit_price)
        trough_price = min(position.trough_price or position.entry_price, exit_price)
        max_favorable_pct = round(
            max(0.0, (peak_price - position.entry_price) / position.entry_price),
            4,
        )
        max_adverse_pct = round(
            max(0.0, (position.entry_price - trough_price) / position.entry_price),
            4,
        )
        return (
            max_favorable_pct,
            max_adverse_pct,
            self._profit_drawdown_ratio(realized_pnl_pct, max_adverse_pct),
        )

    @staticmethod
    def _profit_drawdown_ratio(realized_pnl_pct: float, max_adverse_pct: float) -> float:
        if realized_pnl_pct <= 0:
            return 0.0
        if max_adverse_pct <= 0:
            return 99.0
        return round(realized_pnl_pct / max_adverse_pct, 4)

    @staticmethod
    def _planned_stop_risk_pct(candidate: OneToTwoCandidate) -> float:
        if candidate.entry_price <= 0:
            return 0.0
        return round(
            max(0.0, (candidate.entry_price - candidate.stop_loss) / candidate.entry_price),
            4,
        )

    @staticmethod
    def _planned_first_target_return_pct(candidate: OneToTwoCandidate) -> float:
        if candidate.entry_price <= 0 or candidate.exit_plan is None:
            return 0.0
        return round(
            max(
                0.0,
                (
                    candidate.exit_plan.first_take_profit_price
                    - candidate.entry_price
                )
                / candidate.entry_price,
            ),
            4,
        )

    def _planned_reward_risk_ratio(self, candidate: OneToTwoCandidate) -> float:
        risk_pct = self._planned_stop_risk_pct(candidate)
        reward_pct = self._planned_first_target_return_pct(candidate)
        if risk_pct <= 0:
            return 0.0
        return round(reward_pct / risk_pct, 4)

    def _max_intratrade_drawdown_budget_pct(
        self,
        candidate: OneToTwoCandidate,
    ) -> float:
        # The first target must be able to pay for the process drawdown.
        return self._planned_first_target_return_pct(candidate)

    @staticmethod
    def _planned_position_fields(position: PaperPosition) -> dict[str, float]:
        return {
            "planned_stop_risk_pct": position.planned_stop_risk_pct,
            "planned_first_target_return_pct": (
                position.planned_first_target_return_pct
            ),
            "planned_reward_risk_ratio": position.planned_reward_risk_ratio,
            "max_intratrade_drawdown_budget_pct": (
                position.max_intratrade_drawdown_budget_pct
            ),
        }

    @staticmethod
    def _entry_evidence_position_fields(position: PaperPosition) -> dict[str, Any]:
        return (
            PaperTradeStore._entry_quality_position_fields(position)
            | PaperTradeStore._entry_guard_position_fields(position)
        )

    @staticmethod
    def _entry_quality_position_fields(position: PaperPosition) -> dict[str, Any]:
        return {
            "entry_turnover_quality_score": position.entry_turnover_quality_score,
            "entry_turnover_quality_label": position.entry_turnover_quality_label,
            "entry_turnover_quality_notes": position.entry_turnover_quality_notes,
        }

    @staticmethod
    def _entry_guard_fields(
        guard_decision: PaperTradingGuardDecision | None,
    ) -> dict[str, Any]:
        if guard_decision is None:
            return {
                "entry_guard_status": "",
                "entry_guard_action": "",
                "entry_guard_suggested_position_pct": 0.0,
                "entry_guard_reason": "",
                "entry_guard_quality_bucket": "",
                "entry_guard_quality_sample_count": 0,
                "entry_guard_quality_win_rate": 0.0,
                "entry_guard_quality_average_return_pct": 0.0,
                "entry_guard_quality_pass_rate": 0.0,
            }
        return {
            "entry_guard_status": guard_decision.status,
            "entry_guard_action": guard_decision.action,
            "entry_guard_suggested_position_pct": (
                guard_decision.suggested_position_pct
            ),
            "entry_guard_reason": (
                guard_decision.reasons[0] if guard_decision.reasons else ""
            ),
            "entry_guard_quality_bucket": guard_decision.candidate_quality_bucket,
            "entry_guard_quality_sample_count": (
                guard_decision.candidate_quality_sample_count
            ),
            "entry_guard_quality_win_rate": guard_decision.candidate_quality_win_rate,
            "entry_guard_quality_average_return_pct": (
                guard_decision.candidate_quality_average_return_pct
            ),
            "entry_guard_quality_pass_rate": (
                guard_decision.candidate_quality_risk_quality_pass_rate
            ),
        }

    @staticmethod
    def _entry_guard_position_fields(position: PaperPosition) -> dict[str, Any]:
        return {
            "entry_guard_status": position.entry_guard_status,
            "entry_guard_action": position.entry_guard_action,
            "entry_guard_suggested_position_pct": (
                position.entry_guard_suggested_position_pct
            ),
            "entry_guard_reason": position.entry_guard_reason,
            "entry_guard_quality_bucket": position.entry_guard_quality_bucket,
            "entry_guard_quality_sample_count": (
                position.entry_guard_quality_sample_count
            ),
            "entry_guard_quality_win_rate": position.entry_guard_quality_win_rate,
            "entry_guard_quality_average_return_pct": (
                position.entry_guard_quality_average_return_pct
            ),
            "entry_guard_quality_pass_rate": position.entry_guard_quality_pass_rate,
        }
