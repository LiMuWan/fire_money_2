"""Stability review calculations for FireMoney paper-trading samples."""

from __future__ import annotations

from typing import Protocol

from shared.contracts import (
    OneToTwoRecentSample,
    OneToTwoStabilityReport,
    PaperAccount,
)


class StabilityReviewSettings(Protocol):
    minimum_sample_for_stability: int


class StabilityReviewService:
    """Builds closed-trade stability metrics without reading or writing ledgers."""

    def __init__(self, settings: StabilityReviewSettings) -> None:
        self._settings = settings

    def build_report(self, account: PaperAccount) -> OneToTwoStabilityReport:
        sample_count = len(account.closed_trades)
        sell_count = sum(1 for record in account.closed_trades if record.success)
        warning_count = sum(record.warning_count for record in account.closed_trades)
        total_return = sum(record.realized_pnl_pct for record in account.closed_trades)
        position_label_distribution = self._count_by(
            record.position_label for record in account.closed_trades
        )
        exit_reason_distribution = self._count_by(
            record.exit_reason for record in account.closed_trades
        )
        recent_samples = tuple(
            OneToTwoRecentSample(
                trade_id=record.trade_id,
                symbol=record.symbol,
                name=record.name,
                opened_at=record.opened_at,
                closed_at=record.closed_at,
                realized_pnl=record.realized_pnl,
                realized_pnl_pct=record.realized_pnl_pct,
                holding_trade_days=record.holding_trade_days,
                exit_reason=record.exit_reason,
                position_label=record.position_label,
                success=record.success,
                warning_count=record.warning_count,
                max_favorable_pct=record.max_favorable_pct,
                max_adverse_pct=record.max_adverse_pct,
                profit_drawdown_ratio=record.profit_drawdown_ratio,
            )
            for record in account.closed_trades[:5]
        )
        low_breakout_records = tuple(
            record
            for record in account.closed_trades
            if "低位" in record.position_label and "突破" in record.position_label
        )
        low_breakout_success = sum(1 for record in low_breakout_records if record.success)
        realized_curve = []
        current = 0.0
        for record in reversed(account.closed_trades):
            current += record.realized_pnl
            realized_curve.append(current)
        max_drawdown = min(realized_curve, default=0.0)
        success_rate = round(sell_count / sample_count, 4) if sample_count else 0.0
        average_return_pct = (
            round(total_return / sample_count, 4) if sample_count else 0.0
        )
        stop_warning_rate = (
            round(warning_count / sample_count, 4) if sample_count else 0.0
        )
        low_breakout_success_rate = (
            round(low_breakout_success / len(low_breakout_records), 4)
            if low_breakout_records
            else 0.0
        )
        status = (
            "observation"
            if sample_count < self._settings.minimum_sample_for_stability
            else "reviewable"
        )
        sample_stage = self._sample_stage(sample_count)
        next_milestone = self._next_milestone(sample_count)
        strategy_boundary_suggestion = self._strategy_boundary_suggestion(
            sample_count=sample_count,
            success_rate=success_rate,
            average_return_pct=average_return_pct,
            low_breakout_success_rate=low_breakout_success_rate,
            stop_warning_rate=stop_warning_rate,
        )
        return OneToTwoStabilityReport(
            report_id="one-to-two-stability",
            sample_count=sample_count,
            sample_stage=sample_stage,
            next_milestone=next_milestone,
            success_rate=success_rate,
            average_return_pct=average_return_pct,
            max_drawdown=min(0.0, max_drawdown),
            stop_warning_rate=stop_warning_rate,
            low_breakout_success_rate=low_breakout_success_rate,
            position_label_distribution=position_label_distribution,
            exit_reason_distribution=exit_reason_distribution,
            recent_samples=recent_samples,
            status=status,
            summary=(
                "样本处于观察期，暂不自动给出策略边界结论。"
                if status == "observation"
                else "样本达到复查门槛，可以进入策略边界评估。"
            ),
            strategy_boundary_suggestion=strategy_boundary_suggestion,
            next_action=(
                f"继续积累至 {next_milestone} 笔主线首板样本。"
                if next_milestone
                else "进入 100 笔以上复盘，固定可执行边界并继续滚动验证。"
            ),
        )

    def _count_by(self, values) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            key = str(value or "未标记")
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def _sample_stage(self, sample_count: int) -> str:
        if sample_count < self._settings.minimum_sample_for_stability:
            return "观察期"
        if sample_count < 50:
            return "30 笔初评"
        if sample_count < 100:
            return "50 笔复评"
        return "100 笔定边界"

    def _next_milestone(self, sample_count: int) -> int:
        for milestone in (30, 50, 100):
            if sample_count < milestone:
                return milestone
        return 0

    def _strategy_boundary_suggestion(
        self,
        sample_count: int,
        success_rate: float,
        average_return_pct: float,
        low_breakout_success_rate: float,
        stop_warning_rate: float,
    ) -> str:
        if sample_count < self._settings.minimum_sample_for_stability:
            return "样本少于 30 笔，只记录现象，不自动收窄或放宽策略边界。"
        if (
            success_rate >= 0.55
            and average_return_pct > 0
            and low_breakout_success_rate >= 0.55
        ):
            return "优先保留低位平台突破样本，继续排除高位接力和左侧压力过近样本。"
        if stop_warning_rate >= 0.4 or average_return_pct < 0:
            return "先收紧入池条件：降低高位样本权重，提高压力位距离和承接确认要求。"
        return "维持现有边界，继续积累到下一阶段后再决定是否调整仓位或评分阈值。"
