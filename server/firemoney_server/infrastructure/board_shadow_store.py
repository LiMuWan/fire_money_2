"""Local persistence for limit-up board shadow validation samples."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from time import strftime
from typing import Any, Callable

from shared.contracts import (
    LimitUpBoardShadowReport,
    LimitUpBoardShadowSample,
    LimitUpBoardShadowStabilityReport,
)


DEFAULT_BOARD_SHADOW_STORE_PATH = Path(".firemoney") / "board_shadow_samples.json"


class LimitUpBoardShadowStore:
    """Stores shadow samples separately from the one-to-two paper ledger."""

    def __init__(
        self,
        path: str | Path = DEFAULT_BOARD_SHADOW_STORE_PATH,
        created_at_provider: Callable[[], str] | None = None,
    ) -> None:
        self._path = Path(path)
        self._created_at_provider = created_at_provider

    @property
    def path(self) -> Path:
        return self._path

    def append_report(
        self,
        report: LimitUpBoardShadowReport,
    ) -> LimitUpBoardShadowSample | None:
        if report.candidate is None or report.trade is None:
            return None
        created_at = (
            self._created_at_provider()
            if self._created_at_provider
            else strftime("%Y%m%d%H%M%S")
        )
        sample = LimitUpBoardShadowSample(
            sample_id=f"board-shadow-{report.as_of_date}-{report.candidate.symbol}",
            as_of_date=report.as_of_date,
            status=report.status,
            symbol=report.candidate.symbol,
            name=report.candidate.name,
            entry_price=report.candidate.entry_price,
            stop_loss=report.candidate.stop_loss,
            take_profit_price=report.candidate.take_profit_price,
            rank_score=report.candidate.rank_score,
            exit_date=report.trade.exit_date,
            exit_price=report.trade.exit_price,
            realized_pnl_pct=report.trade.realized_pnl_pct,
            holding_trade_days=report.trade.holding_trade_days,
            exit_reason=report.trade.exit_reason,
            success=report.trade.realized_pnl_pct > 0,
            created_at=created_at,
            limitations=report.limitations,
            market_seal_count=report.candidate.market_seal_count,
            market_touch_count=report.candidate.market_touch_count,
            market_advance_ratio=report.candidate.market_advance_ratio,
        )
        records = [item for item in self.load() if item.sample_id != sample.sample_id]
        records.insert(0, sample)
        self._save(tuple(records[:500]))
        return sample

    def load(self, limit: int | None = None) -> tuple[LimitUpBoardShadowSample, ...]:
        if not self._path.exists():
            return ()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, TypeError, ValueError):
            return ()
        raw_records = payload.get("samples", ())
        if not isinstance(raw_records, list):
            return ()
        records: list[LimitUpBoardShadowSample] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            try:
                records.append(self._from_payload(item))
            except (KeyError, TypeError, ValueError):
                continue
        if limit is not None and limit >= 0:
            return tuple(records[:limit])
        return tuple(records)

    def build_stability_report(self) -> LimitUpBoardShadowStabilityReport:
        samples = self.load()
        sample_count = len(samples)
        success_count = sum(1 for item in samples if item.success)
        average_return = (
            sum(item.realized_pnl_pct for item in samples) / sample_count
            if sample_count
            else 0.0
        )
        max_drawdown = self._max_drawdown(samples)
        stage, next_milestone = self._sample_stage(sample_count)
        exit_distribution: dict[str, int] = {}
        for sample in samples:
            exit_distribution[sample.exit_reason] = (
                exit_distribution.get(sample.exit_reason, 0) + 1
            )
        status = "blocked" if sample_count == 0 else "warning" if sample_count < 30 else "ready"
        summary = (
            "封板影子线暂无闭环样本。"
            if sample_count == 0
            else (
                f"封板影子线已有 {sample_count} 笔样本，"
                f"胜率 {success_count / sample_count:.2%}，"
                f"平均收益 {average_return:.2%}。"
            )
        )
        boundary = (
            "样本少于 30 笔，只能观察，不能升级主线。"
            if sample_count < 30
            else "达到 30 笔后可和一进二样本做阶段性对照。"
            if sample_count < 50
            else "达到 50 笔后复核分年稳定性和真实可成交数据。"
            if sample_count < 100
            else "达到 100 笔后再讨论是否替代一进二主线。"
        )
        return LimitUpBoardShadowStabilityReport(
            report_id="limit-up-board-shadow-stability",
            sample_count=sample_count,
            sample_stage=stage,
            next_milestone=next_milestone,
            success_rate=success_count / sample_count if sample_count else 0.0,
            average_return_pct=average_return,
            max_drawdown=max_drawdown,
            exit_reason_distribution=exit_distribution,
            recent_samples=samples[:10],
            status=status,
            summary=summary,
            strategy_boundary_suggestion=boundary,
            next_action="继续每日记录 board-shadow 样本，并补齐可成交性数据。",
        )

    def _save(self, samples: tuple[LimitUpBoardShadowSample, ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"samples": [self._to_payload(sample) for sample in samples]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _to_payload(self, sample: LimitUpBoardShadowSample) -> dict[str, Any]:
        return {
            "sample_id": sample.sample_id,
            "as_of_date": sample.as_of_date,
            "status": sample.status,
            "symbol": sample.symbol,
            "name": sample.name,
            "entry_price": sample.entry_price,
            "stop_loss": sample.stop_loss,
            "take_profit_price": sample.take_profit_price,
            "rank_score": sample.rank_score,
            "exit_date": sample.exit_date,
            "exit_price": sample.exit_price,
            "realized_pnl_pct": sample.realized_pnl_pct,
            "holding_trade_days": sample.holding_trade_days,
            "exit_reason": sample.exit_reason,
            "success": sample.success,
            "created_at": sample.created_at,
            "limitations": list(sample.limitations),
            "market_seal_count": sample.market_seal_count,
            "market_touch_count": sample.market_touch_count,
            "market_advance_ratio": sample.market_advance_ratio,
        }

    def _from_payload(self, payload: dict[str, Any]) -> LimitUpBoardShadowSample:
        return LimitUpBoardShadowSample(
            sample_id=str(payload["sample_id"]),
            as_of_date=str(payload["as_of_date"]),
            status=str(payload["status"]),
            symbol=str(payload["symbol"]),
            name=str(payload["name"]),
            entry_price=float(payload["entry_price"]),
            stop_loss=float(payload["stop_loss"]),
            take_profit_price=float(payload["take_profit_price"]),
            rank_score=float(payload["rank_score"]),
            exit_date=str(payload["exit_date"]),
            exit_price=float(payload["exit_price"]),
            realized_pnl_pct=float(payload["realized_pnl_pct"]),
            holding_trade_days=int(payload["holding_trade_days"]),
            exit_reason=str(payload["exit_reason"]),
            success=bool(payload["success"]),
            created_at=str(payload["created_at"]),
            limitations=tuple(str(item) for item in payload.get("limitations", ())),
            market_seal_count=int(payload.get("market_seal_count", 0)),
            market_touch_count=int(payload.get("market_touch_count", 0)),
            market_advance_ratio=float(payload.get("market_advance_ratio", 0.0)),
        )

    @staticmethod
    def _max_drawdown(samples: tuple[LimitUpBoardShadowSample, ...]) -> float:
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for sample in reversed(samples):
            equity *= max(0.0, 1 + sample.realized_pnl_pct * 0.08)
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = min(max_drawdown, equity / peak - 1)
        return round(max_drawdown, 6)

    @staticmethod
    def _sample_stage(sample_count: int) -> tuple[str, int]:
        if sample_count < 30:
            return "observation_lt_30", 30
        if sample_count < 50:
            return "validation_30", 50
        if sample_count < 100:
            return "validation_50", 100
        return "strategy_boundary_review", 0
