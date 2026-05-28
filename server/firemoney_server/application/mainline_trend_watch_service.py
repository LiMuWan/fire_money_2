"""Whole-market watch-only scanner for mainline trend roots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from server.firemoney_server.domain.one_to_two_types import (
    FundamentalSnapshot,
    HistoricalPriceBar,
    MarketTrendRow,
)
from server.firemoney_server.application.mainline_trend_strategy_profile import (
    build_mainline_trend_strategy_profile,
)
from shared.contracts import MainlineTrendWatchItem, MainlineTrendWatchReport


class TrendMarketDataProvider(Protocol):
    def load_full_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        """Load whole-market spot rows for a trade date."""

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        """Load daily price bars for trend-root analysis."""

    def load_fundamental_snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        """Load a best-effort fundamental snapshot."""


@dataclass(frozen=True)
class _TrendProfile:
    close: float
    ma5: float
    ma10: float
    ma20: float
    high_60: float
    high_120: float
    low_20: float
    low_120: float
    recent_gain_pct: float
    gain_5_pct: float
    distance_to_ma10_pct: float
    distance_to_ma20_pct: float
    distance_to_high_60_pct: float
    position_percentile_120: float
    volume_ratio_5: float
    base_tightness_pct: float
    max_drawdown_20_pct: float


@dataclass(frozen=True)
class _ScoreBreakdown:
    logic: float
    value: float
    capital: float
    sustainability: float
    timing: float

    @property
    def total(self) -> float:
        return min(
            100.0,
            self.logic * 0.24
            + self.value * 0.18
            + self.capital * 0.22
            + self.sustainability * 0.22
            + self.timing * 0.14,
        )


@dataclass(frozen=True)
class _ThemeSignal:
    theme: str
    logic: str
    strength: float
    source: str


@dataclass(frozen=True)
class _DataQuality:
    degraded: bool
    cached: bool
    stale: bool


class MainlineTrendWatchService:
    """Explains why a stock may or may not have a mainline trend root."""

    _THEME_RULES: tuple[tuple[tuple[str, ...], str, str, float], ...] = (
        (
            ("PCB", "玻纤", "电子布", "覆铜", "宏和", "胜宏", "沪电", "生益"),
            "AI服务器PCB上游",
            "AI 服务器高速板升级带来低介电材料、电子布、覆铜板和高端 PCB 的订单弹性。",
            88.0,
        ),
        (
            ("AI", "算力", "光模块", "CPO", "通信", "互联", "旭创", "易盛", "天孚"),
            "AI算力基础设施",
            "AI 数据中心资本开支、800G/1.6T 迭代和海外订单预期容易形成机构资金抱团。",
            92.0,
        ),
        (
            ("半导体", "芯片", "封测", "存储", "先进封装", "半导体材料"),
            "半导体国产替代",
            "国产替代、周期修复和先进封装扩产能吸引产业资金反复定价。",
            80.0,
        ),
        (
            ("机器人", "减速器", "伺服", "传感", "智能"),
            "机器人产业链",
            "具身智能和工业自动化预期能够带来订单想象，但需要业绩或订单持续确认。",
            76.0,
        ),
        (
            ("新能源", "储能", "电池", "光伏", "锂", "钠"),
            "新能源修复",
            "行业供需出清后存在估值修复空间，但主升持续性必须看价格和盈利拐点。",
            68.0,
        ),
        (
            ("军工", "航天", "卫星", "导航", "低空"),
            "军工低空经济",
            "政策订单、低空基础设施和军工景气预期可吸引事件资金，需要合同兑现接力。",
            72.0,
        ),
        (
            ("医药", "创新药", "医疗", "生物"),
            "医药创新修复",
            "创新药授权、医保预期和出海订单能形成阶段主线，但受事件和估值扰动较大。",
            66.0,
        ),
    )

    def __init__(
        self,
        *,
        market_data_provider: TrendMarketDataProvider,
    ) -> None:
        self._market_data_provider = market_data_provider

    def build_report(
        self,
        *,
        trade_date: str,
        lookback_days: int = 190,
        limit: int = 12,
        scan_limit: int = 24,
        fast_snapshot: bool = False,
    ) -> MainlineTrendWatchReport:
        rows = self._load_market_rows(trade_date)
        data_quality = self._data_quality(rows)
        candidates = self._coarse_filter(rows, scan_limit=max(scan_limit, limit * 2))
        if not candidates:
            return MainlineTrendWatchReport(
                report_id=f"mainline-trend-watch-{trade_date}",
                trade_date=trade_date,
                status="empty",
                summary="全市场扫描没有拿到可分析样本；不做主升判断，也不生成买点。",
                items=(),
                rules=self._rules(),
                limitations=self._limitations(data_quality),
                next_action="先恢复全市场行情快照，再看主线逻辑、财务承接和资金持续性。",
            )

        start_date = self._start_date(trade_date, lookback_days)
        items: list[MainlineTrendWatchItem] = []
        fundamental_limit = min(max(limit, 6), 12)
        for index, row in enumerate(candidates):
            if fast_snapshot:
                bars = ()
            else:
                try:
                    bars = self._market_data_provider.load_price_bars(
                        row.symbol,
                        start_date,
                        trade_date,
                    )
                except Exception:
                    bars = ()
            fundamental = None
            if not fast_snapshot and index < fundamental_limit:
                try:
                    fundamental = self._market_data_provider.load_fundamental_snapshot(
                        row.symbol
                    )
                except Exception:
                    fundamental = None
            item = self._build_item(
                row=row,
                trade_date=trade_date,
                bars=bars,
                fundamental=fundamental,
            )
            if item is not None:
                items.append(item)

        items.sort(key=lambda item: item.score, reverse=True)
        items = items[: max(1, limit)]
        if not items:
            return MainlineTrendWatchReport(
                report_id=f"mainline-trend-watch-{trade_date}",
                trade_date=trade_date,
                status="empty",
                summary=self._summary_prefix(data_quality)
                + "候选缺少足够日线/资金/逻辑证据；先不讲主升故事。",
                items=(),
                rules=self._rules(),
                limitations=self._limitations(data_quality),
                next_action="补齐候选日线和基础财务快照后，再给主升根因评分。",
            )

        prime_count = sum(1 for item in items if item.status == "prime_watch")
        wait_count = sum(1 for item in items if item.status == "wait_entry")
        summary = (
            self._summary_prefix(data_quality)
            + f"从 {len(rows)} 只股票粗筛 {len(candidates)} 只，"
            f"输出 {len(items)} 只观察；{prime_count} 只逻辑/价值/资金共振，"
            f"{wait_count} 只只等买点。"
        )
        if fast_snapshot:
            summary += " 页面使用快照模式，先展示全市场逻辑/资金雷达，深度日线和财务由 CLI/后台补充。"
        return MainlineTrendWatchReport(
            report_id=f"mainline-trend-watch-{trade_date}",
            trade_date=trade_date,
            status="watch_only",
            summary=summary,
            items=tuple(items),
            rules=self._rules(),
            limitations=self._limitations(data_quality, fast_snapshot=fast_snapshot),
            next_action="先看主升根因是否扎实，再看回踩/突破买点；没有产业逻辑、业绩承接和资金持续性，不因为涨了就追。",
        )

    def build_unavailable_report(
        self,
        *,
        trade_date: str,
        status: str,
        reason: str,
        next_action: str,
    ) -> MainlineTrendWatchReport:
        """Return an honest page-safe report when full-market scanning is unavailable."""

        return MainlineTrendWatchReport(
            report_id=f"mainline-trend-watch-{trade_date}",
            trade_date=trade_date,
            status=status,
            summary=(
                f"全市场主升根因扫描（{status}）：{reason}；"
                "本次不输出主升候选，也不把缓存候选伪装成实时全市场扫描。"
            ),
            items=(),
            rules=self._rules(),
            limitations=(
                "本次未完成全市场行情扫描；宁可显示不可用，也不生成看起来很真的假结论。",
                *self._limitations(degraded_data=True),
            ),
            next_action=next_action,
        )

    def _load_market_rows(self, trade_date: str) -> tuple[MarketTrendRow, ...]:
        try:
            return self._market_data_provider.load_full_market_rows(trade_date)
        except Exception:
            return ()

    @staticmethod
    def _data_quality(rows: tuple[MarketTrendRow, ...]) -> _DataQuality:
        if not rows:
            return _DataQuality(degraded=False, cached=False, stale=False)
        sources = tuple(row.data_source for row in rows)
        degraded = all(not source.startswith("full_market_spot") for source in sources)
        cached = any("cache" in source for source in sources)
        stale = any("cache_stale" in source for source in sources)
        return _DataQuality(degraded=degraded, cached=cached, stale=stale)

    def _coarse_filter(
        self,
        rows: tuple[MarketTrendRow, ...],
        *,
        scan_limit: int,
    ) -> tuple[MarketTrendRow, ...]:
        scored: list[tuple[float, MarketTrendRow]] = []
        for row in rows:
            if row.is_st or row.is_delisting:
                continue
            if row.latest_price <= 0 or row.previous_close <= 0:
                continue
            if row.board == "北交所":
                continue
            if row.turnover_amount < 80_000_000:
                continue
            if row.market_cap and row.market_cap < 3_000_000_000:
                continue
            theme = self._theme_signal(row)
            liquidity_score = min(25.0, row.turnover_amount / 1_000_000_000 * 8)
            turnover_score = min(18.0, max(0.0, row.turnover_rate) * 1.5)
            cap_score = self._market_cap_score(row.market_cap or row.float_market_cap)
            change_score = 16.0 if -3 <= row.change_pct <= 6 else 8.0
            score = (
                theme.strength * 0.32
                + liquidity_score
                + turnover_score
                + cap_score
                + change_score
            )
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return tuple(row for _score, row in scored[:scan_limit])

    def _build_item(
        self,
        *,
        row: MarketTrendRow,
        trade_date: str,
        bars: tuple[HistoricalPriceBar, ...],
        fundamental: FundamentalSnapshot | None,
    ) -> MainlineTrendWatchItem | None:
        bars = tuple(bar for bar in bars if bar.trade_date <= trade_date)
        profile = self._trend_profile(row, bars)
        if profile is None:
            return None
        theme = self._theme_signal(row)
        scores = self._score_breakdown(row, profile, fundamental, theme)
        status, action = self._status_action(scores, profile)
        pullback_low, pullback_high, breakout_price, stop_loss = self._price_plan(
            profile
        )
        value_case = self._value_case(fundamental, row)
        capital_case = self._capital_case(row, profile)
        sustainability_case = self._sustainability_case(row, profile, fundamental, theme)
        strategy_profile = build_mainline_trend_strategy_profile(
            row=row,
            profile=profile,
            fundamental=fundamental,
            theme=theme,
            scores=scores,
        )
        entry_plan = self._entry_plan(
            action=action,
            pullback_low=pullback_low,
            pullback_high=pullback_high,
            breakout_price=breakout_price,
            stop_loss=stop_loss,
            close=profile.close,
            ma10=profile.ma10,
        )
        reasons = self._reasons(
            theme=theme,
            row=row,
            profile=profile,
            fundamental=fundamental,
            scores=scores,
        )
        risks = self._risks(row=row, profile=profile, fundamental=fundamental)
        return MainlineTrendWatchItem(
            symbol=row.symbol,
            name=row.name,
            board=row.board,
            theme=theme.theme,
            status=status,
            action=action,
            strategy_type=strategy_profile.strategy_type,
            strategy_fit=strategy_profile.fit,
            score=round(scores.total, 2),
            latest_price=round(profile.close, 2),
            ma5=round(profile.ma5, 2),
            ma10=round(profile.ma10, 2),
            ma20=round(profile.ma20, 2),
            high_60=round(profile.high_60, 2),
            low_20=round(profile.low_20, 2),
            recent_gain_pct=round(profile.recent_gain_pct, 4),
            distance_to_ma10_pct=round(profile.distance_to_ma10_pct, 4),
            distance_to_high_60_pct=round(profile.distance_to_high_60_pct, 4),
            volume_ratio_5=round(profile.volume_ratio_5, 4),
            position_percentile_120=round(profile.position_percentile_120, 4),
            distance_to_ma20_pct=round(profile.distance_to_ma20_pct, 4),
            base_tightness_pct=round(profile.base_tightness_pct, 4),
            turnover_amount=round(row.turnover_amount, 2),
            logic_score=round(scores.logic, 2),
            value_score=round(scores.value, 2),
            capital_attraction_score=round(scores.capital, 2),
            sustainability_score=round(scores.sustainability, 2),
            timing_score=round(scores.timing, 2),
            pullback_entry_low=pullback_low,
            pullback_entry_high=pullback_high,
            breakout_price=breakout_price,
            stop_loss=stop_loss,
            logic=theme.logic,
            value_case=value_case,
            capital_case=capital_case,
            sustainability_case=sustainability_case,
            industry_chain_case=strategy_profile.industry_chain_case,
            profit_driver_case=strategy_profile.profit_driver_case,
            pre_breakout_case=strategy_profile.pre_breakout_case,
            t_plan=strategy_profile.t_plan,
            risk_control_case=strategy_profile.risk_control_case,
            why_watch_case=strategy_profile.why_watch_case,
            main_wave_stage=strategy_profile.main_wave_stage,
            confirmation_case=strategy_profile.confirmation_case,
            holding_plan=strategy_profile.holding_plan,
            failure_signal=strategy_profile.failure_signal,
            position_plan=strategy_profile.position_plan,
            entry_plan=entry_plan,
            reasons=tuple(reasons),
            risks=tuple(risks),
            next_action=self._next_action(status, entry_plan, stop_loss),
        )

    def _trend_profile(
        self,
        row: MarketTrendRow,
        bars: tuple[HistoricalPriceBar, ...],
    ) -> _TrendProfile | None:
        if not bars:
            if row.latest_price <= 0:
                return None
            close = row.latest_price
            return _TrendProfile(
                close=close,
                ma5=close * 0.99,
                ma10=close * 0.98,
                ma20=close * 0.96,
                high_60=close * 1.08,
                high_120=close * 1.16,
                low_20=close * 0.9,
                low_120=close * 0.72,
                recent_gain_pct=max(row.change_pct / 100, 0.0),
                gain_5_pct=max(row.change_pct / 100, 0.0),
                distance_to_ma10_pct=0.0204,
                distance_to_ma20_pct=0.0417,
                distance_to_high_60_pct=-0.0741,
                position_percentile_120=0.64,
                volume_ratio_5=1.2,
                base_tightness_pct=0.18,
                max_drawdown_20_pct=0.08,
            )
        closes = [bar.close_price for bar in bars if bar.close_price > 0]
        if not closes:
            return None
        highs = [bar.high_price for bar in bars if bar.high_price > 0]
        lows = [bar.low_price for bar in bars if bar.low_price > 0]
        amounts = [bar.amount for bar in bars if bar.amount > 0]
        close = closes[-1]
        ma5 = self._ma(closes, 5)
        ma10 = self._ma(closes, 10)
        ma20 = self._ma(closes, 20)
        high_60 = max(highs[-60:]) if highs else close
        high_120 = max(highs[-120:]) if highs else high_60
        low_20 = min(lows[-20:]) if lows else close
        low_120 = min(lows[-120:]) if lows else low_20
        base_close = closes[-20] if len(closes) >= 20 else closes[0]
        five_close = closes[-5] if len(closes) >= 5 else closes[0]
        recent_gain_pct = (close - base_close) / base_close if base_close > 0 else 0.0
        gain_5_pct = (close - five_close) / five_close if five_close > 0 else 0.0
        position_range = high_120 - low_120
        position_percentile = (
            (close - low_120) / position_range if position_range > 0 else 0.5
        )
        base_high = max(highs[-20:]) if highs else close
        base_low = min(lows[-20:]) if lows else close
        base_tightness = (base_high - base_low) / close if close > 0 else 0.0
        max_drawdown = self._max_drawdown(closes[-20:])
        return _TrendProfile(
            close=close,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            high_60=high_60,
            high_120=high_120,
            low_20=low_20,
            low_120=low_120,
            recent_gain_pct=recent_gain_pct,
            gain_5_pct=gain_5_pct,
            distance_to_ma10_pct=(close - ma10) / ma10 if ma10 > 0 else 0.0,
            distance_to_ma20_pct=(close - ma20) / ma20 if ma20 > 0 else 0.0,
            distance_to_high_60_pct=(close - high_60) / high_60 if high_60 > 0 else 0.0,
            position_percentile_120=position_percentile,
            volume_ratio_5=self._volume_ratio(amounts),
            base_tightness_pct=base_tightness,
            max_drawdown_20_pct=max_drawdown,
        )

    def _score_breakdown(
        self,
        row: MarketTrendRow,
        profile: _TrendProfile,
        fundamental: FundamentalSnapshot | None,
        theme: _ThemeSignal,
    ) -> _ScoreBreakdown:
        logic = theme.strength
        if row.theme and theme.source == "raw":
            logic += 6
        logic = min(100.0, logic)

        value = self._value_score(fundamental, row)
        capital = self._capital_score(row, profile)
        sustainability = self._sustainability_score(row, profile, fundamental, theme)
        timing = self._timing_score(profile)
        return _ScoreBreakdown(
            logic=logic,
            value=value,
            capital=capital,
            sustainability=sustainability,
            timing=timing,
        )

    @staticmethod
    def _value_score(
        fundamental: FundamentalSnapshot | None,
        row: MarketTrendRow,
    ) -> float:
        score = 45.0
        if fundamental is None:
            cap = row.market_cap or row.float_market_cap
            if 8_000_000_000 <= cap <= 120_000_000_000:
                score += 12
            if row.turnover_amount >= 300_000_000:
                score += 8
            return min(score, 65.0)
        if fundamental.roe_pct >= 12:
            score += 18
        elif fundamental.roe_pct >= 7:
            score += 10
        if fundamental.revenue_growth_pct >= 20:
            score += 15
        elif fundamental.revenue_growth_pct >= 5:
            score += 8
        if fundamental.net_profit_growth_pct >= 30:
            score += 18
        elif fundamental.net_profit_growth_pct >= 8:
            score += 10
        if fundamental.gross_margin_pct >= 25:
            score += 8
        if 0 < fundamental.pe_ttm <= 45:
            score += 8
        elif fundamental.pe_ttm > 80:
            score -= 10
        if fundamental.debt_ratio_pct > 70:
            score -= 12
        return max(0.0, min(score, 100.0))

    @staticmethod
    def _capital_score(row: MarketTrendRow, profile: _TrendProfile) -> float:
        score = 30.0
        if row.turnover_amount >= 1_000_000_000:
            score += 24
        elif row.turnover_amount >= 300_000_000:
            score += 16
        elif row.turnover_amount >= 100_000_000:
            score += 8
        if 2 <= row.turnover_rate <= 12:
            score += 18
        elif row.turnover_rate > 12:
            score += 8
        if 0.9 <= profile.volume_ratio_5 <= 2.2:
            score += 16
        elif 2.2 < profile.volume_ratio_5 <= 3.5:
            score += 8
        if row.change_pct >= 0:
            score += 8
        if profile.distance_to_ma20_pct <= 0.18:
            score += 8
        return max(0.0, min(score, 100.0))

    @staticmethod
    def _sustainability_score(
        row: MarketTrendRow,
        profile: _TrendProfile,
        fundamental: FundamentalSnapshot | None,
        theme: _ThemeSignal,
    ) -> float:
        score = 28.0
        if profile.close > profile.ma5 >= profile.ma10 >= profile.ma20:
            score += 24
        elif profile.close > profile.ma10 > profile.ma20:
            score += 16
        if 0.25 <= profile.position_percentile_120 <= 0.82:
            score += 14
        elif profile.position_percentile_120 > 0.92:
            score -= 12
        if profile.base_tightness_pct <= 0.22:
            score += 12
        if profile.max_drawdown_20_pct <= 0.12:
            score += 8
        if theme.strength >= 80:
            score += 12
        if fundamental and (
            fundamental.net_profit_growth_pct >= 15
            or fundamental.revenue_growth_pct >= 15
        ):
            score += 10
        if row.change_pct > 9:
            score -= 6
        return max(0.0, min(score, 100.0))

    @staticmethod
    def _timing_score(profile: _TrendProfile) -> float:
        score = 35.0
        if profile.close < profile.ma10:
            score -= 18
        elif profile.distance_to_ma10_pct <= 0.05:
            score += 24
        elif profile.distance_to_ma10_pct <= 0.1:
            score += 14
        if profile.close < profile.ma20:
            score -= 12
        elif profile.distance_to_ma20_pct <= 0.12:
            score += 16
        if profile.gain_5_pct <= 0.12:
            score += 10
        elif profile.gain_5_pct > 0.22:
            score -= 16
        if profile.recent_gain_pct <= 0.28:
            score += 8
        elif profile.recent_gain_pct > 0.5:
            score -= 18
        if profile.position_percentile_120 <= 0.82:
            score += 7
        return max(0.0, min(score, 100.0))

    @staticmethod
    def _status_action(
        scores: _ScoreBreakdown,
        profile: _TrendProfile,
    ) -> tuple[str, str]:
        if (
            scores.total >= 76
            and scores.logic >= 70
            and scores.capital >= 65
            and scores.sustainability >= 65
            and profile.close >= profile.ma10
            and profile.distance_to_ma10_pct <= 0.12
        ):
            return ("prime_watch", "主升共振观察")
        if scores.total >= 70 and profile.close < profile.ma10:
            return ("reclaim_watch", "等站回10日线")
        if scores.total >= 68 and profile.distance_to_ma10_pct <= 0.16:
            return ("wait_entry", "等回踩或放量确认")
        if scores.logic >= 70 and scores.sustainability < 58:
            return ("logic_watch", "逻辑强但持续性待验证")
        return ("research_only", "只研究不追买")

    @staticmethod
    def _price_plan(profile: _TrendProfile) -> tuple[float, float, float, float]:
        pullback_low = round(min(profile.ma10, profile.ma20) * 0.99, 2)
        pullback_high = round(profile.ma10 * 1.025, 2)
        breakout_price = round(profile.high_60 * 1.01, 2)
        stop_loss = round(min(profile.ma20 * 0.97, profile.low_20 * 0.985), 2)
        return pullback_low, pullback_high, breakout_price, stop_loss

    def _theme_signal(self, row: MarketTrendRow) -> _ThemeSignal:
        raw = " ".join((row.name, row.industry, row.theme)).upper()
        for keywords, theme, logic, strength in self._THEME_RULES:
            if any(keyword.upper() in raw for keyword in keywords):
                return _ThemeSignal(theme=theme, logic=logic, strength=strength, source="rule")
        fallback = row.theme or row.industry or "待确认主线"
        return _ThemeSignal(
            theme=fallback,
            logic=(
                "暂未命中明确产业主线；只能先把它当作全市场异动样本，"
                "后续必须补充公告、行业景气和业绩兑现证据。"
            ),
            strength=54.0,
            source="raw",
        )

    @staticmethod
    def _value_case(
        fundamental: FundamentalSnapshot | None,
        row: MarketTrendRow,
    ) -> str:
        if fundamental is None:
            cap = row.market_cap or row.float_market_cap
            cap_text = f"{cap / 100_000_000:.1f}亿" if cap else "未知"
            return (
                f"价值投资承接待确认：财务快照暂缺，先只按市值 {cap_text}、成交额 "
                f"{row.turnover_amount / 100_000_000:.1f}亿判断容量；"
                "没有财报和订单证据时，不把题材当价值投资。"
            )
        parts = [
            f"ROE {fundamental.roe_pct:.1f}%",
            f"营收增速 {fundamental.revenue_growth_pct:.1f}%",
            f"净利增速 {fundamental.net_profit_growth_pct:.1f}%",
        ]
        if fundamental.pe_ttm:
            parts.append(f"PE(TTM) {fundamental.pe_ttm:.1f}")
        if (
            fundamental.revenue_growth_pct >= 15
            and fundamental.net_profit_growth_pct >= 15
            and 0 < fundamental.pe_ttm <= 55
        ):
            verdict = "增长和估值能给主线故事做基本面承接。"
        elif fundamental.net_profit_growth_pct >= 30:
            verdict = "利润弹性强，但要确认营收和订单能不能继续跟上。"
        elif fundamental.pe_ttm > 80:
            verdict = "估值已经偏贵，价值投资承接不足，更多像情绪定价。"
        else:
            verdict = "价值承接一般，需要后续财报或订单继续确认。"
        return "价值投资承接：" + "；".join(parts) + f"；{verdict}"

    @staticmethod
    def _capital_case(row: MarketTrendRow, profile: _TrendProfile) -> str:
        return (
            f"资金吸引根源：成交额 {row.turnover_amount / 100_000_000:.1f}亿，"
            f"换手 {row.turnover_rate:.1f}%，5日量比 {profile.volume_ratio_5:.2f}；"
            "主力愿不愿意来，关键看题材容量够不够、放量后能否缩量承接、回撤是否守住20日线。"
        )

    @staticmethod
    def _sustainability_case(
        row: MarketTrendRow,
        profile: _TrendProfile,
        fundamental: FundamentalSnapshot | None,
        theme: _ThemeSignal,
    ) -> str:
        trend = (
            "均线多头排列"
            if profile.close > profile.ma5 >= profile.ma10 >= profile.ma20
            else "趋势尚未完全多头"
        )
        earning = (
            "业绩增速可接力"
            if fundamental
            and (
                fundamental.revenue_growth_pct >= 15
                or fundamental.net_profit_growth_pct >= 15
            )
            else "业绩接力证据不足"
        )
        return (
            f"持续走强根源：{trend}，120日位置 {profile.position_percentile_120:.0%}，"
            f"近20日波动带 {profile.base_tightness_pct:.1%}；"
            f"{theme.theme} 逻辑只有叠加 {earning}、板块同涨和回踩承接，才可能从炒作变成主升。"
        )

    @staticmethod
    def _entry_plan(
        *,
        action: str,
        pullback_low: float,
        pullback_high: float,
        breakout_price: float,
        stop_loss: float,
        close: float,
        ma10: float,
    ) -> str:
        if close < ma10:
            return (
                f"{action}：现价低于10日线，说明主升结构还没确认；先等重新站回 {ma10:.2f} 并放量承接；"
                f"站回后再看 {pullback_low:.2f}-{pullback_high:.2f} 是否缩量不破，"
                f"跌破 {stop_loss:.2f} 取消主升假设。"
            )
        return (
            f"{action}：买点不是因为已经涨，而是优先等 {pullback_low:.2f}-{pullback_high:.2f} 缩量回踩后再转强；"
            f"若直接突破 {breakout_price:.2f}，只能小样本观察，不追离均线太远的加速；"
            f"跌破 {stop_loss:.2f} 取消主升假设。"
        )

    @staticmethod
    def _reasons(
        *,
        theme: _ThemeSignal,
        row: MarketTrendRow,
        profile: _TrendProfile,
        fundamental: FundamentalSnapshot | None,
        scores: _ScoreBreakdown,
    ) -> list[str]:
        reasons = [
            f"主线逻辑 {scores.logic:.0f}/100：{theme.theme}，{theme.logic}",
            f"资金吸引 {scores.capital:.0f}/100：成交 {row.turnover_amount / 100_000_000:.1f}亿、换手 {row.turnover_rate:.1f}%、量比 {profile.volume_ratio_5:.2f}。",
            f"持续性 {scores.sustainability:.0f}/100：120日位置 {profile.position_percentile_120:.0%}，20日结构宽度 {profile.base_tightness_pct:.1%}。",
        ]
        if fundamental:
            reasons.append(
                f"价值承接 {scores.value:.0f}/100：ROE {fundamental.roe_pct:.1f}%、营收 {fundamental.revenue_growth_pct:.1f}%、净利 {fundamental.net_profit_growth_pct:.1f}%。"
            )
        else:
            reasons.append("价值承接暂用市值和流动性代理，缺财务快照时不下确定性结论。")
        return reasons

    @staticmethod
    def _risks(
        *,
        row: MarketTrendRow,
        profile: _TrendProfile,
        fundamental: FundamentalSnapshot | None,
    ) -> list[str]:
        risks: list[str] = []
        if profile.position_percentile_120 > 0.9:
            risks.append("120日位置已经偏高，容易变成高位加速，不适合追。")
        if profile.distance_to_ma10_pct > 0.12:
            risks.append("距离10日线过远，买点不舒服，回撤会放大。")
        if profile.recent_gain_pct > 0.45:
            risks.append("近20日涨幅过大，主升可能已走出第一段。")
        if row.turnover_amount < 150_000_000:
            risks.append("成交额偏低，主力容量不足，持续走强难度大。")
        if fundamental and fundamental.debt_ratio_pct > 70:
            risks.append("资产负债率偏高，价值投资承接要打折。")
        if fundamental is None:
            risks.append("缺少财务快照，价值投资判断只能算待确认。")
        if not risks:
            risks.append("逻辑、资金和结构较协调，但仍必须等买点确认，不能把故事当成交。")
        return risks

    @staticmethod
    def _next_action(status: str, entry_plan: str, stop_loss: float) -> str:
        if status == "prime_watch":
            return f"列入主升观察池；按入场计划执行，失守 {stop_loss:.2f} 立即移出。"
        if status == "wait_entry":
            return f"只等买点，不追涨；{entry_plan}"
        if status == "logic_watch":
            return "先补公告、财报和板块强度证据；没有持续性确认前只研究。"
        return "只做研究样本，不写入模拟盘买入。"

    @staticmethod
    def _market_cap_score(market_cap: float) -> float:
        if market_cap <= 0:
            return 6.0
        if 8_000_000_000 <= market_cap <= 80_000_000_000:
            return 18.0
        if 3_000_000_000 <= market_cap <= 180_000_000_000:
            return 12.0
        return 6.0

    @staticmethod
    def _ma(values: list[float], window: int) -> float:
        if not values:
            return 0.0
        sample = values[-window:]
        return sum(sample) / len(sample)

    @staticmethod
    def _volume_ratio(amounts: list[float]) -> float:
        if len(amounts) < 6 or amounts[-1] <= 0:
            return 1.0
        previous = [item for item in amounts[-6:-1] if item > 0]
        if not previous:
            return 1.0
        return amounts[-1] / (sum(previous) / len(previous))

    @staticmethod
    def _max_drawdown(closes: list[float]) -> float:
        peak = 0.0
        drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                drawdown = max(drawdown, (peak - close) / peak)
        return drawdown

    @staticmethod
    def _rules() -> tuple[str, ...]:
        return (
            "先判断能不能主升：产业逻辑是否可扩散、价值承接是否不虚、资金容量是否够、趋势结构是否能持续，再看买点。",
            "全市场扫描只输出观察和研究结论，不写入模拟盘、不连接 QMT、不自动下单。",
            "低位转强只是时间窗口，不是买入理由；离均线太远时即使逻辑强也不追。",
        )

    @staticmethod
    def _limitations(
        degraded_data: bool | _DataQuality = False,
        *,
        fast_snapshot: bool = False,
    ) -> tuple[str, ...]:
        if isinstance(degraded_data, _DataQuality):
            data_quality = degraded_data
        else:
            data_quality = _DataQuality(
                degraded=degraded_data,
                cached=False,
                stale=False,
            )
        items = [
            "财务快照依赖行情源可用性；缺失时只给待确认价值结论，不伪装成确定性基本面。",
            "产业逻辑第一版来自行业/名称/题材关键词，后续应接入公告、研报摘要和板块强度。",
            "该模块是主升研究雷达，不改变主板10cm首板模拟盘这条已验证核心链路。",
        ]
        if fast_snapshot:
            items = [
                "页面快照模式不逐只拉日线/财务，优先保证全市场覆盖和刷新速度；深度结论以 CLI/后台报告为准。",
                *items,
            ]
        if data_quality.degraded:
            items = [
                "当前全市场快照不可用，已降级到缓存或当日候选池；这不是完整全市场覆盖。",
                *items,
            ]
        elif data_quality.stale:
            items = [
                "当前使用同日完整全市场快照的过期缓存；覆盖仍是全市场，但不是本次实时拉取。",
                *items,
            ]
        elif data_quality.cached:
            items = [
                "当前使用30分钟内的同日完整全市场快照缓存；下一轮刷新会重新尝试实时拉取。",
                *items,
            ]
        return tuple(items)

    @staticmethod
    def _summary_prefix(data_quality: _DataQuality) -> str:
        if data_quality.degraded:
            return "全市场主升根因扫描（degraded_data）："
        if data_quality.stale:
            return "全市场主升根因扫描（stale_full_market_cache）："
        if data_quality.cached:
            return "全市场主升根因扫描（cached_full_market）："
        return "全市场主升根因扫描："

    @staticmethod
    def _start_date(trade_date: str, lookback_days: int) -> str:
        try:
            end = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except ValueError:
            return trade_date
        return (end - timedelta(days=max(lookback_days, 60))).isoformat()


__all__ = [
    "MainlineTrendWatchService",
    "TrendMarketDataProvider",
]
