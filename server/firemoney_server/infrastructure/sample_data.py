"""Config-backed deterministic sample data for the first remake smoke path."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.contracts import (
    AdjustmentStatus,
    MarketContext,
    Opportunity,
    RiskLevel,
    StrategyChangeRecord,
    StrategyConfig,
    WorkflowStage,
)


_CONFIG_DIR = Path(__file__).with_name("config")
_DEFAULT_LOCALE = "zh_CN"


@lru_cache(maxsize=4)
def _load_sample_payload(locale: str = _DEFAULT_LOCALE) -> dict[str, Any]:
    config_path = _CONFIG_DIR / f"sample_trading_data.{locale}.json"
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def sample_market_context(locale: str = _DEFAULT_LOCALE) -> MarketContext:
    payload = _load_sample_payload(locale)["market_context"]
    return MarketContext(
        trade_date=str(payload["trade_date"]),
        market_temperature=int(payload["market_temperature"]),
        trend=str(payload["trend"]),
        risk_level=RiskLevel(str(payload["risk_level"])),
        summary=str(payload["summary"]),
        next_action=str(payload["next_action"]),
    )


def sample_opportunity_candidates(locale: str = _DEFAULT_LOCALE) -> tuple[Opportunity, ...]:
    return tuple(
        Opportunity(
            symbol=str(item["symbol"]),
            name=str(item["name"]),
            score=float(item["score"]),
            confidence=float(item["confidence"]),
            source_stage=WorkflowStage(str(item["source_stage"])),
            strategy_tags=tuple(str(tag) for tag in item.get("strategy_tags", ())),
            entry_price=float(item["entry_price"]),
            stop_loss=float(item["stop_loss"]),
            target_price=float(item["target_price"]),
            risk_flags=tuple(str(flag) for flag in item.get("risk_flags", ())),
            rationale=str(item["rationale"]),
        )
        for item in _load_sample_payload(locale)["opportunities"]
    )


def sample_strategy_config(locale: str = _DEFAULT_LOCALE) -> StrategyConfig:
    payload = _load_sample_payload(locale)["strategy_config"]
    return StrategyConfig(
        strategy_id=str(payload["strategy_id"]),
        name=str(payload["name"]),
        version=str(payload["version"]),
        risk_profile=str(payload["risk_profile"]),
        parameters=dict(payload["parameters"]),
        impact_summary=str(payload["impact_summary"]),
        adjustment_status=AdjustmentStatus(
            str(payload.get("adjustment_status", AdjustmentStatus.NOT_AVAILABLE.value))
        ),
        adjustment_message=str(payload.get("adjustment_message", "")),
        source=str(payload.get("source", "default")),
        recent_changes=_change_records_from_payload(payload.get("recent_changes", ())),
    )


def sample_universe_size(locale: str = _DEFAULT_LOCALE) -> int:
    return int(_load_sample_payload(locale)["universe_size"])


def sample_current_price(symbol: str, locale: str = _DEFAULT_LOCALE) -> float:
    prices = _load_sample_payload(locale)["current_prices"]
    return float(prices.get(symbol, 0))


def _change_records_from_payload(payload: Any) -> tuple[StrategyChangeRecord, ...]:
    return tuple(
        StrategyChangeRecord(
            record_id=str(item["record_id"]),
            action=str(item["action"]),
            strategy_id=str(item["strategy_id"]),
            from_version=str(item["from_version"]),
            to_version=str(item["to_version"]),
            changes=tuple(str(change) for change in item.get("changes", ())),
            reason=str(item["reason"]),
            created_at=str(item["created_at"]),
        )
        for item in payload
    )
