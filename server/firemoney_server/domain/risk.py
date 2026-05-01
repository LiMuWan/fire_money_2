"""Risk review policy for semi-automatic execution."""

from __future__ import annotations

from shared.contracts import Opportunity, ReviewDecision, RiskLevel, RiskReview


class RiskReviewPolicy:
    """Keeps execution gated by review instead of direct auto-trading."""

    def review(self, opportunity: Opportunity) -> RiskReview:
        blockers: list[str] = []
        warnings: list[str] = []

        if opportunity.score < 70:
            blockers.append("策略评分低于执行门槛")
        if "liquidity_thin" in opportunity.risk_flags:
            blockers.append("流动性不足，禁止自动送审")
        if "gap_high" in opportunity.risk_flags:
            warnings.append("高开缺口偏大，需要人工复核追价风险")
        if opportunity.confidence < 0.72:
            warnings.append("信号置信度不足，建议降低仓位")

        if blockers:
            decision = ReviewDecision.BLOCK
            risk_level = RiskLevel.BLOCKED
            position_limit_pct = 0.0
            next_action = "回到机会池，等待更高质量候选"
        elif warnings:
            decision = ReviewDecision.NEEDS_REVIEW
            risk_level = RiskLevel.MEDIUM
            position_limit_pct = 0.08
            next_action = "进入执行审查，人工确认风险后再提交"
        else:
            decision = ReviewDecision.APPROVE_FOR_CONFIRMATION
            risk_level = RiskLevel.LOW
            position_limit_pct = 0.12
            next_action = "生成委托草稿，等待二次确认"

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
