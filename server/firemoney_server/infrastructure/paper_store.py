"""Local paper-trading account persistence for one-to-two strategy."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any

from shared.contracts import (
    OneToTwoCandidate,
    OneToTwoEventType,
    PaperAccount,
    PaperPosition,
    PaperTradeEvent,
    PaperTradeStatus,
)


DEFAULT_PAPER_STORE_PATH = Path(".firemoney") / "paper_trades.json"


class PaperTradeStore:
    """Stores an event-driven paper account in local JSON."""

    def __init__(
        self,
        path: str | Path = DEFAULT_PAPER_STORE_PATH,
        initial_cash: float = 100000.0,
        max_position_pct: float = 0.08,
        max_daily_trades: int = 1,
    ) -> None:
        self._path = Path(path)
        self._initial_cash = float(initial_cash)
        self._max_position_pct = float(max_position_pct)
        self._max_daily_trades = int(max_daily_trades)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> PaperAccount:
        if not self._path.exists():
            return self._empty_account()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return self._from_payload(payload)
        except (JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            return self._empty_account()

    def save(self, account: PaperAccount) -> PaperAccount:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._to_payload(account), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return account

    def buy_candidate(self, candidate: OneToTwoCandidate) -> PaperAccount:
        account = self.load()
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
        budget = account.initial_cash * account.max_position_pct
        quantity = int(budget // candidate.entry_price // 100) * 100
        amount = round(quantity * candidate.entry_price, 2)
        if quantity <= 0 or amount > account.cash:
            return self.save(
                self._append_event(
                    account,
                    OneToTwoEventType.BLOCKED,
                    candidate,
                    candidate.latest_price,
                    0,
                    "模拟资金不足或买入数量不足一手",
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
            can_sell_today=False,
            status=PaperTradeStatus.HOLDING,
            risk_note="严格 T+1：当天跌破止损只预警，不模拟卖出。",
        )
        account = PaperAccount(
            account_id=account.account_id,
            cash=round(account.cash - amount, 2),
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count + 1,
            positions=(position,),
            events=account.events,
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

    def update_risk(self, candidate: OneToTwoCandidate) -> PaperAccount:
        account = self.load()
        if not account.positions:
            return account
        position = account.positions[0]
        if position.symbol != candidate.symbol:
            return account
        account = self._revalue(account, candidate.latest_price)
        position = account.positions[0]
        if candidate.latest_price >= position.stop_loss:
            return self.save(account)
        if not position.can_sell_today:
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
                can_sell_today=position.can_sell_today,
                status=PaperTradeStatus.WARNING,
                risk_note="跌破止损但受 T+1 约束，次日仍弱再模拟卖出。",
            )
            account = PaperAccount(
                account_id=account.account_id,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.equity,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=account.daily_trade_count,
                positions=(warned,),
                events=account.events,
            )
            account = self._append_event(
                account,
                OneToTwoEventType.STOP_WARNING,
                candidate,
                candidate.latest_price,
                position.quantity,
                "跌破止损，已发出 T+1 风险预警。",
            )
            return self.save(account)
        proceeds = round(position.quantity * candidate.latest_price, 2)
        account = PaperAccount(
            account_id=account.account_id,
            cash=round(account.cash + proceeds, 2),
            initial_cash=account.initial_cash,
            equity=round(account.cash + proceeds, 2),
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(),
            events=account.events,
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
                can_sell_today=True,
                status=position.status,
                risk_note="已过买入日，若继续跌破止损可模拟卖出。",
            )
            for position in account.positions
        )
        return self.save(
            PaperAccount(
                account_id=account.account_id,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.equity,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=0,
                positions=positions,
                events=account.events,
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
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=account.positions,
            events=(event, *account.events)[:50],
        )

    def _revalue(self, account: PaperAccount, latest_price: float) -> PaperAccount:
        if not account.positions:
            return PaperAccount(
                account_id=account.account_id,
                cash=account.cash,
                initial_cash=account.initial_cash,
                equity=account.cash,
                max_position_pct=account.max_position_pct,
                max_daily_trades=account.max_daily_trades,
                daily_trade_count=account.daily_trade_count,
                positions=(),
                events=account.events,
            )
        position = account.positions[0]
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
            can_sell_today=position.can_sell_today,
            status=position.status,
            risk_note=position.risk_note,
        )
        return PaperAccount(
            account_id=account.account_id,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=round(account.cash + value, 2),
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=(updated,),
            events=account.events,
        )

    def _empty_account(self) -> PaperAccount:
        return PaperAccount(
            account_id="one-to-two-paper",
            cash=self._initial_cash,
            initial_cash=self._initial_cash,
            equity=self._initial_cash,
            max_position_pct=self._max_position_pct,
            max_daily_trades=self._max_daily_trades,
            daily_trade_count=0,
            positions=(),
            events=(),
        )

    def _to_payload(self, account: PaperAccount) -> dict[str, Any]:
        return {
            "account_id": account.account_id,
            "cash": account.cash,
            "initial_cash": account.initial_cash,
            "equity": account.equity,
            "max_position_pct": account.max_position_pct,
            "max_daily_trades": account.max_daily_trades,
            "daily_trade_count": account.daily_trade_count,
            "positions": [position.__dict__ | {"status": position.status.value} for position in account.positions],
            "events": [
                event.__dict__ | {"event_type": event.event_type.value}
                for event in account.events
            ],
        }

    def _from_payload(self, payload: dict[str, Any]) -> PaperAccount:
        return PaperAccount(
            account_id=str(payload["account_id"]),
            cash=float(payload["cash"]),
            initial_cash=float(payload["initial_cash"]),
            equity=float(payload["equity"]),
            max_position_pct=float(payload["max_position_pct"]),
            max_daily_trades=int(payload["max_daily_trades"]),
            daily_trade_count=int(payload["daily_trade_count"]),
            positions=tuple(
                PaperPosition(
                    symbol=str(item["symbol"]),
                    name=str(item["name"]),
                    quantity=int(item["quantity"]),
                    entry_price=float(item["entry_price"]),
                    latest_price=float(item["latest_price"]),
                    stop_loss=float(item["stop_loss"]),
                    position_value=float(item["position_value"]),
                    unrealized_pnl=float(item["unrealized_pnl"]),
                    unrealized_pnl_pct=float(item["unrealized_pnl_pct"]),
                    opened_at=str(item["opened_at"]),
                    can_sell_today=bool(item["can_sell_today"]),
                    status=PaperTradeStatus(str(item["status"])),
                    risk_note=str(item["risk_note"]),
                )
                for item in payload.get("positions", ())
            ),
            events=tuple(
                PaperTradeEvent(
                    event_id=str(item["event_id"]),
                    event_type=OneToTwoEventType(str(item["event_type"])),
                    symbol=str(item["symbol"]),
                    name=str(item["name"]),
                    trade_date=str(item["trade_date"]),
                    price=float(item["price"]),
                    quantity=int(item["quantity"]),
                    amount=float(item["amount"]),
                    message=str(item["message"]),
                    created_at=str(item["created_at"]),
                )
                for item in payload.get("events", ())
            ),
        )
