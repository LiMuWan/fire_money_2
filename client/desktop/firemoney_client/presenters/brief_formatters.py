"""Human-readable CLI brief formatters for FireMoney reports."""

from __future__ import annotations

from typing import Any

from shared.contracts import (
    K92EmotionLiquidityReport,
    LimitUpBoardShadowSystemReport,
    MissedOpportunityReport,
    OneToTwoBetaLaunchPlan,
    OneToTwoDoctorReport,
    OneToTwoExecutionQualityReport,
    OneToTwoMorningReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    OneToTwoScheduleHealthReport,
    StrategyDecisionReport,
)

from .notification_presenter import first_notification_detail, notification_display_title


def _stock_label(name: str, symbol: str) -> str:
    return f"{name}（{symbol}）" if name else symbol


def _strategy_name(strategy_id: str) -> str:
    return {
        "board-shadow-system": "封板波段主线",
        "cash": "现金防守",
    }.get(strategy_id, strategy_id)


def _action_name(action: str) -> str:
    return {
        "operate_when_signal_exists": "有信号才进攻",
        "stand_aside": "空仓防守",
    }.get(action, action)


def _role_name(role: str) -> str:
    return {
        "main_operating_line": "每日经营主线",
        "risk_control": "风险控制",
    }.get(role, role)


def format_beta_plan_brief(plan: OneToTwoBetaLaunchPlan) -> str:
    lines = [
        f"FireMoney Beta 上线计划：{plan.status}",
        f"请求日期：{plan.requested_date}",
        f"最近交易日：{plan.trade_date}",
        f"下一交易日：{plan.next_trade_date}",
        (
            f"彩排状态：{plan.rehearsal.status}，事件 {plan.rehearsal.paper_event_count}，"
            f"通知 {plan.rehearsal.notification_record_count}"
        ),
        f"体检状态：{plan.doctor_report.status}",
    ]
    if plan.blockers:
        lines.append("阻断项：")
        lines.extend(f"- {item}" for item in plan.blockers)
    else:
        lines.append("阻断项：无")
    lines.append("建议命令：")
    lines.extend(f"{index}. {command}" for index, command in enumerate(plan.launch_commands, start=1))
    lines.append(f"下一步：{plan.next_action}")
    return "\n".join(lines)


def format_doctor_brief(report: OneToTwoDoctorReport) -> str:
    lines = [
        f"FireMoney 运行体检：{report.status}",
        f"交易日：{report.trade_date}",
        report.summary,
        "检查项：",
    ]
    lines.extend(
        (
            f"- {check.label}：{check.status}；{check.detail} "
            f"下一步：{check.next_action}"
        )
        for check in report.checks
    )
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_notifications_brief(result: Any) -> str:
    records = result.get("records", ())
    lines = [f"FireMoney 飞书行动流：{result.get('record_count', 0)} 条"]
    if not records:
        lines.append("暂无行动通知记录。")
        lines.append(f"下一步：{result.get('next_action', '')}")
        return "\n".join(lines)
    for record in records:
        title = notification_display_title(record)
        workflow = getattr(record, "workflow", "")
        status = getattr(getattr(record, "status", None), "value", getattr(record, "status", ""))
        trade_date = getattr(record, "trade_date", "")
        created_at = getattr(record, "created_at", "")
        first_line = first_notification_detail(getattr(record, "message", ""))
        lines.append(f"- {trade_date} {title} [{workflow}/{status}] {created_at}")
        if first_line:
            lines.append(f"  {first_line}")
    lines.append(f"下一步：{result.get('next_action', '')}")
    return "\n".join(lines)


def format_morning_brief(report: OneToTwoMorningReport) -> str:
    ready = tuple(item for item in report.candidates if item.status == "ready")
    blocked = tuple(item for item in report.candidates if item.status != "ready")
    notification_status = getattr(
        report.notification.status,
        "value",
        report.notification.status,
    )
    lines = [
        f"{report.notification.title or 'FireMoney 主线早评'}：{report.status}",
        f"交易日：{report.trade_date}，市场温度 {report.market_temperature}",
        report.summary,
        (
            f"候选：{len(report.candidates)}，可观察 {len(ready)}，"
            f"风险/剔除 {len(blocked)}"
        ),
        (
            f"账户：权益 {report.account.equity:.2f}，现金 {report.account.cash:.2f}，"
            f"持仓 {len(report.account.positions)}"
        ),
        f"通知：{notification_status}，webhook/app 配置 {report.notification.webhook_configured}",
    ]

    digest_lines = _morning_digest_lines(report.notification.message)
    if digest_lines:
        lines.append("早评精要：")
        lines.extend(f"- {item}" for item in digest_lines)

    if ready:
        lines.append("重点候选：")
        for index, candidate in enumerate(ready[:3], start=1):
            quality = getattr(candidate, "turnover_quality_score", 0.0)
            mainline = getattr(candidate, "mainline_score", 0.0)
            market_cap = getattr(candidate, "market_cap", 0.0)
            lines.append(
                (
                    f"{index}. {_stock_label(candidate.name, candidate.symbol)} "
                    f"综合 {candidate.score:.0f}，换手质量 {quality:.0f}/100，"
                    f"主线 {mainline:.0f}，市值 {_format_yi(market_cap)}"
                )
            )
            lines.append(
                (
                    f"   买入 {candidate.entry_price:.2f}，止损 {candidate.stop_loss:.2f}；"
                    f"{candidate.rationale or candidate.next_action}"
                )
            )
            discipline = getattr(candidate, "discipline_summary", "")
            if discipline:
                lines.append(f"   纪律：{discipline}")
    else:
        lines.append("重点候选：暂无可买候选，按纪律空仓。")

    if blocked:
        preview = "、".join(_stock_label(item.name, item.symbol) for item in blocked[:5])
        lines.append(f"风险/剔除预览：{preview}")
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_watch_brief(report: OneToTwoMorningReport) -> str:
    notification_status = getattr(
        report.notification.status,
        "value",
        report.notification.status,
    )
    ready = tuple(item for item in report.candidates if item.status == "ready")
    latest_event = report.account.events[0] if report.account.events else None
    lines = [
        f"FireMoney 盘中值守：{report.status}",
        f"交易日：{report.trade_date}，市场温度 {report.market_temperature}",
        report.summary,
        (
            f"账户：权益 {report.account.equity:.2f}，现金 {report.account.cash:.2f}，"
            f"持仓 {len(report.account.positions)}，当日交易 {report.account.daily_trade_count}/{report.account.max_daily_trades}"
        ),
        f"通知：{notification_status}，webhook/app 配置 {report.notification.webhook_configured}",
    ]
    if report.account.positions:
        lines.append("当前持仓：")
        for position in report.account.positions:
            lines.append(
                (
                    f"- {_stock_label(position.name, position.symbol)} {position.quantity} 股，"
                    f"成本 {position.entry_price}，现价 {position.latest_price}，"
                    f"浮盈 {position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})，"
                    f"止损 {position.stop_loss}，{'可卖' if position.can_sell_today else 'T+1 未到'}"
                )
            )
            if position.exit_plan:
                lines.append(f"  卖点：{position.exit_plan.summary}")
    elif ready:
        top = ready[0]
        lines.append(
            (
                f"观察候选：{_stock_label(top.name, top.symbol)}，"
                f"综合 {top.score:.0f}，买入 {top.entry_price:.2f}，止损 {top.stop_loss:.2f}"
            )
        )
    else:
        lines.append("当前动作：空仓，暂无可执行候选。")
    if latest_event:
        event_type = getattr(latest_event.event_type, "value", latest_event.event_type)
        lines.append(
            (
                f"最新事件：{event_type} "
                f"{_stock_label(latest_event.name, latest_event.symbol)} "
                f"{latest_event.price} x {latest_event.quantity}；{latest_event.message}"
            )
        )
    else:
        lines.append("最新事件：暂无模拟盘事件。")
    if report.notification.message:
        action_lines = tuple(
            line.strip()
            for line in report.notification.message.splitlines()
            if line.strip().startswith(("今日动作：", "纪律状态：", "提醒："))
        )
        if action_lines:
            lines.append("值守摘要：")
            lines.extend(f"- {line}" for line in action_lines[:4])
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def _morning_digest_lines(message: str) -> tuple[str, ...]:
    prefixes = (
        "今日战法：",
        "消息精华：",
        "资金动向：",
        "资金画像：",
        "封板资金：",
        "操作解读：",
        "主线持续性：",
        "纪律：",
    )
    picked: list[str] = []
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(prefixes):
            picked.append(line)
        if len(picked) >= 8:
            break
    return tuple(picked)


def format_strategy_decision_brief(report: StrategyDecisionReport) -> str:
    visible_options = tuple(
        option
        for option in report.options
        if option.strategy_id in {"board-shadow-system", "cash"}
    ) or report.options
    lines = [
        f"FireMoney 每日策略决策：{report.status}",
        f"交易日：{report.trade_date}",
        f"市场状态：{report.market_regime} / {report.regime_action}",
        f"K92 守门：{report.k92_regime} / {report.k92_gate}",
        f"选择：{_strategy_name(report.selected_strategy_id)} / {_action_name(report.selected_action)}",
        f"角色：{_role_name(report.selected_role)}",
        report.regime_rationale,
        report.k92_rationale,
        report.summary,
        "策略选项：",
    ]
    lines.extend(
        "{strategy} [{role}] {status} {action} {confidence} | {ret} | {dd}".format(
            strategy=_strategy_name(option.strategy_id),
            role=_role_name(option.role),
            status=option.status,
            action=_action_name(option.action),
            confidence=option.confidence,
            ret=option.expected_return_label,
            dd=option.max_drawdown_label,
        )
        for option in visible_options
    )
    lines.append("风控规则：")
    lines.extend(f"- {item}" for item in report.risk_rules)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_k92_emotion_liquidity_brief(report: K92EmotionLiquidityReport) -> str:
    lines = [
        f"FireMoney K92 情绪流动性研究：{report.status}",
        f"交易日：{report.trade_date}",
        f"情绪温度：{report.market_temperature}",
        f"状态：{report.regime_label} / {report.action}",
        report.summary,
    ]
    _extend_k92_candidates(lines, "龙头进攻候选", report.leader_candidates)
    _extend_k92_candidates(lines, "低位补涨候选", report.supplement_candidates)
    _extend_k92_candidates(lines, "题材切换观察", report.switch_candidates)
    _extend_k92_candidates(lines, "风险-only 剔除", report.risk_candidates)
    if report.stand_aside_reasons:
        lines.append("空仓原因：")
        lines.extend(f"- {item}" for item in report.stand_aside_reasons)
    lines.append("研究规则：")
    lines.extend(f"- {item}" for item in report.rules)
    lines.append("限制：")
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def _extend_k92_candidates(lines: list[str], title: str, candidates: tuple[Any, ...]) -> None:
    if not candidates:
        return
    lines.append(f"{title}：")
    for item in candidates:
        reasons = "；".join(item.reasons[:3])
        lines.append(
            f"- {_stock_label(item.name, item.symbol)} 分数 {item.score:.1f}，"
            f"换手质量 {item.turnover_quality_score:.0f}/100，"
            f"市值 {_format_yi(item.market_cap)}，{reasons}"
        )
        if item.blockers:
            lines.append(f"  阻断：{'；'.join(item.blockers[:2])}")


def _format_yi(value: float) -> str:
    if value <= 0:
        return "未知"
    return f"{value / 100_000_000:.1f} 亿"


def format_backtest_audit_brief(report: Any) -> str:
    lines = [
        f"FireMoney 回测准入：{report.status}",
        f"区间：{report.start_date} -> {report.end_date}",
        f"可用交易日：{report.usable_trade_days}/{report.requested_trade_days}",
        f"闭环样本：{report.stability_report.sample_count}",
        f"胜率：{report.stability_report.success_rate:.2%}",
        f"平均收益：{report.stability_report.average_return_pct:.2%}",
        f"最大回撤：{report.stability_report.max_drawdown:.2f}",
        "数据质量：",
    ]
    lines.extend(f"- {check.label}: {check.status} {check.detail}" for check in report.data_quality_checks)
    lines.append("局限：")
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append(f"下一步：{report.recommended_next_action}")
    return "\n".join(lines)


def format_historical_replay_brief(report: Any) -> str:
    lines = [
        f"FireMoney 历史逐日回放：{report.status}",
        f"介入日：{report.entry_date}",
        f"数据模式：{report.data_mode}",
    ]
    if report.candidate:
        lines.append(
            f"候选：{_stock_label(report.candidate.name, report.candidate.symbol)} "
            f"分数 {report.candidate.score}，换手质量 {report.candidate.turnover_quality_score}/100"
        )
        lines.append(f"买入参考：{report.candidate.entry_price}，止损：{report.candidate.stop_loss}")
    if report.trade:
        lines.extend(
            [
                f"卖出：{report.trade.exit_date} {report.trade.exit_price}，原因 {report.trade.exit_reason}",
                (
                    f"收益：{report.trade.realized_pnl_pct:.2%}，"
                    f"盈亏比：{report.trade.risk_reward_ratio:.2f}R，"
                    f"盈亏金额：{report.trade.realized_pnl:.2f}"
                ),
                f"最大顺风：{report.trade.max_favorable_pct:.2%}，最大逆风：{report.trade.max_adverse_pct:.2%}",
            ]
        )
    else:
        lines.append("交易：未生成")
    lines.append("无未来函数说明：")
    lines.extend(f"- {item}" for item in report.no_future_leakage_notes)
    lines.append("数据质量：")
    lines.extend(f"- {check.label}: {check.status} {check.detail}" for check in report.quality_checks)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_board_shadow_brief(report: Any) -> str:
    lines = [
        f"FireMoney 封板影子线：{report.status}",
        f"观察日：{report.as_of_date}",
        report.summary,
    ]
    if report.candidate:
        lines.extend(
            [
                f"候选：{_stock_label(report.candidate.name, report.candidate.symbol)} rank={report.candidate.rank_score:.2f}",
                (
                    f"买点：{report.candidate.entry_price:.2f}，"
                    f"止损：{report.candidate.stop_loss:.2f}，"
                    f"止盈：{report.candidate.take_profit_price:.2f}"
                ),
                (
                    f"热度：封板 {report.candidate.market_seal_count}，"
                    f"触板 {report.candidate.market_touch_count}，"
                    f"上涨占比 {report.candidate.market_advance_ratio:.2%}"
                ),
            ]
        )
    if report.trade:
        lines.append(f"回放：{report.trade.exit_date} {report.trade.exit_reason} {report.trade.realized_pnl_pct:.2%}")
    else:
        lines.append("回放：未生成")
    lines.append("质量检查：")
    lines.extend(f"- {check.label}: {check.status} {check.detail}" for check in report.quality_checks)
    lines.append("限制：")
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_board_shadow_stability_brief(report: Any) -> str:
    lines = [
        f"FireMoney 封板影子线稳定性：{report.status}",
        f"样本数：{report.sample_count}",
        f"阶段：{report.sample_stage}，下一门槛：{report.next_milestone or '复核'}",
        f"胜率：{report.success_rate:.2%}",
        f"平均收益：{report.average_return_pct:.2%}",
        f"最大回撤：{report.max_drawdown:.2%}",
        f"边界建议：{report.strategy_boundary_suggestion}",
    ]
    if report.exit_reason_distribution:
        lines.append("退出原因：")
        lines.extend(f"- {reason}: {count}" for reason, count in report.exit_reason_distribution.items())
    if report.recent_samples:
        lines.append("最近样本：")
        lines.extend(
            f"- {sample.as_of_date} {sample.symbol} {sample.realized_pnl_pct:.2%} {sample.exit_reason}"
            for sample in report.recent_samples[:5]
        )
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_board_shadow_system_brief(report: LimitUpBoardShadowSystemReport) -> str:
    lines = [
        f"FireMoney 封板波段交易体系：{report.status}",
        f"区间：{report.start_date} -> {report.end_date}",
        report.summary,
        "买点规则：",
    ]
    lines.extend(f"- {item}" for item in report.buy_rules)
    lines.append("卖点规则：")
    lines.extend(f"- {item}" for item in report.sell_rules)
    lines.append("仓位规则：")
    lines.extend(f"- {item}" for item in report.position_rules)
    lines.extend(
        [
            _format_system_metric("固定 8%", report.fixed_position_summary),
            _format_system_metric("固定 8% 验证段", report.fixed_position_validation),
            _format_system_metric("动态 8%/12%", report.dynamic_position_summary),
            _format_system_metric("动态 8%/12% 验证段", report.dynamic_position_validation),
        ]
    )
    if report.yearly_dynamic_position_returns:
        lines.append("动态仓位分年复合：")
        lines.extend(f"- {year}: {value:.2%}" for year, value in report.yearly_dynamic_position_returns.items())
    if report.factor_validation_notes:
        lines.append("因子验证结论：")
        lines.extend(f"- {item}" for item in report.factor_validation_notes)
    lines.append("无未来函数说明：")
    lines.extend(f"- {item}" for item in report.no_future_leakage_notes)
    lines.append("限制：")
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def _format_system_metric(label: str, metric: Any) -> str:
    return (
        f"{label}：样本 {metric.sample_count} 胜率 {metric.win_rate:.2%} "
        f"复合 {metric.position_weighted_return_pct:.2%} 回撤 {metric.max_drawdown_pct:.2%}"
    )


def format_paper_backtest_brief(report: PaperBacktestReport) -> str:
    is_k92 = report.strategy_id.startswith("k92-")
    title = (
        "FireMoney K92 情绪流动性影子回测"
        if is_k92
        else "FireMoney 模拟盘买入算法回测"
    )
    improvement_title = "研究结论：" if is_k92 else "本轮优化："
    lines = [
        f"{title}：{report.status}",
        f"区间：{report.start_date} -> {report.end_date}",
        f"算法：{_strategy_name(report.strategy_id)}",
        report.summary,
        f"数据覆盖：{report.data_coverage_start or '未知'} -> {report.data_coverage_end or '未知'}",
        _format_system_metric("全区间", report.overall),
        _format_system_metric("训练段", report.train),
        _format_system_metric("验证段", report.validation),
        "分年收益：",
    ]
    if report.negative_years:
        lines.append(f"亏损年份：{', '.join(report.negative_years)}")
    if report.weak_years:
        lines.append(f"弱年份：{', '.join(report.weak_years)}")
    lines.extend(
        (
            f"- {item.year}: {item.status} 样本 {item.sample_count} 胜率 {item.win_rate:.2%} "
            f"均值 {item.average_return_pct:.2%} 中位 {item.median_return_pct:.2%} "
            f"仓位复合 {item.position_weighted_return_pct:.2%} 回撤 {item.max_drawdown_pct:.2%}，"
            f"{item.conclusion}"
        )
        for item in report.yearly
    )
    if report.monthly_stability is not None:
        lines.append("月度稳定性：")
        lines.append(
            (
                f"- 正收益月份 {report.monthly_stability.positive_months}/"
                f"{report.monthly_stability.total_months} "
                f"({report.monthly_stability.positive_month_ratio:.2%})，"
                f"最差月份 {report.monthly_stability.worst_month} "
                f"{report.monthly_stability.worst_month_return_pct:.2%}，"
                f"最长连亏月 {report.monthly_stability.longest_losing_streak}"
            )
        )
        lines.append(f"- {report.monthly_stability.conclusion}")
    if report.current_month_notes:
        lines.append("本月回测状态：")
        lines.extend(f"- {item}" for item in report.current_month_notes)
    if report.monthly:
        lines.append("月度收益：")
        lines.extend(
            f"- {item.month}: {item.position_weighted_return_pct:.2%} ({item.status}) {item.conclusion}"
            for item in report.monthly
        )
    if report.friction_scenarios:
        lines.append("执行摩擦压力：")
        lines.extend(
            (
                f"- {item.label}: 成本 {item.roundtrip_cost_pct:.2%}，胜率 {item.win_rate:.2%}，"
                f"收益 {item.position_weighted_return_pct:.2%}，回撤 {item.max_drawdown_pct:.2%}，"
                f"验证段 {item.validation_return_pct:.2%}，最弱 {item.weakest_year} "
                f"{item.weakest_year_return_pct:.2%}，{item.status}"
            )
            for item in report.friction_scenarios
        )
    if report.return_target is not None:
        lines.append("年化 100% 目标检查：")
        lines.append(
            (
                f"- 最弱完整年份 {report.return_target.weakest_year}: "
                f"{report.return_target.weakest_year_return_pct:.2%}，"
                f"线性仓位倍数 {report.return_target.required_linear_position_multiple:.2f}x，"
                f"推算回撤 {report.return_target.projected_max_drawdown_pct:.2%}"
            )
        )
        lines.append(f"- {report.return_target.conclusion}")
    if report.efficiency_candidates:
        lines.append("同仓位效率挑战者：")
        lines.extend(
            (
                f"- {item.label}: 收益 {item.total_return_pct:.2%}，回撤 {item.max_drawdown_pct:.2%}，"
                f"验证段 {item.validation_return_pct:.2%}，最弱完整年 {item.weakest_full_year_return_pct:.2%}，"
                f"正收益月份 {item.monthly_positive_ratio:.2%}，最差月 {item.worst_month_return_pct:.2%}"
            )
            for item in report.efficiency_candidates
        )
    lines.append(improvement_title)
    lines.extend(f"- {item}" for item in report.improvement_notes)
    if report.data_coverage_notes:
        lines.append("数据覆盖说明：")
        lines.extend(f"- {item}" for item in report.data_coverage_notes)
    lines.append("无未来函数说明：")
    lines.extend(f"- {item}" for item in report.no_future_leakage_notes)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_missed_opportunities_brief(report: MissedOpportunityReport) -> str:
    lines = [
        f"FireMoney 错失机会审计：{report.status}",
        f"区间：{report.start_date} -> {report.end_date}",
        report.summary,
        (
            f"回测机会 {report.backtest_trade_count}，抓到 {report.caught_count}，"
            f"错失 {report.missed_count}，错失盈利 {report.missed_profit_count}，"
            f"约少赚 {report.missed_account_return_pct:.2%}"
        ),
    ]
    if report.items:
        lines.append("逐笔审计：")
        lines.extend(
            (
                f"- {item.trade_date} {_stock_label(item.name, item.symbol)}："
                f"理论个股 {item.net_return_pct:.2%}，账户 {item.account_return_pct:.2%}，"
                f"仓位 {item.position_pct:.2%}，{item.quantity} 股；"
                f"模拟盘 {item.paper_status}，值守 {item.watch_status}，通知 {item.notification_status}。"
                f"{item.diagnosis} 下一步：{item.next_action}"
            )
            for item in report.items
        )
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_execution_quality_brief(report: OneToTwoExecutionQualityReport) -> str:
    lines = [
        f"FireMoney 主线执行质量验证：{report.status}",
        f"标的：{report.symbol}",
        f"交易日：{report.trade_date}",
        report.summary,
        f"分钟线数量：{report.minute_bar_count}",
        f"Tick 快照数量：{report.tick_snapshot_count}",
        f"首分钟波动：{report.first_minute_range_pct:.2%}",
        f"前五分钟波动：{report.first_five_minute_range_pct:.2%}",
        f"买盘驱动分：{report.buy_drive_score:.2f}",
        f"排队失衡分：{report.queue_imbalance_score:.2f}",
        f"入场动量信号：{report.entry_momentum_signal} / {report.entry_momentum_score:.2f}",
        "入场动量原因：",
    ]
    lines.extend(f"- {item}" for item in report.entry_momentum_reasons)
    lines.append("限制：")
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_paper_trading_decision_brief(report: PaperTradingDecisionReport) -> str:
    lines = [
        f"FireMoney 模拟盘指挥单：{report.status}",
        f"交易日：{report.trade_date}",
        f"市场状态：{report.market_regime}",
        f"执行轨道：{report.execution_track}",
        f"主策略：{_strategy_name(report.selected_strategy_id)} / {_action_name(report.selected_action)}",
        f"证据截止：{report.evidence_end_date}",
        report.summary,
        f"候选：{report.candidate_count}，ready {report.ready_count}，blocked {report.blocked_count}",
        f"账户：权益 {report.account_equity:.2f}，现金 {report.account_cash:.2f}，持仓 {report.existing_position_count}",
    ]
    if report.notification:
        lines.append(
            f"通知：{report.notification.status.value}，webhook/app 配置 {report.notification.webhook_configured}"
        )
    guard = report.guard_decision
    lines.append(
        (
            f"收益守门：{guard.status}/{guard.action}，样本 {guard.review_sample_count}，"
            f"胜率 {guard.win_rate:.2%}，均值 {guard.average_return_pct:.2%}，"
            f"回撤 {guard.max_drawdown_pct:.2%}，连续亏损 {guard.consecutive_losses}，"
            f"建议仓位 {guard.suggested_position_pct:.0%}"
        )
    )
    lines.extend(f"- {item}" for item in guard.reasons)
    if report.holding_instruction:
        holding = report.holding_instruction
        lines.extend(
            [
                f"持仓处置：{holding.action} / {holding.status}",
                (
                    f"持仓：{_stock_label(holding.name, holding.symbol)} {holding.quantity} 股，"
                    f"成本 {holding.entry_price}，现价 {holding.latest_price}，"
                    f"浮盈 {holding.unrealized_pnl:.2f} ({holding.unrealized_pnl_pct:.2%})"
                ),
                (
                    f"价格线：锁盈 {holding.positive_lock_price}，止损 {holding.stop_loss}，"
                    f"第一止盈 {holding.first_take_profit_price}"
                ),
                f"处置理由：{holding.rationale}",
                "卖出触发：",
            ]
        )
        lines.extend(f"- {item}" for item in holding.sell_triggers)
    if report.instruction:
        instruction = report.instruction
        lines.extend(
            [
                f"买入：{_stock_label(instruction.name, instruction.symbol)}",
                f"窗口：{instruction.entry_window} / {instruction.timing}",
                f"触发：{instruction.entry_trigger}",
                (
                    f"价格：买入 {instruction.entry_price}，止损 {instruction.stop_loss}，"
                    f"第一止盈 {instruction.first_take_profit_price}"
                ),
                f"仓位：{instruction.position_pct:.0%}，预算 {instruction.cash_budget:.2f}，数量 {instruction.quantity}",
                (
                    f"入场风控：止损风险 {instruction.planned_stop_risk_pct:.2%}，"
                    f"第一目标收益 {instruction.planned_first_target_return_pct:.2%}，"
                    f"预设盈亏比 {instruction.planned_reward_risk_ratio:.2f}R，"
                    f"过程回撤预算 {instruction.max_intratrade_drawdown_budget_pct:.2%}"
                ),
                f"置信：{instruction.confidence}",
                f"理由：{instruction.rationale}",
                "取消条件：",
            ]
        )
        lines.extend(f"- {item}" for item in instruction.invalidation_rules)
        lines.append("卖点纪律：")
        lines.extend(f"- {item}" for item in instruction.sell_rules)
        if instruction.risk_notes:
            lines.append("风险提示：")
            lines.extend(f"- {item}" for item in instruction.risk_notes)
    else:
        lines.append("买入：今日不生成新的模拟买入。")
    lines.append("决策纪律：")
    lines.extend(f"- {item}" for item in report.decision_rules)
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_paper_trade_database_brief(report: PaperTradeDatabaseReport) -> str:
    lines = [
        f"FireMoney 模拟盘数据库：{report.status}",
        f"数据库：{report.database_path}",
        f"账户：{report.account_id or '-'} / 最近交易日 {report.last_trade_date or '-'}",
        f"权益：{report.equity:.2f}，现金：{report.cash:.2f}",
        f"已实现收益：{report.total_realized_pnl:.2f} ({report.total_realized_return_pct:.2%})",
        (
            f"闭环交易：{report.closed_trade_count}，胜率 {report.win_rate:.2%}，"
            f"平均单笔 {report.average_realized_return_pct:.2%}"
        ),
        f"持仓：{report.open_position_count}，事件：{report.event_count}，快照：{report.snapshot_count}",
        (
            f"收益质量：平均赚撤比 {report.average_profit_drawdown_ratio:.2f}R，"
            f"盈利覆盖回撤达标率 {report.risk_quality_pass_rate:.2%}"
        ),
    ]
    if report.positions:
        lines.append("当前持仓：")
        lines.extend(
            (
                f"- {_stock_label(position.name, position.symbol)} {position.quantity} 股，"
                f"成本 {position.entry_price}，现价 {position.latest_price}，"
                f"浮盈 {position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})"
            )
            for position in report.positions
        )
    if report.daily_audits:
        lines.append("每日运行审计：")
        lines.extend(
            (
                f"- {audit.trade_date} {audit.action_label}：{audit.summary} "
                f"赚撤比 {audit.average_profit_drawdown_ratio:.2f}R，"
                f"质量达标 {audit.risk_quality_pass_rate:.2%}；下一步：{audit.next_action}"
            )
            for audit in report.daily_audits[:5]
        )
    else:
        lines.append("每日运行审计：暂无买入、卖出、阻断或预警事件。")
    if report.recent_trades:
        lines.append("最近闭环交易：")
        lines.extend(
            (
                f"- {trade.closed_at} {_stock_label(trade.name, trade.symbol)} "
                f"{trade.realized_pnl:.2f} ({trade.realized_pnl_pct:.2%}) "
                f"{trade.exit_reason}，顺风 {trade.max_favorable_pct:.2%}，"
                f"回撤 {trade.max_adverse_pct:.2%}，赚撤比 {trade.profit_drawdown_ratio:.2f}R"
            )
            for trade in report.recent_trades
        )
    if report.quality_buckets:
        lines.append("买点质量分层复盘：")
        lines.extend(
            (
                f"- {_paper_quality_bucket_label(bucket.bucket)} {bucket.trade_count} 笔，"
                f"胜率 {bucket.win_rate:.2%}，平均 {bucket.average_realized_return_pct:.2%}，"
                f"赚撤比 {bucket.average_profit_drawdown_ratio:.2f}R，建议：{bucket.next_action}"
            )
            for bucket in report.quality_buckets
        )
    if report.guard_buckets:
        lines.append("入场守门分层复盘：")
        lines.extend(
            (
                f"- {_paper_guard_bucket_label(bucket.bucket)} {bucket.trade_count} 笔，"
                f"建议仓位均值 {bucket.average_suggested_position_pct:.0%}，"
                f"胜率 {bucket.win_rate:.2%}，平均 {bucket.average_realized_return_pct:.2%}，"
                f"赚撤比 {bucket.average_profit_drawdown_ratio:.2f}R，建议：{bucket.next_action}"
            )
            for bucket in report.guard_buckets
        )
    if report.recent_events:
        lines.append("最近事件：")
        lines.extend(
            f"- {event.created_at} {event.event_type} {_stock_label(event.name, event.symbol)} {event.price} x {event.quantity}"
            for event in report.recent_events
        )
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_schedule_health_brief(report: OneToTwoScheduleHealthReport) -> str:
    lines = [
        f"FireMoney 值守稳定性诊断：{report.status}",
        f"请求日期：{report.requested_date} / 交易日：{report.trade_date}",
        f"检查时间：{report.checked_at}",
        report.summary,
        f"调度审计记录：{report.scheduler_run_count}，通知记录：{report.notification_record_count}",
        "关键值守覆盖：",
    ]
    lines.extend(
        (
            f"- {item.workflow} {item.scheduled_time}: {item.status}，"
            f"调度 {item.schedule_status}，通知 {item.notification_status}；"
            f"{item.summary} 下一步：{item.next_action}"
        )
        for item in report.items
    )
    lines.append(f"下一步：{report.next_action}")
    return "\n".join(lines)


def format_scheduler_runs_brief(result: Any) -> str:
    records = tuple(result.get("records", ()))
    lines = [f"FireMoney 调度审计：{result.get('record_count', len(records))} 条"]
    if not records:
        lines.append("暂无调度审计记录。")
        lines.append(f"下一步：{result.get('next_action', '')}")
        return "\n".join(lines)
    for record in records[:5]:
        run = record.get("run", {})
        if not isinstance(run, dict):
            run = _schedule_run_to_dict(run)
        requested_time = run.get("requested_time") or record.get("requested_time", "-")
        executed = run.get("executed_count", 0)
        due = run.get("due_count", 0)
        skipped = run.get("skipped_count", 0)
        lines.append(
            (
                f"- {record.get('trade_date', '-')} {requested_time} "
                f"executed {executed}/{due}，skipped {skipped}，状态 {record.get('status', '-')}"
            )
        )
        for task in tuple(run.get("tasks", ()))[:8]:
            if not isinstance(task, dict):
                task = _schedule_task_to_dict(task)
            phase = f"/{task.get('phase')}" if task.get("phase") else ""
            notification_status = task.get("notification_status", "-")
            if hasattr(notification_status, "value"):
                notification_status = notification_status.value
            lines.append(
                (
                    f"  {task.get('mode', '-')}{phase} {task.get('scheduled_time', '-')} "
                    f"{task.get('status', '-')} / 通知 {notification_status}"
                )
            )
        next_action = run.get("next_action")
        if next_action:
            lines.append(f"  下一步：{next_action}")
    lines.append(f"下一步：{result.get('next_action', '')}")
    return "\n".join(lines)


def _schedule_run_to_dict(run: Any) -> dict[str, Any]:
    return {
        "requested_time": getattr(run, "requested_time", ""),
        "due_count": getattr(run, "due_count", 0),
        "executed_count": getattr(run, "executed_count", 0),
        "skipped_count": getattr(run, "skipped_count", 0),
        "tasks": getattr(run, "tasks", ()),
        "next_action": getattr(run, "next_action", ""),
    }


def _schedule_task_to_dict(task: Any) -> dict[str, Any]:
    status = getattr(task, "notification_status", "")
    return {
        "mode": getattr(task, "mode", ""),
        "phase": getattr(task, "phase", None),
        "scheduled_time": getattr(task, "scheduled_time", ""),
        "status": getattr(task, "status", ""),
        "notification_status": status.value if hasattr(status, "value") else status,
    }


def _paper_quality_bucket_label(bucket: str) -> str:
    labels = {
        "strong_turnover_dragon": "强换手龙",
        "valid_turnover_dragon": "有效换手龙",
        "weak_turnover_quality": "低质量换手",
        "unscored_legacy": "历史未评分",
    }
    return labels.get(bucket, bucket)


def _paper_guard_bucket_label(bucket: str) -> str:
    labels = {
        "allow_full": "守门放行满仓",
        "allow_reduced": "守门降仓",
        "stand_aside": "守门暂停",
        "unscored_legacy": "历史未记录",
    }
    return labels.get(bucket, bucket)


__all__ = [
    "format_backtest_audit_brief",
    "format_beta_plan_brief",
    "format_board_shadow_brief",
    "format_board_shadow_stability_brief",
    "format_board_shadow_system_brief",
    "format_doctor_brief",
    "format_execution_quality_brief",
    "format_historical_replay_brief",
    "format_missed_opportunities_brief",
    "format_morning_brief",
    "format_notifications_brief",
    "format_paper_backtest_brief",
    "format_paper_trade_database_brief",
    "format_paper_trading_decision_brief",
    "format_schedule_health_brief",
    "format_scheduler_runs_brief",
    "format_strategy_decision_brief",
    "format_watch_brief",
]
