"""Signal scan policy for the market judgment workspace."""

from __future__ import annotations

from shared.contracts import Opportunity, SignalScanReport, StrategyConfig, WorkflowStage

from .message_catalog import DomainMessages, load_domain_messages


class SignalScanPolicy:
    """Builds an explainable signal scan report from ranked candidates."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_report(
        self,
        opportunities: tuple[Opportunity, ...],
        strategy_config: StrategyConfig,
        universe_size: int,
        report_id: str,
    ) -> SignalScanReport:
        min_score = float(strategy_config.parameters.get("min_score", 70))
        confidence_floor = float(
            strategy_config.parameters.get("confidence_floor", 0.72)
        )

        ranked = tuple(
            sorted(
                opportunities,
                key=lambda item: (item.score, item.confidence),
                reverse=True,
            )
        )
        executable = tuple(
            item
            for item in ranked
            if item.score >= min_score
            and item.confidence >= confidence_floor
            and "liquidity_thin" not in item.risk_flags
        )
        focus_opportunities = executable[:2]
        focus_opportunity = focus_opportunities[0] if focus_opportunities else None

        watch_notes = self._build_watch_notes(
            ranked=ranked,
            executable=executable,
            min_score=min_score,
            confidence_floor=confidence_floor,
        )

        return SignalScanReport(
            report_id=report_id,
            stage=WorkflowStage.SIGNAL_SCAN,
            universe_size=universe_size,
            candidate_count=len(executable),
            ranked_opportunities=ranked,
            focus_opportunities=focus_opportunities,
            focus_opportunity=focus_opportunity,
            summary=self._build_summary(
                total=len(ranked),
                executable_count=len(executable),
                min_score=min_score,
                confidence_floor=confidence_floor,
            ),
            watch_notes=watch_notes,
            next_action=self._next_action(focus_opportunity),
        )

    def _build_summary(
        self,
        total: int,
        executable_count: int,
        min_score: float,
        confidence_floor: float,
    ) -> str:
        return self._messages.format(
            "signal_scan",
            "summary",
            total=total,
            executable_count=executable_count,
            min_score=min_score,
            confidence_floor=confidence_floor,
        )

    def _build_watch_notes(
        self,
        ranked: tuple[Opportunity, ...],
        executable: tuple[Opportunity, ...],
        min_score: float,
        confidence_floor: float,
    ) -> tuple[str, ...]:
        notes: list[str] = [
            self._messages.format(
                "signal_scan",
                "note_threshold",
                min_score=min_score,
                confidence_floor=confidence_floor,
            ),
            self._messages.text("signal_scan", "note_liquidity"),
        ]
        if any("gap_high" in item.risk_flags for item in executable):
            notes.append(self._messages.text("signal_scan", "note_gap_high"))
        filtered_count = len(ranked) - len(executable)
        if filtered_count:
            notes.append(
                self._messages.format(
                    "signal_scan",
                    "note_filtered",
                    filtered_count=filtered_count,
                )
            )
        return tuple(notes)

    def _next_action(self, focus_opportunity: Opportunity | None) -> str:
        if not focus_opportunity:
            return self._messages.text("signal_scan", "next_empty")
        return self._messages.format(
            "signal_scan",
            "next_focus",
            name=focus_opportunity.name,
        )
