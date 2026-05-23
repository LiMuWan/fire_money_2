"""K92-style emotion and liquidity research system.

This is a shadow research service. It can explain market state and candidate
shape, but it deliberately does not write the paper ledger or send Feishu.
"""

from __future__ import annotations

from shared.contracts import (
    K92EmotionLiquidityCandidate,
    K92EmotionLiquidityReport,
    OneToTwoCandidate,
)


class K92EmotionLiquidityService:
    """Classify candidates into emotion-liquidity trade buckets."""

    def build_report(
        self,
        *,
        trade_date: str,
        market_temperature: int,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> K92EmotionLiquidityReport:
        visible = tuple(candidates)
        ready = tuple(item for item in visible if item.status == "ready")
        leader_candidates = self._leader_candidates(ready)
        supplement_candidates = self._supplement_candidates(ready)
        switch_candidates = self._switch_candidates(ready, leader_candidates)
        risk_candidates = self._risk_candidates(visible)
        regime, regime_label, action, stand_aside_reasons = self._regime(
            market_temperature=market_temperature,
            ready_count=len(ready),
            leader_count=len(leader_candidates),
            supplement_count=len(supplement_candidates),
            risk_count=len(risk_candidates),
        )
        status = "watch_only" if action != "stand_aside" else "blocked"
        summary = self._summary(
            market_temperature=market_temperature,
            ready_count=len(ready),
            leader_count=len(leader_candidates),
            supplement_count=len(supplement_candidates),
            regime_label=regime_label,
            action=action,
        )
        return K92EmotionLiquidityReport(
            report_id=f"k92-emotion-liquidity-{trade_date}",
            trade_date=trade_date,
            status=status,
            market_temperature=market_temperature,
            regime=regime,
            regime_label=regime_label,
            action=action,
            summary=summary,
            leader_candidates=tuple(
                self._to_contract(item, bucket="leader_attack", action="watch_leader")
                for item in leader_candidates[:3]
            ),
            supplement_candidates=tuple(
                self._to_contract(item, bucket="low_level_supplement", action="watch_supplement")
                for item in supplement_candidates[:3]
            ),
            switch_candidates=tuple(
                self._to_contract(item, bucket="theme_switch", action="watch_switch")
                for item in switch_candidates[:3]
            ),
            risk_candidates=tuple(
                self._to_contract(item, bucket="risk_only", action="avoid")
                for item in risk_candidates[:5]
            ),
            stand_aside_reasons=stand_aside_reasons,
            rules=self._rules(),
            limitations=self._limitations(),
            next_action=self._next_action(action),
        )

    def _leader_candidates(
        self,
        ready: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in ready
                    if item.turnover_quality_score >= 86
                    and item.mainline_score >= 18
                    and 0.68 <= item.position_profile.position_percentile_60 <= 0.92
                ),
                key=self._rank_key,
                reverse=True,
            )
        )

    def _supplement_candidates(
        self,
        ready: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in ready
                    if 0.45 <= item.position_profile.position_percentile_60 < 0.68
                    and item.turnover_quality_score >= 78
                    and item.mainline_score >= 16
                ),
                key=self._rank_key,
                reverse=True,
            )
        )

    def _switch_candidates(
        self,
        ready: tuple[OneToTwoCandidate, ...],
        leaders: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        leader_symbols = {item.symbol for item in leaders}
        return tuple(
            sorted(
                (
                    item
                    for item in ready
                    if item.symbol not in leader_symbols
                    and item.turnover_quality_score >= 82
                    and item.mainline_score >= 17
                ),
                key=self._rank_key,
                reverse=True,
            )
        )

    def _risk_candidates(
        self,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in candidates
                    if item.status != "ready"
                    or item.turnover_quality_score < 72
                    or item.position_profile.position_percentile_60 > 0.92
                    or item.blockers
                ),
                key=self._rank_key,
                reverse=True,
            )
        )

    def _regime(
        self,
        *,
        market_temperature: int,
        ready_count: int,
        leader_count: int,
        supplement_count: int,
        risk_count: int,
    ) -> tuple[str, str, str, tuple[str, ...]]:
        if market_temperature >= 70 and leader_count > 0 and ready_count >= 2:
            return (
                "leader_attack_day",
                "龙头进攻日",
                "watch_leader_attack",
                (),
            )
        if risk_count >= ready_count and ready_count > 0:
            return (
                "ebb_stand_aside_day",
                "退潮空仓日",
                "stand_aside",
                ("风险候选不低于可交易候选，说明资金画像不够干净。",),
            )
        if 55 <= market_temperature < 75 and supplement_count > 0:
            return (
                "low_level_supplement_day",
                "低位补涨日",
                "watch_low_level_supplement",
                (),
            )
        if 60 <= market_temperature < 80 and leader_count == 0 and ready_count > 0:
            return (
                "theme_switch_day",
                "题材切换观察日",
                "watch_theme_switch",
                (),
            )
        reasons: list[str] = []
        if market_temperature < 55:
            reasons.append("市场温度低于 55，情绪流动性不支持主动进攻。")
        if ready_count == 0:
            reasons.append("没有 ready 候选，不能为了交易频率硬做。")
        if risk_count >= ready_count and ready_count > 0:
            reasons.append("风险候选不低于可交易候选，说明资金画像不够干净。")
        if not reasons:
            reasons.append("龙头和补涨候选都未达到观察门槛。")
        return (
            "ebb_stand_aside_day",
            "退潮空仓日",
            "stand_aside",
            tuple(reasons),
        )

    def _to_contract(
        self,
        candidate: OneToTwoCandidate,
        *,
        bucket: str,
        action: str,
    ) -> K92EmotionLiquidityCandidate:
        return K92EmotionLiquidityCandidate(
            symbol=candidate.symbol,
            name=candidate.name,
            bucket=bucket,
            action=action,
            status=candidate.status,
            score=candidate.score,
            latest_price=candidate.latest_price,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            market_cap=candidate.market_cap or candidate.float_market_cap,
            turnover_quality_score=candidate.turnover_quality_score,
            mainline_score=candidate.mainline_score,
            position_percentile_60=candidate.position_profile.position_percentile_60,
            rationale=candidate.rationale,
            reasons=self._candidate_reasons(candidate),
            blockers=self._unique_messages(candidate.blockers),
            warnings=self._unique_messages(candidate.warnings),
            next_action=candidate.next_action,
        )

    def _candidate_reasons(self, candidate: OneToTwoCandidate) -> tuple[str, ...]:
        reasons = [
            f"换手龙质量 {candidate.turnover_quality_score:.0f}/100",
            f"主线强度 {candidate.mainline_score:.0f}/20",
            f"60 日位置 {candidate.position_profile.position_percentile_60:.0%}",
        ]
        if candidate.market_cap or candidate.float_market_cap:
            reasons.append(f"市值 {self._format_yi(candidate.market_cap or candidate.float_market_cap)}")
        if candidate.turnover_quality_label:
            reasons.append(candidate.turnover_quality_label)
        return tuple(reasons)

    def _rank_key(self, candidate: OneToTwoCandidate) -> tuple[float, float, float, float]:
        return (
            candidate.turnover_quality_score,
            candidate.score,
            candidate.mainline_score,
            candidate.liquidity_score,
        )

    def _unique_messages(self, messages: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for message in messages:
            key = message.replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            result.append(message)
        return tuple(result)

    def _summary(
        self,
        *,
        market_temperature: int,
        ready_count: int,
        leader_count: int,
        supplement_count: int,
        regime_label: str,
        action: str,
    ) -> str:
        return (
            f"今日情绪温度 {market_temperature}，ready 候选 {ready_count} 只，"
            f"龙头进攻 {leader_count} 只，低位补涨 {supplement_count} 只；"
            f"状态判定为{regime_label}，研究动作 {action}。"
        )

    def _next_action(self, action: str) -> str:
        if action == "stand_aside":
            return "保持空仓研究，只记录情绪样本；不能写入模拟盘买入。"
        return (
            "先用 k92-emotion --brief 做观察记录，再补 2020-2026 分年/月度 point-in-time "
            "回测；未通过前不接入默认模拟盘。"
        )

    def _rules(self) -> tuple[str, ...]:
        return (
            "只研究主板 10cm、非 ST、非新股、50-800 亿市值的情绪流动性机会。",
            "高位只做龙头分歧转一致，不做中位跟风。",
            "龙头不清晰时只观察低位补涨或题材切换，弱市直接空仓。",
            "任何候选进入实盘/模拟盘前，必须先通过 2020-2026 分年、月度、回撤验证。",
        )

    def _limitations(self) -> tuple[str, ...]:
        return (
            "这是 92 科比经验抽象后的研究影子系统，不是收益保证。",
            "当前只复用现有候选池字段，尚未接入完整题材强度、席位结构和实时分时换手。",
            "未完成历史逐日回测前，不允许影响 board-shadow-system 默认买卖决策。",
        )

    def _format_yi(self, value: float) -> str:
        if value <= 0:
            return "未知"
        return f"{value / 100_000_000:.1f} 亿"


__all__ = ["K92EmotionLiquidityService"]
