"""Local persistence for user-confirmed strategy boundaries."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any

from server.firemoney_server.domain.message_catalog import (
    DomainMessages,
    load_domain_messages,
)
from shared.contracts import (
    AdjustmentStatus,
    StrategyChangeRecord,
    StrategyConfig,
)


DEFAULT_STRATEGY_STORE_PATH = Path(".firemoney") / "strategy_config.json"
DEFAULT_CHANGE_LOG_LIMIT = 5


class StrategyConfigStore:
    """Reads and writes strategy config JSON owned by the local workspace."""

    def __init__(
        self,
        path: str | Path = DEFAULT_STRATEGY_STORE_PATH,
        messages: DomainMessages | None = None,
    ) -> None:
        self._path = Path(path)
        self._messages = messages or load_domain_messages()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def history_path(self) -> Path:
        return self._path.with_suffix(".history.json")

    def load_or_default(self, default_config: StrategyConfig) -> StrategyConfig:
        if not self._path.exists():
            return self._with_history(default_config)

        try:
            with self._path.open("r", encoding="utf-8") as file:
                payload: dict[str, Any] = json.load(file)
            return StrategyConfig(
                strategy_id=str(payload["strategy_id"]),
                name=str(payload["name"]),
                version=str(payload["version"]),
                risk_profile=str(payload["risk_profile"]),
                parameters=dict(payload["parameters"]),
                impact_summary=str(payload["impact_summary"]),
                adjustment_status=AdjustmentStatus(str(payload["adjustment_status"])),
                adjustment_message=str(payload["adjustment_message"]),
                source="local",
                recent_changes=self._records_from_payload(payload.get("recent_changes", [])),
            )
        except (JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            return self._with_history(default_config)


    def save(
        self,
        strategy_config: StrategyConfig,
        previous_config: StrategyConfig | None = None,
        reason: str | None = None,
    ) -> StrategyConfig:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        recent_changes = self._next_records(
            current_records=strategy_config.recent_changes,
            previous_config=previous_config,
            strategy_config=strategy_config,
            action="apply",
            reason=reason or self._messages.text("strategy_store", "apply_reason"),
        )
        persisted_config = StrategyConfig(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            version=strategy_config.version,
            risk_profile=strategy_config.risk_profile,
            parameters=dict(strategy_config.parameters),
            impact_summary=strategy_config.impact_summary,
            adjustment_status=strategy_config.adjustment_status,
            adjustment_message=strategy_config.adjustment_message,
            source="local",
            recent_changes=recent_changes,
        )
        payload = {
            "strategy_id": persisted_config.strategy_id,
            "name": persisted_config.name,
            "version": persisted_config.version,
            "risk_profile": persisted_config.risk_profile,
            "parameters": persisted_config.parameters,
            "impact_summary": persisted_config.impact_summary,
            "adjustment_status": persisted_config.adjustment_status.value,
            "adjustment_message": persisted_config.adjustment_message,
            "source": "local",
            "recent_changes": [
                self._record_to_payload(item)
                for item in persisted_config.recent_changes
            ],
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return persisted_config

    def reset(self, default_config: StrategyConfig | None = None) -> StrategyConfig | None:
        if not self._path.exists():
            return None
        if default_config is not None:
            current = self.load_or_default(default_config)
            reset_record = self._build_record(
                action="reset",
                previous_config=current,
                strategy_config=default_config,
                changes=(self._messages.text("strategy_store", "reset_change"),),
                reason=self._messages.text("strategy_store", "reset_reason"),
            )
            archive_payload = {
                "recent_changes": [
                    self._record_to_payload(reset_record),
                    *[
                        self._record_to_payload(item)
                        for item in current.recent_changes[: DEFAULT_CHANGE_LOG_LIMIT - 1]
                    ],
                ]
            }
            self.history_path.write_text(
                json.dumps(archive_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        self._path.unlink()
        return self.load_or_default(default_config) if default_config else None

    def _next_records(
        self,
        current_records: tuple[StrategyChangeRecord, ...],
        previous_config: StrategyConfig | None,
        strategy_config: StrategyConfig,
        action: str,
        reason: str,
    ) -> tuple[StrategyChangeRecord, ...]:
        if previous_config is None:
            return current_records[:DEFAULT_CHANGE_LOG_LIMIT]

        changes = self._describe_parameter_changes(previous_config, strategy_config)
        record = self._build_record(
            action=action,
            previous_config=previous_config,
            strategy_config=strategy_config,
            changes=changes,
            reason=reason,
        )
        return (record, *current_records)[:DEFAULT_CHANGE_LOG_LIMIT]

    def _build_record(
        self,
        action: str,
        previous_config: StrategyConfig,
        strategy_config: StrategyConfig,
        changes: tuple[str, ...],
        reason: str,
    ) -> StrategyChangeRecord:
        timestamp = strftime("%Y%m%d%H%M%S")
        return StrategyChangeRecord(
            record_id=f"{action}-{timestamp}",
            action=action,
            strategy_id=strategy_config.strategy_id,
            from_version=previous_config.version,
            to_version=strategy_config.version,
            changes=changes,
            reason=reason,
            created_at=timestamp,
        )

    def _describe_parameter_changes(
        self,
        previous_config: StrategyConfig,
        strategy_config: StrategyConfig,
    ) -> tuple[str, ...]:
        changes: list[str] = []
        for key, value in strategy_config.parameters.items():
            previous = previous_config.parameters.get(key)
            if previous != value:
                changes.append(f"{key}: {previous} -> {value}")
        return tuple(changes) or (
            self._messages.text("strategy_store", "no_parameter_change"),
        )

    def _records_from_payload(self, payload: Any) -> tuple[StrategyChangeRecord, ...]:
        return tuple(
            StrategyChangeRecord(
                record_id=str(item["record_id"]),
                action=str(item["action"]),
                strategy_id=str(item["strategy_id"]),
                from_version=str(item["from_version"]),
                to_version=str(item["to_version"]),
                changes=tuple(str(change) for change in item.get("changes", [])),
                reason=str(item["reason"]),
                created_at=str(item["created_at"]),
            )
            for item in payload
        )

    def _with_history(self, config: StrategyConfig) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=config.strategy_id,
            name=config.name,
            version=config.version,
            risk_profile=config.risk_profile,
            parameters=dict(config.parameters),
            impact_summary=config.impact_summary,
            adjustment_status=config.adjustment_status,
            adjustment_message=config.adjustment_message,
            source=config.source,
            recent_changes=self._load_history_records(),
        )

    def _load_history_records(self) -> tuple[StrategyChangeRecord, ...]:
        if not self.history_path.exists():
            return ()
        try:
            with self.history_path.open("r", encoding="utf-8") as file:
                payload: dict[str, Any] = json.load(file)
            return self._records_from_payload(payload.get("recent_changes", ()))
        except (JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            return ()

    def _record_to_payload(self, record: StrategyChangeRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "action": record.action,
            "strategy_id": record.strategy_id,
            "from_version": record.from_version,
            "to_version": record.to_version,
            "changes": list(record.changes),
            "reason": record.reason,
            "created_at": record.created_at,
        }
