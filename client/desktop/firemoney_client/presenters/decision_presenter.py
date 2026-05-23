"""Decision cockpit presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import (
    OneToTwoMorningReport,
    PaperTradingDecisionReport,
    StrategyDecisionReport,
)


@dataclass(frozen=True)
class DecisionCockpitView:
    action_label: str
    action_state: str
    execution_summary: str
    data_mode_line: str
    run_state: str
    regime_line: str
    next_step: str
    strategy_line: str
    buy_line: str
    buy_evidence_line: str
    sell_line: str
    risk_line: str


def _strategy_name(strategy_id: str) -> str:
    return {
        "board-shadow-system": "封板波段主线",
        "cash": "空仓防守",
    }.get(strategy_id, strategy_id)


def _action_name(action: str) -> str:
    return {
        "operate_when_signal_exists": "有信号才出手",
        "stand_aside": "空仓等待",
    }.get(action, action)


def _regime_name(regime: str) -> str:
    return {
        "market_data_unavailable_day": "行情异常暂停",
        "trend_main_rise_day": "趋势主升日",
        "defense_stand_aside_day": "防守空仓日",
    }.get(regime, regime)


def _track_name(track: str) -> str:
    return {
        "board_shadow_system_execution": "封板波段主线执行",
        "cash_stand_aside": "空仓等待",
    }.get(track, track)


def _guard_action_name(action: str) -> str:
    return {
        "allow_full": "允许进攻仓位",
        "allow_reduced": "只允许降仓试错",
        "stand_aside": "暂停开仓",
    }.get(action, action)


def _status_name(status: str) -> str:
    return {
        "ready": "就绪",
        "blocked": "阻断",
        "warning": "预警",
        "holding": "持仓中",
        "ready_to_buy": "可买入",
        "reduced": "降仓试错",
        "guard_blocked": "守门拦截",
        "stand_aside": "空仓等待",
        "data_unavailable": "数据缺失降级",
    }.get(status, status)


def _regime_action_name(action: str) -> str:
    return {
        "attack_trend_main_rise": "主升进攻",
        "defense_stand_aside": "防守等待",
        "pause_until_market_data_ready": "暂停修复行情",
    }.get(action, action)


def _k92_gate_name(gate: str) -> str:
    return {
        "confirm": "K92确认",
        "observe": "K92观察",
        "block": "K92退潮阻断",
        "not_available": "K92未接入",
    }.get(gate, gate)


@dataclass(frozen=True)
class DecisionCockpitViewBuilder:
    strategy_report: StrategyDecisionReport | None
    paper_report: PaperTradingDecisionReport | None
    watch_report: OneToTwoMorningReport

    def build(self) -> DecisionCockpitView:
        account = self.watch_report.account
        instruction = self.paper_report.instruction if self.paper_report else None
        holding = self.paper_report.holding_instruction if self.paper_report else None
        guard = self.paper_report.guard_decision if self.paper_report else None
        return DecisionCockpitView(
            action_label=self._action_label(),
            action_state=self._action_state(),
            execution_summary=self._execution_summary(),
            data_mode_line=self._data_mode_line(),
            run_state=self._run_state(),
            regime_line=self._regime_line(),
            next_step=self._next_step(),
            strategy_line=(
                f"{_strategy_name(self.strategy_report.selected_strategy_id)} / "
                f"{_action_name(self.strategy_report.selected_action)}"
                if self.strategy_report
                else "等待每日策略决策"
            ),
            buy_line=(
                f"{instruction.name}（{instruction.symbol}），买入 {instruction.entry_price}，"
                f"止损 {instruction.stop_loss}，第一止盈 {instruction.first_take_profit_price}"
                if instruction
                else "今日不生成新的模拟买入。"
            ),
            buy_evidence_line=self._buy_evidence_line(),
            sell_line=(
                f"{holding.action} / {holding.status}：{holding.rationale}"
                if holding
                else (
                    "空仓等待主线买点触发。"
                    if not account.positions
                    else "持仓按止损、锁盈、主升保护和时间纪律管理。"
                )
            ),
            risk_line=(
                f"{_status_name(guard.status)} / {_guard_action_name(guard.action)}，建议仓位 "
                f"{guard.suggested_position_pct:.0%}，盈利覆盖回撤达标率 "
                f"{guard.risk_quality_pass_rate:.2%}"
                if guard
                else "等待收益守门评估。"
            ),
        )

    def _action_label(self) -> str:
        if self.paper_report is None:
            return "等待指挥单"
        if self.paper_report.instruction:
            return (
                f"买入 {self.paper_report.instruction.name}，"
                f"仓位 {self.paper_report.instruction.position_pct:.0%}"
            )
        if self.paper_report.holding_instruction:
            if self.paper_report.holding_instruction.action == "sell_signal":
                return f"卖出信号：{self.paper_report.holding_instruction.name}"
            return f"持仓管理：{self.paper_report.holding_instruction.name}"
        return "今日不新开仓"

    def _action_state(self) -> str:
        if self.paper_report is None:
            return "neutral"
        if self.paper_report.instruction:
            return "buy"
        if (
            self.paper_report.holding_instruction
            and self.paper_report.holding_instruction.action == "sell_signal"
        ):
            return "sell"
        if self.paper_report.status in {"guard_blocked", "stand_aside", "no_buy", "no_signal"}:
            return "standby"
        return "hold"

    def _execution_summary(self) -> str:
        if self.paper_report is None:
            return "还没有生成模拟盘指挥单，先不要凭感觉交易。"
        if self.paper_report.instruction:
            instruction = self.paper_report.instruction
            return (
                f"今天只盯 {instruction.name}（{instruction.symbol}）："
                f"{instruction.entry_window} 满足触发才模拟买入，"
                f"仓位 {instruction.position_pct:.0%}，跌破条件直接取消。"
            )
        if self.paper_report.holding_instruction:
            holding = self.paper_report.holding_instruction
            if holding.action == "sell_signal":
                return (
                    f"今天优先处理卖点：{holding.name}（{holding.symbol}）"
                    f"{holding.status}，按指令退出，不恋战。"
                )
            return (
                f"今天不新开仓，先管理 {holding.name}（{holding.symbol}）："
                "盯止损、锁盈、主升保护和时间纪律。"
            )
        if self.paper_report.status in {"guard_blocked", "stand_aside", "no_buy", "no_signal"}:
            return "今天没有合格买点，空仓是纪律，不是错过机会。"
        if self.paper_report.status == "data_unavailable":
            return "行情数据不可用，今天不生成新买点，先保护模拟盘。"
        return "今天按主线指挥单执行，买点不过线就不出手。"

    def _data_mode_line(self) -> str:
        if not self.watch_report.trade_context.is_trading_day:
            return "数据来源：休市日只做本地复盘，不发送早评/晚评。"
        return "数据来源：主决策由服务端指挥单生成；若上方实时值守为红灯，先修值守再交易。"

    def _run_state(self) -> str:
        if not self.watch_report.trade_context.is_trading_day:
            return "非交易日：不发送早评、晚评，只保留本地复盘。"
        if "行情数据不可用" in self.watch_report.summary:
            return "降级运行日：行情不可用，只发异常版早评/晚评，不生成新买点。"
        if self.paper_report is not None and self.paper_report.status == "data_unavailable":
            return "降级运行日：模拟盘买点因行情缺失暂时停用。"
        return "正常交易日：只按主线买点、持仓风险和尾盘复盘执行。"

    def _next_step(self) -> str:
        if self.paper_report is None:
            return "先生成 paper-decision 指挥单。"
        if self.paper_report.holding_instruction:
            return self.paper_report.holding_instruction.next_command
        return self.paper_report.next_action

    def _regime_line(self) -> str:
        if self.strategy_report is None:
            return "市场状态：待生成"
        return (
            f"{_regime_name(self.strategy_report.market_regime)} / "
            f"{_regime_action_name(self.strategy_report.regime_action)} / "
            f"{_k92_gate_name(self.strategy_report.k92_gate)} / "
            f"{self.strategy_report.regime_rationale}"
        )

    def _buy_evidence_line(self) -> str:
        if self.paper_report is None or self.paper_report.instruction is None:
            return "买点证据：等待结构、量能、主线和风险收益同时达标。"
        instruction = self.paper_report.instruction
        evidence = next(
            (
                item
                for item in instruction.risk_notes
                if "结构突破" in item or "突破线" in item
            ),
            "",
        )
        if evidence:
            return f"买点证据：{evidence}"
        return (
            "买点证据：已通过主线、换手、结构和收益守门；"
            f"预设盈亏比 {instruction.planned_reward_risk_ratio:.2f}R。"
        )


def build_decision_cockpit_view(
    strategy_report: StrategyDecisionReport | None,
    paper_report: PaperTradingDecisionReport | None,
    watch_report: OneToTwoMorningReport,
) -> DecisionCockpitView:
    return DecisionCockpitViewBuilder(
        strategy_report=strategy_report,
        paper_report=paper_report,
        watch_report=watch_report,
    ).build()


__all__ = ["DecisionCockpitView", "build_decision_cockpit_view"]
