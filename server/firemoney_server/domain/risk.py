"""Risk review policy for semi-automatic execution."""

from __future__ import annotations

from shared.contracts import Opportunity, ReviewDecision, RiskLevel, RiskReview

from .message_catalog import DomainMessages, load_domain_messages


class RiskReviewPolicy:
    """Keeps execution gated by review instead of direct auto-trading."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def review(self, opportunity: Opportunity) -> RiskReview:
        blockers: list[str] = []
        warnings: list[str] = []

        if opportunity.score < 70:
            blockers.append(self._messages.text("risk", "blocker_low_score"))
        if "liquidity_thin" in opportunity.risk_flags:
            blockers.append(self._messages.text("risk", "blocker_liquidity_thin"))
        if "gap_high" in opportunity.risk_flags:
            warnings.append(self._messages.text("risk", "warning_gap_high"))
        if opportunity.confidence < 0.72:
            warnings.append(self._messages.text("risk", "warning_low_confidence"))

        if blockers:
            decision = ReviewDecision.BLOCK
            risk_level = RiskLevel.BLOCKED
            position_limit_pct = 0.0
            next_action = self._messages.text("risk", "next_blocked")
        elif warnings:
            decision = ReviewDecision.NEEDS_REVIEW
            risk_level = RiskLevel.MEDIUM
            position_limit_pct = 0.08
            next_action = self._messages.text("risk", "next_needs_review")
        else:
            decision = ReviewDecision.APPROVE_FOR_CONFIRMATION
            risk_level = RiskLevel.LOW
            position_limit_pct = 0.12
            next_action = self._messages.text("risk", "next_approved")

        return RiskReview(
            review_id=f"review-{opportunity.symbol}",
            opportunity=opportunity,
            decision=decision,
            risk_level=risk_level,
            position_limit_pct=position_limit_pct,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            next_action=next_action,
        )
