"""QMT broker gateway with safe dry-run defaults.

The adapter is intentionally local-only: Tencent Cloud preview servers should
never import or connect to a Windows QMT terminal. xtquant is imported lazily so
ordinary CLI and preview commands keep working when the QMT SDK is absent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import import_module
import os
import time
from typing import Any

from shared.contracts import (
    BrokerConnectionReport,
    BrokerOrderPlan,
    BrokerPosition,
    PaperTradingDecisionReport,
)

BROKER_NAME = "qmt"
DEFAULT_PRICE_TYPE = "FIX_PRICE"
QMT_ACCOUNT_ID_ENV = "FIREMONEY_QMT_ACCOUNT_ID"
QMT_ALLOW_LIVE_ENV = "FIREMONEY_QMT_ALLOW_LIVE"
QMT_PATH_ENV = "FIREMONEY_QMT_PATH"
QMT_SESSION_ID_ENV = "FIREMONEY_QMT_SESSION_ID"


@dataclass(frozen=True)
class QmtConfig:
    qmt_path: str
    account_id: str
    session_id: int


class QmtBrokerGateway:
    """Small adapter around local xtquant trading APIs."""

    def __init__(
        self,
        *,
        qmt_path: str | None = None,
        account_id: str | None = None,
        session_id: int | None = None,
    ) -> None:
        self._qmt_path = (qmt_path or os.getenv(QMT_PATH_ENV) or "").strip()
        self._account_id = (account_id or os.getenv(QMT_ACCOUNT_ID_ENV) or "").strip()
        self._session_id = session_id or _session_id_from_env() or int(time.time())

    @property
    def config(self) -> QmtConfig:
        return QmtConfig(
            qmt_path=self._qmt_path,
            account_id=self._account_id,
            session_id=self._session_id,
        )

    def check(self) -> BrokerConnectionReport:
        config_error = self._config_error()
        if config_error:
            return _blocked_connection_report(
                account_id=self._account_id,
                message=config_error,
                next_action=(
                    "在本机启动并登录 MiniQMT，然后配置 FIREMONEY_QMT_PATH 和 "
                    "FIREMONEY_QMT_ACCOUNT_ID，或通过 CLI 参数传入。"
                ),
            )
        try:
            trader_api = _load_xtquant()
            trader = trader_api.trader_class(self._qmt_path, self._session_id)
            trader.start()
            try:
                connect_result = trader.connect()
                if connect_result not in (0, None):
                    return _blocked_connection_report(
                        account_id=self._account_id,
                        message=f"QMT connect 返回 {connect_result}，未确认连接成功。",
                        next_action="确认 MiniQMT 已登录、路径是 userdata_mini 目录，并重新运行 qmt-check。",
                    )
                account = _stock_account(trader_api, self._account_id)
                _safe_call(trader, "subscribe", account)
                asset = _safe_call(trader, "query_stock_asset", account)
                positions = _safe_call(trader, "query_stock_positions", account) or ()
                return BrokerConnectionReport(
                    broker=BROKER_NAME,
                    status="ready",
                    account_id=self._account_id,
                    cash=_float_attr(asset, "cash", "m_dCash", "available_cash"),
                    available_cash=_float_attr(
                        asset,
                        "available_cash",
                        "m_dAvailableCash",
                        "cash",
                    ),
                    total_asset=_float_attr(asset, "total_asset", "m_dBalance", "asset"),
                    market_value=_float_attr(asset, "market_value", "m_dMarketValue"),
                    positions=tuple(_position_from_qmt(item) for item in positions),
                    message="QMT 本地交易端连接成功，已读取资金和持仓快照。",
                    next_action="先运行 qmt-plan 核对拟委托；实盘提交必须额外开启 --qmt-submit 和 FIREMONEY_QMT_ALLOW_LIVE=true。",
                    dry_run=True,
                )
            finally:
                _stop_trader(trader)
        except ImportError as exc:
            return _blocked_connection_report(
                account_id=self._account_id,
                message="当前 Python 环境未安装 xtquant，无法连接 QMT。",
                next_action="在运行 FireMoney 的 Windows Python 环境安装/配置 QMT 官方 xtquant SDK 后再运行 qmt-check。",
                raw_error=str(exc),
            )
        except Exception as exc:  # pragma: no cover - depends on local QMT runtime
            return _blocked_connection_report(
                account_id=self._account_id,
                message="QMT 连接或账户查询失败。",
                next_action="确认 MiniQMT 已启动登录、账号类型正确、客户端允许 Python API 连接。",
                raw_error=str(exc),
            )

    def plan_paper_decision(
        self,
        report: PaperTradingDecisionReport,
        *,
        submit: bool = False,
    ) -> BrokerOrderPlan:
        instruction = report.instruction
        if not report.should_buy or instruction is None:
            return BrokerOrderPlan(
                broker=BROKER_NAME,
                status="blocked",
                dry_run=not submit,
                trade_date=report.trade_date,
                action=report.selected_action,
                symbol="",
                name="",
                side="",
                quantity=0,
                price=0.0,
                price_type=DEFAULT_PRICE_TYPE,
                account_id=self._account_id,
                summary="今天模拟盘没有生成新的买入指令，QMT 不生成委托。",
                warnings=("未满足买入条件，禁止为了接入而强行下单。",),
                next_action=report.next_action,
            )
        symbol = to_qmt_symbol(instruction.symbol)
        quantity = int(instruction.quantity)
        price = float(instruction.entry_price)
        warnings = tuple(instruction.risk_notes)
        if quantity <= 0 or quantity % 100 != 0:
            return BrokerOrderPlan(
                broker=BROKER_NAME,
                status="blocked",
                dry_run=not submit,
                trade_date=report.trade_date,
                action=instruction.action,
                symbol=symbol,
                name=instruction.name,
                side="buy",
                quantity=quantity,
                price=price,
                price_type=DEFAULT_PRICE_TYPE,
                account_id=self._account_id,
                summary="模拟盘数量不是有效 A 股整百股委托，QMT 不生成委托。",
                warnings=warnings + ("A 股普通买入必须为 100 股整数倍。",),
                next_action="先修正模拟盘仓位/资金规则，再重新生成 qmt-plan。",
            )
        base_plan = BrokerOrderPlan(
            broker=BROKER_NAME,
            status="ready",
            dry_run=not submit,
            trade_date=report.trade_date,
            action=instruction.action,
            symbol=symbol,
            name=instruction.name,
            side="buy",
            quantity=quantity,
            price=price,
            price_type=DEFAULT_PRICE_TYPE,
            account_id=self._account_id,
            summary=(
                f"QMT dry-run 拟委托：买入 {instruction.name}（{symbol}）"
                f"{quantity} 股，限价 {price:.2f}。"
            ),
            warnings=warnings,
            next_action=(
                "核对账号、代码、价格、数量和风控线；确认无误后才可开启 --qmt-submit "
                "和 FIREMONEY_QMT_ALLOW_LIVE=true。"
            ),
        )
        if not submit:
            return base_plan
        live_error = self._live_submit_error()
        if live_error:
            return replace(
                base_plan,
                status="blocked",
                dry_run=False,
                summary=live_error,
                warnings=base_plan.warnings + ("实盘提交被安全闸门拦截。",),
                next_action="确认确实要实盘报单后，设置 FIREMONEY_QMT_ALLOW_LIVE=true 再重试。",
            )
        try:
            order_id = self._submit_buy_order(symbol=symbol, quantity=quantity, price=price)
        except ImportError as exc:
            return replace(
                base_plan,
                status="blocked",
                dry_run=False,
                summary="当前 Python 环境未安装 xtquant，QMT 实盘提交失败。",
                warnings=base_plan.warnings + (str(exc),),
                next_action="在运行 FireMoney 的 Windows Python 环境安装/配置 QMT 官方 xtquant SDK 后再重试。",
            )
        except Exception as exc:  # pragma: no cover - depends on local QMT runtime
            return replace(
                base_plan,
                status="blocked",
                dry_run=False,
                summary="QMT 实盘提交失败，未确认委托成功。",
                warnings=base_plan.warnings + (str(exc),),
                next_action="到 QMT 客户端核对是否产生委托；确认没有重复报单后再决定是否重试。",
            )
        return replace(
            base_plan,
            dry_run=False,
            submitted=True,
            order_id=str(order_id),
            summary=(
                f"QMT 已提交买入委托：{instruction.name}（{symbol}）"
                f"{quantity} 股，限价 {price:.2f}，委托号 {order_id}。"
            ),
            next_action="立刻到 QMT 客户端核对委托状态、成交回报和撤单条件。",
        )

    def _config_error(self) -> str:
        missing = []
        if not self._qmt_path:
            missing.append(QMT_PATH_ENV)
        if not self._account_id:
            missing.append(QMT_ACCOUNT_ID_ENV)
        if missing:
            return "缺少 QMT 配置：" + "、".join(missing)
        return ""

    def _live_submit_error(self) -> str:
        config_error = self._config_error()
        if config_error:
            return config_error
        if os.getenv(QMT_ALLOW_LIVE_ENV, "").strip().lower() != "true":
            return f"未设置 {QMT_ALLOW_LIVE_ENV}=true，禁止实盘提交。"
        return ""

    def _submit_buy_order(self, *, symbol: str, quantity: int, price: float) -> Any:
        trader_api = _load_xtquant()
        trader = trader_api.trader_class(self._qmt_path, self._session_id)
        trader.start()
        try:
            connect_result = trader.connect()
            if connect_result not in (0, None):
                raise RuntimeError(f"QMT connect 返回 {connect_result}")
            account = _stock_account(trader_api, self._account_id)
            _safe_call(trader, "subscribe", account)
            order_type = getattr(trader_api.constant_module, "STOCK_BUY")
            price_type = getattr(trader_api.constant_module, DEFAULT_PRICE_TYPE)
            return trader.order_stock(
                account,
                symbol,
                order_type,
                quantity,
                price_type,
                price,
                "FireMoney",
                "paper-decision",
            )
        finally:
            _stop_trader(trader)


@dataclass(frozen=True)
class _XtquantApi:
    trader_class: Any
    account_class: Any
    constant_module: Any


def to_qmt_symbol(symbol: str) -> str:
    stripped = symbol.strip().upper()
    if "." in stripped:
        return stripped
    if stripped.startswith(("5", "6", "9")):
        return f"{stripped}.SH"
    return f"{stripped}.SZ"


def _load_xtquant() -> _XtquantApi:
    xttrader = import_module("xtquant.xttrader")
    xttype = import_module("xtquant.xttype")
    xtconstant = import_module("xtquant.xtconstant")
    return _XtquantApi(
        trader_class=getattr(xttrader, "XtQuantTrader"),
        account_class=getattr(xttype, "StockAccount"),
        constant_module=xtconstant,
    )


def _stock_account(trader_api: _XtquantApi, account_id: str) -> Any:
    try:
        return trader_api.account_class(account_id)
    except TypeError:
        return trader_api.account_class(account_id, "STOCK")


def _session_id_from_env() -> int | None:
    value = os.getenv(QMT_SESSION_ID_ENV, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _blocked_connection_report(
    *,
    account_id: str,
    message: str,
    next_action: str,
    raw_error: str | None = None,
) -> BrokerConnectionReport:
    return BrokerConnectionReport(
        broker=BROKER_NAME,
        status="blocked",
        account_id=account_id,
        cash=0.0,
        available_cash=0.0,
        total_asset=0.0,
        market_value=0.0,
        positions=(),
        message=message,
        next_action=next_action,
        dry_run=True,
        raw_error=raw_error,
    )


def _safe_call(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if method is None:
        return None
    return method(*args)


def _stop_trader(trader: Any) -> None:
    for method_name in ("stop", "disconnect"):
        method = getattr(trader, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                return
            return


def _float_attr(value: Any, *names: str) -> float:
    for name in names:
        raw = getattr(value, name, None)
        if raw is None and isinstance(value, dict):
            raw = value.get(name)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return 0.0


def _int_attr(value: Any, *names: str) -> int:
    for name in names:
        raw = getattr(value, name, None)
        if raw is None and isinstance(value, dict):
            raw = value.get(name)
        if raw is not None:
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                continue
    return 0


def _str_attr(value: Any, *names: str) -> str:
    for name in names:
        raw = getattr(value, name, None)
        if raw is None and isinstance(value, dict):
            raw = value.get(name)
        if raw is not None:
            return str(raw)
    return ""


def _position_from_qmt(value: Any) -> BrokerPosition:
    symbol = _str_attr(value, "stock_code", "m_strInstrumentID", "symbol")
    return BrokerPosition(
        symbol=to_qmt_symbol(symbol) if symbol else "",
        name=_str_attr(value, "stock_name", "m_strInstrumentName", "name"),
        quantity=_int_attr(value, "volume", "m_nVolume", "quantity"),
        available_quantity=_int_attr(
            value,
            "can_use_volume",
            "available_volume",
            "m_nCanUseVolume",
        ),
        market_value=_float_attr(value, "market_value", "m_dMarketValue"),
        cost_price=_float_attr(value, "open_price", "cost_price", "m_dOpenPrice"),
        latest_price=_float_attr(value, "last_price", "latest_price", "m_dLastPrice"),
    )


__all__ = [
    "QMT_ACCOUNT_ID_ENV",
    "QMT_ALLOW_LIVE_ENV",
    "QMT_PATH_ENV",
    "QMT_SESSION_ID_ENV",
    "QmtBrokerGateway",
    "to_qmt_symbol",
]
