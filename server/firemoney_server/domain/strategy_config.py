"""Strategy configuration policy for applying reviewed adjustments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.contracts import (
    AdjustmentStatus,
    Recap,
    StrategyAdjustment,
    StrategyConfig,
)

from .message_catalog import DomainMessages, load_domain_messages


@dataclass(frozen=True)
class StrategyParameterRule:
    key: str
    value_type: type
    minimum: float | int
    maximum: float | int


DEFAULT_PARAMETER_RULES: tuple[StrategyParameterRule, ...] = (
    StrategyParameterRule("min_score", int, 0, 100),
    StrategyParameterRule("max_position_pct", float, 0.01, 0.2),
    StrategyParameterRule("confidence_floor", float, 0.5, 1.0),
    StrategyParameterRule("max_slippage_pct", float, 0.0, 0.03),
)


class StrategyConfigPolicy:
    """Applies recap suggestions only after explicit user confirmation."""

    def __init__(
        self,
        messages: DomainMessages | None = None,
        parameter_rules: tuple[StrategyParameterRule, ...] = DEFAULT_PARAMETER_RULES,
    ) -> None:
        self._messages = messages or load_domain_messages()
        self._parameter_rules = {rule.key: rule for rule in parameter_rules}

    def normalize_config(
        self,
        strategy_config: StrategyConfig,
        default_config: StrategyConfig,
    ) -> StrategyConfig:
        """Return a strategy config whose parameters satisfy known boundaries."""

        normalized_parameters = dict(default_config.parameters)
        invalid_keys: list[str] = []
        for key, value in strategy_config.parameters.items():
            if key not in self._parameter_rules:
                invalid_keys.append(key)
                continue
            normalized = self._normalize_parameter(key, value)
            if normalized is None:
                invalid_keys.append(key)
                continue
            normalized_parameters[key] = normalized

        if dict(strategy_config.parameters) == normalized_parameters:
            return strategy_config

        return StrategyConfig(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            version=strategy_config.version,
            risk_profile=strategy_config.risk_profile,
            parameters=normalized_parameters,
            impact_summary=self._normalization_summary(invalid_keys),
            adjustment_status=AdjustmentStatus.NOT_AVAILABLE,
            adjustment_message=self._messages.text(
                "strategy_config",
                "normalized_adjustment_message",
            ),
            source=strategy_config.source,
            recent_changes=strategy_config.recent_changes,
        )

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
            normalized = self._normalize_parameter(
                adjustment.key,
                adjustment.suggested_value,
            )
            if normalized is None:
                continue
            parameters[adjustment.key] = normalized
            applied_labels.append(adjustment.label)
        if not applied_labels:
            return StrategyConfig(
                strategy_id=strategy_config.strategy_id,
                name=strategy_config.name,
                version=strategy_config.version,
                risk_profile=strategy_config.risk_profile,
                parameters=dict(strategy_config.parameters),
                impact_summary=self._messages.text(
                    "strategy_config",
                    "no_valid_adjustment_summary",
                ),
                adjustment_status=AdjustmentStatus.NOT_AVAILABLE,
                adjustment_message=self._messages.text(
                    "strategy_config",
                    "no_valid_adjustment_message",
                ),
                source=strategy_config.source,
                recent_changes=strategy_config.recent_changes,
            )

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

    def _normalize_parameter(self, key: str, value: Any) -> float | int | str | None:
        rule = self._parameter_rules.get(key)
        if not rule:
            return None
        try:
            normalized = rule.value_type(value)
        except (TypeError, ValueError):
            return None
        if normalized < rule.minimum or normalized > rule.maximum:
            return None
        return normalized

    def _normalization_summary(self, invalid_keys: list[str]) -> str:
        if not invalid_keys:
            return self._messages.text("strategy_config", "normalized_summary")
        return self._messages.format(
            "strategy_config",
            "normalized_invalid_keys_summary",
            keys=", ".join(sorted(set(invalid_keys))),
        )

    def _next_version(self, version: str) -> str:
        parts = version.split(".")
        if len(parts) != 3 or not parts[-1].isdigit():
            return version
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
