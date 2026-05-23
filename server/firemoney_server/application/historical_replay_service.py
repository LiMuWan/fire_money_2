"""Historical replay and backtest-audit orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.domain.one_to_two_types import (
    HistoricalPriceBar,
    OneToTwoMarketRow,
)
from shared.contracts import (
    BacktestDataQualityCheck,
    OneToTwoBacktestAuditReport,
    OneToTwoCandidate,
    OneToTwoHistoricalReplayReport,
    OneToTwoHistoricalReplayTrade,
    OneToTwoStabilityReport,
    PaperAccount,
    PaperPosition,
)


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


class HistoricalReplaySettings(Protocol):
    initial_cash: float
    max_position_pct: float
    max_daily_trades: int
    first_take_profit_pct: float
    strong_take_profit_pct: float
    trailing_stop_pct: float
    max_holding_trade_days: int
    minimum_sample_for_stability: int


class ResolvedTradingDayLike(Protocol):
    trade_date: str
    next_trade_date: str


class TradingCalendarLike(Protocol):
    def resolve(self, requested_date: str | None = None) -> ResolvedTradingDayLike:
        """Resolve a date into a trading-day context."""


class HistoricalReplayMarketDataProvider(Protocol):
    def load_one_to_two_rows(
        self,
        trade_date: str,
    ) -> tuple[OneToTwoMarketRow, ...]:
        """Load one-to-two market rows for a trade date."""

    def load_price_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> tuple[HistoricalPriceBar, ...]:
        """Load daily price bars for a symbol and date range."""


class HistoricalPaperStore(Protocol):
    def load(self) -> PaperAccount:
        """Load a paper account."""

    def prepare_for_trade_date(self, trade_date: str) -> PaperAccount:
        """Roll the paper account to one trade date."""

    def buy_candidate(self, candidate: OneToTwoCandidate) -> PaperAccount:
        """Buy one candidate in an isolated historical ledger."""

    def exit_position(
        self,
        candidate: OneToTwoCandidate,
        exit_reason: str,
        message: str,
        holding_trade_days: int = 0,
    ) -> PaperAccount:
        """Exit one historical position."""


class HistoricalReplayService:
    """Runs read-only historical validation without mutating the live ledger."""

    def __init__(
        self,
        *,
        settings: HistoricalReplaySettings,
        market_data_provider: HistoricalReplayMarketDataProvider,
        trading_calendar: TradingCalendarLike,
        paper_store_factory: Callable[[Path], HistoricalPaperStore],
        build_stability_report: Callable[[PaperAccount], OneToTwoStabilityReport],
        candidate_for_position: Callable[[PaperPosition, str], OneToTwoCandidate],
        holding_trade_days: Callable[[str, str], int],
        default_trade_date: Callable[[], str],
        pit_data_warning: bool = False,
    ) -> None:
        self._settings = settings
        self._market_data_provider = market_data_provider
        self._trading_calendar = trading_calendar
        self._paper_store_factory = paper_store_factory
        self._build_stability_report = build_stability_report
        self._candidate_for_position = candidate_for_position
        self._holding_trade_days = holding_trade_days
        self._default_trade_date = default_trade_date
        self._pit_data_warning = pit_data_warning
        self._policy = OneToTwoPolicy(settings)

    def run_backtest(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoStabilityReport:
        dates = self._resolve_backtest_dates(start_date, end_date, max_trade_days)

        with TemporaryDirectory() as temp_dir:
            paper_store = self._paper_store_factory(Path(temp_dir) / "paper_trades.json")
            for trade_date in dates:
                try:
                    rows = self._market_data_provider.load_one_to_two_rows(trade_date)
                except Exception:
                    continue
                candidates = self._policy.build_candidates(rows)
                ready = next(
                    (candidate for candidate in candidates if candidate.status == "ready"),
                    None,
                )
                if not ready:
                    continue
                account = paper_store.load()
                if account.positions:
                    position = account.positions[0]
                    matched = next(
                        (
                            candidate
                            for candidate in candidates
                            if candidate.symbol == position.symbol
                        ),
                        None,
                    )
                    if matched and position.can_sell_today:
                        paper_store.exit_position(
                            matched,
                            exit_reason="backtest_discipline",
                            message="历史回放纪律退出，完成一笔主线首板样本。",
                            holding_trade_days=1,
                        )
                if not paper_store.load().positions:
                    paper_store.buy_candidate(ready)
            account = paper_store.load()
            if account.positions and dates:
                position = account.positions[0]
                last_date = dates[-1]
                paper_store.prepare_for_trade_date(last_date)
                synthetic_exit = self._candidate_for_position(position, last_date)
                paper_store.exit_position(
                    synthetic_exit,
                    exit_reason="backtest_forced_close",
                    message="历史回放结束，强制按最新价归档样本。",
                    holding_trade_days=1,
                )
            return self._build_stability_report(paper_store.load())

    def build_backtest_audit(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoBacktestAuditReport:
        dates = self._resolve_backtest_dates(start_date, end_date, max_trade_days)
        stability_report = self.run_backtest(
            start_date=start_date,
            end_date=end_date,
            max_trade_days=max_trade_days,
        )
        quality_checks = self._backtest_data_quality_checks(
            dates=dates,
            stability_report=stability_report,
        )
        blocked = any(check.status == "blocked" for check in quality_checks)
        warning = any(check.status == "warning" for check in quality_checks)
        status = "blocked" if blocked else "warning" if warning else "ready"
        sample_count = stability_report.sample_count
        summary = (
            f"回测准入未通过：{sample_count} 笔样本，存在数据或样本阻断项。"
            if status == "blocked"
            else f"回测仍处观察期：{sample_count} 笔样本，尚不足以证明长期稳定。"
            if status == "warning"
            else f"回测准入通过：{sample_count} 笔样本，可进入模拟盘 Beta 验证。"
        )
        return OneToTwoBacktestAuditReport(
            report_id=f"one-to-two-backtest-audit-{dates[0] if dates else 'none'}-{dates[-1] if dates else 'none'}",
            start_date=dates[0] if dates else "",
            end_date=dates[-1] if dates else "",
            requested_trade_days=max_trade_days,
            usable_trade_days=len(dates),
            data_quality_checks=quality_checks,
            stability_report=stability_report,
            status=status,
            summary=summary,
            limitations=(
                "AkShare 免费数据不等同专业 Point-in-Time 数据，退市和历史成分偏差仍需后续加强。",
                "当前回测以日线/涨停池事件近似，不能替代 Tick 或逐笔成交验证。",
                "少于 30 笔闭环样本只允许观察，不允许宣称策略稳定盈利。",
            ),
            recommended_next_action=(
                "修复 blocked 项后重新运行 backtest-audit。"
                if status == "blocked"
                else "继续扩大回测窗口到 5-8 年或接入更干净的历史数据源。"
                if status == "warning"
                else "进入 beta-check 和 beta-start，只做模拟盘实盘跟踪验证。"
            ),
        )

    def run_historical_replay(
        self,
        *,
        as_of_date: str | None = None,
        holding_days: int = 5,
    ) -> OneToTwoHistoricalReplayReport:
        trade_context = self._trading_calendar.resolve(
            as_of_date or self._default_trade_date()
        )
        entry_date = trade_context.trade_date
        data_mode = self._market_data_provider.__class__.__name__
        no_future_notes = (
            f"选股只读取 {entry_date} 当时的一进二候选池和策略配置。",
            "后续日线只用于模拟卖点、盈亏和盈亏比，不参与候选评分。",
            "日线无法还原盘中先后顺序，同日触发止损和止盈时按保守止损优先。",
        )
        quality_checks: list[BacktestDataQualityCheck] = [
            BacktestDataQualityCheck(
                check_id="no_future_selection",
                label="无未来函数",
                status="ready",
                detail=f"候选选择阶段截止到 {entry_date}，未读取后续价格柱。",
                next_action="正式研究时继续使用逐日快照或 Point-in-Time 数据源复核。",
            )
        ]
        if self._pit_data_warning:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="point_in_time_data",
                    label="PIT 数据",
                    status="warning",
                    detail="AkShare 免费数据适合验证流程，但不等同专业 Point-in-Time 快照。",
                    next_action="正式评价长期胜率前，接入退市样本和逐日快照数据。",
                )
            )

        try:
            rows = self._market_data_provider.load_one_to_two_rows(entry_date)
        except Exception as exc:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="candidate_pool",
                    label="候选池",
                    status="blocked",
                    detail=f"{entry_date} 候选池不可用：{exc}",
                    next_action="先修复行情源或改用 --sample-data 验证链路。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：候选池不可用。",
                next_action="修复行情源后重新运行 replay。",
            )

        candidates = self._policy.build_candidates(rows)
        candidate = next(
            (item for item in candidates if item.status == "ready"),
            None,
        )
        if candidate is None:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="candidate_pool",
                    label="候选池",
                    status="blocked",
                    detail=f"{entry_date} 没有达到执行分数和硬过滤的候选。",
                    next_action="保留空样本，不生成模拟买入。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放无交易：当日没有合格候选。",
                next_action="换一个历史交易日，或先扩大回放窗口做样本统计。",
            )

        replay_dates = self._replay_trade_dates(
            entry_date=entry_date,
            holding_days=holding_days,
        )
        if len(replay_dates) < 2:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_window",
                    label="价格窗口",
                    status="blocked",
                    detail="缺少 T+1 之后的交易日，无法计算卖出和盈亏比。",
                    next_action="选择更早的历史日期或等待后续交易日数据。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：没有足够后续交易日。",
                candidate=candidate,
                next_action="选择更早的历史日期重新运行 replay。",
            )

        try:
            bars = self._market_data_provider.load_price_bars(
                candidate.symbol,
                replay_dates[0],
                replay_dates[-1],
            )
        except Exception as exc:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_bars",
                    label="日线价格",
                    status="blocked",
                    detail=f"{candidate.symbol} 后续日线不可用：{exc}",
                    next_action="修复历史日线源后重新运行 replay。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：后续价格不可用。",
                candidate=candidate,
                next_action="修复历史日线源后重新运行 replay。",
            )

        expected_dates = set(replay_dates)
        bars = tuple(bar for bar in bars if bar.trade_date in expected_dates)
        if len(bars) < 2:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_bars",
                    label="日线价格",
                    status="blocked",
                    detail=f"{candidate.symbol} 只取得 {len(bars)} 根价格柱，无法完成 T+1 回放。",
                    next_action="选择更早日期，或检查历史日线是否缺失。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：日线样本不足。",
                candidate=candidate,
                next_action="补齐历史价格后重新运行 replay。",
            )

        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="price_bars",
                label="日线价格",
                status="ready",
                detail=f"取得 {candidate.symbol} {bars[0].trade_date} 到 {bars[-1].trade_date} 的 {len(bars)} 根日线。",
                next_action="用后续价格柱执行卖点，不回灌选股。",
            )
        )
        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="daily_bar_sequence",
                label="日内顺序",
                status="warning",
                detail="日线只有高低收，无法证明盘中先止盈还是先止损；当前按保守止损优先。",
                next_action="后续若接入分钟线或 Tick，可把执行价精度升级。",
            )
        )
        trade = self._simulate_historical_trade(
            candidate=candidate,
            bars=bars,
            data_mode=data_mode,
        )
        warning = any(check.status == "warning" for check in quality_checks)
        status = "warning" if warning else "ready"
        summary = (
            f"历史逐日回放完成：{_stock_label(candidate.name, candidate.symbol)} "
            f"{trade.entry_date} 买入，{trade.exit_date} 按 {trade.exit_reason} 卖出，"
            f"收益 {trade.realized_pnl_pct:.2%}，盈亏比 {trade.risk_reward_ratio:.2f}R。"
        )
        return OneToTwoHistoricalReplayReport(
            report_id=f"one-to-two-replay-{entry_date}-{candidate.symbol}",
            as_of_date=entry_date,
            entry_date=trade.entry_date,
            exit_date=trade.exit_date,
            data_mode=data_mode,
            status=status,
            summary=summary,
            candidate=candidate,
            trade=trade,
            quality_checks=tuple(quality_checks),
            no_future_leakage_notes=no_future_notes,
            next_action=(
                "这是一笔单点回放；下一步应扩大到连续历史窗口，统计 30/50/100 笔样本。"
            ),
        )

    def _historical_replay_blocked_report(
        self,
        entry_date: str,
        data_mode: str,
        quality_checks: tuple[BacktestDataQualityCheck, ...],
        no_future_notes: tuple[str, ...],
        summary: str,
        next_action: str,
        candidate: OneToTwoCandidate | None = None,
    ) -> OneToTwoHistoricalReplayReport:
        return OneToTwoHistoricalReplayReport(
            report_id=f"one-to-two-replay-{entry_date}-blocked",
            as_of_date=entry_date,
            entry_date=entry_date,
            exit_date="",
            data_mode=data_mode,
            status="blocked",
            summary=summary,
            candidate=candidate,
            trade=None,
            quality_checks=quality_checks,
            no_future_leakage_notes=no_future_notes,
            next_action=next_action,
        )

    def _replay_trade_dates(self, entry_date: str, holding_days: int) -> list[str]:
        dates = [entry_date]
        current = entry_date
        for _index in range(max(1, holding_days)):
            context = self._trading_calendar.resolve(current)
            next_date = context.next_trade_date
            if next_date <= current:
                break
            dates.append(next_date)
            current = next_date
        return dates

    def _simulate_historical_trade(
        self,
        candidate: OneToTwoCandidate,
        bars: tuple[HistoricalPriceBar, ...],
        data_mode: str,
    ) -> OneToTwoHistoricalReplayTrade:
        entry_price = candidate.entry_price
        exit_plan = candidate.exit_plan
        stop_loss = exit_plan.stop_loss if exit_plan else candidate.stop_loss
        first_take_profit_price = (
            exit_plan.first_take_profit_price
            if exit_plan
            else round(entry_price * (1 + self._settings.first_take_profit_pct), 2)
        )
        strong_take_profit_pct = (
            exit_plan.strong_take_profit_pct
            if exit_plan
            else self._settings.strong_take_profit_pct
        )
        trailing_stop_pct = (
            exit_plan.trailing_stop_pct
            if exit_plan
            else self._settings.trailing_stop_pct
        )
        max_holding_trade_days = min(
            len(bars) - 1,
            exit_plan.max_holding_trade_days
            if exit_plan
            else self._settings.max_holding_trade_days,
        )
        position_cash = self._settings.initial_cash * candidate.position_limit_pct
        quantity = int(position_cash // (entry_price * 100)) * 100 if entry_price else 0
        if quantity <= 0 and entry_price > 0:
            quantity = 100

        exit_bar = bars[min(max_holding_trade_days, len(bars) - 1)]
        exit_price = exit_bar.close_price
        exit_reason = "replay_forced_close"
        peak_price = entry_price
        max_favorable_pct = 0.0
        max_adverse_pct = 0.0
        notes = [
            "严格 T+1：买入当天不模拟卖出。",
            "选股完成后才读取后续价格柱计算盈亏。",
        ]

        for holding_day, bar in enumerate(bars[1:], start=1):
            favorable_pct = (bar.high_price - entry_price) / entry_price
            adverse_pct = (bar.low_price - entry_price) / entry_price
            max_favorable_pct = max(max_favorable_pct, favorable_pct)
            max_adverse_pct = min(max_adverse_pct, adverse_pct)

            previous_peak_price = peak_price
            previous_strong_reached = (
                (previous_peak_price - entry_price) / entry_price >= strong_take_profit_pct
                if entry_price
                else False
            )
            previous_trailing_stop = round(
                previous_peak_price * (1 - trailing_stop_pct),
                2,
            )

            if bar.open_price >= first_take_profit_price:
                exit_bar = bar
                exit_price = first_take_profit_price
                exit_reason = "take_profit_first_target"
                break

            if bar.low_price <= stop_loss:
                exit_bar = bar
                exit_price = self._conservative_downside_exit_price(
                    open_price=bar.open_price,
                    trigger_price=stop_loss,
                )
                exit_reason = "stop_loss_t1"
                break

            if previous_strong_reached and bar.low_price <= previous_trailing_stop:
                exit_bar = bar
                exit_price = self._conservative_downside_exit_price(
                    open_price=bar.open_price,
                    trigger_price=previous_trailing_stop,
                )
                exit_reason = "trailing_take_profit"
                break

            if bar.high_price >= first_take_profit_price:
                exit_bar = bar
                exit_price = first_take_profit_price
                exit_reason = "take_profit_first_target"
                break

            if holding_day >= max_holding_trade_days:
                exit_bar = bar
                exit_price = bar.close_price
                exit_reason = "max_holding_close"
                break

            peak_price = max(peak_price, bar.high_price)

        gross_return_pct = (
            (exit_price - entry_price) / entry_price if entry_price else 0.0
        )
        realized_pnl = round((exit_price - entry_price) * quantity, 2)
        stop_risk_pct = (
            exit_plan.stop_loss_pct
            if exit_plan and exit_plan.stop_loss_pct > 0
            else max((entry_price - stop_loss) / entry_price, 0.0001)
            if entry_price
            else 0.0001
        )
        risk_reward_ratio = gross_return_pct / max(stop_risk_pct, 0.0001)
        return OneToTwoHistoricalReplayTrade(
            symbol=candidate.symbol,
            name=candidate.name,
            entry_date=bars[0].trade_date,
            exit_date=exit_bar.trade_date,
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=quantity,
            gross_return_pct=round(gross_return_pct, 6),
            realized_pnl=realized_pnl,
            realized_pnl_pct=round(gross_return_pct, 6),
            holding_trade_days=self._holding_trade_days(
                bars[0].trade_date,
                exit_bar.trade_date,
            ),
            exit_reason=exit_reason,
            risk_reward_ratio=round(risk_reward_ratio, 4),
            max_favorable_pct=round(max_favorable_pct, 6),
            max_adverse_pct=round(max_adverse_pct, 6),
            candidate_score=candidate.score,
            position_label=candidate.position_profile.label,
            evidence_date=candidate.trade_date,
            data_mode=data_mode,
            notes=tuple(notes),
        )

    @staticmethod
    def _conservative_downside_exit_price(
        open_price: float,
        trigger_price: float,
    ) -> float:
        if open_price <= trigger_price:
            return open_price
        return trigger_price

    def _resolve_backtest_dates(
        self,
        start_date: str | None,
        end_date: str | None,
        max_trade_days: int,
    ) -> list[str]:
        end_context = self._trading_calendar.resolve(end_date or self._default_trade_date())
        end_trade_date = date.fromisoformat(end_context.trade_date)
        start_trade_date = (
            date.fromisoformat(self._trading_calendar.resolve(start_date).trade_date)
            if start_date
            else end_trade_date - timedelta(days=max_trade_days * 2)
        )
        dates: list[str] = []
        cursor = start_trade_date
        while cursor <= end_trade_date:
            context = self._trading_calendar.resolve(cursor.isoformat())
            if context.trade_date == cursor.isoformat():
                dates.append(context.trade_date)
                if start_date and len(dates) >= max_trade_days:
                    break
            cursor += timedelta(days=1)
        if start_date:
            return dates
        return dates[-max_trade_days:]

    def _backtest_data_quality_checks(
        self,
        dates: list[str],
        stability_report: OneToTwoStabilityReport,
    ) -> tuple[BacktestDataQualityCheck, ...]:
        checks: list[BacktestDataQualityCheck] = []
        checks.append(
            BacktestDataQualityCheck(
                check_id="data_window",
                label="数据窗口",
                status="ready" if len(dates) >= 20 else "blocked",
                detail=f"可用交易日 {len(dates)} 天；建议正式研究覆盖 5-8 年多轮牛熊。",
                next_action=(
                    "继续执行回测。"
                    if len(dates) >= 20
                    else "扩大 --max-trade-days 或指定更长 start/end 日期。"
                ),
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="sample_size",
                label="样本数",
                status=(
                    "ready"
                    if stability_report.sample_count
                    >= self._settings.minimum_sample_for_stability
                    else "warning"
                    if stability_report.sample_count > 0
                    else "blocked"
                ),
                detail=(
                    f"闭环样本 {stability_report.sample_count} 笔，"
                    f"最低观察门槛 {self._settings.minimum_sample_for_stability} 笔。"
                ),
                next_action=(
                    "样本达到初评门槛，可进入策略边界复核。"
                    if stability_report.sample_count
                    >= self._settings.minimum_sample_for_stability
                    else "样本不足，只能观察，不能宣称稳定盈利。"
                ),
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="survivorship_bias",
                label="幸存者偏差",
                status="warning",
                detail="当前 AkShare 回测未完全保证历史退市股票和成分股 Point-in-Time 覆盖。",
                next_action="后续接入专业 PIT 数据源或维护本地退市股票历史池。",
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="execution_granularity",
                label="执行颗粒度",
                status="warning",
                detail="当前按日线/涨停池事件近似执行，无法模拟排队、炸板瞬时成交和 Tick 级滑点。",
                next_action="模拟盘 Beta 先验证流程，正式研究再引入分钟线或 Tick 数据。",
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="rule_version",
                label="规则版本",
                status="ready",
                detail=(
                    "规则已固化为主线首板龙头候选、T+1、12% 第一止盈、4%/结构止损、"
                    "10% 强势阈值后 2% 回撤保护、主线持续性衰减退出。"
                ),
                next_action="回测结果只对当前规则版本负责，改规则后必须重跑。",
            )
        )
        return tuple(checks)


__all__ = ["HistoricalReplayService"]
