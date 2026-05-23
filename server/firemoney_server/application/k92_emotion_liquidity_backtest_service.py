"""Point-in-time backtest for the K92 emotion-liquidity research system."""

from __future__ import annotations

from shared.contracts import (
    LimitUpBoardShadowSystemMetric,
    PaperBacktestMonthlyMetric,
    PaperBacktestMonthlyStability,
    PaperBacktestReport,
    PaperBacktestYearlyMetric,
)
from tools import research_limit_up_board_profit_matrix as board_matrix


class K92EmotionLiquidityBacktestService:
    """Build a read-only backtest report without touching paper trading state."""

    def build_report(
        self,
        *,
        start_date: str,
        end_date: str,
        candidates: list[board_matrix.BoardCandidate],
        histories: dict[str, list[board_matrix.sm.DailyBar]],
        position_pct: float = 0.08,
        roundtrip_cost_pct: float = 0.0015,
    ) -> PaperBacktestReport:
        start = board_matrix.sm.parse_iso_date(start_date)
        end = board_matrix.sm.parse_iso_date(end_date)
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        entry_case = self._entry_case()
        exit_case = board_matrix.shadow_default_exit_case()
        filtered = [
            item
            for item in candidates
            if start <= board_matrix.sm.parse_iso_date(item.board_date) <= end
            and board_matrix.entry_case_allows(entry_case, item)
            and self._emotion_liquidity_allows(item)
        ]
        daily_candidates = board_matrix.select_daily_top_candidates(filtered, "score")
        result = board_matrix.evaluate_preselected(
            daily_candidates=daily_candidates,
            histories=histories,
            entry_case=entry_case,
            exit_case=exit_case,
            rank_case="score",
            position_pct=position_pct,
            roundtrip_cost_pct=roundtrip_cost_pct,
        )
        overall = self._metric("K92 情绪流动性全区间", result["suggested_position_summary"])
        train = self._metric(
            f"训练段至 {board_matrix.TRAIN_END_DATE}",
            result["suggested_position_train_summary"],
        )
        validation = self._metric(
            f"验证段 {board_matrix.TRAIN_END_DATE} 后",
            result["suggested_position_validation_summary"],
        )
        raw_yearly = result.get("suggested_position_yearly", {})
        yearly = tuple(
            self._yearly_metric(str(year), raw_yearly.get(str(year), {}))
            for year in range(start.year, end.year + 1)
        )
        negative_years = tuple(
            item.year
            for item in yearly
            if item.sample_count > 0 and item.position_weighted_return_pct <= 0
        )
        weak_years = tuple(
            item.year
            for item in yearly
            if item.status in {"warning", "blocked", "no_sample"}
        )
        status = self._status(overall, train, validation, yearly)
        monthly = self._monthly_metrics(result["one_position_trades"])
        monthly_stability = self._monthly_stability(result["one_position_trades"])
        coverage_start, coverage_end = self._data_coverage(histories)
        summary = self._summary(
            status=status,
            overall=overall,
            yearly=yearly,
            negative_years=negative_years,
            weak_years=weak_years,
        )
        return PaperBacktestReport(
            report_id=f"k92-backtest-{start_date}-to-{end_date}",
            start_date=start_date,
            end_date=end_date,
            status=status,
            strategy_id="k92-emotion-liquidity-v1",
            summary=summary,
            overall=overall,
            train=train,
            validation=validation,
            yearly=yearly,
            negative_years=negative_years,
            weak_years=weak_years,
            buy_rule_summary=(
                "只使用封板当日可见字段做候选筛选和排序，不读取后续走势。",
                "基础过滤：主板 10cm 非一字封板、50-800 亿市值、热度 20-150、20 日涨幅不超过 20%、量比不低于 1.0、均线多头。",
                "情绪过滤：强情绪高位龙头、低位补涨、题材切换观察三类才允许进入回测；中位跟风和弱市样本剔除。",
                "卖点暂复用主线低回撤纪律：6% 止损、普通 5.5% 止盈、强情绪 8% 止盈、最多持有 1 个交易日。",
            ),
            improvement_notes=self._improvement_notes(
                status=status,
                negative_years=negative_years,
                weak_years=weak_years,
            ),
            no_future_leakage_notes=(
                "买点筛选、情绪分组和每日排序只用 board-day 可见字段。",
                "未来日线只在成交后用于止损、止盈、持有天数和收益统计。",
                "逐年和逐月报告强制展示，不允许用总收益掩盖弱年或亏损月。",
            ),
            limitations=(
                "K92 v1 是日线近似，无法还原盘中分歧转一致、席位结构、炸板回封和真实排队成交。",
                "历史缓存若缺失市值字段，只能在有市值时执行 50-800 亿过滤；报告不能假装知道缺失市值。",
                "这是研究影子回测，不等于收益保证；未通过稳定性验证前不能写入模拟盘。",
            ),
            next_action=(
                "若 status 不是 ready，K92 继续留在研究层；若分年、月度和回撤全部通过，"
                "下一步也只允许先并入主线守门，而不是直接扩大开仓入口。"
            ),
            data_coverage_start=coverage_start,
            data_coverage_end=coverage_end,
            monthly_stability=monthly_stability,
            monthly=monthly,
        )

    def _entry_case(self) -> board_matrix.EntryCase:
        return board_matrix.EntryCase(
            case_id="k92_emotion_liquidity_v1_heat20_150_gain20_ma_cap50_800",
            require_first_board=False,
            min_turnover_amount=80_000_000.0,
            max_recent_gain_pct=0.20,
            max_ma20_deviation_pct=0.35,
            min_volume_ratio_20=1.0,
            require_ma_bullish=True,
            min_position_percentile_60=0.45,
            min_market_seal_count=20,
            max_market_seal_count=150,
            min_market_cap=5_000_000_000.0,
            max_market_cap=80_000_000_000.0,
        )

    def _emotion_liquidity_allows(self, candidate: board_matrix.BoardCandidate) -> bool:
        leader_attack = (
            candidate.market_advance_ratio >= 0.70
            and candidate.position_percentile_60 >= 0.68
            and candidate.recent_gain_pct <= 0.20
        )
        low_level_supplement = (
            0.55 <= candidate.market_advance_ratio < 0.75
            and 0.45 <= candidate.position_percentile_60 < 0.68
        )
        theme_switch = (
            0.60 <= candidate.market_advance_ratio < 0.80
            and 0.45 <= candidate.position_percentile_60 <= 0.85
            and candidate.volume_ratio_20 >= 1.3
        )
        return leader_attack or low_level_supplement or theme_switch

    def _metric(
        self,
        label: str,
        summary: dict[str, object],
    ) -> LimitUpBoardShadowSystemMetric:
        return LimitUpBoardShadowSystemMetric(
            label=label,
            sample_count=int(summary.get("sample_count") or 0),
            win_rate=float(summary.get("win_rate") or 0.0),
            position_weighted_return_pct=float(
                summary.get("position_weighted_return_pct") or 0.0
            ),
            max_drawdown_pct=float(summary.get("max_drawdown_pct") or 0.0),
        )

    def _yearly_metric(
        self,
        year: str,
        summary: dict[str, object],
    ) -> PaperBacktestYearlyMetric:
        sample_count = int(summary.get("sample_count") or 0)
        win_rate = float(summary.get("win_rate") or 0.0)
        average_return_pct = float(summary.get("average_net_return_pct") or 0.0)
        median_return_pct = float(summary.get("median_net_return_pct") or 0.0)
        position_return = float(summary.get("position_weighted_return_pct") or 0.0)
        max_drawdown = float(summary.get("max_drawdown_pct") or 0.0)
        if sample_count <= 0:
            status = "no_sample"
            conclusion = "样本不足，不能证明当年盈利"
        elif position_return <= 0:
            status = "blocked"
            conclusion = "年度亏损，不能进入默认模拟盘"
        elif win_rate < 0.45 or max_drawdown < -0.08:
            status = "warning"
            conclusion = "年度正收益，但胜率或回撤质量偏弱"
        else:
            status = "ready"
            conclusion = "年度正收益且回撤受控"
        return PaperBacktestYearlyMetric(
            year=year,
            sample_count=sample_count,
            win_rate=win_rate,
            average_return_pct=average_return_pct,
            median_return_pct=median_return_pct,
            position_weighted_return_pct=position_return,
            max_drawdown_pct=max_drawdown,
            status=status,
            conclusion=conclusion,
        )

    def _status(
        self,
        overall: LimitUpBoardShadowSystemMetric,
        train: LimitUpBoardShadowSystemMetric,
        validation: LimitUpBoardShadowSystemMetric,
        yearly: tuple[PaperBacktestYearlyMetric, ...],
    ) -> str:
        traded_years = [item for item in yearly if item.sample_count > 0]
        if (
            overall.sample_count < 80
            or overall.position_weighted_return_pct <= 0
            or train.position_weighted_return_pct <= 0
            or validation.position_weighted_return_pct <= 0
        ):
            return "blocked"
        if any(item.status == "blocked" for item in traded_years):
            return "blocked"
        if any(item.status in {"warning", "no_sample"} for item in yearly):
            return "warning"
        return "ready"

    def _summary(
        self,
        *,
        status: str,
        overall: LimitUpBoardShadowSystemMetric,
        yearly: tuple[PaperBacktestYearlyMetric, ...],
        negative_years: tuple[str, ...],
        weak_years: tuple[str, ...],
    ) -> str:
        traded_years = [item for item in yearly if item.sample_count > 0]
        positive_year_count = sum(
            1 for item in traded_years if item.position_weighted_return_pct > 0
        )
        verdict = (
            "K92 影子回测通过"
            if status == "ready"
            else "K92 影子回测未通过"
            if status == "blocked"
            else "K92 影子回测存在弱点"
        )
        negative_text = (
            "无亏损年份"
            if not negative_years
            else f"亏损年份：{'、'.join(negative_years)}"
        )
        weak_text = "无明显弱年" if not weak_years else f"弱年份：{'、'.join(weak_years)}"
        return (
            f"{verdict}：样本 {overall.sample_count}，仓位复合收益 "
            f"{overall.position_weighted_return_pct:.2%}，最大回撤 "
            f"{overall.max_drawdown_pct:.2%}；{positive_year_count}/"
            f"{len(traded_years)} 个有样本年份为正收益，{negative_text}，{weak_text}。"
        )

    def _improvement_notes(
        self,
        *,
        status: str,
        negative_years: tuple[str, ...],
        weak_years: tuple[str, ...],
    ) -> tuple[str, ...]:
        notes = [
            "K92 v1 先验证情绪流动性状态本身是否有收益质量，不直接扩大开仓入口。",
            "升级默认主线的最低条件：弱年份不变差、最大回撤不变大、验证段不明显变弱。",
        ]
        if negative_years:
            notes.append(f"{'、'.join(negative_years)} 出现年度亏损，K92 暂不允许进模拟盘。")
        if weak_years:
            notes.append(f"{'、'.join(weak_years)} 是弱年份/无样本年份，必须继续收紧情绪或流动性门槛。")
        if status == "ready":
            notes.append("K92 影子验证暂时通过，但仍需先小流量影子观察，不能直接实盘化。")
        return tuple(notes)

    def _monthly_stability(
        self,
        trades: list[object],
    ) -> PaperBacktestMonthlyStability | None:
        month_returns = self._month_returns(trades)
        if not month_returns:
            return None
        positive_months = sum(1 for _, value in month_returns if value >= 0)
        worst_month, worst_return = min(month_returns, key=lambda item: item[1])
        longest_losing_streak = 0
        current_streak = 0
        for _, value in month_returns:
            if value < 0:
                current_streak += 1
                longest_losing_streak = max(longest_losing_streak, current_streak)
            else:
                current_streak = 0
        positive_ratio = round(positive_months / max(1, len(month_returns)), 4)
        conclusion = (
            f"月度正收益占比 {positive_ratio:.2%}，最差月份 {worst_month} "
            f"{worst_return:.2%}，最长连续亏损月 {longest_losing_streak}。"
        )
        return PaperBacktestMonthlyStability(
            total_months=len(month_returns),
            positive_months=positive_months,
            positive_month_ratio=positive_ratio,
            worst_month=worst_month,
            worst_month_return_pct=worst_return,
            longest_losing_streak=longest_losing_streak,
            conclusion=conclusion,
        )

    def _monthly_metrics(
        self,
        trades: list[object],
    ) -> tuple[PaperBacktestMonthlyMetric, ...]:
        result: list[PaperBacktestMonthlyMetric] = []
        for month, month_return in self._month_returns(trades):
            if month_return > 0:
                status = "ready"
                conclusion = "月度正收益"
            elif month_return > -0.02:
                status = "warning"
                conclusion = "月度小幅回撤"
            else:
                status = "blocked"
                conclusion = "月度回撤偏大，需要复盘"
            result.append(
                PaperBacktestMonthlyMetric(
                    month=month,
                    position_weighted_return_pct=month_return,
                    status=status,
                    conclusion=conclusion,
                )
            )
        return tuple(result)

    def _month_returns(self, trades: list[object]) -> list[tuple[str, float]]:
        by_month: dict[str, list[float]] = {}
        for trade in trades:
            if isinstance(trade, dict):
                entry_date = str(trade.get("entry_date", ""))
                net_return_pct = float(trade.get("net_return_pct", 0.0) or 0.0)
            else:
                entry_date = str(getattr(trade, "entry_date", ""))
                net_return_pct = float(getattr(trade, "net_return_pct", 0.0) or 0.0)
            if len(entry_date) >= 7:
                by_month.setdefault(entry_date[:7], []).append(net_return_pct)
        month_returns: list[tuple[str, float]] = []
        for month in sorted(by_month):
            equity = 1.0
            for value in by_month[month]:
                equity *= max(0.0, 1 + value * 0.08)
            month_returns.append((month, round(equity - 1, 4)))
        return month_returns

    def _data_coverage(
        self,
        histories: dict[str, list[object]],
    ) -> tuple[str, str]:
        first_dates: list[str] = []
        last_dates: list[str] = []
        for bars in histories.values():
            if not bars:
                continue
            first_dates.append(str(getattr(bars[0], "trade_date", "")))
            last_dates.append(str(getattr(bars[-1], "trade_date", "")))
        return (
            min(first_dates) if first_dates else "",
            max(last_dates) if last_dates else "",
        )


__all__ = ["K92EmotionLiquidityBacktestService"]
