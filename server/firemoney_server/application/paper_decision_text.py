"""Text helpers for paper-trading decision reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Callable, Protocol


class PaperDecisionTextSettings(Protocol):
    max_position_pct: float
    initial_cash: float
    paper_entry_mainboard_only: bool
    small_account_mode_enabled: bool
    small_account_min_lot_shares: int
    small_account_target_position_pct: float
    small_account_reduced_target_position_pct: float
    small_account_max_position_pct: float
    small_account_reduced_max_position_pct: float
    positive_lock_profit_pct: float
    positive_lock_min_profit_drawdown_ratio: float
    paper_guard_min_profit_drawdown_ratio: float
    paper_guard_max_consecutive_quality_failures: int
    paper_guard_review_sample: int
    paper_guard_min_win_rate: float
    paper_guard_min_average_return_pct: float
    paper_guard_reduced_position_pct: float
    min_turnover_dragon_score: float
    minimum_reward_risk_ratio: float
    hard_max_holding_trade_days: int


class StrategyDecisionReportLike(Protocol):
    selected_strategy_id: str
    selected_action: str
    evidence_end_date: str
    market_regime: str


class PaperAccountLike(Protocol):
    equity: float
    cash: float
    positions: Sequence[object]
    daily_trade_count: int
    max_daily_trades: int


class PaperTradingGuardDecisionLike(Protocol):
    status: str
    action: str
    review_sample_count: int
    win_rate: float
    average_return_pct: float
    max_drawdown_pct: float
    suggested_position_pct: float
    reasons: Sequence[str]


class PaperTradingInstructionLike(Protocol):
    name: str
    symbol: str
    entry_window: str
    entry_price: float
    position_pct: float
    cash_budget: float
    quantity: int
    stop_loss: float
    first_take_profit_price: float
    planned_stop_risk_pct: float
    planned_first_target_return_pct: float
    planned_reward_risk_ratio: float
    max_intratrade_drawdown_budget_pct: float
    entry_trigger: str
    rationale: str
    invalidation_rules: Sequence[str]
    sell_rules: Sequence[str]
    risk_notes: Sequence[str]


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


def execution_friction_guard_note() -> str:
    return (
        "执行摩擦守门：回测压力显示 1.00% 往返成本下最弱年份 2021 "
        "只剩约 +1.71%，若盘口排队、炸板风险或预估滑点接近 1.00%，"
        "本次模拟买入应降仓或跳过。"
    )

def position_recovery_guard_note(
    *,
    current_position_pct: float,
    max_position_pct: float,
    format_pct: Callable[[float], str],
) -> str:
    if current_position_pct + 0.0001 >= max_position_pct:
        return (
            f"仓位恢复纪律：当前已是进攻档 {format_pct(current_position_pct)}，"
            "继续保持每天最多一笔、买点不过线不追、卖点触发不恋战。"
        )
    return (
        f"仓位恢复纪律：当前 {format_pct(current_position_pct)}，暂不放大到 "
        f"{format_pct(max_position_pct)}；只有收益守门 allow_full、无执行摩擦降仓提示、"
        "买点仍为高质量强换手龙时，才恢复进攻档。"
    )


class PaperHoldingInstructionLike(Protocol):
    action: str
    status: str
    name: str
    symbol: str
    quantity: int
    entry_price: float
    latest_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    positive_lock_price: float
    stop_loss: float
    first_take_profit_price: float
    holding_trade_days: int
    can_sell_today: bool
    rationale: str
    sell_triggers: Sequence[str]


def paper_decision_rules(
    settings: PaperDecisionTextSettings,
    *,
    format_pct: Callable[[float], str],
    current_position_pct: float | None = None,
) -> tuple[str, ...]:
    position_pct = (
        settings.paper_guard_reduced_position_pct
        if current_position_pct is None
        else current_position_pct
    )
    return (
        f"正收益锁盈也必须过质量门槛：T+1 后不仅要达到 {format_pct(settings.positive_lock_profit_pct)}，还要满足利润覆盖过程最大回撤不低于 {settings.positive_lock_min_profit_drawdown_ratio:.1f}R。",
        f"模拟盘收益质量：盈利样本必须做到收益覆盖过程最大回撤，赚撤比不低于 {settings.paper_guard_min_profit_drawdown_ratio:.1f}R；不达标先降仓继续验证。",
        f"模拟盘质量暂停线：连续 {settings.paper_guard_max_consecutive_quality_failures} 笔收益质量失败时，今日不再生成新的模拟买入。",
        f"模拟盘收益守门：最近 {settings.paper_guard_review_sample} 笔胜率不低于 {format_pct(settings.paper_guard_min_win_rate)}，平均收益不低于 {format_pct(settings.paper_guard_min_average_return_pct)}；连续亏损或回撤超线则暂停开仓。",
        "先由策略决策简报选主策略，再由模拟盘指挥单生成唯一模拟盘动作。",
        "长期赚钱证据只来自封板波段主线；其他研究项不进入每日经营买入路由。",
        (
            "模拟盘买入默认只做沪深主板 10cm：创业板、科创板、北交所不进入买入候选，只可作为证据观察。"
            if getattr(settings, "paper_entry_mainboard_only", True)
            else "模拟盘买入允许非主板候选，但仍必须通过独立风险约束。"
        ),
        f"封板波段主线买入前必须通过主线门槛：封板热度 20-150、20 日涨幅不超过 20%、量比不低于 1.0、均线多头、换手质量不低于 {settings.min_turnover_dragon_score:.0f}/100；不再用普通一进二 2R 口径硬卡已验证主线。",
        f"T+1 到达后浮盈达到 {format_pct(settings.positive_lock_profit_pct)} 只是基础锁盈线；真正卖出还要通过过程回撤质量门槛。",
        f"持仓硬上限 {settings.hard_max_holding_trade_days} 个交易日，超过一周不恋战。",
        "每天最多一笔，已有持仓或当日已交易则不再开新仓。",
        small_account_position_note(settings),
        "默认早盘执行；若 14:50 前仍未触发且候选未走弱，才允许尾盘复核，不追高补票。",
        execution_friction_guard_note(),
        (
            "小账户仓位恢复纪律：先恢复到一手可控交易，不把仓位放大当成赚钱能力；"
            "只有真实闭环收益守门 allow_full，才允许从降档一手规则回到常态一手规则。"
            if getattr(settings, "small_account_mode_enabled", False)
            else position_recovery_guard_note(
                current_position_pct=position_pct,
                max_position_pct=settings.max_position_pct,
                format_pct=format_pct,
            )
        ),
        "每次改策略后，仍必须从 2024-01-01 做逐日快照回测，买点不得使用未来走势。",
    )


def small_account_position_note(settings: PaperDecisionTextSettings) -> str:
    if not getattr(settings, "small_account_mode_enabled", False):
        return (
            "仓位规则：按固定比例仓位执行，收益守门未恢复前不放大风险。"
        )
    return (
        "小账户一手制：初始资金 "
        f"{settings.initial_cash:.0f} 元，A 股按 "
        f"{settings.small_account_min_lot_shares} 股一手；常态目标 "
        f"{settings.small_account_target_position_pct:.0%}，降档目标 "
        f"{settings.small_account_reduced_target_position_pct:.0%}，"
        f"单票硬上限 {settings.small_account_max_position_pct:.0%}，"
        f"收益守门降档时硬上限 {settings.small_account_reduced_max_position_pct:.0%}；"
        "一手成本超过上限就跳过，不为交易次数硬买。"
    )


def paper_decision_notification_message(
    *,
    report_date: str,
    strategy_report: StrategyDecisionReportLike,
    status: str,
    summary: str,
    instruction: PaperTradingInstructionLike | None,
    holding_instruction: PaperHoldingInstructionLike | None,
    candidate_count: int,
    ready_count: int,
    blocked_count: int,
    account: PaperAccountLike,
    guard_decision: PaperTradingGuardDecisionLike,
    next_action: str,
) -> str:
    lines = [
        f"交易日：{report_date}",
        f"状态：{status}",
        f"市场状态：{strategy_report.market_regime}",
        f"主策略：{strategy_report.selected_strategy_id} / {strategy_report.selected_action}",
        f"证据截止：{strategy_report.evidence_end_date}",
        summary,
        (
            f"候选池：{candidate_count} 个，ready {ready_count} 个，"
            f"blocked {blocked_count} 个。"
        ),
        (
            f"模拟盘：权益 {account.equity:.2f}，现金 {account.cash:.2f}，"
            f"持仓 {len(account.positions)}，今日已交易 {account.daily_trade_count}/{account.max_daily_trades}。"
        ),
        (
            "收益守门：{status}/{action}，近样本 {sample}，胜率 {win:.2%}，"
            "平均收益 {avg:.2%}，最大回撤 {drawdown:.2%}，建议仓位 {position:.0%}。"
        ).format(
            status=guard_decision.status,
            action=guard_decision.action,
            sample=guard_decision.review_sample_count,
            win=guard_decision.win_rate,
            avg=guard_decision.average_return_pct,
            drawdown=guard_decision.max_drawdown_pct,
            position=guard_decision.suggested_position_pct,
        ),
    ]
    if guard_decision.reasons:
        lines.append(f"守门理由：{guard_decision.reasons[0]}")

    if holding_instruction is not None:
        lines.extend(
            [
                "卖点/持仓处置：",
                (
                    f"- {holding_instruction.action} / {holding_instruction.status}："
                    f"{_stock_label(holding_instruction.name, holding_instruction.symbol)} "
                    f"{holding_instruction.quantity} 股。"
                ),
                (
                    f"- 成本 {holding_instruction.entry_price}，现价 "
                    f"{holding_instruction.latest_price}，浮盈 "
                    f"{holding_instruction.unrealized_pnl:.2f} "
                    f"({holding_instruction.unrealized_pnl_pct:.2%})。"
                ),
                (
                    f"- 锁盈 {holding_instruction.positive_lock_price}，止损 "
                    f"{holding_instruction.stop_loss}，第一止盈 "
                    f"{holding_instruction.first_take_profit_price}。"
                ),
                (
                    f"- 已持仓 {holding_instruction.holding_trade_days} 个交易日，"
                    f"T+1 可卖 {holding_instruction.can_sell_today}。"
                ),
                f"- 理由：{holding_instruction.rationale}",
            ]
        )
        lines.append("卖出触发：")
        lines.extend(f"- {item}" for item in holding_instruction.sell_triggers)
    elif instruction is not None:
        lines.extend(
            [
                "买点：",
                (
                    f"- {_stock_label(instruction.name, instruction.symbol)}，窗口 "
                    f"{instruction.entry_window}，触发价 {instruction.entry_price}。"
                ),
                (
                    f"- 仓位 {instruction.position_pct:.0%}，预算 "
                    f"{instruction.cash_budget:.2f}，数量 {instruction.quantity} 股。"
                ),
                (
                    f"- 止损 {instruction.stop_loss}，第一止盈 "
                    f"{instruction.first_take_profit_price}。"
                ),
                (
                    "入场风控：止损风险 {risk:.2%}，第一目标收益 {reward:.2%}，"
                    "预设盈亏比 {ratio:.2f}R，允许过程回撤 {budget:.2%}。"
                ).format(
                    risk=instruction.planned_stop_risk_pct,
                    reward=instruction.planned_first_target_return_pct,
                    ratio=instruction.planned_reward_risk_ratio,
                    budget=instruction.max_intratrade_drawdown_budget_pct,
                ),
                f"买入触发：{instruction.entry_trigger}",
                f"买入理由：{instruction.rationale}",
            ]
        )
        lines.append("取消买入：")
        lines.extend(f"- {item}" for item in instruction.invalidation_rules)
        lines.append("风险提示：")
        lines.extend(f"- {item}" for item in getattr(instruction, "risk_notes", ()))
        lines.append("卖点纪律：")
        lines.extend(f"- {item}" for item in instruction.sell_rules)
    else:
        lines.extend(
            [
                "买点：今日不买。",
                f"原因：{summary}",
                "纪律：没有高赔率窗口时，空仓也是交易系统的一部分。",
            ]
        )

    lines.extend(
        [
            f"下一步：{next_action}",
            "边界：这是模拟盘指挥单，不连接真实账户，不自动下单，也不保证每笔盈利。",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "PaperAccountLike",
    "PaperDecisionTextSettings",
    "PaperHoldingInstructionLike",
    "PaperTradingGuardDecisionLike",
    "PaperTradingInstructionLike",
    "StrategyDecisionReportLike",
    "execution_friction_guard_note",
    "position_recovery_guard_note",
    "paper_decision_notification_message",
    "paper_decision_rules",
]
