"""Small paper-trading runtime adapters shared by watch and command sheets."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from server.firemoney_server.application.paper_entry_policy import PaperEntryPolicy
from server.firemoney_server.application.paper_trading_guard import PaperTradingGuardResult
from shared.contracts import (
    OneToTwoCandidate,
    OneToTwoPositionProfile,
    PaperAccount,
    PaperTradingGuardDecision,
)


class PaperRuntimeSettingsLike(Protocol):
    max_position_pct: float


class TradingCalendarLike(Protocol):
    def resolve(self, requested_date: str | None = None):
        """Resolve a date into trading-day context."""


class PaperStoreLike(Protocol):
    def load(self) -> PaperAccount:
        """Load the current paper account."""


class PaperRuntimeService:
    """Owns paper-account view and guard DTO adaptation outside MainChain."""

    def __init__(
        self,
        *,
        settings: PaperRuntimeSettingsLike,
        trading_calendar: TradingCalendarLike,
        paper_store: PaperStoreLike,
        entry_policy: PaperEntryPolicy,
    ) -> None:
        self._settings = settings
        self._trading_calendar = trading_calendar
        self._paper_store = paper_store
        self._entry_policy = entry_policy

    def holding_trade_days(self, opened_at: str, trade_date: str) -> int:
        if opened_at >= trade_date:
            return 0
        current = opened_at
        count = 0
        while current < trade_date:
            next_context = self._trading_calendar.resolve(current)
            next_date = next_context.next_trade_date
            if next_date <= current:
                break
            current = next_date
            count += 1
        return count

    def account_view_for_trade_date(self, trade_date: str) -> PaperAccount:
        account = self._paper_store.load()
        if not account.last_trade_date:
            return replace(account, last_trade_date=trade_date, daily_trade_count=0)
        if trade_date <= account.last_trade_date:
            return account
        positions = tuple(
            replace(
                position,
                can_sell_today=True,
                risk_note="已进入下一交易日，若继续跌破止损可模拟卖出。",
            )
            for position in account.positions
        )
        return replace(
            account,
            last_trade_date=trade_date,
            daily_trade_count=0,
            positions=positions,
        )

    def positive_expectancy_candidates(
        self,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        return self._entry_policy.positive_expectancy_candidates(candidates)

    def candidate_with_guard_position_limit(
        self,
        candidate: OneToTwoCandidate,
        guard_result: PaperTradingGuardResult,
    ) -> OneToTwoCandidate:
        guarded = self._entry_policy.candidate_with_guard_position_limit(
            candidate,
            guard_result,
            format_pct=self.format_pct,
        )
        return self._entry_policy.candidate_with_execution_friction_position_limit(
            guarded,
            format_pct=self.format_pct,
        )

    def guard_contract(
        self,
        result: PaperTradingGuardResult,
    ) -> PaperTradingGuardDecision:
        return PaperTradingGuardDecision(
            status=result.status,
            action=result.action,
            review_sample_count=result.review_sample_count,
            win_rate=result.win_rate,
            average_return_pct=result.average_return_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            consecutive_losses=result.consecutive_losses,
            consecutive_quality_failures=result.consecutive_quality_failures,
            average_profit_drawdown_ratio=result.average_profit_drawdown_ratio,
            risk_quality_pass_rate=result.risk_quality_pass_rate,
            suggested_position_pct=result.suggested_position_pct,
            reasons=result.reasons,
            next_action=result.next_action,
            candidate_quality_bucket=result.candidate_quality_bucket,
            candidate_quality_sample_count=result.candidate_quality_sample_count,
            candidate_quality_win_rate=result.candidate_quality_win_rate,
            candidate_quality_average_return_pct=(
                result.candidate_quality_average_return_pct
            ),
            candidate_quality_risk_quality_pass_rate=(
                result.candidate_quality_risk_quality_pass_rate
            ),
        )

    def candidate_for_position(self, position, trade_date: str) -> OneToTwoCandidate:
        return OneToTwoCandidate(
            symbol=position.symbol,
            name=position.name,
            trade_date=trade_date,
            score=position.opened_score,
            status="ready",
            latest_price=position.latest_price,
            limit_up_price=position.latest_price,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            position_limit_pct=self._settings.max_position_pct,
            first_board_score=0,
            auction_score=0,
            position_score=0,
            theme_score=0,
            liquidity_score=0,
            position_profile=OneToTwoPositionProfile(
                label=position.position_label,
                low_position_score=0,
                breakout_score=0,
                pressure_score=0,
                moving_average_score=0,
                volume_score=0,
                summary=position.position_label,
                risk_notes=(),
            ),
            blockers=(),
            warnings=(),
            rationale="历史回放强制归档样本。",
            next_action="回放结束。",
            exit_plan=position.exit_plan,
            mainline_continuity=position.mainline_continuity,
            turnover_quality_label="持仓回放",
        )

    @staticmethod
    def format_pct(value: float) -> str:
        text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"


__all__ = ["PaperRuntimeService"]
