"""Strategy-boundary reset review policy."""

from __future__ import annotations

from shared.contracts import AdjustmentStatus, StrategyConfig, StrategyResetReview

from .message_catalog import DomainMessages, load_domain_messages


class StrategyResetReviewPolicy:
    """Describes whether a local strategy boundary reset can be confirmed."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def build_review(
        self,
        strategy_config: StrategyConfig,
        default_config: StrategyConfig,
        has_local_config: bool,
    ) -> StrategyResetReview:
        blockers = self._blockers(has_local_config)
        reset_status = (
            AdjustmentStatus.WAITING_USER
            if has_local_config and not blockers
            else AdjustmentStatus.NOT_AVAILABLE
        )
        can_reset = reset_status is AdjustmentStatus.WAITING_USER
        return StrategyResetReview(
            review_id=f"strategy-reset-review-{strategy_config.strategy_id}",
            strategy_id=strategy_config.strategy_id,
            source=strategy_config.source,
            from_version=strategy_config.version,
            to_version=default_config.version,
            reset_status=reset_status,
            can_reset=can_reset,
            blockers=blockers,
            recent_changes=strategy_config.recent_changes,
            summary=self._summary(reset_status),
            next_action=self._next_action(reset_status),
        )

    def _blockers(self, has_local_config: bool) -> tuple[str, ...]:
        if has_local_config:
            return ()
        return (self._messages.text("strategy_reset_review", "blocker_no_local"),)

    def _summary(self, reset_status: AdjustmentStatus) -> str:
        if reset_status is AdjustmentStatus.WAITING_USER:
            return self._messages.text("strategy_reset_review", "summary_waiting")
        return self._messages.text("strategy_reset_review", "summary_blocked")

    def _next_action(self, reset_status: AdjustmentStatus) -> str:
        if reset_status is AdjustmentStatus.WAITING_USER:
            return self._messages.text("strategy_reset_review", "next_waiting")
        return self._messages.text("strategy_reset_review", "next_blocked")
