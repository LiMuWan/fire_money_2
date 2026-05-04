"""One-to-two mainboard strategy scoring and review policy."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

from shared.contracts import (
    MainlineContinuity,
    OneToTwoExitPlan,
    OneToTwoCandidate,
    OneToTwoPositionProfile,
)


@dataclass(frozen=True)
class OneToTwoMarketRow:
    symbol: str
    name: str
    trade_date: str
    board: str
    is_st: bool
    is_delisting: bool
    listing_days: int
    latest_price: float
    previous_close: float
    limit_up_price: float
    first_limit_up_time: str
    sealed_amount: float
    turnover_amount: float
    turnover_rate: float
    open_pct: float
    auction_amount: float
    low_20: float
    high_60: float
    pressure_price: float
    ma_5: float
    ma_10: float
    ma_20: float
    recent_gain_pct: float
    theme: str
    market_temperature: int
    first_board_count: int = 0
    volume_ratio_5: float = 1.5
    rsi_14: float = 65.0
    position_percentile_60: float = 0.75


@dataclass(frozen=True)
class HistoricalPriceBar:
    trade_date: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    amount: float = 0.0


class OneToTwoSettings(Protocol):
    min_score: int
    max_position_pct: float
    stop_loss_pct: float
    min_confirm_open_pct: float
    max_confirm_open_pct: float
    min_turnover_amount: float
    liquidity_score_amount: float
    market_temperature_floor: int
    high_deviation_block_pct: float
    recent_gain_block_pct: float
    near_pressure_pct: float
    min_sealed_amount_ratio: float
    min_leader_score: float
    min_mainline_score: float
    min_volume_ratio_5: float
    min_rsi_14: float
    max_rsi_14: float
    min_position_percentile_60: float
    min_low_breakout_first_board_count: int
    min_low_breakout_ready_candidates: int
    max_ready_candidates: int
    allowed_position_labels: tuple[str, ...]
    selection_rank: str
    board_strategy_enabled: bool
    first_take_profit_pct: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    max_holding_trade_days: int
    exclude_st: bool
    exclude_delisting: bool
    exclude_new_stock_days: int
    excluded_boards: tuple[str, ...]


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
        blockers = self._blockers(row)
        warnings = self._warnings(row)
        first_board_score = self._first_board_score(row)
        auction_score = self._auction_score(row)
        position_profile = self._position_profile(row)
        theme_score = self._theme_score(row)
        liquidity_score = self._liquidity_score(row)
        mainline_score = self._mainline_score(row, position_profile)
        sealing_score = self._sealing_score(row)
        leader_score = self._leader_score(row, position_profile)
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
            if score >= self._settings.min_score
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
            warnings=warnings,
            rationale=self._rationale(row, position_profile, blockers),
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
            ),
            discipline_summary=self._discipline_summary(row, exit_plan),
            exit_plan=exit_plan,
            mainline_continuity=continuity,
        )

    def _blockers(self, row: OneToTwoMarketRow) -> tuple[str, ...]:
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
        if self._settings.board_strategy_enabled and row.turnover_amount > 0:
            sealed_ratio = row.sealed_amount / row.turnover_amount
            if sealed_ratio < self._settings.min_sealed_amount_ratio:
                blockers.append("封板资金不足，不能作为主线首板龙头候选")
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
        position_profile = self._position_profile(row)
        if not self._position_label_allowed(position_profile.label):
            blockers.append("位置一般，不符合低位/突破一进二核心买点")
        if self._mainline_score(row, position_profile) < self._settings.min_mainline_score:
            blockers.append("主线首板强度不足，先不进入模拟盘")
        if self._leader_score(row, position_profile) < self._settings.min_leader_score:
            blockers.append("龙头候选辨识度不足，避免普通跟风票")
        return tuple(blockers)

    def _position_label_allowed(self, label: str) -> bool:
        allowed = self._settings.allowed_position_labels
        return not allowed or label in allowed

    def _warnings(self, row: OneToTwoMarketRow) -> tuple[str, ...]:
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
    ) -> tuple[str, ...]:
        tags: list[str] = [
            self._leader_label(leader_score, sealing_score, mainline_score)
        ]
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
            f"60日位置 {row.position_percentile_60:.0%}、{self._capital_style_label(row)}；"
            f"次日一进二只作为确认点，模拟盘严格 T+1；{exit_plan.summary}"
        )

    def _rationale(
        self,
        row: OneToTwoMarketRow,
        profile: OneToTwoPositionProfile,
        blockers: tuple[str, ...],
    ) -> str:
        if blockers:
            return f"{row.name} 被拦截：{blockers[0]}"
        return (
            f"{row.name} 属于{profile.label}，封板纪律、主线强度和龙头候选辨识度进入观察。"
        )

    def _next_action(self, status: str) -> str:
        if status == "blocked":
            return "不生成模拟买入，只保留风险记录。"
        if status == "ready":
            return "等待封板纪律和竞价确认后进入事件驱动模拟盘。"
        return "仅观察，不触发模拟买入。"
