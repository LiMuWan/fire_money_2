"""Notification message text helpers for the one-to-two workflow."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PositionProfileLike(Protocol):
    label: str


class ExitPlanLike(Protocol):
    summary: str


class NewsItemLike(Protocol):
    title: str


class MainlineContinuityLike(Protocol):
    theme: str
    score: float
    status: str
    news_count: int
    next_action: str
    latest_news: Sequence[NewsItemLike]


class CandidateLike(Protocol):
    symbol: str
    name: str
    score: float
    status: str
    entry_price: float
    stop_loss: float
    position_limit_pct: float
    position_profile: PositionProfileLike
    blockers: Sequence[str]
    sealing_score: float
    mainline_score: float
    leader_score: float
    leader_label: str
    exit_plan: ExitPlanLike | None
    mainline_continuity: MainlineContinuityLike | None
    turnover_quality_score: float
    turnover_quality_notes: Sequence[str]
    discipline_summary: str
    market_cap: float
    float_market_cap: float
    breakout_structure: object | None


class PaperEventLike(Protocol):
    event_type: object


class PaperClosedTradeLike(Protocol):
    symbol: str
    name: str
    exit_price: float
    quantity: int
    exit_reason: str
    holding_trade_days: int
    realized_pnl: float
    realized_pnl_pct: float
    max_favorable_pct: float
    max_adverse_pct: float
    profit_drawdown_ratio: float
    position_label: str
    warning_count: int


class PaperPositionLike(Protocol):
    symbol: str
    name: str
    quantity: int
    entry_price: float
    latest_price: float
    stop_loss: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    can_sell_today: bool
    position_label: str
    exit_plan: ExitPlanLike | None
    mainline_continuity: MainlineContinuityLike | None


class PaperAccountLike(Protocol):
    equity: float
    cash: float
    initial_cash: float
    daily_trade_count: int
    max_daily_trades: int
    positions: Sequence[PaperPositionLike]
    events: Sequence[PaperEventLike]
    closed_trades: Sequence[PaperClosedTradeLike]


class RecentSampleLike(Protocol):
    symbol: str
    name: str
    realized_pnl_pct: float
    exit_reason: str
    position_label: str


class StabilityReportLike(Protocol):
    sample_stage: str
    next_milestone: int
    strategy_boundary_suggestion: str
    recent_samples: Sequence[RecentSampleLike]


class BoardShadowCandidateLike(Protocol):
    symbol: str
    name: str
    rank_score: float
    entry_price: float
    stop_loss: float
    take_profit_price: float
    estimated_turnover_amount: float
    volume_ratio_20: float
    recent_gain_pct: float
    market_seal_count: int
    market_touch_count: int
    market_advance_ratio: float


class BoardShadowTradeLike(Protocol):
    exit_date: str
    exit_reason: str
    realized_pnl_pct: float


class QualityCheckLike(Protocol):
    label: str
    status: str
    detail: str


class BoardShadowReportLike(Protocol):
    as_of_date: str
    status: str
    summary: str
    candidate: BoardShadowCandidateLike | None
    trade: BoardShadowTradeLike | None
    quality_checks: Sequence[QualityCheckLike]
    limitations: Sequence[str]


class BoardShadowStabilityReportLike(Protocol):
    sample_count: int
    sample_stage: str
    next_milestone: int
    success_rate: float
    average_return_pct: float
    max_drawdown: float


def _stock_label(name: str | None, symbol: str | None) -> str:
    if name and symbol:
        return f"{name}（{symbol}）"
    if name:
        return name
    return symbol or ""


def _position_by_symbol(
    positions: Sequence[PaperPositionLike],
    symbol: str,
) -> PaperPositionLike | None:
    return next((position for position in positions if position.symbol == symbol), None)


def _candidate_by_symbol(
    candidates: Sequence[CandidateLike],
    symbol: str,
) -> CandidateLike | None:
    return next((candidate for candidate in candidates if candidate.symbol == symbol), None)


def _phase_label(phase: str) -> str:
    return {
        "open": "开盘确认",
        "risk": "风险复核",
        "scan": "盘前扫描",
        "auction": "竞价确认",
    }.get(phase, phase)


def _exit_reason_label(reason: str) -> str:
    if reason.startswith("discipline_weak_after_") and reason.endswith("_days"):
        days = reason.removeprefix("discipline_weak_after_").removesuffix("_days")
        return f"持仓 {days} 日未走强，按纪律退出"
    labels = {
        "main_rise_runner_trailing_lock": "主升回撤保护止盈",
        "positive_profit_lock": "正收益质量锁盈",
        "take_profit_first_target": "第一目标止盈",
        "trailing_take_profit": "强势回撤止盈",
        "stop_loss_t1": "stop_loss_t1 / 次日仍破止损卖出",
        "stop_loss": "跌破止损纪律退出",
        "mainline_fade_exit": "主线退潮退出",
        "weekly_hard_limit": "持仓超一周硬退出",
    }
    return labels.get(reason, reason.replace("_", " "))


def _account_line(account: PaperAccountLike) -> str:
    initial_cash = float(getattr(account, "initial_cash", account.equity))
    return (
        f"账户：1万小账户，本金 {initial_cash:.2f}，权益 {account.equity:.2f}，"
        f"现金 {account.cash:.2f}，持仓 {len(account.positions)}"
    )


def _candidate_action_line(candidate: CandidateLike) -> str:
    return (
        f"买入候选：{_stock_label(candidate.name, candidate.symbol)}，"
        f"分数 {candidate.score}，买入参考 {candidate.entry_price}，止损 {candidate.stop_loss}"
    )


def _candidate_brief_list(candidates: Sequence[CandidateLike], limit: int = 3) -> str:
    return "、".join(
        _stock_label(candidate.name, candidate.symbol)
        for candidate in candidates[:limit]
    )


def _format_yi(value: float) -> str:
    if value <= 0:
        return "未知"
    return f"{value / 100_000_000:.1f}亿"


def _morning_news_digest(candidates: Sequence[CandidateLike]) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for candidate in candidates:
        continuity = candidate.mainline_continuity
        if continuity is None:
            continue
        for item in continuity.latest_news:
            if item.title in seen:
                continue
            seen.add(item.title)
            source = f"（{getattr(item, 'source', '')}）" if getattr(item, "source", "") else ""
            lines.append(f"消息精华：{item.title}{source}")
            if len(lines) >= 3:
                return lines
    if lines:
        return lines
    return ["消息精华：暂未抓取到新的主线新闻，今天只按封板、成交、位置和风控纪律判断。"]


def _morning_capital_digest(
    *,
    market_temperature: int,
    candidates: Sequence[CandidateLike],
    ready: Sequence[CandidateLike],
    blocked_count: int,
) -> list[str]:
    if market_temperature <= 0 and not candidates:
        return [
            "资金动向：行情源未返回有效数据，市场温度不可判定；这不是策略防守信号，而是数据异常。"
        ]
    top = ready[0] if ready else candidates[0] if candidates else None
    if top is None:
        return [
            f"资金动向：市场温度 {market_temperature}，候选池为空；资金没有给出可执行主线，防守优先。"
        ]
    continuity = top.mainline_continuity
    theme = continuity.theme if continuity else "主线未确认"
    style = (
        getattr(top.position_profile, "capital_style_label", "")
        or getattr(top.position_profile, "label", "资金风格待确认")
    )
    cap = getattr(top, "float_market_cap", 0.0) or getattr(top, "market_cap", 0.0)
    attitude = (
        "偏进攻"
        if market_temperature >= 70 and ready
        else "谨慎试探"
        if ready
        else "防守"
    )
    lines = [
        (
            f"资金动向：市场温度 {market_temperature}，可执行 {len(ready)}/{len(candidates)}，"
            f"硬拦截 {blocked_count}；资金态度 {attitude}，主线 {theme}。"
        ),
        (
            f"资金画像：{_stock_label(top.name, top.symbol)}，{style}，"
            f"市值 {_format_yi(cap)}，换手质量 {top.turnover_quality_score}/100。"
        ),
    ]
    discipline_summary = getattr(top, "discipline_summary", "")
    if discipline_summary:
        lines.append(f"封板资金：{discipline_summary}")
    elif top.turnover_quality_notes:
        lines.append(f"封板资金：{top.turnover_quality_notes[0]}")
    return lines


def _morning_operation_read(
    *,
    data_unavailable: bool,
    ready: Sequence[CandidateLike],
) -> str:
    if data_unavailable:
        return "操作解读：行情源不可用时不猜方向、不补票，先保护模拟盘账本。"
    if ready:
        top = ready[0]
        return (
            f"操作解读：只盯 {_stock_label(top.name, top.symbol)}，消息和资金只做背景；"
            "09:31 后仍满足主板、封板、换手、主线和收益守门，才写入模拟盘。"
        )
    return "操作解读：没有主线首板可执行买点，今天空仓也是纪律的一部分。"


def one_to_two_morning_notification_message(
    *,
    report_date: str,
    market_temperature: int,
    data_unavailable: bool,
    candidates: Sequence[CandidateLike],
    account: PaperAccountLike,
    regime_label: str = "",
) -> str:
    ready = tuple(item for item in candidates if item.status == "ready")
    blocked_count = sum(1 for item in candidates if item.status == "blocked")
    action = (
        "暂停，行情不可用"
        if data_unavailable
        else "买入观察，等待 09:31 确认"
        if ready
        else "防守空仓"
    )
    next_step = (
        "下一步：先运行 doctor --market-data-timeout-seconds 20 或 schedule-health --brief 定位行情源；修复前不生成模拟买入。"
        if data_unavailable
        else "下一步：09:31 只复核排名第一的主线首板候选，满足才写入模拟盘。"
        if ready
        else "下一步：保持空仓，等待下一交易日重新扫描。"
    )
    lines = [
        f"今日动作：{action}",
        *( [f"今日战法：{regime_label}"] if regime_label else [] ),
        f"交易日：{report_date}，市场温度 {market_temperature}",
        *_morning_news_digest(candidates),
        *_morning_capital_digest(
            market_temperature=market_temperature,
            candidates=candidates,
            ready=ready,
            blocked_count=blocked_count,
        ),
        _account_line(account),
        f"小账户本金 {float(getattr(account, 'initial_cash', account.equity)):.2f}，小账户一手制上限按风控仓位执行。",
        f"候选入池：{len(candidates)} 只，等待封板、资金和主线确认。",
        f"候选池：主线首板 {len(candidates)}，可执行 {len(ready)}，硬拦截 {blocked_count}",
        _morning_operation_read(data_unavailable=data_unavailable, ready=ready),
    ]
    if data_unavailable:
        lines.append("异常原因：行情数据不可用，系统没有拿到可验证的主线候选。")
        lines.append("风险提示：行情异常暂停不是防守空仓日，不能把数据故障当成策略判断。")
        lines.append(next_step)
        return "\n".join(lines)
    if ready:
        top = ready[0]
        lines.append(_candidate_action_line(top))
        if top.mainline_continuity:
            lines.append(
                f"主线持续性：{top.mainline_continuity.theme} "
                f"{top.mainline_continuity.score}/100，"
                f"状态 {top.mainline_continuity.status}，"
                f"消息 {top.mainline_continuity.news_count} 条"
            )
        lines.append(
            f"买点证据：封板 {top.sealing_score}/20，主线 {top.mainline_score}/20，"
            f"龙头 {top.leader_score}/20，换手质量 {top.turnover_quality_score}/100"
        )
        if top.breakout_structure:
            lines.append(f"结构突破：{getattr(top.breakout_structure, 'summary', '')}")
        if top.exit_plan:
            lines.append(f"卖点纪律：{top.exit_plan.summary}")
        if len(ready) > 1:
            lines.append(f"备选观察：{_candidate_brief_list(ready[1:4])}")
    else:
        lines.append("空仓原因：今日没有达到模拟买入条件的主线首板候选。")
    blockers = tuple(item for item in candidates if item.blockers)
    if blockers:
        lines.append(
            "主要拦截："
            + "；".join(
                f"{_stock_label(candidate.name, candidate.symbol)}：{candidate.blockers[0]}"
                for candidate in blockers[:2]
            )
        )
    lines.append(
        "纪律：只做主板 10cm 主线首板龙头候选；"
        "1万小账户按一手制执行，一手成本超限就空仓；"
        "模拟盘严格 T+1，当天买入只预警不卖出。"
    )
    lines.append(next_step)
    return "\n".join(lines)


def one_to_two_watch_notification_message(
    *,
    phase: str,
    trade_date: str,
    ready: Sequence[CandidateLike],
    account: PaperAccountLike,
    latest_event: str,
    sell_event_types: set[object],
    stop_warning_event_type: object,
) -> str:
    lines = [
        _account_line(account),
        f"交易日：{trade_date}",
        f"阶段：{_phase_label(phase)}",
    ]
    latest_closed_sample = account.closed_trades[0] if account.closed_trades else None
    latest_event_type = account.events[0].event_type if account.events else None
    if phase == "risk" and latest_closed_sample and latest_event_type in sell_event_types:
        lines.extend(
            [
                f"今日动作：卖出 {_stock_label(latest_closed_sample.name, latest_closed_sample.symbol)}",
                f"模拟卖出：{_stock_label(latest_closed_sample.name, latest_closed_sample.symbol)}",
                f"卖出价：{latest_closed_sample.exit_price}；数量 {latest_closed_sample.quantity} 股",
                f"退出原因：{_exit_reason_label(latest_closed_sample.exit_reason)}；持仓 {latest_closed_sample.holding_trade_days} 日",
                f"实现盈亏：{latest_closed_sample.realized_pnl:.2f} ({latest_closed_sample.realized_pnl_pct:.2%})",
                (
                    f"收益质量：顺风 {latest_closed_sample.max_favorable_pct:.2%}，"
                    f"回撤 {latest_closed_sample.max_adverse_pct:.2%}，"
                    f"赚撤比 {latest_closed_sample.profit_drawdown_ratio:.2f}R"
                ),
                f"位置：{latest_closed_sample.position_label}；止损预警 {latest_closed_sample.warning_count} 次",
            ]
        )
        matched_position = _position_by_symbol(account.positions, latest_closed_sample.symbol)
        matched_ready = _candidate_by_symbol(ready, latest_closed_sample.symbol)
        continuity = (
            matched_position.mainline_continuity
            if matched_position and matched_position.mainline_continuity
            else matched_ready.mainline_continuity
            if matched_ready and matched_ready.mainline_continuity
            else None
        )
        if continuity:
            lines.append(
                f"主线持续性：{continuity.theme} {continuity.score}/100，"
                f"状态 {continuity.status}，消息 {continuity.news_count} 条"
            )
            if continuity.latest_news:
                lines.append(f"最新消息：{continuity.latest_news[0].title}")
    elif (
        phase == "risk"
        and latest_event_type == stop_warning_event_type
        and account.positions
    ):
        position = account.positions[0]
        lines.extend(
            [
                f"今日动作：止损预警 {_stock_label(position.name, position.symbol)}",
                f"止损预警：{_stock_label(position.name, position.symbol)}",
                f"当前价 {position.latest_price}，止损价 {position.stop_loss}",
                f"浮动盈亏：{position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})",
                f"位置：{position.position_label}",
                "T+1 处理：当日只预警不卖出，下一交易日仍低于止损再模拟卖出。",
            ]
        )
        if position.mainline_continuity:
            lines.append(
                f"主线持续性：{position.mainline_continuity.theme} "
                f"{position.mainline_continuity.score}/100，"
                f"消息 {position.mainline_continuity.news_count} 条，"
                f"{position.mainline_continuity.next_action}"
            )
    elif account.positions:
        position = account.positions[0]
        sell_state = "可按纪律卖出" if position.can_sell_today else "T+1 未到，只预警不卖出"
        stock = _stock_label(position.name, position.symbol)
        if phase == "open":
            lines.extend(
                [
                    f"今日动作：买入 {stock}",
                    f"模拟买入：{stock} {position.quantity} 股",
                    f"买入价：{position.entry_price}；成交金额 {position.position_value:.2f}",
                ]
            )
        else:
            lines.extend(
                [
                    f"今日动作：持仓风控 {stock}",
                    f"持仓复核：{stock} {position.quantity} 股",
                    f"持仓成本：{position.entry_price}；当前市值 {position.position_value:.2f}",
                ]
            )
        lines.extend(
            [
                f"成本 {position.entry_price}，现价 {position.latest_price}，止损 {position.stop_loss}",
                f"浮动盈亏：{position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})",
                f"纪律状态：{sell_state}",
            ]
        )
        if position.exit_plan:
            lines.append(f"卖点计划：{position.exit_plan.summary}")
        if position.mainline_continuity:
            lines.append(
                f"主线持续性：{position.mainline_continuity.theme} "
                f"{position.mainline_continuity.score}/100，"
                f"状态 {position.mainline_continuity.status}，"
                f"消息 {position.mainline_continuity.news_count} 条"
            )
            if position.mainline_continuity.latest_news:
                lines.append(
                    f"最新消息：{position.mainline_continuity.latest_news[0].title}"
                )
    elif ready:
        candidate = ready[0]
        lines.extend(
            [
                f"今日动作：观察 {_stock_label(candidate.name, candidate.symbol)}",
                f"观察候选：{_stock_label(candidate.name, candidate.symbol)} 分数 {candidate.score}",
                f"标签：{candidate.leader_label or candidate.position_profile.label}；"
                f"换手质量 {candidate.turnover_quality_score}/100；"
                f"封板 {candidate.sealing_score}/20；买入参考 {candidate.entry_price}；止损 {candidate.stop_loss}",
                f"仓位上限：{candidate.position_limit_pct:.0%}；状态：{candidate.status}",
            ]
        )
        if candidate.turnover_quality_notes:
            lines.append(f"买点质量：{candidate.turnover_quality_notes[0]}")
        if candidate.breakout_structure:
            lines.append(
                f"结构突破：{getattr(candidate.breakout_structure, 'summary', '')}"
            )
        if candidate.exit_plan:
            lines.append(f"卖点计划：{candidate.exit_plan.summary}")
        if candidate.mainline_continuity:
            lines.append(
                f"主线持续性：{candidate.mainline_continuity.theme} "
                f"{candidate.mainline_continuity.score}/100，"
                f"{candidate.mainline_continuity.next_action}"
            )
    else:
        lines.append("今日动作：空仓，当前无可执行候选。")
    lines.append(f"最新事件：{latest_event}")
    lines.append("提醒：模拟盘不是实盘，不连接真实账户，不自动下单。")
    return "\n".join(lines)


def one_to_two_watch_notification_title(
    *,
    phase: str,
    trade_date: str,
    latest_event_trade_date: str | None,
    is_buy_event: bool,
    is_sell_event: bool,
    latest_event_name: str | None,
    latest_event_symbol: str | None,
) -> str:
    if latest_event_trade_date != trade_date:
        return "FireMoney 主线首板盘中"
    if phase == "open" and is_buy_event:
        return f"FireMoney 模拟买入：{_stock_label(latest_event_name, latest_event_symbol)}"
    if phase == "risk" and is_sell_event:
        return f"FireMoney 模拟卖出：{_stock_label(latest_event_name, latest_event_symbol)}"
    return "FireMoney 主线首板盘中"


def one_to_two_end_of_day_notification_message(
    *,
    report_date: str,
    account: PaperAccountLike,
    warning_count: int,
    t1_sell_count: int,
    realized_pnl: float,
    stability_report: StabilityReportLike,
    board_shadow_hint: str,
    data_unavailable: bool,
    regime_label: str = "",
) -> str:
    next_milestone = (
        f"{stability_report.next_milestone} 笔"
        if stability_report.next_milestone
        else "滚动复盘"
    )
    action = "暂停，行情不可用" if data_unavailable else "防守空仓" if not account.positions else "持仓观察"
    latest_sample = stability_report.recent_samples[0] if stability_report.recent_samples else None
    lines = [
        f"今日动作：{action}",
        *( [f"今日战法：{regime_label}"] if regime_label else [] ),
        f"交易日：{report_date}",
        _account_line(account),
        f"交易结果：今日事件 {len(account.events)}，止损预警 {warning_count}，T+1 卖出 {t1_sell_count}，已实现盈亏 {realized_pnl:.2f}",
        f"稳定性：已归档 {len(account.closed_trades)} 笔，阶段 {stability_report.sample_stage}，下一门槛 {next_milestone}",
    ]
    if data_unavailable:
        lines.append("风险提示：行情数据不可用，今日没有生成新的模拟买入，尾盘只归档和复盘。")
    if latest_sample:
        lines.append(
            f"最近闭环：{_stock_label(latest_sample.name, latest_sample.symbol)}，收益 {latest_sample.realized_pnl_pct:.2%}，"
            f"退出原因 {_exit_reason_label(latest_sample.exit_reason)}，位置 {latest_sample.position_label}"
        )
        lines.append(
            f"最新样本：{_stock_label(latest_sample.name, latest_sample.symbol)}，收益 {latest_sample.realized_pnl_pct:.2%}"
        )
    else:
        lines.append("最近闭环：暂无完成样本，继续按主线首板闭环观察。")
        lines.append("最新样本：暂无完成样本，继续按主线首板闭环观察。")
    if account.positions:
        position = account.positions[0]
        lines.append(
            f"隔夜观察：{_stock_label(position.name, position.symbol)}，止损 {position.stop_loss}，"
            f"{'次日可卖' if position.can_sell_today else '仍受 T+1 约束'}"
        )
        if position.exit_plan:
            lines.append(f"隔夜卖点：{position.exit_plan.summary}")
        if position.mainline_continuity:
            lines.append(
                f"主线持续性：{position.mainline_continuity.theme} "
                f"{position.mainline_continuity.score}/100，"
                f"{position.mainline_continuity.next_action}"
            )
    else:
        lines.append("当前无持仓，等待下一交易日重新扫描主线首板候选池。")
    lines.append(f"风险提示：{stability_report.strategy_boundary_suggestion}")
    lines.append("纪律：尾盘只归档和评估边界，不改变当日交易。")
    lines.append(board_shadow_hint)
    lines.append("下一步：明日 08:50 早评，09:31 只在主线首板候选通过时写入模拟盘。")
    return "\n".join(lines)


def board_shadow_notification_message(
    *,
    report: BoardShadowReportLike,
    stability_report: BoardShadowStabilityReportLike,
    sample_recorded: bool,
) -> str:
    lines = [
        f"观察日：{report.as_of_date}",
        f"状态：{report.status}",
        f"样本记录：{'已写入独立影子样本账本' if sample_recorded else '未写入，保持观察'}",
        report.summary,
    ]
    if report.candidate:
        candidate = report.candidate
        lines.extend(
            [
                f"候选：{_stock_label(candidate.name, candidate.symbol)} rank={candidate.rank_score:.2f}",
                (
                    f"封板价 {candidate.entry_price:.2f}，止损 "
                    f"{candidate.stop_loss:.2f}，止盈 {candidate.take_profit_price:.2f}"
                ),
                (
                    f"成交额约 {candidate.estimated_turnover_amount:.0f}，"
                    f"20日量比 {candidate.volume_ratio_20:.2f}，"
                    f"近20日涨幅 {candidate.recent_gain_pct:.2%}"
                ),
                (
                    f"市场热度：封板 {candidate.market_seal_count} 家，"
                    f"触板 {candidate.market_touch_count} 家，"
                    f"上涨占比 {candidate.market_advance_ratio:.2%}"
                ),
            ]
        )
    if report.trade:
        trade = report.trade
        lines.append(
            f"回放卖点：{trade.exit_date} {trade.exit_reason}，收益 {trade.realized_pnl_pct:.2%}"
        )
    else:
        lines.append("回放卖点：未生成闭环交易，不能进入样本统计。")
    lines.extend(
        [
            (
                "累计证据样本："
                f"{stability_report.sample_count} 笔，胜率 "
                f"{stability_report.success_rate:.2%}，平均收益 "
                f"{stability_report.average_return_pct:.2%}，最大回撤 "
                f"{stability_report.max_drawdown:.2%}"
            ),
            f"阶段门槛：{stability_report.sample_stage}，下一门槛 {stability_report.next_milestone or '滚动复核'}",
            "边界：封板波段主线已是模拟盘经营主线；仍不代表实盘交易指令，不连接真实账户。",
        ]
    )
    if report.quality_checks:
        first_check = report.quality_checks[-1]
        lines.append(f"质量检查：{first_check.label} {first_check.status}，{first_check.detail}")
    if report.limitations:
        lines.append(f"限制：{report.limitations[0]}")
    lines.append("下一步：继续积累 30/50/100 笔样本，并补齐封单、开板、滑点和主线消息持续性。")
    return "\n".join(lines)


__all__ = [
    "board_shadow_notification_message",
    "one_to_two_end_of_day_notification_message",
    "one_to_two_morning_notification_message",
    "one_to_two_watch_notification_title",
    "one_to_two_watch_notification_message",
]
