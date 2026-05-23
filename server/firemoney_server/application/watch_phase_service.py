"""Watch-phase orchestration for FireMoney paper-trading events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from shared.contracts import (
    OneToTwoCandidate,
    OneToTwoEventType,
    OneToTwoMorningReport,
    PaperAccount,
    PaperPosition,
)


class MarketDataProviderLike(Protocol):
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        """Load the market rows for one trade date."""


class PaperTradeStoreLike(Protocol):
    def prepare_for_trade_date(self, trade_date: str) -> PaperAccount:
        """Prepare the account for the requested trade date."""

    def record_candidate_event(
        self,
        candidate: OneToTwoCandidate,
        message: str,
        event_type: OneToTwoEventType = OneToTwoEventType.CANDIDATE_SELECTED,
    ) -> PaperAccount:
        """Append a candidate-stage account event."""

    def buy_candidate(self, candidate: OneToTwoCandidate, guard_decision: object | None = None) -> PaperAccount:
        """Append a paper-buy account event."""

    def update_risk(self, candidate: OneToTwoCandidate) -> PaperAccount:
        """Refresh an open position's risk state."""


class GuardLike(Protocol):
    def evaluate(self, account: PaperAccount, quality_score: float | None) -> object:
        """Evaluate whether a new paper entry is allowed."""


@dataclass(frozen=True)
class WatchPhaseResult:
    phase: str
    account: PaperAccount
    ready: tuple[OneToTwoCandidate, ...]


PositiveCandidates = Callable[
    [tuple[OneToTwoCandidate, ...]],
    tuple[OneToTwoCandidate, ...],
]
WithLiveMainlineContinuity = Callable[
    [OneToTwoCandidate, tuple[OneToTwoCandidate, ...]],
    OneToTwoCandidate,
]
ExitIfDisciplineRequires = Callable[[OneToTwoCandidate], PaperAccount]
CandidateForPosition = Callable[[PaperPosition, str], OneToTwoCandidate]
CandidateWithGuardLimit = Callable[[OneToTwoCandidate, object], OneToTwoCandidate]
GuardContract = Callable[[object], object]


class WatchPhaseService:
    """Applies scan/auction/open/risk phase effects without formatting notifications."""

    VALID_PHASES = frozenset({"scan", "auction", "open", "risk"})

    def __init__(
        self,
        *,
        paper_store: PaperTradeStoreLike,
        market_data_provider: MarketDataProviderLike,
        policy: OneToTwoPolicy,
        guard: GuardLike,
        positive_expectancy_candidates: PositiveCandidates,
        with_live_mainline_continuity: WithLiveMainlineContinuity,
        exit_if_discipline_requires: ExitIfDisciplineRequires,
        candidate_for_position: CandidateForPosition,
        candidate_with_guard_position_limit: CandidateWithGuardLimit,
        guard_contract: GuardContract,
    ) -> None:
        self._paper_store = paper_store
        self._market_data_provider = market_data_provider
        self._policy = policy
        self._guard = guard
        self._positive_expectancy_candidates = positive_expectancy_candidates
        self._with_live_mainline_continuity = with_live_mainline_continuity
        self._exit_if_discipline_requires = exit_if_discipline_requires
        self._candidate_for_position = candidate_for_position
        self._candidate_with_guard_position_limit = candidate_with_guard_position_limit
        self._guard_contract = guard_contract

    def normalize_phase(self, phase: str) -> str:
        return phase if phase in self.VALID_PHASES else "scan"

    def run_phase(
        self,
        *,
        report: OneToTwoMorningReport,
        phase: str,
        allow_new_entry: bool = True,
        entry_block_message: str = "今日主策略要求空仓，watch 不写入新的模拟买入。",
    ) -> WatchPhaseResult:
        phase = self.normalize_phase(phase)
        ready = self._positive_expectancy_candidates(report.candidates)
        account = self._paper_store.prepare_for_trade_date(report.trade_date)
        raw_candidates = report.candidates
        if account.positions and phase in {"open", "risk"}:
            raw_candidates = self._load_raw_candidates(report)
        guard_result = self._guard.evaluate(
            account,
            ready[0].turnover_quality_score if ready else None,
        )
        notification_candidates = ready
        if account.positions:
            notification_candidates = self._position_context_candidates(
                account=account,
                phase=phase,
                report=report,
                raw_candidates=raw_candidates,
                ready=ready,
            )
            account = self._apply_position_phase(
                account=account,
                phase=phase,
                report=report,
                raw_candidates=raw_candidates,
            )
        elif ready and phase == "scan":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "主线首板候选入池，等待封板纪律和竞价确认。",
            )
        elif ready and phase == "auction":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "竞价确认，主线首板候选进入一进二确认观察。",
                event_type=OneToTwoEventType.AUCTION_CONFIRMED,
            )
        elif ready and phase == "open" and not allow_new_entry:
            account = self._paper_store.record_candidate_event(
                ready[0],
                entry_block_message,
                event_type=OneToTwoEventType.BLOCKED,
            )
        elif ready and phase == "open" and getattr(guard_result, "action", "") == "stand_aside":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "模拟盘收益守门未通过，今天暂停新开仓，先保护账户收益曲线。",
                event_type=OneToTwoEventType.BLOCKED,
            )
        elif ready and phase == "open":
            buy_candidate = self._first_executable_candidate(
                account=account,
                candidates=ready,
                guard_result=guard_result,
            )
            if buy_candidate is None:
                return WatchPhaseResult(
                    phase=phase,
                    account=self._paper_store.record_candidate_event(
                        ready[0],
                        "小账户一手成本超过当前仓位上限，今日跳过模拟买入。",
                        event_type=OneToTwoEventType.BLOCKED,
                    ),
                    ready=notification_candidates,
                )
            account = self._paper_store.buy_candidate(
                buy_candidate,
                guard_decision=self._guard_contract(guard_result),
            )
        return WatchPhaseResult(
            phase=phase,
            account=account,
            ready=notification_candidates,
        )

    def _position_context_candidates(
        self,
        *,
        account: PaperAccount,
        phase: str,
        report: OneToTwoMorningReport,
        raw_candidates: tuple[OneToTwoCandidate, ...],
        ready: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        if not account.positions or phase not in {"open", "risk"}:
            return ready
        held_symbol = account.positions[0].symbol
        matched = self._candidate_by_symbol(raw_candidates, held_symbol)
        if matched is None:
            matched = self._candidate_by_symbol(report.candidates, held_symbol)
        if matched is None:
            return ready
        matched = self._with_live_mainline_continuity(matched, report.candidates)
        return (matched, *(item for item in ready if item.symbol != held_symbol))

    def _apply_position_phase(
        self,
        *,
        account: PaperAccount,
        phase: str,
        report: OneToTwoMorningReport,
        raw_candidates: tuple[OneToTwoCandidate, ...],
    ) -> PaperAccount:
        if not account.positions:
            return account
        position = account.positions[0]
        matched = self._candidate_by_symbol(report.candidates, position.symbol)
        raw_match = self._candidate_by_symbol(raw_candidates, position.symbol)
        if matched is None and phase in {"open", "risk"}:
            matched = raw_match
        elif matched is not None and raw_match is not None and phase == "risk":
            # Paper exits should follow live risk context. The daily board-shadow
            # candidate can still drive entries, but it must not mask a fading
            # raw market row when we already hold the symbol.
            matched = raw_match
        if matched and phase in {"open", "risk"}:
            matched = self._with_live_mainline_continuity(matched, report.candidates)
            account = self._paper_store.update_risk(matched)
            if account.positions and phase == "risk":
                account = self._exit_if_discipline_requires(matched)
        elif phase == "risk":
            fallback = self._candidate_for_position(position, report.trade_date)
            account = self._exit_if_discipline_requires(fallback)
        return account

    def _load_raw_candidates(
        self,
        report: OneToTwoMorningReport,
    ) -> tuple[OneToTwoCandidate, ...]:
        try:
            return self._policy.build_candidates(
                self._market_data_provider.load_one_to_two_rows(report.trade_date)
            )
        except Exception:
            return report.candidates

    @staticmethod
    def _candidate_by_symbol(
        candidates: tuple[OneToTwoCandidate, ...],
        symbol: str,
    ) -> OneToTwoCandidate | None:
        return next((candidate for candidate in candidates if candidate.symbol == symbol), None)

    def _first_executable_candidate(
        self,
        *,
        account: PaperAccount,
        candidates: tuple[OneToTwoCandidate, ...],
        guard_result: object,
    ) -> OneToTwoCandidate | None:
        for candidate in candidates:
            adjusted = self._candidate_with_guard_position_limit(candidate, guard_result)
            lot_cost = adjusted.entry_price * 100
            max_budget = account.equity * min(
                account.max_position_pct,
                adjusted.position_limit_pct,
            )
            if lot_cost <= account.cash + 0.0001 and lot_cost <= max_budget + 0.0001:
                return adjusted
        return None


__all__ = ["WatchPhaseResult", "WatchPhaseService"]
