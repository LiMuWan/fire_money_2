"""Paper-decision instruction DTO builders."""

from __future__ import annotations

from server.firemoney_server.application.paper_decision_text import (
    execution_friction_guard_note,
)
from server.firemoney_server.application.paper_entry_policy import PaperEntryPolicy
from server.firemoney_server.application.paper_exit_policy import PaperExitPolicy
from server.firemoney_server.domain.paper_position_sizing import (
    resolve_paper_position_size,
)
from shared.contracts import (
    OneToTwoCandidate,
    PaperAccount,
    PaperHoldingInstruction,
    PaperTradingInstruction,
    StrategyDecisionReport,
)


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


def _format_pct(value: float) -> str:
    text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


class PaperInstructionBuilder:
    """Builds paper buy/holding instructions without deciding ledger writes."""

    def __init__(
        self,
        *,
        settings,
        entry_policy: PaperEntryPolicy,
        exit_policy: PaperExitPolicy,
        holding_trade_days,
    ) -> None:
        self._settings = settings
        self._entry_policy = entry_policy
        self._exit_policy = exit_policy
        self._holding_trade_days = holding_trade_days

    def build_trading_instruction(
        self,
        strategy_report: StrategyDecisionReport,
        account: PaperAccount,
        candidate: OneToTwoCandidate,
    ) -> PaperTradingInstruction:
        position_size = resolve_paper_position_size(
            settings=self._settings,
            account=account,
            candidate=candidate,
        )
        quantity = position_size.quantity
        cash_budget = position_size.cash_budget
        first_take_profit_price = (
            candidate.exit_plan.first_take_profit_price
            if candidate.exit_plan
            else round(candidate.entry_price * 1.12, 2)
        )
        entry_quality = self._entry_policy.candidate_entry_quality(candidate)
        breakout_structure = candidate.breakout_structure
        breakout_summary = (
            breakout_structure.summary
            if breakout_structure
            else "结构突破未评分"
        )
        quality_positive_lock_price = round(
            candidate.entry_price * (1 + self._settings.positive_lock_profit_pct),
            2,
        )
        planned_max_holding_days = (
            candidate.exit_plan.max_holding_trade_days
            if candidate.exit_plan
            else self._settings.max_holding_trade_days
        )
        if strategy_report.selected_strategy_id != "board-shadow-system":
            raise ValueError(
                "paper trading instruction can only be built for board-shadow-system"
            )
        confidence = (
            "high"
            if candidate.score >= 95
            and candidate.sealing_score >= 18
            and candidate.leader_score >= 18
            and candidate.turnover_quality_score >= 86
            else "medium"
        )
        entry_trigger = (
            "开盘确认不高于 3.5%，封板资金和主线龙头分仍维持 ready，"
            "换手龙质量仍过线，模拟盘没有已有持仓，且执行摩擦未接近压力红线。"
        )
        rationale = (
            f"{_stock_label(candidate.name, candidate.symbol)} 当前分数 {candidate.score}，"
            f"封板 {candidate.sealing_score}/20，主线 {candidate.mainline_score}/20，"
            f"龙头 {candidate.leader_score}/20，"
            f"{candidate.turnover_quality_label} {candidate.turnover_quality_score}/100；"
            f"{breakout_summary}；"
            f"预设盈亏比 {self._entry_policy.candidate_reward_risk_ratio(candidate):.2f}R；"
            f"{candidate.rationale}"
        )
        risk_notes = tuple(dict.fromkeys((
            breakout_summary,
            *(
                breakout_structure.risk_notes[:2]
                if breakout_structure
                else ()
            ),
            "入场风险预算：计划止损风险 {risk:.2%}，第一目标收益 {reward:.2%}，"
            "最多承受过程回撤 {budget:.2%}。".format(
                risk=entry_quality.risk_pct,
                reward=entry_quality.reward_pct,
                budget=entry_quality.drawdown_budget_pct,
            ),
            *(
                item
                for item in candidate.warnings
                if "执行摩擦风险触发降仓" in item
            ),
            *candidate.turnover_quality_notes[:2],
            *candidate.warnings[:3],
            position_size.note,
            execution_friction_guard_note(),
            "模拟盘不是实盘，不连接真实账户，不自动下单。",
            f"策略证据截止 {strategy_report.evidence_end_date}，今日只使用盘前可见信息。",
        )))
        return PaperTradingInstruction(
            action="paper_buy" if quantity > 0 else "stand_aside",
            strategy_id=strategy_report.selected_strategy_id,
            symbol=candidate.symbol,
            name=candidate.name,
            timing="early_session",
            entry_window="09:31-09:45",
            entry_trigger=entry_trigger,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            first_take_profit_price=first_take_profit_price,
            planned_stop_risk_pct=entry_quality.risk_pct,
            planned_first_target_return_pct=entry_quality.reward_pct,
            planned_reward_risk_ratio=entry_quality.reward_risk_ratio,
            max_intratrade_drawdown_budget_pct=entry_quality.drawdown_budget_pct,
            position_pct=position_size.position_pct or candidate.position_limit_pct,
            cash_budget=cash_budget,
            quantity=quantity,
            confidence=confidence,
            rationale=rationale,
            invalidation_rules=(
                "09:31 前候选状态从 ready 变为 blocked/watch_only，取消买入。",
                "开盘涨幅超过策略上限或快速回落跌破买入参考价，取消买入。",
                "结构突破分跌破门槛、价格跌回突破线或放量确认失效，取消买入。",
                "封板资金、换手龙质量、主线持续性或市场宽度出现新的硬拦截，取消买入。",
                position_size.note,
                execution_friction_guard_note(),
                "已有持仓、当日已交易一次或可买数量不足一手，取消买入。",
            ),
            sell_rules=(
                f"质量锁盈：T+1 后浮盈至少 {_format_pct(self._settings.positive_lock_profit_pct)}，且利润覆盖过程最大回撤不低于 {self._settings.positive_lock_min_profit_drawdown_ratio:.1f}R；计划锁盈价 {quality_positive_lock_price}。",
                f"T+1 到达后浮盈达到 {_format_pct(self._settings.positive_lock_profit_pct)} 只是基础锁盈线；真正卖出还要通过过程回撤质量门槛。",
                f"若买入后仍满足强换手龙、高评分、强主线，进入主升持有：峰值涨幅达到 {_format_pct(self._settings.main_rise_runner_trailing_start_pct)} 后用 {_format_pct(self._settings.main_rise_runner_trailing_stop_pct)} 回撤锁盈，曾过基础锁盈后利润不能回落到 {_format_pct(self._settings.main_rise_runner_profit_floor_pct)} 以下。",
                (
                    candidate.exit_plan.summary
                    if candidate.exit_plan
                    else "跌破止损先预警，T+1 仍弱再卖；盈利 12% 第一止盈。"
                ),
                "强势达到 10% 后启用 2% 回撤保护。",
                f"持仓达到计划最长 {planned_max_holding_days} 个交易日仍未走强，按纪律退出。",
                "持仓硬上限 5 个交易日，超过一周不恋战。",
                "主线持续性跌破阈值且 T+1 已到，优先退出保护本金。",
            ),
            risk_notes=risk_notes,
            next_check_time="09:31",
        )

    def build_holding_instruction(
        self,
        account: PaperAccount,
        trade_date: str,
    ) -> PaperHoldingInstruction | None:
        if not account.positions:
            return None
        position = account.positions[0]
        holding_trade_days = self._holding_trade_days(
            position.opened_at,
            trade_date,
        )
        positive_lock_profit_pct = (
            self._exit_policy.quality_positive_lock_profit_pct(position)
        )
        positive_lock_price = round(position.entry_price * (1 + positive_lock_profit_pct), 2)
        max_adverse_pct = self._exit_policy.max_adverse_pct_for_position(position)
        planned_max_holding_days = (
            self._exit_policy.max_holding_trade_days_for_position(position)
        )
        first_take_profit_price = (
            position.exit_plan.first_take_profit_price
            if position.exit_plan
            else round(position.entry_price * (1 + self._settings.first_take_profit_pct), 2)
        )
        action = "hold"
        status = "manage"
        reasons: list[str] = []
        if not position.can_sell_today:
            reasons.append("T+1 未到，今天只做风险预警，不做模拟卖出。")
        elif self._exit_policy.is_main_rise_runner_protect_ready(
            position,
            position.latest_price,
        ):
            action = "sell_signal"
            status = "main_rise_runner_protect"
            reasons.append("主升持有跌破分段保护线，优先锁住强势利润。")
        elif (
            self._exit_policy.is_main_rise_runner(position)
            and self._exit_policy.is_quality_positive_lock_ready(position)
        ):
            action = "hold"
            status = "main_rise_runner_hold"
            reasons.append("强买点进入主升持有模式，暂不按 3% 基础锁盈卖飞。")
        elif self._exit_policy.is_quality_positive_lock_ready(position):
            action = "sell_signal"
            status = "profit_lock"
            reasons.append("浮盈已经达到正收益质量锁定线，利润覆盖了过程回撤，优先落袋。")
        elif position.latest_price <= position.stop_loss:
            action = "sell_signal"
            status = "stop_loss"
            reasons.append("现价已经触及或跌破止损线，T+1 到达后应执行风险卖出。")
        elif holding_trade_days >= self._settings.hard_max_holding_trade_days:
            action = "sell_signal"
            status = "time_exit"
            reasons.append("持仓达到一周硬上限，不再恋战。")
        elif holding_trade_days >= planned_max_holding_days:
            action = "watch_sell"
            status = "weak_timeout_watch"
            reasons.append(
                f"持仓已经达到计划最长 {planned_max_holding_days} 个交易日，"
                "若仍未走强，盘中风险检查应纪律退出。"
            )
        else:
            reasons.append("尚未触发卖出纪律，继续按正收益锁定、止损和时间上限管理。")

        main_rise_protect_price = self._exit_policy.main_rise_runner_protect_price(
            position
        )
        main_rise_trigger = (
            f"主升持有保护线：{main_rise_protect_price}（峰值涨幅 "
            f"{self._exit_policy.main_rise_runner_peak_return_pct(position):.2%}，达到 "
            f"{_format_pct(self._settings.main_rise_runner_trailing_start_pct)} "
            f"后回撤 {_format_pct(self._settings.main_rise_runner_trailing_stop_pct)} "
            f"锁盈；曾过基础锁盈后利润地板 "
            f"{_format_pct(self._settings.main_rise_runner_profit_floor_pct)}）。"
        )
        sell_triggers = (
            f"正收益质量锁定价：{positive_lock_price}（基础 {_format_pct(self._settings.positive_lock_profit_pct)}，过程最大回撤 {max_adverse_pct:.2%}，赚撤比要求 {self._settings.positive_lock_min_profit_drawdown_ratio:.1f}R）。",
            main_rise_trigger
            if self._exit_policy.is_main_rise_runner(position)
            else "主升持有：未达到强买点/强主线阈值，仍按普通正收益锁盈纪律。",
            f"止损价：{position.stop_loss}，跌破后用 watch --phase risk 写入风险卖出。",
            f"第一止盈价：{first_take_profit_price}。",
            f"持仓硬上限：{self._settings.hard_max_holding_trade_days} 个交易日。",
        )
        rationale = (
            f"模拟盘持仓处置：{_stock_label(position.name, position.symbol)}，"
            f"成本 {position.entry_price}，现价 {position.latest_price}，"
            f"浮盈 {position.unrealized_pnl_pct:.2%}，持仓 {holding_trade_days} 个交易日；"
            + "；".join(reasons)
        )
        return PaperHoldingInstruction(
            action=action,
            symbol=position.symbol,
            name=position.name,
            opened_at=position.opened_at,
            holding_trade_days=holding_trade_days,
            can_sell_today=position.can_sell_today,
            quantity=position.quantity,
            entry_price=position.entry_price,
            latest_price=position.latest_price,
            stop_loss=position.stop_loss,
            positive_lock_price=positive_lock_price,
            first_take_profit_price=first_take_profit_price,
            hard_exit_trade_days=self._settings.hard_max_holding_trade_days,
            unrealized_pnl=position.unrealized_pnl,
            unrealized_pnl_pct=position.unrealized_pnl_pct,
            status=status,
            rationale=rationale,
            sell_triggers=sell_triggers,
            next_check_time="10:30/14:50",
            next_command=(
                f"运行 watch --phase risk --trade-date {trade_date} 复核持仓卖点并写入模拟盘数据库。"
            ),
        )


__all__ = ["PaperInstructionBuilder"]
