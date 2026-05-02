"""One-to-two mainboard strategy scoring and review policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared.contracts import (
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


class OneToTwoSettings(Protocol):
    min_score: int
    max_position_pct: float
    stop_loss_pct: float
    min_turnover_amount: float
    market_temperature_floor: int
    high_deviation_block_pct: float
    recent_gain_block_pct: float
    near_pressure_pct: float
    min_sealed_amount_ratio: float
    min_leader_score: float
    min_mainline_score: float
    board_strategy_enabled: bool
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
        candidates = tuple(self._candidate_from_row(row) for row in rows)
        return tuple(sorted(candidates, key=lambda item: item.score, reverse=True))

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
        stop_loss = round(max(structure_stop, percent_stop), 2)
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
            discipline_summary=self._discipline_summary(row),
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
        position_profile = self._position_profile(row)
        if self._mainline_score(row, position_profile) < self._settings.min_mainline_score:
            blockers.append("主线首板强度不足，先不进入模拟盘")
        if self._leader_score(row, position_profile) < self._settings.min_leader_score:
            blockers.append("龙头候选辨识度不足，避免普通跟风票")
        return tuple(blockers)

    def _warnings(self, row: OneToTwoMarketRow) -> tuple[str, ...]:
        warnings: list[str] = ["严格 T+1：当天买入后跌破止损只预警，次日才模拟卖出"]
        if row.open_pct > 0.07:
            warnings.append("竞价/开盘涨幅偏高，防止高开兑现")
        if row.turnover_rate < 2:
            warnings.append("换手偏低，可能买不到或承接不足")
        if row.auction_amount < row.turnover_amount * 0.02:
            warnings.append("竞价成交占比偏低，强度仍需开盘确认")
        if row.sealed_amount and row.turnover_amount:
            sealed_ratio = row.sealed_amount / row.turnover_amount
            if sealed_ratio < self._settings.min_sealed_amount_ratio * 1.5:
                warnings.append("封板资金刚过线，盘中炸板风险需要重点盯")
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
        if 0.02 <= row.open_pct <= 0.07:
            score += 7.0
        elif 0 <= row.open_pct < 0.02:
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
        volume_score = 2.0 if row.turnover_amount >= self._settings.min_turnover_amount * 2 else 1.0
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
        return OneToTwoPositionProfile(
            label=label,
            low_position_score=low_score,
            breakout_score=breakout_score,
            pressure_score=pressure_score,
            moving_average_score=ma_score,
            volume_score=volume_score,
            summary=f"{label}，位置结构 {total:.0f}/25",
            risk_notes=tuple(risk_notes),
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
        if row.turnover_amount >= self._settings.min_turnover_amount * 3:
            return 15.0
        if row.turnover_amount >= self._settings.min_turnover_amount:
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
        if row.open_pct >= 0.07:
            tags.append("高开谨慎")
        return tuple(tags)

    def _discipline_summary(self, row: OneToTwoMarketRow) -> str:
        sealed_ratio = row.sealed_amount / row.turnover_amount if row.turnover_amount else 0.0
        return (
            f"封板资金占比 {sealed_ratio:.1%}；只做非一字、封板确认后的主线首板候选，"
            "次日一进二只作为确认点，模拟盘严格 T+1。"
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
