"""Strategy configuration policy for applying reviewed adjustments."""

from __future__ import annotations

from shared.contracts import (
    AdjustmentStatus,
    Recap,
    StrategyAdjustment,
    StrategyConfig,
)

from .message_catalog import DomainMessages, load_domain_messages


class StrategyConfigPolicy:
    """Applies recap suggestions only after explicit user confirmation."""

    def __init__(self, messages: DomainMessages | None = None) -> None:
        self._messages = messages or load_domain_messages()

    def mark_waiting_adjustment(
        self,
        strategy_config: StrategyConfig,
        recap: Recap | None,
    ) -> StrategyConfig:
        if not recap or not recap.strategy_adjustments:
            return strategy_config

        return StrategyConfig(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            version=strategy_config.version,
            risk_profile=strategy_config.risk_profile,
            parameters=dict(strategy_config.parameters),
            impact_summary=strategy_config.impact_summary,
            adjustment_status=AdjustmentStatus.WAITING_USER,
            adjustment_message=self._messages.text(
                "strategy_config",
                "waiting_adjustment_message",
            ),
            source=strategy_config.source,
            recent_changes=strategy_config.recent_changes,
        )

    def apply_adjustments(
        self,
        strategy_config: StrategyConfig,
        adjustments: tuple[StrategyAdjustment, ...],
    ) -> StrategyConfig:
        if not adjustments:
            return strategy_config

        parameters = dict(strategy_config.parameters)
        applied_labels: list[str] = []
        for adjustment in adjustments:
            parameters[adjustment.key] = adjustment.suggested_value
            applied_labels.append(adjustment.label)

        label_separator = self._messages.text(
            "strategy_config",
            "applied_label_separator",
        )
        return StrategyConfig(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            version=self._next_version(strategy_config.version),
            risk_profile=strategy_config.risk_profile,
            parameters=parameters,
            impact_summary=self._messages.format(
                "strategy_config",
                "applied_impact_summary",
                labels=label_separator.join(applied_labels),
            ),
            adjustment_status=AdjustmentStatus.APPLIED,
            adjustment_message=self._messages.text(
                "strategy_config",
                "applied_adjustment_message",
            ),
            source="local",
            recent_changes=strategy_config.recent_changes,
        )

    def _next_version(self, version: str) -> str:
        parts = version.split(".")
        if len(parts) != 3 or not parts[-1].isdigit():
            return version
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
