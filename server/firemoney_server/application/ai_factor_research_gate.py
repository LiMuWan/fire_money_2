"""Admission gate for AI-proposed trading factor research.

The gate is intentionally deterministic. LLMs may propose hypotheses, but this
service only accepts measurable evidence and never authorizes live trading.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIFactorYearEvidence:
    year: str
    sample_count: int
    return_pct: float
    win_rate: float
    max_drawdown_pct: float


@dataclass(frozen=True)
class AIFactorResearchEvidence:
    factor_id: str
    factor_name: str
    hypothesis: str
    source: str
    deterministic_rule: str
    point_in_time_safe: bool
    total_sample_count: int
    validation_sample_count: int
    validation_return_pct: float
    validation_win_rate: float
    validation_max_drawdown_pct: float
    baseline_validation_return_pct: float
    baseline_max_drawdown_pct: float
    challenger_weak_year_return_pct: float
    baseline_weak_year_return_pct: float
    average_profit_drawdown_ratio: float
    yearly: tuple[AIFactorYearEvidence, ...]


@dataclass(frozen=True)
class AIFactorGateThresholds:
    min_total_sample_count: int = 100
    min_validation_sample_count: int = 20
    min_validation_win_rate: float = 0.55
    min_average_profit_drawdown_ratio: float = 1.0
    validation_return_tolerance_pct: float = 0.005
    drawdown_worse_tolerance_pct: float = 0.002
    weak_year_return_tolerance_pct: float = 0.0


@dataclass(frozen=True)
class AIFactorGateDecision:
    factor_id: str
    status: str
    action: str
    can_affect_trading: bool
    summary: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_steps: tuple[str, ...]


class AIFactorResearchGate:
    """Validate whether an AI-proposed factor may enter shadow research."""

    def __init__(self, thresholds: AIFactorGateThresholds | None = None) -> None:
        self._thresholds = thresholds or AIFactorGateThresholds()

    def evaluate(self, evidence: AIFactorResearchEvidence) -> AIFactorGateDecision:
        blockers: list[str] = []
        warnings: list[str] = []
        thresholds = self._thresholds

        if not evidence.deterministic_rule.strip():
            blockers.append("AI hypothesis has not been converted into a deterministic rule.")
        if not evidence.point_in_time_safe:
            blockers.append("Point-in-time safety is not proven; future leakage is possible.")
        if evidence.total_sample_count < thresholds.min_total_sample_count:
            blockers.append(
                "Total samples are insufficient: "
                f"{evidence.total_sample_count} < {thresholds.min_total_sample_count}."
            )
        if evidence.validation_sample_count < thresholds.min_validation_sample_count:
            blockers.append(
                "Validation samples are insufficient: "
                f"{evidence.validation_sample_count} < {thresholds.min_validation_sample_count}."
            )
        if evidence.validation_win_rate < thresholds.min_validation_win_rate:
            blockers.append(
                "Validation win rate is below the gate: "
                f"{evidence.validation_win_rate:.2%} < {thresholds.min_validation_win_rate:.2%}."
            )
        if (
            evidence.average_profit_drawdown_ratio
            < thresholds.min_average_profit_drawdown_ratio
        ):
            blockers.append(
                "Average profit/drawdown ratio is below the gate: "
                f"{evidence.average_profit_drawdown_ratio:.2f}R < "
                f"{thresholds.min_average_profit_drawdown_ratio:.2f}R."
            )

        negative_years = tuple(item for item in evidence.yearly if item.return_pct < 0)
        if negative_years:
            years = ", ".join(item.year for item in negative_years)
            blockers.append(f"Calendar-year return is negative in: {years}.")
        if not evidence.yearly:
            blockers.append("Yearly evidence is missing; total return cannot hide weak years.")

        if self._validation_return_is_worse(evidence, thresholds):
            blockers.append(
                "Validation return is worse than the current mainline tolerance: "
                f"{evidence.validation_return_pct:.2%} vs "
                f"{evidence.baseline_validation_return_pct:.2%}."
            )
        if self._drawdown_is_worse(evidence, thresholds):
            blockers.append(
                "Max drawdown is worse than the current mainline tolerance: "
                f"{evidence.validation_max_drawdown_pct:.2%} vs "
                f"{evidence.baseline_max_drawdown_pct:.2%}."
            )
        if self._weak_year_is_worse(evidence, thresholds):
            blockers.append(
                "Weak-year return is worse than the current mainline: "
                f"{evidence.challenger_weak_year_return_pct:.2%} vs "
                f"{evidence.baseline_weak_year_return_pct:.2%}."
            )

        if evidence.source.lower() == "ai":
            warnings.append(
                "AI source is treated as a hypothesis only; it cannot trigger buy/sell actions."
            )

        if blockers:
            return AIFactorGateDecision(
                factor_id=evidence.factor_id,
                status="rejected",
                action="reject_factor",
                can_affect_trading=False,
                summary=(
                    f"{evidence.factor_name} is rejected before shadow research; "
                    "fix blockers and rerun PIT backtests first."
                ),
                blockers=tuple(blockers),
                warnings=tuple(warnings),
                next_steps=(
                    "Convert the idea into deterministic fields and thresholds.",
                    "Rerun 2020+ yearly/monthly/drawdown/friction backtests.",
                    "Keep the factor out of strategy-decision and paper-decision.",
                ),
            )

        return AIFactorGateDecision(
            factor_id=evidence.factor_id,
            status="shadow_research_only",
            action="allow_shadow_research",
            can_affect_trading=False,
            summary=(
                f"{evidence.factor_name} may enter shadow research, but it still cannot "
                "affect live or paper trading until future reviews explicitly promote it."
            ),
            blockers=(),
            warnings=tuple(warnings),
            next_steps=(
                "Record daily shadow signals without writing the paper ledger.",
                "Compare against the current board-shadow-system baseline.",
                "Promote only after weak years, validation return, drawdown, and real paper samples pass.",
            ),
        )

    @staticmethod
    def _validation_return_is_worse(
        evidence: AIFactorResearchEvidence,
        thresholds: AIFactorGateThresholds,
    ) -> bool:
        allowed = evidence.baseline_validation_return_pct - thresholds.validation_return_tolerance_pct
        return evidence.validation_return_pct < allowed

    @staticmethod
    def _drawdown_is_worse(
        evidence: AIFactorResearchEvidence,
        thresholds: AIFactorGateThresholds,
    ) -> bool:
        challenger = abs(evidence.validation_max_drawdown_pct)
        baseline = abs(evidence.baseline_max_drawdown_pct)
        return challenger > baseline + thresholds.drawdown_worse_tolerance_pct

    @staticmethod
    def _weak_year_is_worse(
        evidence: AIFactorResearchEvidence,
        thresholds: AIFactorGateThresholds,
    ) -> bool:
        allowed = evidence.baseline_weak_year_return_pct - thresholds.weak_year_return_tolerance_pct
        return evidence.challenger_weak_year_return_pct < allowed


__all__ = [
    "AIFactorGateDecision",
    "AIFactorGateThresholds",
    "AIFactorResearchEvidence",
    "AIFactorResearchGate",
    "AIFactorYearEvidence",
]
