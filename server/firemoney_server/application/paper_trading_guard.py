"""Risk gate for paper-trading entries based on closed simulated trades."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import PaperAccount, PaperTradeRecord


@dataclass(frozen=True)
class PaperTradingGuardSettings:
    review_sample: int
    min_win_rate: float
    min_average_return_pct: float
    max_consecutive_losses: int
    max_consecutive_quality_failures: int
    max_drawdown_pct: float
    max_position_pct: float
    reduced_position_pct: float
    min_profit_drawdown_ratio: float
    min_quality_bucket_samples: int = 3
    quality_bucket_block_losses: int = 2


@dataclass(frozen=True)
class PaperTradingGuardResult:
    status: str
    action: str
    review_sample_count: int
    win_rate: float
    average_return_pct: float
    max_drawdown_pct: float
    consecutive_losses: int
    consecutive_quality_failures: int
    average_profit_drawdown_ratio: float
    risk_quality_pass_rate: float
    suggested_position_pct: float
    reasons: tuple[str, ...]
    next_action: str
    candidate_quality_bucket: str = ""
    candidate_quality_sample_count: int = 0
    candidate_quality_win_rate: float = 0.0
    candidate_quality_average_return_pct: float = 0.0
    candidate_quality_risk_quality_pass_rate: float = 0.0


class PaperTradingGuard:
    """Decides whether the next paper trade deserves full size, reduced size, or no entry."""

    def __init__(self, settings: PaperTradingGuardSettings) -> None:
        self._settings = settings

    def evaluate(
        self,
        account: PaperAccount,
        candidate_turnover_quality_score: float | None = None,
    ) -> PaperTradingGuardResult:
        samples = account.closed_trades[: max(0, self._settings.review_sample)]
        bucket = self._turnover_quality_bucket(candidate_turnover_quality_score)
        if not samples:
            return PaperTradingGuardResult(
                status="warmup",
                action="allow_reduced",
                review_sample_count=0,
                win_rate=0.0,
                average_return_pct=0.0,
                max_drawdown_pct=0.0,
                consecutive_losses=0,
                consecutive_quality_failures=0,
                average_profit_drawdown_ratio=0.0,
                risk_quality_pass_rate=0.0,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    "暂无真实闭环样本，先按降档仓位验证；"
                    "达到复盘样本数且收益质量通过后，才允许恢复常态仓位。",
                ),
                next_action="继续用小仓位模拟盘积累闭环样本，达到复盘样本数后自动启用完整收益守门。",
                candidate_quality_bucket=bucket,
            )

        metrics = self._metrics(samples)
        bucket_samples = self._bucket_samples(account.closed_trades, bucket)
        bucket_metrics = self._metrics(bucket_samples)
        bucket_decision = self._quality_bucket_decision(
            bucket=bucket,
            samples=bucket_samples,
            win_rate=bucket_metrics["win_rate"],
            average_return_pct=bucket_metrics["average_return_pct"],
            risk_quality_pass_rate=bucket_metrics["risk_quality_pass_rate"],
        )
        reasons: list[str] = []

        if metrics["consecutive_losses"] >= self._settings.max_consecutive_losses:
            reasons.append(
                f"最近连续亏损 {metrics['consecutive_losses']} 笔，"
                f"达到暂停线 {self._settings.max_consecutive_losses} 笔。"
            )
        if (
            metrics["consecutive_quality_failures"]
            >= self._settings.max_consecutive_quality_failures
        ):
            reasons.append(
                f"最近连续 {metrics['consecutive_quality_failures']} 笔收益质量失败，"
                f"达到暂停线 {self._settings.max_consecutive_quality_failures} 笔；"
                "先停手复盘，避免用大回撤换小利润。"
            )
        if metrics["max_drawdown_pct"] >= self._settings.max_drawdown_pct:
            reasons.append(
                f"最近样本最大回撤 {metrics['max_drawdown_pct']:.2%}，"
                f"超过守门线 {self._settings.max_drawdown_pct:.2%}。"
            )
        if reasons:
            return self._result(
                status="blocked",
                action="stand_aside",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=0.0,
                reasons=tuple(reasons),
                next_action="今天不新开模拟仓，先复盘亏损/低质量样本和卖点纪律，再等下一次高质量信号。",
            )

        if bucket_decision[0] == "block":
            return self._result(
                status="blocked",
                action="stand_aside",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=0.0,
                reasons=(bucket_decision[1],),
                next_action="同类买点质量段连续失败，暂停新开仓，等新的高质量闭环样本修复后再恢复。",
            )
        if bucket_decision[0] == "reduce":
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(bucket_decision[1],),
                next_action="同类买点质量段表现偏弱，只允许小仓位继续验证。",
            )

        weak_risk_quality = any(
            sample.realized_pnl_pct > 0 and self._is_quality_failure(sample)
            for sample in samples
        )
        if weak_risk_quality:
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"最近盈利样本里有赚撤比低于 "
                    f"{self._settings.min_profit_drawdown_ratio:.2f}R 的交易，"
                    "先降仓，避免用大回撤换小利润。",
                ),
                next_action="先用降仓继续验证，只接受盈利覆盖过程回撤的买卖闭环。",
            )

        if metrics["risk_quality_pass_rate"] < self._settings.min_win_rate:
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"最近 {len(samples)} 笔盈利覆盖回撤达标率 "
                    f"{metrics['risk_quality_pass_rate']:.2%}，低于要求 "
                    f"{self._settings.min_win_rate:.2%}；不允许用满仓试错。",
                ),
                next_action="收益质量达标率修复前只允许降仓模拟，优先复盘卖点和回撤来源。",
            )

        if (
            metrics["average_profit_drawdown_ratio"]
            < self._settings.min_profit_drawdown_ratio
        ):
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"最近 {len(samples)} 笔平均赚撤比 "
                    f"{metrics['average_profit_drawdown_ratio']:.2f}R，低于要求 "
                    f"{self._settings.min_profit_drawdown_ratio:.2f}R；"
                    "先降仓，直到利润能稳定覆盖过程回撤。",
                ),
                next_action="平均赚撤比达标前不放大仓位，继续用小仓位验证买点和卖点纪律。",
            )

        if metrics["average_return_pct"] < self._settings.min_average_return_pct:
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"最近 {len(samples)} 笔平均收益 "
                    f"{metrics['average_return_pct']:.2%}，未超过正收益门槛 "
                    f"{self._settings.min_average_return_pct:.2%}。",
                ),
                next_action="先降仓继续模拟，直到最近闭环交易的平均收益重新转正并超过门槛。",
            )

        if (
            len(samples) >= self._settings.review_sample
            and metrics["win_rate"] < self._settings.min_win_rate
        ):
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"最近 {len(samples)} 笔胜率 {metrics['win_rate']:.2%}，"
                    f"低于要求 {self._settings.min_win_rate:.2%}。",
                ),
                next_action="允许继续模拟，但仓位降档，直到最近样本胜率和平均收益重新达标。",
            )

        if len(samples) < self._settings.review_sample:
            return self._result(
                status="reduced",
                action="allow_reduced",
                samples=samples,
                metrics=metrics,
                bucket=bucket,
                bucket_samples=bucket_samples,
                bucket_metrics=bucket_metrics,
                suggested_position_pct=self._reduced_position_pct(),
                reasons=(
                    f"真实闭环样本 {len(samples)} 笔，尚未达到复盘门槛 "
                    f"{self._settings.review_sample} 笔；先小仓验证，不把早期胜率当成长期能力。",
                ),
                next_action="继续积累真实闭环样本；样本数、胜率、平均收益和赚撤比同时达标后，才允许恢复常态仓位。",
            )

        return self._result(
            status="ready",
            action="allow_full",
            samples=samples,
            metrics=metrics,
            bucket=bucket,
            bucket_samples=bucket_samples,
            bucket_metrics=bucket_metrics,
            suggested_position_pct=self._settings.max_position_pct,
            reasons=(
                f"最近样本胜率 {metrics['win_rate']:.2%}，平均收益 "
                f"{metrics['average_return_pct']:.2%}，回撤 "
                f"{metrics['max_drawdown_pct']:.2%}，允许按计划执行。",
            ),
            next_action="收益守门通过，仍按买点失效规则和 T+1 正收益质量锁定纪律执行。",
        )

    def _result(
        self,
        status: str,
        action: str,
        samples: tuple[PaperTradeRecord, ...],
        metrics: dict[str, float],
        bucket: str,
        bucket_samples: tuple[PaperTradeRecord, ...],
        bucket_metrics: dict[str, float],
        suggested_position_pct: float,
        reasons: tuple[str, ...],
        next_action: str,
    ) -> PaperTradingGuardResult:
        return PaperTradingGuardResult(
            status=status,
            action=action,
            review_sample_count=len(samples),
            win_rate=metrics["win_rate"],
            average_return_pct=metrics["average_return_pct"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            consecutive_losses=int(metrics["consecutive_losses"]),
            consecutive_quality_failures=int(metrics["consecutive_quality_failures"]),
            average_profit_drawdown_ratio=metrics["average_profit_drawdown_ratio"],
            risk_quality_pass_rate=metrics["risk_quality_pass_rate"],
            suggested_position_pct=suggested_position_pct,
            reasons=reasons,
            next_action=next_action,
            candidate_quality_bucket=bucket,
            candidate_quality_sample_count=len(bucket_samples),
            candidate_quality_win_rate=bucket_metrics["win_rate"],
            candidate_quality_average_return_pct=bucket_metrics[
                "average_return_pct"
            ],
            candidate_quality_risk_quality_pass_rate=bucket_metrics[
                "risk_quality_pass_rate"
            ],
        )

    def _metrics(self, samples: tuple[PaperTradeRecord, ...]) -> dict[str, float]:
        return {
            "win_rate": self._win_rate(samples),
            "average_return_pct": self._average_return_pct(samples),
            "max_drawdown_pct": self._max_drawdown_pct(samples),
            "consecutive_losses": float(self._consecutive_losses(samples)),
            "consecutive_quality_failures": float(
                self._consecutive_quality_failures(samples)
            ),
            "average_profit_drawdown_ratio": self._average_profit_drawdown_ratio(
                samples
            ),
            "risk_quality_pass_rate": self._risk_quality_pass_rate(samples),
        }

    def _reduced_position_pct(self) -> float:
        return min(self._settings.max_position_pct, self._settings.reduced_position_pct)

    @staticmethod
    def _win_rate(samples: tuple[PaperTradeRecord, ...]) -> float:
        if not samples:
            return 0.0
        return round(sum(1 for sample in samples if sample.success) / len(samples), 4)

    @staticmethod
    def _average_return_pct(samples: tuple[PaperTradeRecord, ...]) -> float:
        if not samples:
            return 0.0
        return round(sum(sample.realized_pnl_pct for sample in samples) / len(samples), 4)

    @staticmethod
    def _consecutive_losses(samples: tuple[PaperTradeRecord, ...]) -> int:
        count = 0
        for sample in samples:
            if sample.success:
                break
            count += 1
        return count

    def _consecutive_quality_failures(
        self,
        samples: tuple[PaperTradeRecord, ...],
    ) -> int:
        count = 0
        for sample in samples:
            if not self._is_quality_failure(sample):
                break
            count += 1
        return count

    def _is_quality_failure(self, sample: PaperTradeRecord) -> bool:
        if sample.realized_pnl_pct <= 0:
            return True
        if sample.max_adverse_pct <= 0:
            return False
        required_profit_pct = (
            sample.max_adverse_pct * self._settings.min_profit_drawdown_ratio
        )
        return sample.realized_pnl_pct < required_profit_pct

    @staticmethod
    def _max_drawdown_pct(samples: tuple[PaperTradeRecord, ...]) -> float:
        equity_curve = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for sample in reversed(samples):
            equity_curve *= 1 + sample.realized_pnl_pct
            peak = max(peak, equity_curve)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity_curve) / peak)
        return round(max_drawdown, 4)

    @staticmethod
    def _average_profit_drawdown_ratio(samples: tuple[PaperTradeRecord, ...]) -> float:
        ratios = tuple(
            sample.profit_drawdown_ratio
            for sample in samples
            if sample.profit_drawdown_ratio > 0
        )
        if not ratios:
            return 0.0
        return round(sum(ratios) / len(ratios), 4)

    def _risk_quality_pass_rate(self, samples: tuple[PaperTradeRecord, ...]) -> float:
        if not samples:
            return 0.0
        passes = sum(1 for sample in samples if not self._is_quality_failure(sample))
        return round(passes / len(samples), 4)

    @staticmethod
    def _turnover_quality_bucket(score: float | None) -> str:
        if score is None:
            return ""
        if score >= 86:
            return "strong_turnover_dragon"
        if score >= 72:
            return "valid_turnover_dragon"
        if score > 0:
            return "weak_turnover_quality"
        return "unscored_legacy"

    def _bucket_samples(
        self,
        samples: tuple[PaperTradeRecord, ...],
        bucket: str,
    ) -> tuple[PaperTradeRecord, ...]:
        if not bucket:
            return ()
        return tuple(
            sample
            for sample in samples
            if self._turnover_quality_bucket(sample.entry_turnover_quality_score)
            == bucket
        )

    def _quality_bucket_decision(
        self,
        bucket: str,
        samples: tuple[PaperTradeRecord, ...],
        win_rate: float,
        average_return_pct: float,
        risk_quality_pass_rate: float,
    ) -> tuple[str, str]:
        if not bucket or bucket == "unscored_legacy":
            return ("allow", "")
        consecutive_failures = self._consecutive_quality_failures(samples)
        if consecutive_failures >= self._settings.quality_bucket_block_losses:
            return (
                "block",
                f"同类买点质量段 {bucket} 连续 {consecutive_failures} 笔收益质量失败，暂停新开仓。",
            )
        if len(samples) < self._settings.min_quality_bucket_samples:
            return (
                "reduce",
                (
                    f"同类买点质量段 {bucket} 只有 {len(samples)} 笔闭环样本，"
                    f"少于复核门槛 {self._settings.min_quality_bucket_samples} 笔；"
                    "先小仓验证，不借用其他买点段的收益放大仓位。"
                ),
            )
        if (
            win_rate < self._settings.min_win_rate
            or average_return_pct < self._settings.min_average_return_pct
            or risk_quality_pass_rate < self._settings.min_win_rate
        ):
            return (
                "reduce",
                (
                    f"同类买点质量段 {bucket} 样本 {len(samples)} 笔，"
                    f"胜率 {win_rate:.2%}、平均收益 {average_return_pct:.2%}、"
                    f"收益质量 {risk_quality_pass_rate:.2%} 未达标，先降仓验证。"
                ),
            )
        return ("allow", "")
