"""Opportunity ranking rules."""

from __future__ import annotations

from shared.contracts import Opportunity


class OpportunityRanker:
    """Ranks opportunities for the opportunity pool."""

    def rank(self, candidates: tuple[Opportunity, ...]) -> tuple[Opportunity, ...]:
        return tuple(
            sorted(
                candidates,
                key=lambda item: (item.score, item.confidence),
                reverse=True,
            )
        )
