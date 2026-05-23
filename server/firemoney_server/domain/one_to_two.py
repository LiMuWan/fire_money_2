"""One-to-two mainboard strategy scoring and review policy."""

from __future__ import annotations

import math
from dataclasses import replace

from shared.contracts import (
    BreakoutStructureProfile,
    MainlineContinuity,
    OneToTwoExitPlan,
    OneToTwoCandidate,
    OneToTwoPositionProfile,
)
from server.firemoney_server.domain.one_to_two_types import (
    HistoricalPriceBar,
    IntradayPriceBar,
    OneToTwoMarketRow,
    OneToTwoSettings,
    TickSnapshot,
)

class OneToTwoPolicy:
    """Scores yesterday's first boards for next-day mainboard one-to-two review."""

    def __init__(self, settings: OneToTwoSettings) -> None:
        self._settings = settings

    def build_candidates(
        self,
        rows: tuple[OneToTwoMarketRow, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        candidates = tuple((row, self._candidate_from_row(row)) for row in rows)
        base_ready_count = sum(1 for _, candidate in candidates if candidate.status == "ready")
        candidates = tuple(
            (
                row,
                self._apply_market_width_gate(
                    row,
                    candidate,
                    base_ready_count=base_ready_count,
                ),
            )
            for row, candidate in candidates
        )
        ranked = sorted(candidates, key=self._candidate_rank_key, reverse=True)
        return tuple(candidate for _, candidate in ranked)

    def _apply_market_width_gate(
        self,
        row: OneToTwoMarketRow,
        candidate: OneToTwoCandidate,
        base_ready_count: int,
    ) -> OneToTwoCandidate:
        if candidate.status != "ready":
            return candidate
        if (
            self._settings.max_ready_candidates > 0
            and base_ready_count > self._settings.max_ready_candidates
        ):
            return replace(
                candidate,
                status="blocked",
                blockers=candidate.blockers
                + (
                    f"今日可执行候选 {base_ready_count} 个超过 {self._settings.max_ready_candidates} 个，主线过散只观察",
                ),
                warnings=candidate.warnings + ("候选池过热过散，先不做唯一票模拟买入。",),
                rationale=f"{candidate.name} 当日候选池过宽，资金主线不够集中，先观察不买入。",
                next_action="候选池过热闸门未通过，不生成模拟买入。",
            )
        if not self._is_low_breakout(candidate.position_profile):
            return candidate

        min_first_board_count = self._settings.min_low_breakout_first_board_count
        min_ready_candidates = self._settings.min_low_breakout_ready_candidates
        blockers: list[str] = []
        if min_first_board_count > 0 and row.first_board_count < min_first_board_count:
            blockers.append(
                f"昨日首板宽度 {row.first_board_count} 家不足 {min_first_board_count} 家，低位突破只观察"
            )
        if min_ready_candidates > 0 and base_ready_count < min_ready_candidates:
            blockers.append(
                f"今日可执行候选 {base_ready_count} 个不足 {min_ready_candidates} 个，低位突破不单点出手"
            )
        if not blockers:
            return candidate

        return replace(
            candidate,
            status="blocked",
            blockers=candidate.blockers + tuple(blockers),
            warnings=candidate.warnings + ("低位突破必须有市场宽度确认。",),
            rationale=f"{candidate.name} 是低位平台突破，但市场宽度不足，先观察不买入。",
            next_action="低位突破宽度闸门未通过，不生成模拟买入。",
        )

    def _is_low_breakout(self, profile: OneToTwoPositionProfile) -> bool:
        return profile.low_position_score >= 8 and profile.breakout_score >= 7

    def _candidate_rank_key(
        self,
        item: tuple[OneToTwoMarketRow, OneToTwoCandidate],
    ) -> tuple[float, ...]:
        row, candidate = item
        if self._settings.selection_rank == "turnover":
            return self._turnover_rank_key(row, candidate)
        open_confirm_bonus = (
            1
            if self._settings.min_confirm_open_pct
            <= row.open_pct
            <= self._settings.max_confirm_open_pct
            else 0
        )
        position_bonus = (
            1
            if candidate.position_profile.low_position_score >= 8
            or candidate.position_profile.breakout_score >= 7
            else 0
        )
        return (
            candidate.score,
            open_confirm_bonus,
            position_bonus,
            row.open_pct,
            row.turnover_amount,
        )

    def _turnover_rank_key(
        self,
        row: OneToTwoMarketRow,
        candidate: OneToTwoCandidate,
    ) -> tuple[float, ...]:
        return (
            candidate.score,
            candidate.turnover_quality_score,
            row.turnover_amount,
            self._position_rank(candidate.position_profile),
            -abs(row.open_pct - 0.025),
        )

    def _position_rank(self, profile: OneToTwoPositionProfile) -> float:
        if profile.low_position_score >= 8 and profile.breakout_score >= 7:
            return 3.0
        if profile.breakout_score >= 7:
            return 2.0
        if profile.low_position_score >= 8:
            return 1.0
        return 0.0

    def _candidate_from_row(self, row: OneToTwoMarketRow) -> OneToTwoCandidate:
        first_board_score = self._first_board_score(row)
        auction_score = self._auction_score(row)
        position_profile = self._position_profile(row)
        theme_score = self._theme_score(row)
        liquidity_score = self._liquidity_score(row)
        mainline_score = self._mainline_score(row, position_profile)
        sealing_score = self._sealing_score(row)
        leader_score = self._leader_score(row, position_profile)
        breakout_structure = self._breakout_structure_profile(row, position_profile)
        turnover_quality_score, turnover_quality_label, turnover_quality_notes = (
            self._turnover_dragon_quality(row, position_profile)
        )
        blockers = self._blockers(
            row,
            position_profile=position_profile,
            mainline_score=mainline_score,
            leader_score=leader_score,
            turnover_quality_score=turnover_quality_score,
            breakout_structure=breakout_structure,
        )
        warnings = self._warnings(
            row,
            turnover_quality_score=turnover_quality_score,
            turnover_quality_notes=turnover_quality_notes,
        )
        execution_score = self._execution_score(
            first_board_score=first_board_score,
            auction_score=auction_score,
            position_profile=position_profile,
            theme_score=theme_score,
            liquidity_score=liquidity_score,
        )
        score = round(
            min(
                100.0,
                sealing_score
                + mainline_score
                + leader_score
                + min(auction_score, 15.0)
                + min(self._position_score(position_profile), 20.0)
                + min(liquidity_score, 10.0),
            ),
            2,
        )
        status = (
            "blocked"
            if blockers
            else "ready"
            if self._is_executable_score(execution_score)
            else "watch_only"
        )
        entry_price = round(row.latest_price, 2)
        structure_stop = max(
            row.ma_5,
            row.latest_price * (1 - self._settings.stop_loss_pct * 1.25),
        )
        percent_stop = row.latest_price * (1 - self._settings.stop_loss_pct)
        stop_loss = self._round_price_up(max(structure_stop, percent_stop))
        exit_plan = self._exit_plan(row.latest_price, stop_loss)
        continuity = self._mainline_continuity(
            row,
            mainline_score=mainline_score,
            sealing_score=sealing_score,
            leader_score=leader_score,
        )
        return OneToTwoCandidate(
            symbol=row.symbol,
            name=row.name,
            trade_date=row.trade_date,
            score=score,
            status=status,
            latest_price=round(row.latest_price, 2),
            limit_up_price=round(row.limit_up_price, 2),
            entry_price=entry_price,
            stop_loss=stop_loss,
            position_limit_pct=self._settings.max_position_pct,
            first_board_score=round(first_board_score, 2),
            auction_score=round(auction_score, 2),
            position_score=round(self._position_score(position_profile), 2),
            theme_score=round(theme_score, 2),
            liquidity_score=round(liquidity_score, 2),
            position_profile=position_profile,
            blockers=blockers,
            warnings=self._candidate_warnings(warnings, execution_score),
            rationale=self._rationale(
                row,
                position_profile,
                blockers,
                execution_score,
            ),
            next_action=self._next_action(status),
            mainline_score=round(mainline_score, 2),
            sealing_score=round(sealing_score, 2),
            leader_score=round(leader_score, 2),
            leader_label=self._leader_label(leader_score, sealing_score, mainline_score),
            strategy_tags=self._strategy_tags(
                row,
                position_profile,
                leader_score,
                sealing_score,
                mainline_score,
                turnover_quality_score,
            ),
            discipline_summary=self._discipline_summary(row, exit_plan),
            exit_plan=exit_plan,
            mainline_continuity=continuity,
            turnover_quality_score=turnover_quality_score,
            turnover_quality_label=turnover_quality_label,
            turnover_quality_notes=turnover_quality_notes,
            market_cap=round(row.market_cap, 2),
            float_market_cap=round(row.float_market_cap, 2),
            market_cap_source=self._market_cap_source(row),
            breakout_structure=breakout_structure,
        )

    def _execution_score(
        self,
        first_board_score: float,
        auction_score: float,
        position_profile: OneToTwoPositionProfile,
        theme_score: float,
        liquidity_score: float,
    ) -> float:
        return round(
            first_board_score
            + auction_score
            + self._position_score(position_profile)
            + theme_score
            + liquidity_score,
            2,
        )

    def _is_executable_score(self, score: float) -> bool:
        if score < self._settings.min_score:
            return False
        max_score = getattr(self._settings, "max_execution_score", 0)
        return max_score <= 0 or score < max_score

    def _candidate_warnings(
        self,
        warnings: tuple[str, ...],
        score: float,
    ) -> tuple[str, ...]:
        if score >= self._settings.min_score and not self._is_executable_score(score):
            return warnings + (
                f"执行分 {score:g} 达到过热阈值 "
                f"{self._settings.max_execution_score:g}，"
                "一致性过强时先观察，避免拥挤接力。",
            )
        return warnings

    def _blockers(
        self,
        row: OneToTwoMarketRow,
        *,
        position_profile: OneToTwoPositionProfile,
        mainline_score: float,
        leader_score: float,
        turnover_quality_score: float,
        breakout_structure: BreakoutStructureProfile,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if row.board in self._settings.excluded_boards:
            blockers.append(f"{row.board} 不在主板 10cm 一进二范围内")
        if self._settings.exclude_st and row.is_st:
            blockers.append("ST 股票不参与一进二模拟盘")
        if self._settings.exclude_delisting and row.is_delisting:
            blockers.append("退市整理风险，禁止参与")
        if row.listing_days <= self._settings.exclude_new_stock_days:
            blockers.append("新股前 5 个交易日不参与")
        if row.turnover_amount < self._settings.min_turnover_amount:
            blockers.append("成交额低于流动性门槛")
        effective_market_cap = self._effective_market_cap(row)
        if effective_market_cap <= 0:
            blockers.append("缺少总市值/流通市值，不能确认 50-800 亿市值带")
        elif effective_market_cap < self._settings.min_market_cap:
            blockers.append(
                f"市值低于 {self._format_yi(self._settings.min_market_cap)} 亿，"
                "不做流动性过弱的小票"
            )
        elif effective_market_cap > self._settings.max_market_cap:
            blockers.append(
                f"市值高于 {self._format_yi(self._settings.max_market_cap)} 亿，"
                "不做弹性不足的大票"
            )
        if self._settings.board_strategy_enabled and row.turnover_amount > 0:
            sealed_ratio = row.sealed_amount / row.turnover_amount
            if sealed_ratio < self._settings.min_sealed_amount_ratio:
                blockers.append("封板资金不足，不能作为主线首板龙头候选")
            if sealed_ratio < self._settings.min_turnover_dragon_sealed_ratio:
                blockers.append("换手龙封单/成交额不足，炸板风险过高")
        if row.turnover_rate < self._settings.min_turnover_dragon_turnover_rate:
            blockers.append("换手不足，资金接力不够，不能作为换手龙买点")
        if row.turnover_rate > self._settings.max_turnover_dragon_turnover_rate:
            blockers.append("换手过高，疑似分歧过大，换手龙买点失效")
        if row.open_pct < self._settings.min_confirm_open_pct:
            blockers.append("次日确认未红盘开，产品算法不进入模拟买入")
        if row.open_pct > self._settings.max_confirm_open_pct:
            blockers.append(
                f"次日确认高开超过 {self._settings.max_confirm_open_pct:.1%}，追高盈亏比不足"
            )
        if row.open_pct >= 0.095 and row.auction_amount < row.turnover_amount * 0.01:
            blockers.append("一字板买不到，只观察不买入")
        if row.market_temperature < self._settings.market_temperature_floor:
            blockers.append("市场温度低于策略执行门槛")
        if row.recent_gain_pct >= self._settings.recent_gain_block_pct:
            blockers.append("首板前涨幅过大，疑似高位接力")
        if row.latest_price and row.ma_20:
            deviation = (row.latest_price - row.ma_20) / row.ma_20
            if deviation >= self._settings.high_deviation_block_pct:
                blockers.append("距离 20 日均线过远，短线乖离过大")
        if row.pressure_price and row.latest_price:
            pressure_distance = (row.pressure_price - row.latest_price) / row.latest_price
            if 0 <= pressure_distance <= self._settings.near_pressure_pct:
                blockers.append("上方压力位过近")
        if row.volume_ratio_5 < self._settings.min_volume_ratio_5:
            blockers.append("首板量比不足，持续性承接未确认")
        if row.rsi_14 < self._settings.min_rsi_14:
            blockers.append("RSI 过冷，更像弱反抽而不是主线承接")
        if row.rsi_14 > self._settings.max_rsi_14:
            blockers.append("RSI 过热，短线追高风险偏高")
        if row.position_percentile_60 < self._settings.min_position_percentile_60:
            blockers.append("60 日位置分位过低，突破持续性不足")
        if not self._position_label_allowed(position_profile.label):
            blockers.append("位置一般，不符合低位/突破一进二核心买点")
        if mainline_score < self._settings.min_mainline_score:
            blockers.append("主线首板强度不足，先不进入模拟盘")
        if leader_score < self._settings.min_leader_score:
            blockers.append("龙头候选辨识度不足，避免普通跟风票")
        if turnover_quality_score < self._settings.min_turnover_dragon_score:
            blockers.append(
                f"换手龙质量 {turnover_quality_score:.0f}/100 未达 "
                f"{self._settings.min_turnover_dragon_score:.0f}，不做启动前买点"
            )
        if not breakout_structure.passed:
            blockers.append(
                f"结构突破评分 {breakout_structure.score:.0f}/100 未达 "
                f"{self._settings.min_breakout_structure_score:.0f}，不做弱结构买点"
            )
        return tuple(blockers)

    @staticmethod
    def _effective_market_cap(row: OneToTwoMarketRow) -> float:
        return row.market_cap or row.float_market_cap

    @staticmethod
    def _market_cap_source(row: OneToTwoMarketRow) -> str:
        if row.market_cap > 0:
            return "total"
        if row.float_market_cap > 0:
            return "float"
        return "missing"

    @staticmethod
    def _format_yi(value: float) -> str:
        return f"{value / 100_000_000:.0f}"

    def _position_label_allowed(self, label: str) -> bool:
        allowed = self._settings.allowed_position_labels
        return not allowed or label in allowed

    def _warnings(
        self,
        row: OneToTwoMarketRow,
        *,
        turnover_quality_score: float,
        turnover_quality_notes: tuple[str, ...],
    ) -> tuple[str, ...]:
        warnings: list[str] = ["严格 T+1：当天买入后跌破止损只预警，次日才模拟卖出"]
        if row.open_pct > self._settings.max_confirm_open_pct:
            warnings.append("竞价/开盘涨幅偏高，防止高开兑现")
        if row.turnover_rate < 2:
            warnings.append("换手偏低，可能买不到或承接不足")
        if row.auction_amount < row.turnover_amount * 0.02:
            warnings.append("竞价成交占比偏低，强度仍需开盘确认")
        if row.sealed_amount and row.turnover_amount:
            sealed_ratio = row.sealed_amount / row.turnover_amount
            if sealed_ratio < self._settings.min_sealed_amount_ratio * 1.5:
                warnings.append("封板资金刚过线，盘中炸板风险需要重点盯")
        if turnover_quality_score < self._settings.min_turnover_dragon_score + 8:
            warnings.append("换手龙质量刚过线，必须等开盘承接继续确认")
        warnings.extend(turnover_quality_notes[:2])
        warnings.append(f"资金风格代理：{self._capital_style_label(row)}")
        return tuple(warnings)

    def _first_board_score(self, row: OneToTwoMarketRow) -> float:
        score = 10.0
        if row.first_limit_up_time and row.first_limit_up_time <= "10:30":
            score += 6.0
        if row.sealed_amount >= row.turnover_amount * 0.12:
            score += 5.0
        if row.turnover_rate >= 3:
            score += 4.0
        return min(score, 25.0)

    def _auction_score(self, row: OneToTwoMarketRow) -> float:
        score = 8.0
        if 0.02 <= row.open_pct <= self._settings.max_confirm_open_pct:
            score += 7.0
        elif self._settings.min_confirm_open_pct <= row.open_pct < 0.02:
            score += 3.0
        if row.auction_amount >= row.turnover_amount * 0.04:
            score += 5.0
        return min(score, 20.0)

    def _position_profile(self, row: OneToTwoMarketRow) -> OneToTwoPositionProfile:
        low_score = 8.0 if row.low_20 and row.latest_price <= row.low_20 * 1.25 else 4.0
        breakout_score = (
            7.0
            if row.high_60 and row.latest_price >= row.high_60 * 0.98
            else 3.0
        )
        pressure_distance = (
            (row.pressure_price - row.latest_price) / row.latest_price
            if row.pressure_price and row.latest_price
            else 1.0
        )
        pressure_score = 5.0 if pressure_distance > 0.08 else 2.0
        ma_score = 3.0 if row.ma_5 >= row.ma_10 >= row.ma_20 else 1.0
        volume_score = 2.0 if row.turnover_amount >= self._settings.liquidity_score_amount * 2 else 1.0
        total = low_score + breakout_score + pressure_score + ma_score + volume_score
        label = (
            "低位平台突破"
            if low_score >= 8 and breakout_score >= 7
            else "平台突破"
            if breakout_score >= 7
            else "低位启动"
            if low_score >= 8
            else "位置一般"
        )
        risk_notes: list[str] = []
        if pressure_score < 5:
            risk_notes.append("上方压力较近")
        if ma_score < 3:
            risk_notes.append("均线结构尚未完全多头")
        if row.volume_ratio_5 < self._settings.min_volume_ratio_5:
            risk_notes.append("量比不足，持续性待确认")
        if row.rsi_14 > self._settings.max_rsi_14:
            risk_notes.append("RSI 过热")
        elif row.rsi_14 < self._settings.min_rsi_14:
            risk_notes.append("RSI 过冷")
        if row.position_percentile_60 < self._settings.min_position_percentile_60:
            risk_notes.append("60 日位置分位偏低")
        return OneToTwoPositionProfile(
            label=label,
            low_position_score=low_score,
            breakout_score=breakout_score,
            pressure_score=pressure_score,
            moving_average_score=ma_score,
            volume_score=volume_score,
            summary=f"{label}，位置结构 {total:.0f}/25",
            risk_notes=tuple(risk_notes),
            volume_ratio=round(row.volume_ratio_5, 2),
            rsi_14=round(row.rsi_14, 2),
            position_percentile_60=round(row.position_percentile_60, 4),
            capital_style_label=self._capital_style_label(row),
        )

    def _position_score(self, profile: OneToTwoPositionProfile) -> float:
        return (
            profile.low_position_score
            + profile.breakout_score
            + profile.pressure_score
            + profile.moving_average_score
            + profile.volume_score
        )

    def _breakout_structure_profile(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
    ) -> BreakoutStructureProfile:
        breakout_line = row.high_60 or row.pressure_price or row.ma_20 or row.latest_price
        distance_pct = (
            max((row.latest_price - breakout_line) / breakout_line, 0.0)
            if breakout_line
            else 0.0
        )
        base_tightness_score = self._base_tightness_score(row)
        volume_surge_score = self._volume_surge_score(row)
        overhead_supply_score = self._overhead_supply_score(row)
        relative_strength_score = self._relative_strength_score(row, profile)
        score = round(
            min(
                100.0,
                base_tightness_score
                + volume_surge_score
                + overhead_supply_score
                + relative_strength_score,
            ),
            2,
        )
        risk_notes: list[str] = []
        if distance_pct > self._settings.max_breakout_entry_distance_pct:
            risk_notes.append(
                f"买点距离突破线 {distance_pct:.1%}，超过 "
                f"{self._settings.max_breakout_entry_distance_pct:.1%} 容忍线"
            )
        if row.volume_ratio_5 < self._settings.min_breakout_volume_ratio:
            risk_notes.append(
                f"突破量比 {row.volume_ratio_5:.2f} 低于 "
                f"{self._settings.min_breakout_volume_ratio:.2f}"
            )
        if overhead_supply_score < 16:
            risk_notes.append("左侧压力没有完全打开，突破后容易回落验证。")
        if base_tightness_score < 18:
            risk_notes.append("平台紧凑度不足，不是最干净的强势整理。")
        passed = (
            score >= self._settings.min_breakout_structure_score
            and distance_pct <= self._settings.max_breakout_entry_distance_pct
            and row.volume_ratio_5 >= self._settings.min_breakout_volume_ratio
        )
        label = (
            "强结构突破"
            if passed and score >= 82
            else "有效结构突破"
            if passed
            else "结构突破不足"
        )
        summary = (
            f"{label} {score:.0f}/100，突破线 {breakout_line:.2f}，"
            f"距突破线 {distance_pct:.1%}，量比 {row.volume_ratio_5:.2f}"
        )
        return BreakoutStructureProfile(
            score=score,
            label=label,
            breakout_line=round(breakout_line, 2),
            distance_pct=round(distance_pct, 4),
            base_tightness_score=round(base_tightness_score, 2),
            volume_surge_score=round(volume_surge_score, 2),
            overhead_supply_score=round(overhead_supply_score, 2),
            relative_strength_score=round(relative_strength_score, 2),
            passed=passed,
            summary=summary,
            risk_notes=tuple(risk_notes),
        )

    def _base_tightness_score(self, row: OneToTwoMarketRow) -> float:
        if not row.low_20 or not row.latest_price:
            return 10.0
        range_pct = max((row.latest_price - row.low_20) / row.low_20, 0.0)
        if range_pct <= 0.12:
            return 28.0
        if range_pct <= 0.20:
            return 24.0
        if range_pct <= 0.28:
            return 18.0
        return 10.0

    def _volume_surge_score(self, row: OneToTwoMarketRow) -> float:
        ratio = row.volume_ratio_5
        if 1.5 <= ratio <= 3.5:
            return 24.0
        if ratio >= self._settings.min_breakout_volume_ratio:
            return 18.0
        if ratio >= self._settings.min_volume_ratio_5:
            return 10.0
        return 4.0

    def _overhead_supply_score(self, row: OneToTwoMarketRow) -> float:
        if not row.pressure_price or not row.latest_price:
            return 18.0
        pressure_distance = (row.pressure_price - row.latest_price) / row.latest_price
        if pressure_distance > 0.12:
            return 24.0
        if pressure_distance > self._settings.near_pressure_pct:
            return 18.0
        if pressure_distance >= 0:
            return 8.0
        return 22.0

    def _relative_strength_score(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
    ) -> float:
        score = 8.0
        if profile.breakout_score >= 7:
            score += 10.0
        if row.position_percentile_60 >= 0.75:
            score += 8.0
        elif row.position_percentile_60 >= self._settings.min_position_percentile_60:
            score += 5.0
        if 0.08 <= row.recent_gain_pct <= 0.35:
            score += 6.0
        elif row.recent_gain_pct < self._settings.recent_gain_block_pct:
            score += 3.0
        return min(score, 24.0)

    def _theme_score(self, row: OneToTwoMarketRow) -> float:
        if row.theme:
            return 12.0 if row.market_temperature >= 70 else 9.0
        return 6.0

    def _liquidity_score(self, row: OneToTwoMarketRow) -> float:
        if row.turnover_amount >= self._settings.liquidity_score_amount * 3:
            return 15.0
        if row.turnover_amount >= self._settings.liquidity_score_amount:
            return 10.0
        return 0.0

    def _sealing_score(self, row: OneToTwoMarketRow) -> float:
        score = 4.0
        if row.first_limit_up_time and row.first_limit_up_time <= "10:00":
            score += 5.0
        elif row.first_limit_up_time and row.first_limit_up_time <= "10:30":
            score += 4.0
        sealed_ratio = row.sealed_amount / row.turnover_amount if row.turnover_amount else 0.0
        if sealed_ratio >= 0.15:
            score += 6.0
        elif sealed_ratio >= self._settings.min_sealed_amount_ratio:
            score += 4.0
        if 3 <= row.turnover_rate <= 15:
            score += 4.0
        elif row.turnover_rate > 0:
            score += 2.0
        if row.open_pct < 0.095:
            score += 3.0
        return min(score, 20.0)

    def _mainline_score(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
    ) -> float:
        score = 4.0
        if row.market_temperature >= 70:
            score += 5.0
        elif row.market_temperature >= self._settings.market_temperature_floor:
            score += 3.0
        if row.theme:
            score += 4.0
        if profile.breakout_score >= 7:
            score += 3.0
        if profile.low_position_score >= 8:
            score += 2.0
        if 0.08 <= row.recent_gain_pct <= 0.35:
            score += 2.0
        return min(score, 20.0)

    def _leader_score(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
    ) -> float:
        score = 3.0
        sealed_ratio = row.sealed_amount / row.turnover_amount if row.turnover_amount else 0.0
        if row.first_limit_up_time and row.first_limit_up_time <= "10:30":
            score += 4.0
        if sealed_ratio >= 0.12:
            score += 4.0
        elif sealed_ratio >= self._settings.min_sealed_amount_ratio:
            score += 2.0
        if row.turnover_rate >= 5:
            score += 3.0
        elif row.turnover_rate >= 3:
            score += 2.0
        if 0.10 <= row.recent_gain_pct <= 0.30:
            score += 3.0
        if profile.breakout_score >= 7:
            score += 2.0
        if row.market_temperature >= 70 and row.theme:
            score += 2.0
        return min(score, 20.0)

    def _turnover_dragon_quality(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
    ) -> tuple[float, str, tuple[str, ...]]:
        sealed_ratio = row.sealed_amount / row.turnover_amount if row.turnover_amount else 0.0
        auction_ratio = row.auction_amount / row.turnover_amount if row.turnover_amount else 0.0
        score = 0.0
        notes: list[str] = []

        if (
            self._settings.min_turnover_dragon_turnover_rate
            <= row.turnover_rate
            <= self._settings.max_turnover_dragon_turnover_rate
        ):
            score += 20.0
        elif row.turnover_rate > 0:
            score += 8.0
            notes.append("换手不在有效接力区间")

        if sealed_ratio >= 0.15:
            score += 20.0
        elif sealed_ratio >= self._settings.min_turnover_dragon_sealed_ratio:
            score += 16.0
        elif sealed_ratio >= self._settings.min_sealed_amount_ratio:
            score += 8.0
            notes.append("封单/成交额刚过最低线")
        else:
            notes.append("封单/成交额不足")

        if row.first_limit_up_time and row.first_limit_up_time <= "10:00":
            score += 16.0
        elif row.first_limit_up_time and row.first_limit_up_time <= "10:30":
            score += 12.0
        elif row.first_limit_up_time:
            score += 5.0
            notes.append("首封时间偏晚")
        else:
            notes.append("缺少首封时间，换手质量只能降级评估")

        if auction_ratio >= 0.04:
            score += 12.0
        elif auction_ratio >= self._settings.min_turnover_dragon_auction_ratio:
            score += 8.0
        elif row.auction_amount > 0:
            score += 4.0
            notes.append("竞价成交占比偏低")
        else:
            notes.append("缺少竞价成交额")

        if row.market_temperature >= 70 and row.theme:
            score += 12.0
        elif row.market_temperature >= self._settings.market_temperature_floor:
            score += 7.0
        else:
            notes.append("市场温度不足，换手持续性打折")

        if row.volume_ratio_5 >= 1.5:
            score += 8.0
        elif row.volume_ratio_5 >= self._settings.min_volume_ratio_5:
            score += 5.0
        else:
            notes.append("量比不足")

        if self._settings.min_rsi_14 <= row.rsi_14 <= min(78.0, self._settings.max_rsi_14):
            score += 6.0
        elif self._settings.min_rsi_14 <= row.rsi_14 <= self._settings.max_rsi_14:
            score += 3.0
            notes.append("RSI 偏热，启动买点安全垫变薄")
        else:
            notes.append("RSI 不在健康区间")

        if (
            profile.low_position_score >= 8
            or profile.breakout_score >= 7
            or row.position_percentile_60 >= 0.7
        ):
            score += 6.0
        else:
            notes.append("位置结构不够像主升启动前")

        score = round(min(score, 100.0), 2)
        label = (
            "强换手龙买点"
            if score >= 86
            else "有效换手龙买点"
            if score >= self._settings.min_turnover_dragon_score
            else "换手质量不足"
        )
        summary = (
            f"换手质量 {score:.0f}/100，换手 {row.turnover_rate:.1f}%，"
            f"封单/成交额 {sealed_ratio:.1%}，竞价占比 {auction_ratio:.1%}"
        )
        return score, label, tuple(dict.fromkeys((summary, *notes)))

    def _leader_label(
        self,
        leader_score: float,
        sealing_score: float,
        mainline_score: float,
    ) -> str:
        if leader_score >= 18 and sealing_score >= 18 and mainline_score >= 18:
            return "主线龙头候选"
        if leader_score >= self._settings.min_leader_score:
            return "龙头候选"
        return "普通首板观察"

    def _strategy_tags(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
        leader_score: float,
        sealing_score: float,
        mainline_score: float,
        turnover_quality_score: float,
    ) -> tuple[str, ...]:
        tags: list[str] = [
            self._leader_label(leader_score, sealing_score, mainline_score)
        ]
        if turnover_quality_score >= 86:
            tags.append("强换手龙")
        elif turnover_quality_score >= self._settings.min_turnover_dragon_score:
            tags.append("有效换手龙")
        if sealing_score >= 18:
            tags.append("封板纪律达标")
        if mainline_score >= 18:
            tags.append("主线强度高")
        if profile.low_position_score >= 8 and profile.breakout_score >= 7:
            tags.append("低位突破")
        if row.volume_ratio_5 >= self._settings.min_volume_ratio_5:
            tags.append("量比确认")
        if self._settings.min_rsi_14 <= row.rsi_14 <= self._settings.max_rsi_14:
            tags.append("RSI 区间")
        if row.position_percentile_60 >= self._settings.min_position_percentile_60:
            tags.append("60日位置达标")
        if row.open_pct >= self._settings.max_confirm_open_pct:
            tags.append("高开谨慎")
        return tuple(tags)

    def _capital_style_label(self, row: OneToTwoMarketRow) -> str:
        if row.turnover_amount >= 1_200_000_000:
            return "机构/大票风格代理"
        if row.turnover_amount >= 500_000_000:
            return "游资+机构共同代理"
        return "游资弹性代理"

    def _exit_plan(self, entry_price: float, stop_loss: float) -> OneToTwoExitPlan:
        first_take_profit_price = round(
            entry_price * (1 + self._settings.first_take_profit_pct),
            2,
        )
        strong_take_profit_price = round(
            entry_price * (1 + self._settings.strong_take_profit_pct),
            2,
        )
        stop_loss_pct = (
            round((entry_price - stop_loss) / entry_price, 4)
            if entry_price
            else self._settings.stop_loss_pct
        )
        return OneToTwoExitPlan(
            stop_loss=stop_loss,
            stop_loss_pct=stop_loss_pct,
            first_take_profit_price=first_take_profit_price,
            first_take_profit_pct=self._settings.first_take_profit_pct,
            strong_take_profit_price=strong_take_profit_price,
            strong_take_profit_pct=self._settings.strong_take_profit_pct,
            trailing_stop_pct=self._settings.trailing_stop_pct,
            max_holding_trade_days=self._settings.max_holding_trade_days,
            summary=(
                f"亏损跌破 {stop_loss} 先预警、T+1 再卖；"
                f"盈利 {self._format_pct(self._settings.first_take_profit_pct)} 第一止盈；"
                f"强势达到 {self._format_pct(self._settings.strong_take_profit_pct)} 后用 "
                f"{self._format_pct(self._settings.trailing_stop_pct)} 回撤保护。"
            ),
        )

    def _format_pct(self, value: float) -> str:
        text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"

    def _round_price_up(self, value: float) -> float:
        return math.ceil(value * 100 - 1e-9) / 100

    def _mainline_continuity(
        self,
        row: OneToTwoMarketRow,
        mainline_score: float,
        sealing_score: float,
        leader_score: float,
    ) -> MainlineContinuity:
        hot_stock_count = 1 if row.theme else 0
        limit_up_count = 1 if row.latest_price >= row.limit_up_price * 0.995 else 0
        score = min(
            100.0,
            row.market_temperature * 0.35
            + mainline_score * 1.5
            + sealing_score * 0.8
            + leader_score * 0.8
            + (8 if row.theme else 0)
            + (6 if limit_up_count else 0),
        )
        reasons = [
            f"市场温度 {row.market_temperature}",
            f"主线强度 {mainline_score:.0f}/20",
            f"封板纪律 {sealing_score:.0f}/20",
            f"龙头辨识度 {leader_score:.0f}/20",
        ]
        risk_notes: list[str] = []
        if row.market_temperature < 60:
            risk_notes.append("市场温度不足，接力持续性打折")
        if mainline_score < self._settings.min_mainline_score:
            risk_notes.append("主线强度低于执行门槛")
        status = (
            "strong"
            if score >= 75
            else "watch"
            if score >= self._settings.mainline_fade_score
            else "fading"
        )
        next_action = (
            "主线仍强，持仓可按止盈和回撤纪律观察。"
            if status == "strong"
            else "主线需继续确认，达到第一止盈优先落袋。"
            if status == "watch"
            else "主线衰减，若 T+1 已到应优先退出。"
        )
        return MainlineContinuity(
            theme=row.theme or "未标记主线",
            score=round(score, 2),
            status=status,
            hot_stock_count=hot_stock_count,
            limit_up_count=limit_up_count,
            news_count=0,
            latest_news=(),
            reasons=tuple(reasons),
            risk_notes=tuple(risk_notes),
            next_action=next_action,
        )

    def _discipline_summary(self, row: OneToTwoMarketRow, exit_plan: OneToTwoExitPlan) -> str:
        sealed_ratio = row.sealed_amount / row.turnover_amount if row.turnover_amount else 0.0
        return (
            f"封板资金占比 {sealed_ratio:.1%}；只做非一字、封板确认后的主线首板候选，"
            f"量比 {row.volume_ratio_5:.2f}、RSI {row.rsi_14:.1f}、"
            f"换手 {row.turnover_rate:.1f}%、60日位置 {row.position_percentile_60:.0%}、"
            f"{self._capital_style_label(row)}；"
            f"次日一进二只作为确认点，模拟盘严格 T+1；{exit_plan.summary}"
        )

    def _rationale(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
        blockers: tuple[str, ...],
        score: float,
    ) -> str:
        if blockers:
            return f"{row.name} 被拦截：{blockers[0]}"
        if score >= self._settings.min_score and not self._is_executable_score(score):
            return (
                f"{row.name} 执行分 {score:g} 已达到过热区间，"
                "本轮回测显示先过滤拥挤高分票能改善收益和回撤。"
            )
        return (
            f"{row.name} 属于{profile.label}，封板纪律、主线强度和龙头候选辨识度进入观察。"
        )

    def _next_action(self, status: str) -> str:
        if status == "blocked":
            return "不生成模拟买入，只保留风险记录。"
        if status == "ready":
            return "等待封板纪律和竞价确认后进入事件驱动模拟盘。"
        return "仅观察，不触发模拟买入。"
