"""Paper-trading entry discipline for FireMoney candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from server.firemoney_server.application.paper_trading_guard import PaperTradingGuardResult
from shared.contracts import OneToTwoCandidate


class PaperEntrySettings(Protocol):
    stop_loss_pct: float
    paper_entry_mainboard_only: bool
    minimum_reward_risk_ratio: float
    paper_guard_min_profit_drawdown_ratio: float
    min_turnover_dragon_score: float
    min_volume_ratio_5: float
    min_rsi_14: float
    max_rsi_14: float
    min_position_percentile_60: float
    min_breakout_structure_score: float
    paper_guard_reduced_position_pct: float
    mainline_fade_score: float


@dataclass(frozen=True)
class PaperEntryQuality:
    risk_pct: float
    reward_pct: float
    reward_risk_ratio: float
    drawdown_budget_pct: float


class PaperEntryPolicy:
    """Decides whether a candidate deserves a new paper-trading entry."""

    def __init__(self, settings: PaperEntrySettings) -> None:
        self._settings = settings

    def positive_expectancy_candidates(
        self,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        return tuple(
            candidate
            for candidate in candidates
            if self.is_positive_expectancy_candidate(candidate)
        )

    def is_positive_expectancy_candidate(self, candidate: OneToTwoCandidate) -> bool:
        if candidate.status != "ready" or candidate.exit_plan is None:
            return False
        if self._mainboard_only() and not self._is_mainboard_symbol(candidate.symbol):
            return False
        if self._is_mainline_continuity_fading(candidate):
            return False
        if not self._has_valid_breakout_structure(candidate):
            return False
        if "board-shadow-system" in candidate.strategy_tags:
            quality = self.candidate_entry_quality(candidate)
            return (
                candidate.score >= 95
                and candidate.turnover_quality_score
                >= self._settings.min_turnover_dragon_score
                and quality.reward_pct > 0
                and quality.risk_pct <= candidate.exit_plan.stop_loss_pct + 0.001
            )
        if candidate.score < 95:
            return False
        if candidate.sealing_score < 18 or candidate.mainline_score < 18:
            return False
        if candidate.leader_score < 18:
            return False
        if candidate.turnover_quality_score < self._settings.min_turnover_dragon_score:
            return False
        profile = candidate.position_profile
        if profile.volume_ratio < max(1.2, self._settings.min_volume_ratio_5):
            return False
        if not (
            self._settings.min_rsi_14
            <= profile.rsi_14
            <= min(78.0, self._settings.max_rsi_14)
        ):
            return False
        if profile.position_percentile_60 < max(
            0.7,
            self._settings.min_position_percentile_60,
        ):
            return False
        quality = self.candidate_entry_quality(candidate)
        return (
            quality.reward_risk_ratio >= self._settings.minimum_reward_risk_ratio
            and quality.reward_pct > quality.risk_pct
            and quality.risk_pct <= quality.drawdown_budget_pct
        )

    def _has_valid_breakout_structure(self, candidate: OneToTwoCandidate) -> bool:
        structure = candidate.breakout_structure
        return bool(
            structure
            and structure.passed
            and structure.score >= self._settings.min_breakout_structure_score
        )

    def _mainboard_only(self) -> bool:
        return bool(getattr(self._settings, "paper_entry_mainboard_only", True))

    def _is_mainline_continuity_fading(self, candidate: OneToTwoCandidate) -> bool:
        continuity = candidate.mainline_continuity
        if continuity is None:
            return False
        return (
            continuity.status == "fading"
            or continuity.score < self._settings.mainline_fade_score
        )

    @staticmethod
    def _is_mainboard_symbol(symbol: str) -> bool:
        code = str(symbol).strip()
        return code.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))

    def candidate_reward_risk_ratio(self, candidate: OneToTwoCandidate) -> float:
        return self.candidate_entry_quality(candidate).reward_risk_ratio

    def candidate_entry_quality(self, candidate: OneToTwoCandidate) -> PaperEntryQuality:
        if candidate.exit_plan is None:
            return PaperEntryQuality(
                risk_pct=0.0,
                reward_pct=0.0,
                reward_risk_ratio=0.0,
                drawdown_budget_pct=0.0,
            )
        risk_pct = max(
            (candidate.entry_price - candidate.stop_loss) / candidate.entry_price,
            0.0001,
        )
        reward_pct = max(
            (
                candidate.exit_plan.first_take_profit_price
                - candidate.entry_price
            )
            / candidate.entry_price,
            0.0,
        )
        reward_risk_ratio = reward_pct / max(risk_pct, 0.0001)
        drawdown_budget_pct = reward_pct / max(
            self._settings.paper_guard_min_profit_drawdown_ratio,
            0.0001,
        )
        return PaperEntryQuality(
            risk_pct=round(risk_pct, 4),
            reward_pct=round(reward_pct, 4),
            reward_risk_ratio=round(reward_risk_ratio, 4),
            drawdown_budget_pct=round(drawdown_budget_pct, 4),
        )

    @staticmethod
    def candidate_with_guard_position_limit(
        candidate: OneToTwoCandidate,
        guard_result: PaperTradingGuardResult,
        *,
        format_pct,
    ) -> OneToTwoCandidate:
        if guard_result.action != "allow_reduced":
            return candidate
        from dataclasses import replace

        return replace(
            candidate,
            position_limit_pct=min(
                candidate.position_limit_pct,
                guard_result.suggested_position_pct,
            ),
            warnings=candidate.warnings
            + (
                f"模拟盘收益守门降仓至 {format_pct(guard_result.suggested_position_pct)}。",
            ),
        )

    def candidate_with_execution_friction_position_limit(
        self,
        candidate: OneToTwoCandidate,
        *,
        format_pct,
    ) -> OneToTwoCandidate:
        if not self._has_execution_friction_risk(candidate):
            return candidate
        from dataclasses import replace

        reduced_position = min(
            candidate.position_limit_pct,
            self._settings.paper_guard_reduced_position_pct,
        )
        return replace(
            candidate,
            position_limit_pct=reduced_position,
            warnings=candidate.warnings
            + (
                "执行摩擦风险触发降仓：候选存在炸板、排队或滑点风险提示，"
                f"模拟买入仓位上限降至 {format_pct(reduced_position)}。",
            ),
        )

    @staticmethod
    def _has_execution_friction_risk(candidate: OneToTwoCandidate) -> bool:
        keywords = ("炸板", "买不到", "排队", "滑点", "封板资金刚过线")
        return any(
            keyword in warning
            for warning in candidate.warnings
            for keyword in keywords
        )


__all__ = ["PaperEntryPolicy", "PaperEntryQuality", "PaperEntrySettings"]
