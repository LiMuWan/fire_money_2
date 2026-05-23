"""Paper-trading command-sheet orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from server.firemoney_server.application.paper_decision_text import (
    paper_decision_notification_message,
    paper_decision_rules,
)
from server.firemoney_server.application.paper_trading_guard import PaperTradingGuard
from server.firemoney_server.domain.paper_position_sizing import (
    resolve_paper_position_size,
)
from shared.contracts import (
    FeishuNotificationResult,
    OneToTwoCandidate,
    PaperAccount,
    PaperHoldingInstruction,
    PaperTradingDecisionReport,
    PaperTradingGuardDecision,
    PaperTradingInstruction,
    StrategyDecisionReport,
)


class PaperDecisionSettings(Protocol):
    pass


NotifyOrPrepare = Callable[[bool, str, str], FeishuNotificationResult]
RecordNotification = Callable[[str, str, FeishuNotificationResult], None]
FormatPct = Callable[[float], str]
BuildHoldingInstruction = Callable[[PaperAccount, str], PaperHoldingInstruction | None]
PositiveCandidates = Callable[[tuple[OneToTwoCandidate, ...]], tuple[OneToTwoCandidate, ...]]
WithLiveMainlineContinuity = Callable[
    [OneToTwoCandidate, tuple[OneToTwoCandidate, ...]],
    OneToTwoCandidate,
]
GuardContract = Callable[[object], PaperTradingGuardDecision]
CandidateWithGuardLimit = Callable[[OneToTwoCandidate, object], OneToTwoCandidate]
BuildTradingInstruction = Callable[
    [StrategyDecisionReport, PaperAccount, OneToTwoCandidate],
    PaperTradingInstruction,
]
StandAsideSummary = Callable[
    [StrategyDecisionReport, PaperAccount, int, int, bool, object | None],
    str,
]


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


class PaperTradingDecisionService:
    """Builds read-only paper-trading command sheets without mutating ledgers."""

    def __init__(
        self,
        *,
        settings: PaperDecisionSettings,
        guard: PaperTradingGuard,
        notify_or_prepare: NotifyOrPrepare,
        record_notification: RecordNotification,
        format_pct: FormatPct,
        build_holding_instruction: BuildHoldingInstruction,
        positive_expectancy_candidates: PositiveCandidates,
        with_live_mainline_continuity: WithLiveMainlineContinuity | None = None,
        paper_guard_contract: GuardContract,
        candidate_with_guard_position_limit: CandidateWithGuardLimit,
        build_trading_instruction: BuildTradingInstruction,
        stand_aside_summary: StandAsideSummary | None = None,
    ) -> None:
        self._settings = settings
        self._guard = guard
        self._notify_or_prepare = notify_or_prepare
        self._record_notification = record_notification
        self._format_pct = format_pct
        self._build_holding_instruction = build_holding_instruction
        self._positive_expectancy_candidates = positive_expectancy_candidates
        self._with_live_mainline_continuity = with_live_mainline_continuity
        self._paper_guard_contract = paper_guard_contract
        self._candidate_with_guard_position_limit = candidate_with_guard_position_limit
        self._build_trading_instruction = build_trading_instruction
        self._stand_aside_summary = stand_aside_summary or self._stand_aside_summary_text

    def build_report(
        self,
        *,
        report_date: str,
        strategy_report: StrategyDecisionReport,
        candidates: tuple[OneToTwoCandidate, ...],
        account: PaperAccount,
        data_unavailable: bool,
        notify: bool = False,
        record_notification: bool = False,
    ) -> PaperTradingDecisionReport:
        holding_instruction = self._build_holding_instruction(account, report_date)
        enriched_candidates = self._with_live_continuity(candidates)
        ready = self._positive_expectancy_candidates(enriched_candidates)
        guard_result = self._guard.evaluate(
            account,
            ready[0].turnover_quality_score if ready else None,
        )
        guard_decision = self._paper_guard_contract(guard_result)
        blocked_count = sum(
            1 for candidate in enriched_candidates if candidate.status == "blocked"
        )
        can_open_new_position = (
            not account.positions
            and account.daily_trade_count < account.max_daily_trades
            and not data_unavailable
            and strategy_report.selected_action == "operate_when_signal_exists"
            and strategy_report.selected_strategy_id == "board-shadow-system"
            and guard_result.action != "stand_aside"
        )
        selected_candidate = self._first_executable_lot_candidate(
            account=account,
            candidates=ready,
            guard_result=guard_result,
        )
        candidate_instruction = (
            self._build_trading_instruction(
                strategy_report,
                account,
                selected_candidate,
            )
            if selected_candidate is not None and can_open_new_position
            else None
        )
        instruction = (
            candidate_instruction
            if candidate_instruction is not None and candidate_instruction.quantity > 0
            else None
        )
        should_buy = instruction is not None
        status = "ready_to_buy" if should_buy else "stand_aside"
        if account.positions:
            status = "holding"
        elif data_unavailable:
            status = "data_unavailable"
        elif strategy_report.selected_strategy_id != "board-shadow-system":
            status = "stand_aside"
        elif not ready:
            status = "no_signal"
        elif guard_result.action == "stand_aside":
            status = "guard_blocked"
        elif account.daily_trade_count >= account.max_daily_trades:
            status = "daily_limit_reached"

        summary = (
            f"今日模拟盘执行 {instruction.name}（{instruction.symbol}），"
            f"{instruction.timing}，仓位 {instruction.position_pct:.0%}，"
            f"触发价 {instruction.entry_price}，止损 {instruction.stop_loss}。"
            if instruction
            else self._stand_aside_summary(
                strategy_report,
                account,
                len(ready),
                blocked_count,
                data_unavailable,
                guard_result,
            )
        )
        next_action = (
            f"{instruction.next_check_time} 复核触发条件，满足后由 watch --phase open 写入模拟盘。"
            if instruction
            else "今日没有新的模拟买入指令；继续观察早评、盘中风险和尾盘复盘。"
        )
        if holding_instruction is not None:
            summary = holding_instruction.rationale
            next_action = holding_instruction.next_command
        notification = self._notify_or_prepare(
            notify,
            "FireMoney 模拟盘买卖点",
            paper_decision_notification_message(
                report_date=strategy_report.trade_date,
                strategy_report=strategy_report,
                status=status,
                summary=summary,
                instruction=instruction,
                holding_instruction=holding_instruction,
                candidate_count=len(enriched_candidates),
                ready_count=len(ready),
                blocked_count=blocked_count,
                account=account,
                guard_decision=guard_decision,
                next_action=next_action,
            ),
        )
        if notify and record_notification:
            self._record_notification(
                "paper-decision",
                strategy_report.trade_date,
                notification,
            )
        return PaperTradingDecisionReport(
            report_id=f"paper-trading-decision-{strategy_report.trade_date}",
            trade_date=strategy_report.trade_date,
            status=status,
            market_regime=strategy_report.market_regime,
            execution_track=(
                "board_shadow_system_execution"
                if strategy_report.selected_strategy_id == "board-shadow-system"
                else "cash_stand_aside"
            ),
            selected_strategy_id=strategy_report.selected_strategy_id,
            selected_action=strategy_report.selected_action,
            evidence_end_date=strategy_report.evidence_end_date,
            should_buy=should_buy,
            instruction=instruction,
            holding_instruction=holding_instruction,
            candidate_count=len(enriched_candidates),
            ready_count=len(ready),
            blocked_count=blocked_count,
            account_equity=account.equity,
            account_cash=account.cash,
            existing_position_count=len(account.positions),
            guard_decision=guard_decision,
            summary=summary,
            decision_rules=paper_decision_rules(
                self._settings,
                format_pct=self._format_pct,
                current_position_pct=guard_decision.suggested_position_pct,
            ),
            next_action=next_action,
            notification=notification,
        )

    def _with_live_continuity(
        self,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        if self._with_live_mainline_continuity is None:
            return candidates
        return tuple(
            self._with_live_mainline_continuity(candidate, candidates)
            for candidate in candidates
        )

    def _first_executable_lot_candidate(
        self,
        *,
        account: PaperAccount,
        candidates: tuple[OneToTwoCandidate, ...],
        guard_result: object,
    ) -> OneToTwoCandidate | None:
        for candidate in candidates:
            adjusted = self._candidate_with_guard_position_limit(candidate, guard_result)
            position_size = resolve_paper_position_size(
                settings=self._settings,
                account=account,
                candidate=adjusted,
            )
            if position_size.can_buy:
                return adjusted
        return None

    @staticmethod
    def _stand_aside_summary_text(
        strategy_report: StrategyDecisionReport,
        account: PaperAccount,
        ready_count: int,
        blocked_count: int,
        data_unavailable: bool = False,
        guard_result: object | None = None,
    ) -> str:
        if account.positions:
            position = account.positions[0]
            return (
                f"模拟盘已有持仓 {_stock_label(position.name, position.symbol)}，今日不开新仓，"
                "只按止损、止盈和 T+1 纪律管理。"
            )
        if (
            guard_result is not None
            and getattr(guard_result, "action", "") == "stand_aside"
        ):
            reasons = "；".join(getattr(guard_result, "reasons", ()))
            return f"模拟盘收益守门未通过，今天暂停新开仓：{reasons}"
        if data_unavailable:
            return "今日行情数据不可用，模拟盘不生成新的买入指令。"
        if account.daily_trade_count >= account.max_daily_trades:
            return "模拟盘今日交易次数已用完，剩余时间只做风险观察。"
        if strategy_report.selected_strategy_id != "board-shadow-system":
            return (
                "今日主策略为现金防守，未进入可执行主线，模拟盘空仓等待。"
            )
        if ready_count <= 0:
            return (
                f"今日早盘没有 ready 候选，硬拦截 {blocked_count} 个；"
                "空仓也是策略，不用低质量交易补次数。"
            )
        return "今日条件不完整，模拟盘不新开仓，等待下一次明确主线信号。"


__all__ = ["PaperDecisionSettings", "PaperTradingDecisionService"]
