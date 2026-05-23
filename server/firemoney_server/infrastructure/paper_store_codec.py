"""JSON contract codec for the local paper-trading store."""

from __future__ import annotations

from typing import Any

from shared.contracts import (
    MainlineContinuity,
    MainlineNewsItem,
    OneToTwoEventType,
    OneToTwoExitPlan,
    PaperAccount,
    PaperPosition,
    PaperTradeEvent,
    PaperTradeRecord,
    PaperTradeStatus,
    contract_to_dict,
)


class PaperStoreCodec:
    """Converts paper-trading contracts to and from JSON-safe payloads."""

    def __init__(
        self,
        *,
        initial_cash: float,
        max_position_pct: float,
        max_daily_trades: int,
    ) -> None:
        self._initial_cash = initial_cash
        self._max_position_pct = max_position_pct
        self._max_daily_trades = max_daily_trades

    def empty_account(self) -> PaperAccount:
        return PaperAccount(
            account_id="one-to-two-paper",
            last_trade_date="",
            cash=self._initial_cash,
            initial_cash=self._initial_cash,
            equity=self._initial_cash,
            max_position_pct=self._max_position_pct,
            max_daily_trades=self._max_daily_trades,
            daily_trade_count=0,
            positions=(),
            events=(),
            closed_trades=(),
        )

    def to_payload(self, account: PaperAccount) -> dict[str, Any]:
        return {
            "account_id": account.account_id,
            "last_trade_date": account.last_trade_date,
            "cash": account.cash,
            "initial_cash": account.initial_cash,
            "equity": account.equity,
            "max_position_pct": account.max_position_pct,
            "max_daily_trades": account.max_daily_trades,
            "daily_trade_count": account.daily_trade_count,
            "positions": [contract_to_dict(position) for position in account.positions],
            "events": [
                event.__dict__ | {"event_type": event.event_type.value}
                for event in account.events
            ],
            "closed_trades": [record.__dict__ for record in account.closed_trades],
        }

    def from_payload(self, payload: dict[str, Any]) -> PaperAccount:
        last_trade_date = str(
            payload.get("last_trade_date")
            or self._infer_last_trade_date(payload)
            or ""
        )
        return PaperAccount(
            account_id=str(payload["account_id"]),
            last_trade_date=last_trade_date,
            cash=float(payload["cash"]),
            initial_cash=float(payload["initial_cash"]),
            equity=float(payload["equity"]),
            max_position_pct=float(payload["max_position_pct"]),
            max_daily_trades=int(payload["max_daily_trades"]),
            daily_trade_count=int(payload["daily_trade_count"]),
            positions=tuple(
                self._position_from_payload(item)
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
            closed_trades=tuple(
                self._closed_trade_from_payload(item)
                for item in payload.get("closed_trades", ())
            ),
        )

    def _position_from_payload(self, item: dict[str, Any]) -> PaperPosition:
        return PaperPosition(
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
            position_label=str(item.get("position_label") or "未标记样本"),
            opened_score=float(item.get("opened_score", 0.0)),
            can_sell_today=bool(item["can_sell_today"]),
            status=PaperTradeStatus(str(item["status"])),
            risk_note=str(item["risk_note"]),
            exit_plan=self._exit_plan_from_payload(item.get("exit_plan")),
            mainline_continuity=self._continuity_from_payload(
                item.get("mainline_continuity")
            ),
            peak_price=float(item.get("peak_price", item["latest_price"])),
            trough_price=float(item.get("trough_price", item["latest_price"])),
            planned_stop_risk_pct=float(item.get("planned_stop_risk_pct", 0.0)),
            planned_first_target_return_pct=float(
                item.get("planned_first_target_return_pct", 0.0)
            ),
            planned_reward_risk_ratio=float(item.get("planned_reward_risk_ratio", 0.0)),
            max_intratrade_drawdown_budget_pct=float(
                item.get("max_intratrade_drawdown_budget_pct", 0.0)
            ),
            entry_turnover_quality_score=float(
                item.get("entry_turnover_quality_score", 0.0)
            ),
            entry_turnover_quality_label=str(
                item.get("entry_turnover_quality_label", "")
            ),
            entry_turnover_quality_notes=self._string_tuple(
                item.get("entry_turnover_quality_notes", ())
            ),
            **self._entry_guard_payload_fields(item),
        )

    def _closed_trade_from_payload(self, item: dict[str, Any]) -> PaperTradeRecord:
        return PaperTradeRecord(
            trade_id=str(item["trade_id"]),
            symbol=str(item["symbol"]),
            name=str(item["name"]),
            opened_at=str(item["opened_at"]),
            closed_at=str(item["closed_at"]),
            entry_price=float(item["entry_price"]),
            exit_price=float(item["exit_price"]),
            quantity=int(item["quantity"]),
            entry_amount=float(item["entry_amount"]),
            exit_amount=float(item["exit_amount"]),
            realized_pnl=float(item["realized_pnl"]),
            realized_pnl_pct=float(item["realized_pnl_pct"]),
            holding_trade_days=int(item["holding_trade_days"]),
            exit_reason=str(item["exit_reason"]),
            position_label=str(item["position_label"]),
            success=bool(item["success"]),
            warning_count=int(item["warning_count"]),
            max_favorable_pct=float(item.get("max_favorable_pct", 0.0)),
            max_adverse_pct=float(item.get("max_adverse_pct", 0.0)),
            profit_drawdown_ratio=float(item.get("profit_drawdown_ratio", 0.0)),
            planned_stop_risk_pct=float(item.get("planned_stop_risk_pct", 0.0)),
            planned_first_target_return_pct=float(
                item.get("planned_first_target_return_pct", 0.0)
            ),
            planned_reward_risk_ratio=float(item.get("planned_reward_risk_ratio", 0.0)),
            max_intratrade_drawdown_budget_pct=float(
                item.get("max_intratrade_drawdown_budget_pct", 0.0)
            ),
            entry_turnover_quality_score=float(
                item.get("entry_turnover_quality_score", 0.0)
            ),
            entry_turnover_quality_label=str(
                item.get("entry_turnover_quality_label", "")
            ),
            entry_turnover_quality_notes=self._string_tuple(
                item.get("entry_turnover_quality_notes", ())
            ),
            **self._entry_guard_payload_fields(item),
        )

    def _exit_plan_from_payload(self, payload: Any) -> OneToTwoExitPlan | None:
        if not isinstance(payload, dict):
            return None
        return OneToTwoExitPlan(
            stop_loss=float(payload["stop_loss"]),
            stop_loss_pct=float(payload["stop_loss_pct"]),
            first_take_profit_price=float(payload["first_take_profit_price"]),
            first_take_profit_pct=float(payload["first_take_profit_pct"]),
            strong_take_profit_price=float(payload["strong_take_profit_price"]),
            strong_take_profit_pct=float(payload["strong_take_profit_pct"]),
            trailing_stop_pct=float(payload["trailing_stop_pct"]),
            max_holding_trade_days=int(payload["max_holding_trade_days"]),
            summary=str(payload["summary"]),
        )

    def _continuity_from_payload(self, payload: Any) -> MainlineContinuity | None:
        if not isinstance(payload, dict):
            return None
        return MainlineContinuity(
            theme=str(payload["theme"]),
            score=float(payload["score"]),
            status=str(payload["status"]),
            hot_stock_count=int(payload["hot_stock_count"]),
            limit_up_count=int(payload["limit_up_count"]),
            news_count=int(payload["news_count"]),
            latest_news=tuple(
                MainlineNewsItem(
                    title=str(item["title"]),
                    source=str(item["source"]),
                    published_at=str(item["published_at"]),
                    related_symbols=tuple(
                        str(symbol) for symbol in item.get("related_symbols", ())
                    ),
                    url=str(item.get("url", "")),
                )
                for item in payload.get("latest_news", ())
            ),
            reasons=tuple(str(item) for item in payload.get("reasons", ())),
            risk_notes=tuple(str(item) for item in payload.get("risk_notes", ())),
            next_action=str(payload["next_action"]),
        )

    @staticmethod
    def _string_tuple(payload: Any) -> tuple[str, ...]:
        if isinstance(payload, (list, tuple)):
            return tuple(str(item) for item in payload if item is not None)
        if isinstance(payload, str) and payload:
            return (payload,)
        return ()

    @staticmethod
    def _entry_guard_payload_fields(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "entry_guard_status": str(item.get("entry_guard_status", "")),
            "entry_guard_action": str(item.get("entry_guard_action", "")),
            "entry_guard_suggested_position_pct": float(
                item.get("entry_guard_suggested_position_pct", 0.0)
            ),
            "entry_guard_reason": str(item.get("entry_guard_reason", "")),
            "entry_guard_quality_bucket": str(
                item.get("entry_guard_quality_bucket", "")
            ),
            "entry_guard_quality_sample_count": int(
                item.get("entry_guard_quality_sample_count", 0)
            ),
            "entry_guard_quality_win_rate": float(
                item.get("entry_guard_quality_win_rate", 0.0)
            ),
            "entry_guard_quality_average_return_pct": float(
                item.get("entry_guard_quality_average_return_pct", 0.0)
            ),
            "entry_guard_quality_pass_rate": float(
                item.get("entry_guard_quality_pass_rate", 0.0)
            ),
        }

    def _infer_last_trade_date(self, payload: dict[str, Any]) -> str:
        dates = [
            str(item.get("trade_date", ""))
            for item in payload.get("events", ())
            if item.get("trade_date")
        ]
        dates.extend(
            str(item.get("opened_at", ""))
            for item in payload.get("positions", ())
            if item.get("opened_at")
        )
        return max(dates, default="")


__all__ = ["PaperStoreCodec"]
