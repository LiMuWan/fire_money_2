"""Board-shadow review and evidence-layer orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from server.firemoney_server.application.one_to_two_notification_text import (
    board_shadow_notification_message,
)
from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.infrastructure.board_shadow_store import (
    LimitUpBoardShadowStore,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
)
from shared.contracts import (
    BacktestDataQualityCheck,
    FeishuNotificationResult,
    LimitUpBoardShadowCandidate,
    LimitUpBoardShadowReport,
    LimitUpBoardShadowStabilityReport,
    LimitUpBoardShadowSystemMetric,
    LimitUpBoardShadowSystemReport,
    LimitUpBoardShadowTrade,
)
from tools import research_limit_up_board_profit_matrix as board_matrix


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


class NotifyOrPrepare(Protocol):
    def __call__(self, notify: bool, title: str, message: str) -> FeishuNotificationResult:
        """Send or prepare one notification payload."""


class RecordNotification(Protocol):
    def __call__(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
    ) -> None:
        """Persist one notification audit record."""


class BoardShadowReviewService:
    """Owns board-shadow report assembly and evidence-layer summaries."""

    def __init__(
        self,
        *,
        settings: OneToTwoStrategySettings,
        board_shadow_store: LimitUpBoardShadowStore,
        default_trade_date: Callable[[], str],
        notify_or_prepare: NotifyOrPrepare,
        record_notification: RecordNotification,
    ) -> None:
        self._settings = settings
        self._board_shadow_store = board_shadow_store
        self._default_trade_date = default_trade_date
        self._notify_or_prepare = notify_or_prepare
        self._record_notification = record_notification
        self._policy = OneToTwoPolicy(settings)

    def build_report(
        self,
        *,
        as_of_date: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> LimitUpBoardShadowReport:
        as_of = as_of_date or self._default_trade_date()
        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        data_mode = f"cached_daily:{cache_path}"
        no_future_notes = (
            f"封板影子线选股只读取 {as_of} 当日及以前的本地日线缓存。",
            "市场热度窗口只使用封板日当日可见的封板家数、触板家数和上涨占比。",
            "候选确定后，后续日线只用于卖点回放和盈亏计算，不参与排名。",
            "卖点只使用封板日已可见的市场上涨占比：上涨占比超过 70% 用 8% 止盈，否则用 5.5% 均衡止盈。",
            "同一日线同时碰到止盈和 6% 止损时，按保守止损优先。",
        )
        limitations = (
            "日线缓存不能证明封单强度、开板次数、排队可成交或真实滑点。",
            "当前入口只做主线证据复盘，不直接写入模拟盘，不代表实盘交易建议。",
            "当前证据样本默认要求封板日市场封板家数在 20 到 150 家之间，过冷或过热只观察。",
            "动态止盈仍是日线代理，真实可执行性需要分钟线/Tick 和滑点验证。",
            "封板线进入模拟盘前必须接入分钟线/Tick、封单和主线消息持续性。",
        )
        quality_checks: list[BacktestDataQualityCheck] = [
            BacktestDataQualityCheck(
                check_id="runtime_boundary",
                label="运行边界",
                status="ready",
                detail="封板证据线只做复盘验证，不直接写入模拟盘。",
                next_action="继续作为主线证据层观察，不直接替代当日模拟盘指挥。",
            )
        ]
        try:
            universe, histories = board_matrix.load_cached_research_data(
                cache_path,
                board_matrix.sm.parse_iso_date(as_of),
                board_matrix.sm.parse_iso_date(as_of),
            )
        except Exception as exc:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="cached_daily_data",
                    label="历史缓存",
                    status="blocked",
                    detail=f"封板影子线无法读取本地历史缓存：{exc}",
                    next_action="先运行封板利润矩阵或修复 .firemoney/research_cache/one_to_two_daily。",
                )
            )
            return LimitUpBoardShadowReport(
                report_id=f"limit-up-board-shadow-{as_of}-blocked",
                as_of_date=as_of,
                status="blocked",
                summary="封板影子线被阻断：本地历史缓存不可用。",
                candidate=None,
                trade=None,
                quality_checks=tuple(quality_checks),
                no_future_leakage_notes=no_future_notes,
                limitations=limitations,
                next_action="先补齐历史缓存，再运行 board-shadow。",
            )

        candidates = board_matrix.build_board_candidates(
            universe,
            histories,
            board_matrix.sm.parse_iso_date(as_of),
            board_matrix.sm.parse_iso_date(as_of),
        )
        entry_case = board_matrix.shadow_default_entry_case()
        exit_case = board_matrix.shadow_default_exit_case()
        filtered = [
            item for item in candidates if board_matrix.entry_case_allows(entry_case, item)
        ]
        daily_candidates = board_matrix.select_daily_top_candidates(filtered, "score")
        if not daily_candidates:
            heat_counts = [candidate.market_seal_count for candidate in candidates]
            heat_detail = (
                f"当日封板热度 {heat_counts[0]} 家，不在 20 到 150 家窗口内。"
                if heat_counts and all(count < 20 or count > 150 for count in heat_counts)
                else f"{as_of} 没有符合封板验证线的候选。"
            )
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="candidate",
                    label="封板热度/候选",
                    status="blocked",
                    detail=heat_detail,
                    next_action="保持空仓观察，不生成影子买入。",
                )
            )
            return LimitUpBoardShadowReport(
                report_id=f"limit-up-board-shadow-{as_of}-empty",
                as_of_date=as_of,
                status="blocked",
                summary="封板影子线无交易：当日没有合格候选。",
                candidate=None,
                trade=None,
                quality_checks=tuple(quality_checks),
                no_future_leakage_notes=no_future_notes,
                limitations=limitations,
                next_action="继续观察下一交易日，或只做历史区间回测。",
            )
        selected = daily_candidates[0]
        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="candidate",
                label="封板候选",
                status="ready",
                detail=f"{as_of} 选出 {selected.name}（{selected.symbol}），排序分 {selected.rank_score:.2f}。",
                next_action="后续只用 T+1 日线回放卖点，不回灌选股。",
            )
        )
        trade = board_matrix.simulate_board_trade(
            selected,
            histories[selected.symbol],
            exit_case,
            roundtrip_cost_pct=0.0015,
        )
        shadow_candidate = self._to_board_shadow_candidate(selected, exit_case)
        if trade is None:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="exit_replay",
                    label="卖点回放",
                    status="blocked",
                    detail=f"{selected.symbol} 缺少 T+1 日线，无法回放卖点。",
                    next_action="换更早的历史日期，或补齐后续日线缓存。",
                )
            )
            return LimitUpBoardShadowReport(
                report_id=f"limit-up-board-shadow-{as_of}-{selected.symbol}",
                as_of_date=as_of,
                status="blocked",
                summary="封板影子线候选已生成，但卖点回放缺少后续日线。",
                candidate=shadow_candidate,
                trade=None,
                quality_checks=tuple(quality_checks),
                no_future_leakage_notes=no_future_notes,
                limitations=limitations,
                next_action="补齐 T+1 日线后重新运行 board-shadow。",
            )
        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="exit_replay",
                label="卖点回放",
                status="ready",
                detail=f"{trade.exit_date} 按 {trade.reason} 卖出，收益 {trade.net_return_pct:.2%}。",
                next_action="把影子结果与一进二 Beta 当日结果并行复盘。",
            )
        )
        warning = any(item.status == "warning" for item in quality_checks)
        status = "warning" if warning else "ready"
        shadow_trade = LimitUpBoardShadowTrade(
            symbol=trade.symbol,
            name=trade.name,
            entry_date=trade.entry_date,
            exit_date=trade.exit_date,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            gross_return_pct=trade.gross_return_pct,
            realized_pnl_pct=trade.net_return_pct,
            holding_trade_days=trade.hold_days,
            exit_reason=trade.reason,
            data_mode=data_mode,
        )
        return LimitUpBoardShadowReport(
            report_id=f"limit-up-board-shadow-{as_of}-{selected.symbol}",
            as_of_date=as_of,
            status=status,
            summary=(
                f"封板影子线：{_stock_label(selected.name, selected.symbol)} "
                f"{trade.entry_date} 打板价 {trade.entry_price:.2f}，"
                f"{trade.exit_date} {trade.reason}，收益 {trade.net_return_pct:.2%}。"
            ),
            candidate=shadow_candidate,
            trade=shadow_trade,
            quality_checks=tuple(quality_checks),
            no_future_leakage_notes=no_future_notes,
            limitations=limitations,
            next_action="继续并行跟踪 30/50/100 笔 shadow 样本，再决定是否升级为模拟盘主线。",
        )

    def record_sample(
        self,
        *,
        as_of_date: str | None = None,
        cache_dir: str | Path | None = None,
        notify: bool = False,
    ) -> LimitUpBoardShadowReport:
        report = self.build_report(
            as_of_date=as_of_date,
            cache_dir=cache_dir,
        )
        sample = self._board_shadow_store.append_report(report)
        stability = self.build_stability_report()
        notification = self._notify_or_prepare(
            notify=False,
            title="FireMoney 封板影子线复盘",
            message=board_shadow_notification_message(
                report=report,
                stability_report=stability,
                sample_recorded=sample is not None,
            ),
        )
        self._record_notification(
            "board-shadow:record",
            report.as_of_date,
            notification,
        )
        if sample is None:
            return replace(report, notification=notification)
        return replace(
            report,
            summary=f"{report.summary} 已记录 shadow 样本 {sample.sample_id}。",
            next_action="运行 board-shadow-stability 查看累计胜率和阶段门槛。",
            notification=notification,
        )

    def build_stability_report(self) -> LimitUpBoardShadowStabilityReport:
        return self._board_shadow_store.build_stability_report()

    def build_system_report(
        self,
        *,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> LimitUpBoardShadowSystemReport:
        end = end_date or self._default_trade_date()
        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        start_parsed = board_matrix.sm.parse_iso_date(start_date)
        end_parsed = board_matrix.sm.parse_iso_date(end)
        if end_parsed < start_parsed:
            raise ValueError("end_date must be on or after start_date")

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
            position_pct=self._settings.max_position_pct,
            roundtrip_cost_pct=0.0015,
        )

        fixed_summary = self._to_board_shadow_system_metric(
            label="固定 8% 仓位全区间",
            summary=result["summary"],
        )
        fixed_validation = self._to_board_shadow_system_metric(
            label="固定 8% 仓位验证段",
            summary=result["validation_summary"],
        )
        dynamic_summary = self._to_board_shadow_system_metric(
            label="动态 8%/12% 仓位全区间",
            summary=result["suggested_position_summary"],
        )
        dynamic_validation = self._to_board_shadow_system_metric(
            label="动态 8%/12% 仓位验证段",
            summary=result["suggested_position_validation_summary"],
        )
        yearly_dynamic_returns = {
            year: float(item["position_weighted_return_pct"] or 0.0)
            for year, item in result["suggested_position_yearly"].items()
        }
        summary = (
            "封板波段交易体系以主板 10cm 非一字封板为买点源，封板当日只用可见字段做筛选、"
            "排序和强弱判断；次日以后只做卖点回放，不倒推买点。当前 2024 至今固定 8% "
            f"仓位复合 {fixed_summary.position_weighted_return_pct:.2%}，动态 8%/12% "
            f"仓位复合 {dynamic_summary.position_weighted_return_pct:.2%}。"
        )
        return LimitUpBoardShadowSystemReport(
            report_id=f"limit-up-board-shadow-system-{start_date}-to-{end}",
            start_date=start_date,
            end_date=end,
            status="ready",
            system_name="mainboard_10cm_limit_up_board_shadow_system",
            summary=summary,
            buy_rules=(
                "只做主板 10cm 非一字封板，不碰创业板、科创板、北交所。",
                "封板日成交额不低于 8000 万，20 日涨幅不高于 20%，20 日均线乖离不高于 35%。",
                "要求均线多头、20 日量比不低于 1.0，并且市场封板家数处于 20 到 150 家热度窗口。",
                "同日只按封板当日可见强度做排序，默认只选最强一只，不重叠持仓。",
            ),
            sell_rules=(
                "封板日市场上涨占比超过 70% 时，次日卖点采用 8% 动态止盈；否则采用 5.5% 均衡止盈。",
                "统一使用 6% 止损，日线同日触发止盈和止损时按保守止损优先。",
                "最多持有 1 个交易日，超出后按收盘退出，不在样本外拉长持有期。",
            ),
            position_rules=(
                "固定仓位研究口径为单票 8%，用于和历史主线做同口径比较。",
                "建议仓位口径为强市 12%、常态 8%，只有在同一封板日强市条件触发动态止盈时才加仓。",
                "任何时点都只做单仓不重叠，避免样本内靠并发堆收益。",
            ),
            fixed_position_summary=fixed_summary,
            fixed_position_validation=fixed_validation,
            dynamic_position_summary=dynamic_summary,
            dynamic_position_validation=dynamic_validation,
            yearly_dynamic_position_returns=yearly_dynamic_returns,
            factor_validation_notes=(
                "当前默认主线最稳的买点结构仍是：封板热度 20-150、20日涨幅上限 20%、20日量比不低于 1.0、均线多头。",
                "现有 2020-2026 邻域研究表明，放宽 20日涨幅上限到 22%-25% 虽然可能抬高总收益，但会放大回撤并削弱验证段稳定性。",
                "快速低波动过滤实验没有改善主线，反而明显压缩样本和收益，因此暂不进入默认闸门。",
                "额外增加局部主线集中度或过热过滤（如上涨占比阈值、触板/封板比约束）在当前缓存回测里也没有带来更稳且更赚钱的结果，因此暂不纳入默认规则。",
                "在低回撤优先的卖点邻域测试里，普通止盈 5.5% / 强市止盈 8% 比旧版 6% / 8% 拥有相同回撤、更强的 2021 弱年份表现和更高的验证段收益，因此升级为默认卖点。",
                "主线后续优先继续优化流动性质量、热度窗口和卖点纪律，不新增缺乏长期证据的短炒因子。",
            ),
            no_future_leakage_notes=(
                "买点筛选、日内排序和动态止盈判断只使用封板当日可见字段。",
                "验证段从 2026-01-01 开始，未来日线只在买点确定后用于卖点回放和盈亏计算。",
                "固定与动态仓位都遵守单仓不重叠，不用未来收益反向挑当天标的。",
            ),
            limitations=(
                "日线缓存不能证明封单强度、开板次数、排队成交和真实滑点。",
                "这套体系当前更适合波段打板，不适合拿它去宣称单票做 T 的可验证优势。",
                "进入正式模拟盘主线前仍建议补分钟线/Tick 和更强的可成交性校验。",
            ),
            next_action=(
                "继续积累封板波段主线证据样本，并和今日主线值守结果并行复盘。"
            ),
        )

    def board_shadow_system_hint(self) -> str:
        return (
            "经营提示：主线首板已按 1万小账户一手制回测，日常复盘重点看分年收益、"
            "验证段收益、月度回撤和真实模拟盘闭环质量。"
        )

    @staticmethod
    def market_regime_label(regime: str) -> str:
        labels = {
            "market_data_unavailable_day": "行情异常暂停",
            "trend_main_rise_day": "趋势主升日",
            "defense_stand_aside_day": "防守空仓日",
            "": "待确认",
        }
        return labels.get(regime, regime)

    def _to_board_shadow_candidate(
        self,
        candidate: board_matrix.BoardCandidate,
        exit_case: board_matrix.ExitCase,
    ) -> LimitUpBoardShadowCandidate:
        stop_loss = round(candidate.entry_price * (1 - exit_case.stop_loss_pct), 2)
        take_profit_pct = board_matrix.resolve_take_profit_pct(candidate, exit_case)
        suggested_position_pct = board_matrix.resolve_position_pct(candidate, exit_case)
        take_profit = round(candidate.entry_price * (1 + take_profit_pct), 2)
        risk_notes = (
            "仍缺封单强度、开板次数和排队可成交验证。",
            "日线同日碰止盈止损时按止损优先。",
            "封板影子线仅在市场封板家数 20 到 150 家的热度窗口内观察。",
            "近 20 日涨幅超过 20% 的高位加速板只观察，不纳入证据样本。",
            "封板日市场上涨占比超过 70% 时使用 8% 动态止盈，否则使用 5.5% 均衡止盈。",
            "强市证据仓位 12%，普通市场保持 8%；仅用于主线复盘。",
            "主线证据复盘不直接写入当前模拟盘。",
        )
        return LimitUpBoardShadowCandidate(
            symbol=candidate.symbol,
            name=candidate.name,
            board_date=candidate.board_date,
            entry_price=candidate.entry_price,
            stop_loss=stop_loss,
            take_profit_price=take_profit,
            rank_score=candidate.rank_score,
            estimated_turnover_amount=candidate.estimated_turnover_amount,
            volume_ratio_20=candidate.volume_ratio_20,
            recent_gain_pct=candidate.recent_gain_pct,
            ma20_deviation_pct=candidate.ma20_deviation_pct,
            first_board=candidate.first_board,
            ma_bullish=candidate.ma_bullish,
            risk_notes=risk_notes,
            next_action="仅做影子验证；若后续补齐可成交数据，再进入模拟盘。",
            market_seal_count=candidate.market_seal_count,
            market_touch_count=candidate.market_touch_count,
            market_advance_ratio=candidate.market_advance_ratio,
            suggested_position_pct=suggested_position_pct,
        )

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


__all__ = ["BoardShadowReviewService"]
