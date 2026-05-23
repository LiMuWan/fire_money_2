"""Paper-backtest report orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable
import concurrent.futures
import json
import time
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from shared.contracts import (
    LimitUpBoardShadowSystemMetric,
    PaperBacktestEfficiencyCandidate,
    PaperBacktestFrictionScenario,
    PaperBacktestMonthlyMetric,
    PaperBacktestMonthlyStability,
    PaperBacktestReport,
    PaperBacktestReturnTarget,
    PaperBacktestYearlyMetric,
)
from server.firemoney_server.domain.paper_position_sizing import (
    simulate_small_account_trades,
    summarize_account_return_by_year,
    summarize_account_return_trades,
)
from tools import research_limit_up_board_profit_matrix as board_matrix
from tools import research_one_to_two_backtest as research_daily


class PaperBacktestService:
    """Builds yearly/monthly validation reports without touching live paper ledgers."""

    def __init__(self, *, default_trade_date: Callable[[], str], settings=None) -> None:
        self._default_trade_date = default_trade_date
        self._settings = settings

    def build_report(
        self,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
        refresh_cache: bool = False,
    ) -> PaperBacktestReport:
        end = end_date or self._default_trade_date()
        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        start_parsed = board_matrix.sm.parse_iso_date(start_date)
        end_parsed = board_matrix.sm.parse_iso_date(end)
        if end_parsed < start_parsed:
            raise ValueError("end_date must be on or after start_date")

        if refresh_cache:
            universe, histories, failed = self._refresh_research_cache_incremental(
                cache_path=cache_path,
                start=start_parsed,
                end=end_parsed,
            )
            minimum_count = getattr(board_matrix.sm, "MIN_COMPLETE_MAINBOARD_UNIVERSE", 2500)
            if failed and len(histories) < minimum_count:
                raise RuntimeError(
                    "research cache refresh failed before a complete universe was loaded: "
                    f"loaded={len(histories)} failed={len(failed)}"
                )
        else:
            universe, histories = board_matrix.load_cached_research_data(
                cache_path,
                start_parsed,
                end_parsed,
            )
        candidates = board_matrix.build_board_candidates(
            universe,
            histories,
            start_parsed,
            end_parsed,
        )
        result = board_matrix.evaluate_case(
            candidates=candidates,
            histories=histories,
            entry_case=board_matrix.shadow_default_entry_case(),
            exit_case=board_matrix.shadow_default_exit_case(),
            rank_case="score",
            position_pct=0.08,
            roundtrip_cost_pct=0.0015,
        )
        result = self._with_small_account_result(result)
        active_trades = self._active_trades(result)

        overall = self._to_board_shadow_system_metric(
            label="模拟盘买入算法全区间",
            summary=self._active_summary(result, "suggested_position_summary"),
        )
        train = self._to_board_shadow_system_metric(
            label=f"训练段至 {board_matrix.TRAIN_END_DATE}",
            summary=self._active_summary(result, "suggested_position_train_summary"),
        )
        validation = self._to_board_shadow_system_metric(
            label=f"验证段 {board_matrix.TRAIN_END_DATE} 后",
            summary=self._active_summary(result, "suggested_position_validation_summary"),
        )
        raw_yearly = self._active_yearly(result)
        yearly = tuple(
            self._to_paper_backtest_yearly_metric(
                str(year),
                raw_yearly.get(str(year), {}),
            )
            for year in range(start_parsed.year, end_parsed.year + 1)
        )
        data_coverage_start, data_coverage_end = self._paper_backtest_data_coverage(
            histories
        )
        data_coverage_notes = self._paper_backtest_data_coverage_notes(
            requested_start=start_date,
            requested_end=end,
            coverage_start=data_coverage_start,
            coverage_end=data_coverage_end,
            yearly=yearly,
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
        status = self._paper_backtest_status(overall, train, validation, yearly)
        friction_scenarios = self._paper_backtest_friction_scenarios(
            candidates=candidates,
            histories=histories,
            start_year=start_parsed.year,
            end_year=end_parsed.year,
        )
        return_target = self._paper_backtest_return_target(
            yearly=yearly,
            start_date=start_date,
            end_date=end,
        )
        monthly = self._paper_backtest_monthly_metrics(
            active_trades,
        )
        monthly_stability = self._paper_backtest_monthly_stability(
            active_trades,
        )
        current_month_notes = self._paper_backtest_current_month_notes(
            requested_end=end,
            coverage_end=data_coverage_end,
            monthly=monthly,
        )
        efficiency_candidates = self._paper_backtest_efficiency_candidates(
            candidates=candidates,
            histories=histories,
            baseline=result,
            start=start_parsed,
            end=end_parsed,
        )
        summary = self._paper_backtest_summary(
            status=status,
            overall=overall,
            yearly=yearly,
            negative_years=negative_years,
            weak_years=weak_years,
        )
        return PaperBacktestReport(
            report_id=f"paper-backtest-{start_date}-to-{end}",
            start_date=start_date,
            end_date=end,
            status=status,
            strategy_id="board-shadow-system",
            summary=summary,
            overall=overall,
            train=train,
            validation=validation,
            yearly=yearly,
            negative_years=negative_years,
            weak_years=weak_years,
            buy_rule_summary=(
                "主板 10cm 非一字封板作为买点来源，过滤创业板、科创板、北交所和 ST。",
                "买点排序只使用封板当日可见字段，并把近 20 日涨幅上限收紧到 20%，降低高位加速板回撤风险。",
                self._position_rule_summary(result),
                "卖点只在买入后用后续日线回放：普通 5.5% 均衡止盈，强市 8% 动态止盈，6% 止损，最多持有 1 个交易日。",
            ),
            improvement_notes=self._paper_backtest_improvement_notes(
                negative_years=negative_years,
                weak_years=weak_years,
                status=status,
                efficiency_challenger_note=(
                    efficiency_candidates[0].conclusion
                    if efficiency_candidates
                    else None
                ),
            ),
            no_future_leakage_notes=(
                "无未来函数约束：筛选和排序只读取买点当日之前或当日收盘可见字段，不读取未来涨跌。",
                "未来日线只用于成交后的卖点模拟、收益、胜率和回撤计算。",
                "逐年报告强制展示 2020 起每一年，避免用总收益掩盖弱年份。",
            ),
            limitations=(
                "日线回测无法证明真实排队成交、炸板时序、封单强弱和盘中滑点。",
                "当前验证是模拟盘买入算法的纪律证据，不等于保证每笔交易盈利。",
                "执行摩擦压力测试只把滑点/手续费按固定比例加入，不能替代封单排队和分时成交检查。",
                "若数据覆盖起点晚于请求起点，早期年份会标为样本不足，不能当成已验证盈利。",
                "若出现负收益年份，下一轮应针对该年份样本调买点守门，而不是盲目加仓。",
            ),
            next_action=(
                "先以 paper-backtest --start-date 2020-01-01 --brief 作为买入算法年度体检；"
                "若年度回撤或负收益暴露，再针对弱年份收紧市场宽度、换手质量和仓位。"
            ),
            data_coverage_start=data_coverage_start,
            data_coverage_end=data_coverage_end,
            data_coverage_notes=data_coverage_notes,
            friction_scenarios=friction_scenarios,
            return_target=return_target,
            efficiency_candidates=efficiency_candidates,
            monthly_stability=monthly_stability,
            monthly=monthly,
            current_month_notes=current_month_notes,
        )

    @staticmethod
    def _refresh_research_cache_incremental(
        *,
        cache_path: Path,
        start: date,
        end: date,
        workers: int = 12,
    ) -> tuple[list[research_daily.StockMeta], dict[str, list[research_daily.DailyBar]], list[str]]:
        """Refresh only missing recent daily bars instead of redownloading years."""

        cache_path.mkdir(parents=True, exist_ok=True)
        universe = PaperBacktestService._cached_research_universe(cache_path)
        minimum_count = getattr(research_daily, "MIN_COMPLETE_MAINBOARD_UNIVERSE", 2500)
        if len(universe) < minimum_count:
            universe = research_daily.load_mainboard_universe(
                cache_dir=cache_path,
                minimum_count=minimum_count,
            )

        histories: dict[str, list[research_daily.DailyBar]] = {}
        failed: list[str] = []
        lookback_start = start - timedelta(days=220)
        started_at = time.monotonic()
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(
                    PaperBacktestService._refresh_cached_history,
                    stock,
                    cache_path,
                    lookback_start,
                    end,
                ): stock
                for stock in universe
            }
            for future in concurrent.futures.as_completed(futures):
                stock = futures[future]
                completed += 1
                try:
                    bars = future.result()
                except Exception as exc:  # pragma: no cover - network dependent
                    failed.append(f"{stock.code}:{exc}")
                else:
                    if bars:
                        histories[stock.code] = bars
                    else:
                        failed.append(f"{stock.code}:empty")
                if completed % 200 == 0 or completed == len(universe):
                    elapsed = time.monotonic() - started_at
                    print(
                        "paper-backtest-cache "
                        f"progress={completed}/{len(universe)} "
                        f"loaded={len(histories)} failed={len(failed)} "
                        f"elapsed={elapsed:.1f}s",
                        flush=True,
                    )
        return universe, histories, failed

    @staticmethod
    def _cached_research_universe(cache_path: Path) -> list[research_daily.StockMeta]:
        universe: list[research_daily.StockMeta] = []
        for cache_file in sorted(cache_path.glob("*.json")):
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            code = research_daily.normalize_code(payload.get("symbol") or cache_file.stem)
            name = research_daily.normalize_name(payload.get("name")) or code
            if not research_daily.is_mainboard_code(code):
                continue
            if not name or research_daily.is_blocked_name(name):
                continue
            universe.append(
                research_daily.StockMeta(
                    code=code,
                    name=name,
                    listing_date=payload.get("listing_date"),
                )
            )
        return universe

    @staticmethod
    def _refresh_cached_history(
        stock: research_daily.StockMeta,
        cache_path: Path,
        lookback_start: date,
        end: date,
    ) -> list[research_daily.DailyBar]:
        cache_file = cache_path / f"{stock.code}.json"
        cached = PaperBacktestService._read_cached_daily_bars(cache_file)
        cached_dates = [research_daily.parse_iso_date(item.trade_date) for item in cached]
        if cached_dates and max(cached_dates) >= end:
            return PaperBacktestService._filter_daily_bars(cached, lookback_start, end)

        fetch_start = lookback_start
        if cached_dates:
            # Keep a short overlap so amended daily bars are corrected on refresh.
            fetch_start = max(lookback_start, max(cached_dates) - timedelta(days=5))
        fetched = research_daily.fetch_tencent_daily_bars(stock.code, fetch_start, end)
        merged = research_daily.deduplicate_bars((*cached, *fetched))
        merged = sorted(merged, key=lambda item: item.trade_date)
        payload = {
            "symbol": stock.code,
            "name": stock.name,
            "listing_date": stock.listing_date,
            "source": "tencent_newfqkline",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "start_date": min((item.trade_date for item in merged), default=lookback_start.isoformat()),
            "end_date": max((item.trade_date for item in merged), default=end.isoformat()),
            "rows": [asdict(item) for item in merged],
        }
        cache_file.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return PaperBacktestService._filter_daily_bars(merged, lookback_start, end)

    @staticmethod
    def _read_cached_daily_bars(cache_file: Path) -> list[research_daily.DailyBar]:
        if not cache_file.exists():
            return []
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            rows = payload.get("rows", [])
            return [research_daily.DailyBar(**row) for row in rows]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []

    @staticmethod
    def _filter_daily_bars(
        bars: list[research_daily.DailyBar],
        start: date,
        end: date,
    ) -> list[research_daily.DailyBar]:
        return [
            item
            for item in bars
            if start <= research_daily.parse_iso_date(item.trade_date) <= end
        ]

    @staticmethod
    def _to_board_shadow_system_metric(
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

    def _with_small_account_result(self, result: dict[str, object]) -> dict[str, object]:
        settings = self._settings
        if settings is None or not getattr(settings, "small_account_mode_enabled", False):
            return result
        raw_trades = list(result.get("one_position_trades", []))
        small_trades, skipped = simulate_small_account_trades(
            trades=raw_trades,
            initial_cash=float(settings.initial_cash),
            lot_shares=int(settings.small_account_min_lot_shares),
            target_position_pct=float(settings.small_account_target_position_pct),
            max_position_pct=float(settings.small_account_max_position_pct),
        )
        train_trades = [
            item
            for item in small_trades
            if item.entry_date <= board_matrix.TRAIN_END_DATE
        ]
        validation_trades = [
            item
            for item in small_trades
            if item.entry_date > board_matrix.TRAIN_END_DATE
        ]
        return result | {
            "small_account_enabled": True,
            "small_account_skipped_count": skipped,
            "small_account_trades": small_trades,
            "small_account_summary": summarize_account_return_trades(small_trades),
            "small_account_train_summary": summarize_account_return_trades(train_trades),
            "small_account_validation_summary": summarize_account_return_trades(
                validation_trades
            ),
            "small_account_yearly": summarize_account_return_by_year(small_trades),
        }

    @staticmethod
    def _active_summary(result: dict[str, object], fallback_key: str) -> dict[str, object]:
        small_key = {
            "suggested_position_summary": "small_account_summary",
            "suggested_position_train_summary": "small_account_train_summary",
            "suggested_position_validation_summary": "small_account_validation_summary",
        }.get(fallback_key)
        if small_key and result.get("small_account_enabled"):
            return result.get(small_key, {})  # type: ignore[return-value]
        return result.get(fallback_key, {})  # type: ignore[return-value]

    @staticmethod
    def _active_yearly(result: dict[str, object]) -> dict[str, object]:
        if result.get("small_account_enabled"):
            return result.get("small_account_yearly", {})  # type: ignore[return-value]
        return result.get("suggested_position_yearly", {})  # type: ignore[return-value]

    @staticmethod
    def _active_trades(result: dict[str, object]) -> list[object]:
        if result.get("small_account_enabled"):
            return list(result.get("small_account_trades", []))
        return list(result.get("one_position_trades", []))

    def _position_rule_summary(self, result: dict[str, object]) -> str:
        settings = self._settings
        if settings is None or not getattr(settings, "small_account_mode_enabled", False):
            return "每天最多选一只且不重叠持仓，动态仓位为常态 8%、强市 12%。"
        skipped = int(result.get("small_account_skipped_count") or 0)
        return (
            f"每天最多选一只且不重叠持仓；按 {settings.initial_cash:.0f} 元小账户、"
            f"{settings.small_account_min_lot_shares} 股一手回放，目标仓位 "
            f"{settings.small_account_target_position_pct:.0%}，单票硬上限 "
            f"{settings.small_account_max_position_pct:.0%}；一手成本超限跳过 "
            f"{skipped} 次。"
        )

    @staticmethod
    def _to_paper_backtest_yearly_metric(
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
            conclusion = "年度亏损，需要收紧买入守门或降低仓位"
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

    def _paper_backtest_friction_scenarios(
        self,
        *,
        candidates: list[board_matrix.BoardCandidate],
        histories: dict[str, list[board_matrix.sm.DailyBar]],
        start_year: int,
        end_year: int,
    ) -> tuple[PaperBacktestFrictionScenario, ...]:
        scenarios: list[PaperBacktestFrictionScenario] = []
        for label, cost in (
            ("baseline_cost_0.15pct", 0.0015),
            ("stress_cost_0.30pct", 0.0030),
            ("stress_cost_0.50pct", 0.0050),
            ("stress_cost_0.80pct", 0.0080),
            ("stress_cost_1.00pct", 0.0100),
        ):
            result = board_matrix.evaluate_case(
                candidates=candidates,
                histories=histories,
                entry_case=board_matrix.shadow_default_entry_case(),
                exit_case=board_matrix.shadow_default_exit_case(),
                rank_case="score",
                position_pct=0.08,
                roundtrip_cost_pct=cost,
            )
            result = self._with_small_account_result(result)
            summary = self._active_summary(result, "suggested_position_summary")
            validation = self._active_summary(
                result,
                "suggested_position_validation_summary",
            )
            yearly = self._active_yearly(result)
            year_returns = {
                str(year): float(
                    yearly.get(str(year), {}).get("position_weighted_return_pct") or 0.0
                )
                for year in range(start_year, end_year + 1)
            }
            negative_years = tuple(
                year for year, value in year_returns.items() if value <= 0
            )
            weakest_year, weakest_value = min(
                year_returns.items(),
                key=lambda item: item[1],
                default=("", 0.0),
            )
            status = "ready"
            if (
                not year_returns
                or float(summary.get("position_weighted_return_pct") or 0.0) <= 0
                or float(validation.get("position_weighted_return_pct") or 0.0) <= 0
                or negative_years
            ):
                status = "blocked"
            elif weakest_value < 0.03:
                status = "warning"
            conclusion = (
                "Friction stress passed; all tested years stay positive."
                if status == "ready"
                else "Friction stress is fragile; weakest year is close to zero."
                if status == "warning"
                else "Friction stress failed; tighten execution or reduce size."
            )
            scenarios.append(
                PaperBacktestFrictionScenario(
                    label=label,
                    roundtrip_cost_pct=cost,
                    sample_count=int(summary.get("sample_count") or 0),
                    win_rate=float(summary.get("win_rate") or 0.0),
                    position_weighted_return_pct=float(
                        summary.get("position_weighted_return_pct") or 0.0
                    ),
                    max_drawdown_pct=float(summary.get("max_drawdown_pct") or 0.0),
                    validation_return_pct=float(
                        validation.get("position_weighted_return_pct") or 0.0
                    ),
                    negative_years=negative_years,
                    weakest_year=weakest_year,
                    weakest_year_return_pct=weakest_value,
                    status=status,
                    conclusion=conclusion,
                )
            )
        return tuple(scenarios)

    @staticmethod
    def _paper_backtest_status(
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
            return "warning"
        if any(item.status in {"warning", "no_sample"} for item in yearly):
            return "warning"
        return "ready"

    @staticmethod
    def _paper_backtest_summary(
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
        if status == "ready":
            verdict = "年度验证通过"
        elif status == "blocked":
            verdict = "年度验证未通过"
        else:
            verdict = "年度验证有弱点"
        weak_text = "无明显弱年" if not weak_years else f"弱年份：{'、'.join(weak_years)}"
        negative_text = (
            "无亏损年份"
            if not negative_years
            else f"亏损年份：{'、'.join(negative_years)}"
        )
        return (
            f"{verdict}：模拟盘买入算法全区间样本 {overall.sample_count}，"
            f"仓位复合收益 {overall.position_weighted_return_pct:.2%}，"
            f"最大回撤 {overall.max_drawdown_pct:.2%}；"
            f"{positive_year_count}/{len(traded_years)} 个有样本年份为正收益，"
            f"{negative_text}，{weak_text}。"
        )

    @staticmethod
    def _paper_backtest_improvement_notes(
        *,
        negative_years: tuple[str, ...],
        weak_years: tuple[str, ...],
        status: str,
        efficiency_challenger_note: str | None,
    ) -> tuple[str, ...]:
        notes = [
            "本轮把算法验证口径从 2024 起扩展到 2020 起，并强制逐年展示收益、胜率和回撤。",
            "买入算法新增年度稳定性守门：负收益年份、低胜率年份、回撤偏大年份不能被总收益掩盖。",
        ]
        if negative_years:
            notes.append(
                f"{'、'.join(negative_years)} 出现年度亏损，下一轮优先检验更高市场宽度、换手质量和压力位距离门槛。"
            )
        if weak_years:
            notes.append(
                f"{'、'.join(weak_years)} 属于弱年份，模拟盘当天若环境接近这些年份特征，应降低仓位或跳过。"
            )
        if status == "ready":
            notes.append("当前年度体检未发现亏损年份，可继续小仓位模拟并用真实成交闭环校验。")
        if efficiency_challenger_note:
            notes.append(efficiency_challenger_note)
        return tuple(notes)

    @staticmethod
    def _paper_backtest_return_target(
        *,
        yearly: tuple[PaperBacktestYearlyMetric, ...],
        start_date: str,
        end_date: str,
    ) -> PaperBacktestReturnTarget | None:
        completed_years = tuple(
            item
            for item in yearly
            if item.sample_count > 0 and end_date[:4] > item.year
        )
        baseline_years = completed_years or tuple(
            item for item in yearly if item.sample_count > 0
        )
        if not baseline_years:
            return None
        weakest = min(
            baseline_years,
            key=lambda item: item.position_weighted_return_pct,
        )
        weakest_return = weakest.position_weighted_return_pct
        if weakest_return <= 0:
            return PaperBacktestReturnTarget(
                target_annual_return_pct=1.0,
                weakest_year=weakest.year,
                weakest_year_return_pct=weakest_return,
                required_linear_position_multiple=0.0,
                projected_max_drawdown_pct=0.0,
                conclusion=(
                    f"{weakest.year} 年仍未稳定盈利，不能把年化 100% 当成加仓目标；"
                    "应先修复弱年买点和回撤。"
                ),
            )
        required_multiple = round(1.0 / weakest_return, 2)
        projected_drawdown = round(
            abs(weakest.max_drawdown_pct) * required_multiple,
            4,
        )
        conclusion = (
            f"以 {weakest.year} 年 {weakest_return:.2%} 的最弱完整年度测算，若只靠线性放大仓位去冲"
            f" 100%，大约需要 {required_multiple:.2f} 倍风险暴露，"
            f"对应同尺度回撤约 {projected_drawdown:.2%}。"
        )
        if required_multiple > 2.0:
            conclusion += " 这已经超出当前稳定型仓位纪律，不建议直接靠加仓实现。"
        else:
            conclusion += " 仍应先确认执行摩擦、收益守门和弱年环境都同步改善。"
        return PaperBacktestReturnTarget(
            target_annual_return_pct=1.0,
            weakest_year=weakest.year,
            weakest_year_return_pct=weakest_return,
            required_linear_position_multiple=required_multiple,
            projected_max_drawdown_pct=projected_drawdown,
            conclusion=conclusion,
        )

    def _paper_backtest_efficiency_challenger(
        self,
        *,
        candidates: list[board_matrix.BoardCandidate],
        histories: dict[str, list[board_matrix.sm.DailyBar]],
        baseline: dict[str, object],
        start: date,
        end: date,
    ) -> PaperBacktestEfficiencyCandidate | None:
        challenger = board_matrix.evaluate_case(
            candidates=candidates,
            histories=histories,
            entry_case=board_matrix.EntryCase(
                case_id="shadow_efficiency_gain20_target65",
                require_first_board=False,
                min_turnover_amount=80_000_000.0,
                max_recent_gain_pct=0.20,
                max_ma20_deviation_pct=0.35,
                min_volume_ratio_20=1.0,
                require_ma_bullish=True,
                min_position_percentile_60=0.0,
                min_market_seal_count=20,
                max_market_seal_count=150,
            ),
            exit_case=board_matrix.ExitCase(
                case_id="shadow_efficiency_stop6_target6.5_or8_hold1",
                stop_loss_pct=0.06,
                take_profit_pct=0.065,
                max_hold_days=1,
                weak_next_open_exit_pct=None,
                strong_market_advance_ratio=0.70,
                strong_market_take_profit_pct=0.08,
            ),
            rank_case="score",
            position_pct=0.08,
            roundtrip_cost_pct=0.0015,
        )
        challenger = self._with_small_account_result(challenger)
        baseline_summary = self._active_summary(baseline, "suggested_position_summary")
        baseline_validation = self._active_summary(
            baseline,
            "suggested_position_validation_summary",
        )
        challenger_summary = self._active_summary(challenger, "suggested_position_summary")
        challenger_validation = self._active_summary(
            challenger,
            "suggested_position_validation_summary",
        )
        baseline_yearly = self._active_yearly(baseline)
        challenger_yearly = self._active_yearly(challenger)
        baseline_full_years = [
            float(baseline_yearly.get(str(year), {}).get("position_weighted_return_pct") or 0.0)
            for year in range(start.year, end.year)
        ]
        challenger_full_years = [
            float(challenger_yearly.get(str(year), {}).get("position_weighted_return_pct") or 0.0)
            for year in range(start.year, end.year)
        ]
        if not baseline_full_years or not challenger_full_years:
            return None
        baseline_worst = min(baseline_full_years)
        challenger_worst = min(challenger_full_years)
        baseline_return = float(baseline_summary.get("position_weighted_return_pct") or 0.0)
        challenger_return = float(challenger_summary.get("position_weighted_return_pct") or 0.0)
        baseline_dd = abs(float(baseline_summary.get("max_drawdown_pct") or 0.0))
        challenger_dd = abs(float(challenger_summary.get("max_drawdown_pct") or 0.0))
        baseline_validation_return = float(
            baseline_validation.get("position_weighted_return_pct") or 0.0
        )
        challenger_validation_return = float(
            challenger_validation.get("position_weighted_return_pct") or 0.0
        )
        if (
            challenger_return <= baseline_return
            or challenger_dd > baseline_dd + 0.0001
            or challenger_worst < baseline_worst - 0.01
            or challenger_validation_return < baseline_validation_return - 0.01
        ):
            return None
        challenger_monthly = PaperBacktestService._paper_backtest_monthly_stability(
            self._active_trades(challenger),
        )
        return PaperBacktestEfficiencyCandidate(
            label="6.5% 第一止盈",
            total_return_pct=challenger_return,
            max_drawdown_pct=-challenger_dd,
            validation_return_pct=challenger_validation_return,
            weakest_full_year_return_pct=challenger_worst,
            monthly_positive_ratio=(
                challenger_monthly.positive_month_ratio if challenger_monthly is not None else 0.0
            ),
            worst_month_return_pct=(
                challenger_monthly.worst_month_return_pct if challenger_monthly is not None else 0.0
            ),
            conclusion=(
                "同仓位高收益低回撤挑战者已出现：6.5% 第一止盈版本在 2020-2026 全区间收益 "
                f"{challenger_return:.2%}，高于当前主线 {baseline_return:.2%}；最大回撤仍为 "
                f"{challenger_dd:.2%}，最弱完整年度 {challenger_worst:.2%}，"
                f"验证段 {challenger_validation_return:.2%}。建议继续并行验证，不直接替换主线。"
            ),
        )

    def _paper_backtest_efficiency_candidates(
        self,
        *,
        candidates: list[board_matrix.BoardCandidate],
        histories: dict[str, list[board_matrix.sm.DailyBar]],
        baseline: dict[str, object],
        start: date,
        end: date,
    ) -> tuple[PaperBacktestEfficiencyCandidate, ...]:
        accepted: list[PaperBacktestEfficiencyCandidate] = []
        baseline_trades = self._active_trades(baseline)
        baseline_monthly = PaperBacktestService._paper_backtest_monthly_stability(
            baseline_trades,
        )
        primary = self._paper_backtest_efficiency_challenger(
            candidates=candidates,
            histories=histories,
            baseline=baseline,
            start=start,
            end=end,
        )
        if primary is not None:
            accepted.append(primary)

        for label, exit_case in (
            (
                "7.0% 第一止盈",
                board_matrix.ExitCase(
                    case_id="shadow_efficiency_stop6_target7_or8_hold1",
                    stop_loss_pct=0.06,
                    take_profit_pct=0.07,
                    max_hold_days=1,
                    weak_next_open_exit_pct=None,
                    strong_market_advance_ratio=0.70,
                    strong_market_take_profit_pct=0.08,
                ),
            ),
            (
                "6.0% 第一止盈，强势 9%",
                board_matrix.ExitCase(
                    case_id="shadow_efficiency_stop6_target6_or9_hold1",
                    stop_loss_pct=0.06,
                    take_profit_pct=0.06,
                    max_hold_days=1,
                    weak_next_open_exit_pct=None,
                    strong_market_advance_ratio=0.70,
                    strong_market_take_profit_pct=0.09,
                ),
            ),
        ):
            challenger = board_matrix.evaluate_case(
                candidates=candidates,
                histories=histories,
                entry_case=board_matrix.shadow_default_entry_case(),
                exit_case=exit_case,
                rank_case="score",
                position_pct=0.08,
                roundtrip_cost_pct=0.0015,
            )
            challenger = self._with_small_account_result(challenger)
            baseline_summary = self._active_summary(
                baseline,
                "suggested_position_summary",
            )
            baseline_validation = self._active_summary(
                baseline,
                "suggested_position_validation_summary",
            )
            challenger_summary = self._active_summary(
                challenger,
                "suggested_position_summary",
            )
            challenger_validation = self._active_summary(
                challenger,
                "suggested_position_validation_summary",
            )
            baseline_yearly = self._active_yearly(baseline)
            challenger_yearly = self._active_yearly(challenger)
            baseline_full_years = [
                float(
                    baseline_yearly.get(str(year), {}).get("position_weighted_return_pct")
                    or 0.0
                )
                for year in range(start.year, end.year)
            ]
            challenger_full_years = [
                float(
                    challenger_yearly.get(str(year), {}).get("position_weighted_return_pct")
                    or 0.0
                )
                for year in range(start.year, end.year)
            ]
            if not baseline_full_years or not challenger_full_years:
                continue
            baseline_worst = min(baseline_full_years)
            challenger_worst = min(challenger_full_years)
            baseline_return = float(
                baseline_summary.get("position_weighted_return_pct") or 0.0
            )
            challenger_return = float(
                challenger_summary.get("position_weighted_return_pct") or 0.0
            )
            baseline_dd = abs(float(baseline_summary.get("max_drawdown_pct") or 0.0))
            challenger_dd = abs(float(challenger_summary.get("max_drawdown_pct") or 0.0))
            baseline_validation_return = float(
                baseline_validation.get("position_weighted_return_pct") or 0.0
            )
            challenger_validation_return = float(
                challenger_validation.get("position_weighted_return_pct") or 0.0
            )
            challenger_monthly = PaperBacktestService._paper_backtest_monthly_stability(
                self._active_trades(challenger),
            )
            if (
                challenger_return <= baseline_return
                or challenger_dd > baseline_dd + 0.0001
                or challenger_worst < baseline_worst - 0.01
                or challenger_validation_return < baseline_validation_return - 0.01
                or not PaperBacktestService._paper_backtest_monthly_stability_passes(
                    baseline_monthly,
                    challenger_monthly,
                )
            ):
                continue
            accepted.append(
                PaperBacktestEfficiencyCandidate(
                    label=label,
                    total_return_pct=challenger_return,
                    max_drawdown_pct=-challenger_dd,
                    validation_return_pct=challenger_validation_return,
                    weakest_full_year_return_pct=challenger_worst,
                    monthly_positive_ratio=challenger_monthly.positive_month_ratio,
                    worst_month_return_pct=challenger_monthly.worst_month_return_pct,
                    conclusion=(
                        "同仓位高收益低回撤挑战者已出现："
                        f"{label} 在 2020-2026 全区间收益 {challenger_return:.2%}，"
                        f"高于当前主线 {baseline_return:.2%}；最大回撤仍为 "
                        f"{challenger_dd:.2%}，最弱完整年度 {challenger_worst:.2%}，"
                        f"验证段 {challenger_validation_return:.2%}。建议继续并行验证，不直接替换主线。"
                    ),
                )
            )
        accepted.sort(
            key=lambda item: (
                item.total_return_pct,
                item.validation_return_pct,
                item.weakest_full_year_return_pct,
            ),
            reverse=True,
        )
        unique: list[PaperBacktestEfficiencyCandidate] = []
        seen: set[str] = set()
        for item in accepted:
            if item.label in seen:
                continue
            seen.add(item.label)
            unique.append(item)
        return tuple(unique[:3])

    @staticmethod
    def _paper_backtest_monthly_stability(
        trades: list[object],
    ) -> PaperBacktestMonthlyStability | None:
        if not trades:
            return None
        by_month: dict[str, list[float]] = {}
        for trade in trades:
            entry_date = PaperBacktestService._trade_entry_date(trade)
            account_return_pct = PaperBacktestService._trade_account_return_pct(trade)
            if len(entry_date) < 7:
                continue
            by_month.setdefault(entry_date[:7], []).append(account_return_pct)
        if not by_month:
            return None
        month_returns: list[tuple[str, float]] = []
        for month in sorted(by_month):
            equity = 1.0
            for value in by_month[month]:
                equity *= max(0.0, 1 + value)
            month_returns.append((month, round(equity - 1, 4)))
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
            f"月度正收益占比 {positive_ratio:.2%}，最差月份 {worst_month} {worst_return:.2%}，"
            f"最长连续亏损月 {longest_losing_streak}。"
        )
        if longest_losing_streak == 0 and worst_return > 0:
            conclusion += " 历史样本没有亏损月，但这不构成未来保证。"
        elif positive_ratio >= 0.7 and worst_return > -0.03:
            conclusion += " 月度稳定性较强，但仍不能保证未来每个月都赚钱。"
        else:
            conclusion += " 月度波动仍需继续优化，重点压缩亏损月和连亏段。"
        return PaperBacktestMonthlyStability(
            total_months=len(month_returns),
            positive_months=positive_months,
            positive_month_ratio=positive_ratio,
            worst_month=worst_month,
            worst_month_return_pct=worst_return,
            longest_losing_streak=longest_losing_streak,
            conclusion=conclusion,
        )

    @staticmethod
    def _paper_backtest_monthly_metrics(
        trades: list[object],
    ) -> tuple[PaperBacktestMonthlyMetric, ...]:
        if not trades:
            return ()
        by_month: dict[str, list[float]] = {}
        for trade in trades:
            entry_date = PaperBacktestService._trade_entry_date(trade)
            account_return_pct = PaperBacktestService._trade_account_return_pct(trade)
            if len(entry_date) < 7:
                continue
            by_month.setdefault(entry_date[:7], []).append(account_return_pct)
        result: list[PaperBacktestMonthlyMetric] = []
        for month in sorted(by_month):
            equity = 1.0
            for value in by_month[month]:
                equity *= max(0.0, 1 + value)
            month_return = round(equity - 1, 4)
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

    @staticmethod
    def _paper_backtest_current_month_notes(
        *,
        requested_end: str,
        coverage_end: str,
        monthly: tuple[PaperBacktestMonthlyMetric, ...],
    ) -> tuple[str, ...]:
        requested_month = requested_end[:7] if len(requested_end) >= 7 else ""
        if not requested_month:
            return ()
        current_month = next(
            (item for item in monthly if item.month == requested_month),
            None,
        )
        if current_month is not None:
            return (
                (
                    f"本月回测：{current_month.month} 已纳入，收益 "
                    f"{current_month.position_weighted_return_pct:.2%}，"
                    f"{current_month.conclusion}。"
                ),
            )
        if not coverage_end:
            return (
                f"本月回测：请求到 {requested_end}，但研究缓存无覆盖终点，不能判断本月是否空仓。",
            )
        if coverage_end < requested_end:
            return (
                (
                    f"本月回测：请求到 {requested_end}，但日线研究缓存只覆盖到 {coverage_end}，"
                    f"{requested_month} 尚未完整纳入战法回测；这不是确认本月一直空仓。"
                ),
            )
        return (
            (
                f"本月回测：{requested_month} 数据已覆盖到 {coverage_end}，"
                "但没有触发可执行主线买点，回测口径为空仓。"
            ),
        )

    @staticmethod
    def _trade_entry_date(trade: object) -> str:
        if isinstance(trade, dict):
            return str(trade.get("entry_date", ""))
        return str(getattr(trade, "entry_date", ""))

    @staticmethod
    def _trade_account_return_pct(trade: object) -> float:
        if isinstance(trade, dict):
            if "account_return_pct" in trade:
                return float(trade.get("account_return_pct") or 0.0)
            return float(trade.get("net_return_pct") or 0.0) * 0.08
        if hasattr(trade, "account_return_pct"):
            return float(getattr(trade, "account_return_pct") or 0.0)
        return float(getattr(trade, "net_return_pct", 0.0) or 0.0) * 0.08

    @staticmethod
    def _paper_backtest_monthly_stability_passes(
        baseline: PaperBacktestMonthlyStability | None,
        challenger: PaperBacktestMonthlyStability | None,
    ) -> bool:
        if baseline is None or challenger is None:
            return False
        return (
            challenger.positive_month_ratio >= baseline.positive_month_ratio - 0.02
            and challenger.worst_month_return_pct >= baseline.worst_month_return_pct - 0.01
            and challenger.longest_losing_streak <= baseline.longest_losing_streak + 1
        )

    @staticmethod
    def _paper_backtest_data_coverage(
        histories: dict[str, list[object]],
    ) -> tuple[str, str]:
        first_dates: list[str] = []
        last_dates: list[str] = []
        for bars in histories.values():
            if not bars:
                continue
            dates = [str(getattr(item, "trade_date", "")) for item in bars]
            dates = [item for item in dates if item]
            if not dates:
                continue
            first_dates.append(min(dates))
            last_dates.append(max(dates))
        if not first_dates or not last_dates:
            return "", ""
        return min(first_dates), max(last_dates)

    @staticmethod
    def _paper_backtest_data_coverage_notes(
        *,
        requested_start: str,
        requested_end: str,
        coverage_start: str,
        coverage_end: str,
        yearly: tuple[PaperBacktestYearlyMetric, ...],
    ) -> tuple[str, ...]:
        notes = [
            f"请求区间：{requested_start} -> {requested_end}；缓存覆盖：{coverage_start or '未知'} -> {coverage_end or '未知'}。",
        ]
        no_sample_years = tuple(item.year for item in yearly if item.sample_count <= 0)
        if no_sample_years:
            notes.append(
                f"{'、'.join(no_sample_years)} 无有效交易样本，只能标记为数据/样本不足，不能计入已验证盈利年份。"
            )
        if coverage_start and coverage_start[:4] > requested_start[:4]:
            notes.append(
                "缓存覆盖起点晚于请求起点，建议先刷新 2020 起日线缓存后再做最终算法体检。"
            )
        if coverage_end and coverage_end < requested_end:
            if coverage_end[:7] == requested_end[:7]:
                notes.append(
                    (
                        "缓存已覆盖到请求月份内的最近可用交易日；若请求终点是周末、节假日或"
                        "尚未落库的当日数据，不应把自然日差异误判为本月未纳入。"
                    )
                )
            else:
                notes.append(
                    (
                        "缓存覆盖终点早于请求终点，近日报告只能说明已覆盖区间表现，"
                        "不能把未覆盖月份当成已回测空仓。"
                    )
                )
        return tuple(notes)


__all__ = ["PaperBacktestService"]
