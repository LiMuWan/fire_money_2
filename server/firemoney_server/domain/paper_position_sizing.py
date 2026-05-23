"""Position sizing rules for the local paper-trading ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.contracts import OneToTwoCandidate, PaperAccount


class PaperPositionSizingSettings(Protocol):
    small_account_mode_enabled: bool
    small_account_min_lot_shares: int
    small_account_target_position_pct: float
    small_account_reduced_target_position_pct: float
    small_account_max_position_pct: float
    small_account_reduced_max_position_pct: float
    paper_guard_reduced_position_pct: float


@dataclass(frozen=True)
class PaperPositionSize:
    quantity: int
    cash_budget: float
    position_pct: float
    target_position_pct: float
    max_position_pct: float
    note: str

    @property
    def can_buy(self) -> bool:
        return self.quantity > 0 and self.cash_budget > 0


@dataclass(frozen=True)
class SmallAccountBacktestTrade:
    entry_date: str
    symbol: str
    name: str
    entry_price: float
    net_return_pct: float
    account_return_pct: float
    position_pct: float
    quantity: int


def resolve_paper_position_size(
    *,
    settings: PaperPositionSizingSettings,
    account: PaperAccount,
    candidate: OneToTwoCandidate,
) -> PaperPositionSize:
    """Resolve executable A-share lot size for a paper-trading candidate."""

    if getattr(settings, "small_account_mode_enabled", False):
        return _resolve_small_account_size(
            settings=settings,
            account=account,
            candidate=candidate,
        )
    return _resolve_legacy_position_size(account=account, candidate=candidate)


def _resolve_legacy_position_size(
    *,
    account: PaperAccount,
    candidate: OneToTwoCandidate,
) -> PaperPositionSize:
    budget = min(
        account.cash,
        account.initial_cash * min(account.max_position_pct, candidate.position_limit_pct),
    )
    quantity = int(budget // candidate.entry_price // 100) * 100
    cash_budget = round(quantity * candidate.entry_price, 2)
    equity = _account_equity(account)
    position_pct = round(cash_budget / equity, 4) if equity > 0 else 0.0
    return PaperPositionSize(
        quantity=quantity,
        cash_budget=cash_budget,
        position_pct=position_pct or candidate.position_limit_pct,
        target_position_pct=candidate.position_limit_pct,
        max_position_pct=min(account.max_position_pct, candidate.position_limit_pct),
        note="固定比例仓位。",
    )


def _resolve_small_account_size(
    *,
    settings: PaperPositionSizingSettings,
    account: PaperAccount,
    candidate: OneToTwoCandidate,
) -> PaperPositionSize:
    equity = _account_equity(account)
    entry_price = float(candidate.entry_price or 0.0)
    lot_shares = max(1, int(settings.small_account_min_lot_shares))
    if equity <= 0 or entry_price <= 0:
        return _blocked_size("账户权益或买入价无效。")

    reduced = _has_reduced_position_warning(candidate)
    target_position_pct = (
        settings.small_account_reduced_target_position_pct
        if reduced
        else settings.small_account_target_position_pct
    )
    max_position_pct = (
        settings.small_account_reduced_max_position_pct
        if reduced
        else settings.small_account_max_position_pct
    )
    lot_cost = round(entry_price * lot_shares, 2)
    lot_position_pct = lot_cost / equity
    if lot_cost > account.cash + 0.0001:
        return _blocked_size(
            f"小账户现金不足，一手需 {lot_cost:.2f}，当前现金 {account.cash:.2f}。",
            target_position_pct=target_position_pct,
            max_position_pct=max_position_pct,
        )
    if lot_position_pct > max_position_pct + 0.0001:
        return _blocked_size(
            "小账户一手成本过高："
            f"一手约占 {lot_position_pct:.2%}，超过上限 {max_position_pct:.0%}。",
            target_position_pct=target_position_pct,
            max_position_pct=max_position_pct,
        )

    max_budget = min(account.cash, equity * max_position_pct)
    target_budget = min(account.cash, equity * target_position_pct)
    quantity = int(target_budget // lot_cost) * lot_shares
    if quantity < lot_shares:
        quantity = lot_shares
    max_quantity = int(max_budget // lot_cost) * lot_shares
    quantity = min(quantity, max_quantity)
    if quantity < lot_shares:
        return _blocked_size(
            "小账户按一手交易后会超过仓位上限，跳过。",
            target_position_pct=target_position_pct,
            max_position_pct=max_position_pct,
        )
    cash_budget = round(quantity * entry_price, 2)
    return PaperPositionSize(
        quantity=quantity,
        cash_budget=cash_budget,
        position_pct=round(cash_budget / equity, 4),
        target_position_pct=target_position_pct,
        max_position_pct=max_position_pct,
        note=(
            f"1万小账户一手制：目标 {target_position_pct:.0%}，"
            f"单票硬上限 {max_position_pct:.0%}，一手 {lot_shares} 股。"
        ),
    )


def simulate_small_account_trades(
    *,
    trades: list[object],
    initial_cash: float,
    lot_shares: int,
    target_position_pct: float,
    max_position_pct: float,
) -> tuple[list[SmallAccountBacktestTrade], int]:
    """Replay one-position trades with A-share lot sizing and a small account."""

    equity = float(initial_cash)
    executed: list[SmallAccountBacktestTrade] = []
    skipped = 0
    for trade in sorted(trades, key=lambda item: (_trade_entry_date(item), _trade_symbol(item))):
        entry_price = _trade_entry_price(trade)
        net_return_pct = _trade_net_return_pct(trade)
        lot_cost = entry_price * lot_shares
        if equity <= 0 or entry_price <= 0 or lot_cost > equity * max_position_pct:
            skipped += 1
            continue
        max_budget = equity * max_position_pct
        target_budget = equity * target_position_pct
        quantity = int(target_budget // lot_cost) * lot_shares
        if quantity < lot_shares:
            quantity = lot_shares
        max_quantity = int(max_budget // lot_cost) * lot_shares
        quantity = min(quantity, max_quantity)
        if quantity < lot_shares:
            skipped += 1
            continue
        position_pct = (quantity * entry_price) / equity
        account_return_pct = net_return_pct * position_pct
        equity *= max(0.0, 1 + account_return_pct)
        executed.append(
            SmallAccountBacktestTrade(
                entry_date=_trade_entry_date(trade),
                symbol=_trade_symbol(trade),
                name=_trade_name(trade),
                entry_price=round(entry_price, 2),
                net_return_pct=round(net_return_pct, 4),
                account_return_pct=round(account_return_pct, 6),
                position_pct=round(position_pct, 4),
                quantity=quantity,
            )
        )
    return executed, skipped


def summarize_account_return_trades(
    trades: list[SmallAccountBacktestTrade],
) -> dict[str, object]:
    if not trades:
        return {
            "sample_count": 0,
            "win_count": 0,
            "win_rate": None,
            "average_net_return_pct": None,
            "median_net_return_pct": None,
            "position_weighted_return_pct": None,
            "max_drawdown_pct": None,
            "average_position_pct": None,
            "strong_position_count": 0,
        }
    from statistics import mean, median

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    returns = [item.account_return_pct for item in trades]
    positions = [item.position_pct for item in trades]
    for trade in trades:
        equity *= max(0.0, 1 + trade.account_return_pct)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1)
    win_count = sum(1 for item in trades if item.account_return_pct > 0)
    return {
        "sample_count": len(trades),
        "win_count": win_count,
        "win_rate": round(win_count / len(trades), 4),
        "average_net_return_pct": round(mean(returns), 4),
        "median_net_return_pct": round(median(returns), 4),
        "position_weighted_return_pct": round(equity - 1, 4),
        "max_drawdown_pct": round(max_drawdown, 4),
        "average_position_pct": round(mean(positions), 4),
        "strong_position_count": 0,
    }


def summarize_account_return_by_year(
    trades: list[SmallAccountBacktestTrade],
) -> dict[str, dict[str, object]]:
    years = sorted({item.entry_date[:4] for item in trades})
    return {
        year: summarize_account_return_trades(
            [item for item in trades if item.entry_date.startswith(year)]
        )
        for year in years
    }


def _blocked_size(
    note: str,
    *,
    target_position_pct: float = 0.0,
    max_position_pct: float = 0.0,
) -> PaperPositionSize:
    return PaperPositionSize(
        quantity=0,
        cash_budget=0.0,
        position_pct=0.0,
        target_position_pct=target_position_pct,
        max_position_pct=max_position_pct,
        note=note,
    )


def _has_reduced_position_warning(candidate: OneToTwoCandidate) -> bool:
    markers = (
        "模拟盘收益守门降仓",
        "执行摩擦风险触发降仓",
    )
    return any(marker in warning for warning in candidate.warnings for marker in markers)


def _account_equity(account: PaperAccount) -> float:
    return float(account.equity or account.initial_cash or account.cash or 0.0)


def _trade_entry_date(trade: object) -> str:
    return str(_trade_value(trade, "entry_date"))


def _trade_symbol(trade: object) -> str:
    return str(_trade_value(trade, "symbol"))


def _trade_name(trade: object) -> str:
    return str(_trade_value(trade, "name"))


def _trade_entry_price(trade: object) -> float:
    return float(_trade_value(trade, "entry_price") or 0.0)


def _trade_net_return_pct(trade: object) -> float:
    return float(_trade_value(trade, "net_return_pct") or 0.0)


def _trade_value(trade: object, key: str) -> object:
    if isinstance(trade, dict):
        return trade.get(key)
    return getattr(trade, key, None)


__all__ = [
    "PaperPositionSize",
    "PaperPositionSizingSettings",
    "SmallAccountBacktestTrade",
    "resolve_paper_position_size",
    "simulate_small_account_trades",
    "summarize_account_return_by_year",
    "summarize_account_return_trades",
]
