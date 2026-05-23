"""Paper-trading exit discipline for FireMoney positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.contracts import OneToTwoEventType, PaperPosition


class PaperExitSettings(Protocol):
    mainline_fade_score: float
    hard_max_holding_trade_days: int
    max_holding_trade_days: int
    discipline_exit_min_gain_pct: float
    positive_lock_profit_pct: float
    positive_lock_min_profit_drawdown_ratio: float
    main_rise_runner_min_quality_score: float
    main_rise_runner_min_opened_score: float
    main_rise_runner_min_mainline_score: float
    main_rise_runner_trailing_start_pct: float
    main_rise_runner_trailing_stop_pct: float
    main_rise_runner_profit_floor_pct: float


@dataclass(frozen=True)
class PaperExitDecision:
    exit_reason: str
    message: str
    event_type: OneToTwoEventType = OneToTwoEventType.DISCIPLINE_EXIT


class PaperExitPolicy:
    """Decides whether an open paper position should be exited today."""

    def __init__(self, settings: PaperExitSettings) -> None:
        self._settings = settings

    def decide(self, position: PaperPosition, latest_price: float) -> PaperExitDecision | None:
        if (
            position.mainline_continuity
            and position.mainline_continuity.score < self._settings.mainline_fade_score
        ):
            return PaperExitDecision(
                exit_reason=(
                    "mainline_fade_profit_protect"
                    if position.unrealized_pnl_pct > 0
                    else "mainline_fade_risk_exit"
                ),
                message="主线持续性跌破纪律阈值，T+1 已到，优先退出保护本金。",
                event_type=OneToTwoEventType.MAINLINE_FADE_EXIT,
            )
        if position.exit_plan:
            peak_price = position.peak_price or position.latest_price
            strong_take_profit_price = position.entry_price * (
                1 + position.exit_plan.strong_take_profit_pct
            )
            trailing_stop_price = round(
                peak_price * (1 - position.exit_plan.trailing_stop_pct),
                2,
            )
            if peak_price >= strong_take_profit_price and latest_price <= trailing_stop_price:
                return PaperExitDecision(
                    exit_reason="trailing_take_profit",
                    message=(
                        "强势涨幅已达到 "
                        f"{format_pct(position.exit_plan.strong_take_profit_pct)}，"
                        "回撤触发 "
                        f"{format_pct(position.exit_plan.trailing_stop_pct)} "
                        "保护，T+1 已到，模拟止盈。"
                    ),
                    event_type=OneToTwoEventType.TAKE_PROFIT,
                )
        if self.is_main_rise_runner_protect_ready(position, latest_price):
            return PaperExitDecision(
                exit_reason="main_rise_runner_trailing_lock",
                message=(
                    "主升持有已达到分段保护区，价格跌破动态保护线，"
                    "T+1 已到，先锁住强势利润。"
                ),
                event_type=OneToTwoEventType.TAKE_PROFIT,
            )
        if self.is_quality_positive_lock_ready(position):
            if self.is_main_rise_runner(position):
                if not (
                    position.exit_plan
                    and position.unrealized_pnl_pct >= position.exit_plan.first_take_profit_pct
                ):
                    return None
            else:
                return PaperExitDecision(
                    exit_reason="positive_profit_lock",
                    message=(
                        "T+1 已到且浮盈达到正收益质量锁定线，"
                        "模拟盘先落袋，避免盈利变亏。"
                    ),
                    event_type=OneToTwoEventType.TAKE_PROFIT,
                )
        if (
            position.exit_plan
            and position.unrealized_pnl_pct >= position.exit_plan.first_take_profit_pct
        ):
            return PaperExitDecision(
                exit_reason="take_profit_first_target",
                message=(
                    f"浮盈达到 {format_pct(position.exit_plan.first_take_profit_pct)} "
                    "第一止盈纪律，T+1 已到，模拟落袋。"
                ),
                event_type=OneToTwoEventType.TAKE_PROFIT,
            )
        return None

    def time_exit_decision(
        self,
        position: PaperPosition,
        holding_trade_days: int,
    ) -> PaperExitDecision | None:
        planned_max_holding_trade_days = self.max_holding_trade_days_for_position(
            position
        )
        if holding_trade_days >= self._settings.hard_max_holding_trade_days:
            return PaperExitDecision(
                exit_reason=(
                    "weekly_profit_lock"
                    if position.unrealized_pnl_pct > 0
                    else "weekly_risk_timeout"
                ),
                message="持仓达到一周硬上限，模拟盘按时间纪律退出并记录收益质量。",
            )
        if holding_trade_days < planned_max_holding_trade_days:
            return None
        if position.unrealized_pnl_pct >= self._settings.discipline_exit_min_gain_pct:
            return None
        return PaperExitDecision(
            exit_reason=f"discipline_weak_after_{planned_max_holding_trade_days}_days",
            message=(
                f"持仓达到计划最长 {planned_max_holding_trade_days} 个交易日"
                "仍未继续走强，按主线首板纪律退出。"
            ),
        )

    def max_holding_trade_days_for_position(self, position: PaperPosition) -> int:
        if position.exit_plan is not None and position.exit_plan.max_holding_trade_days > 0:
            return min(
                position.exit_plan.max_holding_trade_days,
                self._settings.hard_max_holding_trade_days,
            )
        return self._settings.max_holding_trade_days

    def is_main_rise_runner(self, position: PaperPosition) -> bool:
        if position.exit_plan is None or position.mainline_continuity is None:
            return False
        return (
            position.entry_turnover_quality_score
            >= self._settings.main_rise_runner_min_quality_score
            and position.opened_score >= self._settings.main_rise_runner_min_opened_score
            and position.mainline_continuity.score
            >= self._settings.main_rise_runner_min_mainline_score
        )

    @staticmethod
    def main_rise_runner_peak_return_pct(position: PaperPosition) -> float:
        if position.entry_price <= 0:
            return 0.0
        peak_price = position.peak_price or position.latest_price or position.entry_price
        return max(0.0, (peak_price - position.entry_price) / position.entry_price)

    def main_rise_runner_protect_price(self, position: PaperPosition) -> float:
        if position.entry_price <= 0:
            return 0.0
        peak_return_pct = self.main_rise_runner_peak_return_pct(position)
        if peak_return_pct >= self._settings.main_rise_runner_trailing_start_pct:
            peak_price = position.peak_price or position.latest_price
            return round(
                peak_price * (1 - self._settings.main_rise_runner_trailing_stop_pct),
                2,
            )
        if peak_return_pct >= self._settings.positive_lock_profit_pct:
            return round(
                position.entry_price
                * (1 + self._settings.main_rise_runner_profit_floor_pct),
                2,
            )
        return 0.0

    def is_main_rise_runner_protect_ready(
        self,
        position: PaperPosition,
        latest_price: float,
    ) -> bool:
        if not self.is_main_rise_runner(position):
            return False
        protect_price = self.main_rise_runner_protect_price(position)
        return protect_price > 0 and latest_price <= protect_price

    def is_quality_positive_lock_ready(self, position: PaperPosition) -> bool:
        return position.unrealized_pnl_pct > self.quality_positive_lock_profit_pct(position)

    def quality_positive_lock_profit_pct(self, position: PaperPosition) -> float:
        return max(
            self._settings.positive_lock_profit_pct,
            self.max_adverse_pct_for_position(position)
            * self._settings.positive_lock_min_profit_drawdown_ratio,
        )

    @staticmethod
    def max_adverse_pct_for_position(position: PaperPosition) -> float:
        trough_price = position.trough_price or position.latest_price or position.entry_price
        if position.entry_price <= 0:
            return 0.0
        return max(0.0, (position.entry_price - trough_price) / position.entry_price)


def format_pct(value: float) -> str:
    text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


__all__ = ["PaperExitDecision", "PaperExitPolicy", "PaperExitSettings", "format_pct"]
