"""Section renderers for the FireMoney desktop preview."""

from __future__ import annotations

from typing import Any

from shared.contracts import (
    CommercialReadinessReport,
    NotificationRecord,
    OneToTwoBacktestAuditReport,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoRecentSample,
    OneToTwoScheduleHealthReport,
    OneToTwoScheduleRun,
    OneToTwoStabilityReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
    PaperTradeStatus,
    StrategyDecisionReport,
)

from .presenters.decision_presenter import build_decision_cockpit_view
from .presenters.notification_highlight import highlight_notification_lines
from .presenters.notification_presenter import notification_display_title
from .presenters.trust_presenter import (
    build_performance_status_card,
    build_trust_status_card,
)
from .render_helpers import (
    action_name as _action_name,
    bool_name as _bool_name,
    candidate_brief as _candidate_brief,
    candidate_market_cap_line as _candidate_market_cap_line,
    confidence_name as _confidence_name,
    database_status_name as _database_status_name,
    decision_status_name as _decision_status_name,
    execution_track_name as _execution_track_name,
    expected_return_label as _expected_return_label,
    guard_action_name as _guard_action_name,
    guard_status_name as _guard_status_name,
    holding_action_name as _holding_action_name,
    holding_status_name as _holding_status_name,
    k92_gate_name as _k92_gate_name,
    notification_status_name as _notification_status_name,
    paper_backtest_status_name as _paper_backtest_status_name,
    paper_quality_line as _paper_quality_line,
    phase_name as _phase_name,
    regime_action_name as _regime_action_name,
    regime_name as _regime_name,
    role_name as _role_name,
    safe_database_label as _safe_database_label,
    score_text as _score_text,
    strategy_name as _strategy_name,
    text as _text,
    timing_name as _timing_name,
    trade_context_note as _trade_context_note,
    translate_misc_text as _translate_misc_text,
    workflow_name as _workflow_name,
)


def render_after_hours_radar(report: OneToTwoMorningReport) -> str:
    candidates = tuple(report.candidates)
    if not candidates:
        return ""
    ready = tuple(item for item in candidates if item.status == "ready")
    blocked = tuple(item for item in candidates if item.status == "blocked")
    risk_watch = tuple(
        item for item in candidates if item.status != "ready" and not item.blockers
    )
    style_hit = tuple(
        item
        for item in candidates
        if item.market_cap_source != "missing"
        and 5_000_000_000 <= (item.market_cap or item.float_market_cap) <= 80_000_000_000
    )
    top_watch = ready[:5]
    blocked_preview = blocked[:6]
    risk_preview = risk_watch[:5]
    top_watch_html = "".join(
        f"""
        <li>
          <strong>{index}. {_text(_candidate_brief(item))}</strong>
          <span>上榜原因：主线首板 + 换手质量 {item.turnover_quality_score:.0f}/100 | 综合分 {item.score:.0f}</span>
          <span>资金画像：{_candidate_market_cap_line(item)} | {_text(_translate_misc_text(item.turnover_quality_label or "换手观察"))}</span>
          <span>归属：{_text(item.position_profile.capital_style_label or item.position_profile.label)} | 主线 {item.mainline_score:.0f}/20 | 龙头 {item.leader_score:.0f}/20</span>
        </li>
        """
        for index, item in enumerate(top_watch, 1)
    ) or "<li>暂无可通测正向候选，今天先防守。</li>"
    risk_html = "".join(
        f"<li><strong>{_text(_candidate_brief(item))}</strong><span>{_text(_translate_misc_text(item.warnings[0] if item.warnings else item.next_action))}</span></li>"
        for item in risk_preview
    ) or "<li>暂无风险观察候选。</li>"
    blocked_html = "".join(
        f"<li><strong>{index}. {_text(_candidate_brief(item))}</strong><span>剔除原因：{_text(_translate_misc_text(item.blockers[0] if item.blockers else item.next_action))}</span><span>{_candidate_market_cap_line(item)} | 换手质量 {item.turnover_quality_score:.0f}/100</span></li>"
        for index, item in enumerate(blocked_preview, 1)
    ) or "<li>暂无硬剔除候选。</li>"
    return f"""
      <section class="radar-card">
        <div class="radar-title">
          <span>工作日盘后③</span>
          <strong>龙虎榜雷达 {_text(report.trade_date)}</strong>
        </div>
        <p class="radar-subtitle">主线首板 + 50-800 亿市值带 + 换手龙质量 + 次日重点风控</p>
        <div class="radar-metrics">
          <div><strong>{len(candidates)}</strong><span>上榜股票</span></div>
          <div><strong>{len(ready)}</strong><span>可通测</span></div>
          <div><strong>{len(style_hit)}</strong><span>市值命中</span></div>
          <div><strong>{len(blocked)}</strong><span>硬剔除</span></div>
        </div>
        <div class="radar-section">
          <h3>30 秒结论</h3>
          <ol>
            <li>今日上榜 {len(candidates)} 只；可通测正向 {len(ready)} 只；硬剔除 {len(blocked)} 只。</li>
            <li>主线只做 50-800 亿市值带；低于 50 亿视为流动性过弱，高于 800 亿视为弹性不足。</li>
            <li>模拟盘只允许从可通测候选里生成买点；风险观察和硬剔除都不写入买入账本。</li>
          </ol>
        </div>
        <div class="radar-section">
          <h3>通测分组</h3>
          <ol class="radar-list">
            <li>可通测正向：{len(ready)} 只 | {_text("、".join(_candidate_brief(item) for item in ready[:5]) or "暂无")}</li>
            <li>风险观察：{len(risk_watch)} 只 | {_text("、".join(_candidate_brief(item) for item in risk_preview) or "暂无")}</li>
            <li>硬剔除：{len(blocked)} 只 | {_text("、".join(_candidate_brief(item) for item in blocked_preview[:5]) or "暂无")}</li>
          </ol>
        </div>
        <div class="radar-section">
          <h3>次日重点观察候选</h3>
          <ol class="radar-stock-list">
            {top_watch_html}
          </ol>
        </div>
        <div class="radar-section">
          <h3>风险观察名单</h3>
          <ol class="radar-stock-list compact">
            {risk_html}
          </ol>
        </div>
        <div class="radar-section">
          <h3>重点剔除名单</h3>
          <ol class="radar-stock-list compact">
            {blocked_html}
          </ol>
        </div>
      </section>
    """


def render_mainline_candidates(report: OneToTwoMorningReport) -> str:
    if not report.candidates:
        return '<p class="empty-note">行情不可用或今日没有符合条件的主线首板龙头候选。</p>'
    return "\n".join(
        f"""
        <article class="one-to-two-card" data-status="{_text(candidate.status)}">
          <div class="candidate-head">
            <div>
              <div class="candidate-name">{_text(candidate.name)}</div>
              <div class="candidate-code">{_text(candidate.name)}（{_text(candidate.symbol)}）</div>
            </div>
            <div class="candidate-score">{_text(_score_text(candidate.score))}</div>
          </div>
          <div class="tags">
            <span class="tag">{_text(_translate_misc_text(candidate.leader_label or candidate.position_profile.label))}</span>
            <span class="tag">{_candidate_market_cap_line(candidate)}</span>
            <span class="tag">{_text(_translate_misc_text(candidate.status))}</span>
            <span class="tag">{_text(_translate_misc_text(candidate.turnover_quality_label or "换手质量"))} {_text(candidate.turnover_quality_score)}/100</span>
            {f'<span class="tag">{_text(_translate_misc_text(candidate.breakout_structure.label))} {_text(candidate.breakout_structure.score)}/100</span>' if candidate.breakout_structure else ''}
            {"".join(f'<span class=\"tag\">{_text(_translate_misc_text(item))}</span>' for item in candidate.strategy_tags[:3])}
            <span class="tag is-risk">止损 {_text(candidate.stop_loss)}</span>
          </div>
          <p>{_text(_translate_misc_text(candidate.rationale))}</p>
          <ul class="detail-list compact">
            <li>先看动作：买入价 {_text(candidate.entry_price)}，仓位上限 {candidate.position_limit_pct:.0%}，严格 T+1，2 个交易日不走强则纪律退出。</li>
            <li>封板 {candidate.sealing_score}/20，主线 {candidate.mainline_score}/20，龙头 {candidate.leader_score}/20，竞价 {candidate.auction_score}/20</li>
            <li>换手龙质量 {candidate.turnover_quality_score}/100，位置 {candidate.position_score}/25，流动性 {candidate.liquidity_score}/15，首板质量 {candidate.first_board_score}/25</li>
            {f'<li>结构突破：{_text(_translate_misc_text(candidate.breakout_structure.summary))}</li>' if candidate.breakout_structure else ''}
            {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in (candidate.breakout_structure.risk_notes[:2] if candidate.breakout_structure else ()))}
            {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in candidate.turnover_quality_notes[:2])}
            <li>持有纪律：{_text(_translate_misc_text(candidate.discipline_summary))}</li>
            {f'<li>卖点计划：{_text(_translate_misc_text(candidate.exit_plan.summary))}</li>' if candidate.exit_plan else ''}
            {f'<li>主线跟踪：{_text(_translate_misc_text(candidate.mainline_continuity.theme))} {_text(candidate.mainline_continuity.score)}/100，消息 {candidate.mainline_continuity.news_count} 条，{_text(_translate_misc_text(candidate.mainline_continuity.next_action))}</li>' if candidate.mainline_continuity else ''}
            {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in candidate.blockers[:3])}
            {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in candidate.warnings[:2])}
          </ul>
        </article>
        """
        for candidate in report.candidates
    )


def render_one_to_two_candidates(report: OneToTwoMorningReport) -> str:
    if not report.candidates:
        return '<p class="empty-note">行情不可用或今日没有符合条件的一进二候选。</p>'
    return render_mainline_candidates(report)


def render_one_to_two_position(report: OneToTwoMorningReport) -> str:
    account = report.account
    if not account.positions:
        return '<p class="empty-note">当前没有模拟持仓，等待候选达到触发条件。</p>'
    position = account.positions[0]
    status_label = {
        PaperTradeStatus.HOLDING: "持仓观察",
        PaperTradeStatus.WARNING: "止损预警",
        PaperTradeStatus.CLOSED: "已归档",
        PaperTradeStatus.EMPTY: "空仓",
    }.get(position.status, position.status.value)
    action = (
        "当日只预警不卖出；下一交易日仍低于止损再模拟卖出。"
        if position.status == PaperTradeStatus.WARNING
        else "继续盯住止损位、承接强度和 T+1 纪律。"
    )
    return f"""
      <article class="one-to-two-card position-card" data-status="{_text(position.status.value)}">
        <div class="candidate-head">
          <div>
            <div class="candidate-name">{_text(position.name)}</div>
            <div class="candidate-code">{_text(position.name)}（{_text(position.symbol)}） / {_text(_translate_misc_text(position.position_label))}</div>
          </div>
          <div class="candidate-score">{position.unrealized_pnl_pct:.2%}</div>
        </div>
        <div class="tags">
          <span class="tag is-risk">{_text(status_label)}</span>
          <span class="tag">持仓 {position.quantity} 股</span>
          <span class="tag">现价 {_text(position.latest_price)}</span>
          <span class="tag is-risk">止损 {_text(position.stop_loss)}</span>
        </div>
        <ul class="risk-steps">
          <li><span>浮动盈亏</span><strong>{position.unrealized_pnl:.2f} / {position.unrealized_pnl_pct:.2%}</strong></li>
          <li><span>当前纪律</span><strong>{_text(_translate_misc_text(position.risk_note))}</strong></li>
          {f'<li><span>卖点计划</span><strong>{_text(_translate_misc_text(position.exit_plan.summary))}</strong></li>' if position.exit_plan else ''}
          {f'<li><span>主线跟踪</span><strong>{_text(_translate_misc_text(position.mainline_continuity.theme))} {_text(position.mainline_continuity.score)}/100，消息 {position.mainline_continuity.news_count} 条，{_text(_translate_misc_text(position.mainline_continuity.next_action))}</strong></li>' if position.mainline_continuity else ''}
          <li><span>下一步</span><strong>{_text(action)}</strong></li>
        </ul>
      </article>
    """


def render_mainline_continuity(report: OneToTwoMorningReport) -> str:
    continuities = tuple(
        candidate.mainline_continuity
        for candidate in report.candidates
        if candidate.mainline_continuity is not None
    )
    if not continuities:
        return '<p class="empty-note">暂无主线持续性证据。</p>'
    by_theme = {item.theme: item for item in continuities}
    return "\n".join(
        f"""
        <article class="continuity-card" data-status="{_text(item.status)}">
          <div class="candidate-head">
            <div>
              <div class="candidate-name">{_text(_translate_misc_text(theme))}</div>
              <div class="candidate-code">主线状态 {_text(_translate_misc_text(item.status))} / 最新消息 {item.news_count} 条</div>
            </div>
            <div class="candidate-score">{_text(_score_text(item.score))}</div>
          </div>
          <ul class="detail-list compact">
            <li>同主线候选 {item.hot_stock_count}，近涨停强度 {item.limit_up_count}</li>
            <li>{_text(_translate_misc_text(item.next_action))}</li>
            {"".join(f"<li>{_text(_translate_misc_text(reason))}</li>" for reason in item.reasons[:4])}
            {"".join(f"<li>{_text(_translate_misc_text(note))}</li>" for note in item.risk_notes[:2])}
            {"".join(f"<li>消息：{_text(_translate_misc_text(news.title))}</li>" for news in item.latest_news[:2])}
          </ul>
        </article>
        """
        for theme, item in list(by_theme.items())[:3]
    )


def render_schedule_panel(
    schedule_run: OneToTwoScheduleRun | None,
    schedule_health_report: OneToTwoScheduleHealthReport | None = None,
) -> str:
    if schedule_run is None and schedule_health_report is None:
        return ""
    health_html = _render_schedule_health_diagnostics(schedule_health_report)
    if schedule_run is None:
        return f"""
          <section class="panel one-to-two-panel">
            <h2>本地调度</h2>
            {health_html}
          </section>
        """
    labels = {
        "completed": "已执行",
        "skipped": "已跳过",
        "pending": "待触发",
        "closed": "休市关闭",
        "failed": "失败",
        "expired": "已过期",
    }
    mode_labels = {
        "morning": "早盘判断",
        "watch": "盘中值守",
        "eod": "尾盘复盘",
        "board-shadow-record": "封板影子记录",
        "strategy-decision": "策略决策简报",
        "paper-decision": "模拟盘指挥单",
        "shadow": "影子样本",
    }
    items = "".join(
        f"""
        <li class="schedule-item" data-status="{_text(task.status)}">
          <span class="schedule-time">{_text(task.scheduled_time)}</span>
          <span class="schedule-name">{_text(mode_labels.get(task.mode, task.mode))}{f' / {_text(_phase_name(task.phase))}' if task.phase else ''}</span>
          <span class="schedule-status">{_text(labels.get(task.status, task.status))}</span>
        </li>
        """
        for task in schedule_run.tasks
    )
    return f"""
      <section class="panel one-to-two-panel">
        <h2>本地调度</h2>
        {health_html}
        <p class="next-action">已到 {schedule_run.requested_time}，应执行 {schedule_run.due_count} 项，已执行 {schedule_run.executed_count} 项，跳过 {schedule_run.skipped_count} 项。</p>
        <ul class="schedule-list">
          {items}
        </ul>
      </section>
    """


def _render_schedule_health_diagnostics(
    report: OneToTwoScheduleHealthReport | None,
) -> str:
    if report is None:
        return """
          <div class="schedule-diagnostics" data-status="warning">
            <div class="schedule-diagnostics__head">
              <span>漏发定位</span>
              <strong>缺少 schedule-health 报告</strong>
            </div>
            <p>先运行 schedule-health，确认今天早评/晚评是否应该发送、是否 sent。</p>
          </div>
        """
    items = "".join(_render_schedule_health_item(item) for item in report.items)
    trade_day_label = "交易日" if report.is_trading_day else "非交易日"
    return f"""
      <div class="schedule-diagnostics" data-status="{_text(report.status)}">
        <div class="schedule-diagnostics__head">
          <span>漏发定位</span>
          <strong>{_text(_translate_misc_text(report.summary))}</strong>
        </div>
        <div class="schedule-diagnostics__meta">
          <span>{_text(trade_day_label)}</span>
          <span>检查 {_text(report.checked_at)}</span>
          <span>调度审计 {report.scheduler_run_count}</span>
          <span>通知记录 {report.notification_record_count}</span>
        </div>
        <div class="schedule-health-grid">
          {items}
        </div>
        <p>{_text(_translate_misc_text(report.next_action))}</p>
      </div>
    """


def _render_schedule_health_item(item) -> str:
    workflow_label = {
        "morning": "早评",
        "eod": "晚评",
    }.get(item.workflow, item.workflow)
    status_label = {
        "ready": "正常",
        "warning": "待确认",
        "blocked": "阻断",
    }.get(item.status, item.status)
    schedule_label = {
        "not_seen": "未见调度",
        "completed": "已执行",
        "skipped": "已跳过",
        "expired": "窗口过期",
        "closed": "休市关闭",
        "failed": "执行失败",
    }.get(item.schedule_status, item.schedule_status)
    notification_label = {
        "sent": "已送达",
        "prepared": "仅生成",
        "failed": "发送失败",
        "missing": "无记录",
        "pending": "等待",
        "not_required": "不需要",
    }.get(item.notification_status, item.notification_status)
    return f"""
      <article class="schedule-health-card" data-status="{_text(item.status)}">
        <div>
          <span>{_text(workflow_label)} · {_text(item.scheduled_time)}</span>
          <strong>{_text(status_label)}</strong>
        </div>
        <div class="schedule-health-card__chips">
          <b>调度：{_text(schedule_label)}</b>
          <b>飞书：{_text(notification_label)}</b>
        </div>
        <p>{_text(_translate_misc_text(item.summary))}</p>
        <small>{_text(_translate_misc_text(item.next_action))}</small>
      </article>
    """


def render_strategy_decision_panel(report: StrategyDecisionReport | None) -> str:
    if report is None:
        return ""
    options = "".join(
        f"""
        <li>
          <strong>{_text(_strategy_name(option.strategy_id))}</strong>
          <span>{_text(_action_name(option.action))}</span>
          <span>{_text(_expected_return_label(option.expected_return_label))}；{_text(_translate_misc_text(option.max_drawdown_label))}</span>
        </li>
        """
        for option in (
            tuple(item for item in report.options if item.strategy_id in {"board-shadow-system", "cash"})
            or report.options
        )
    )
    return f"""
      <section class="panel one-to-two-panel">
        <h2>每日策略决策</h2>
        <p class="next-action">{_text(_translate_misc_text(report.summary))}</p>
        <ul class="detail-list compact">
          <li>交易日：{_text(report.trade_date)}</li>
          <li>市场状态：{_text(_regime_name(report.market_regime))} / {_text(_regime_action_name(report.regime_action))}</li>
          <li>K92 守门：{_text(_k92_gate_name(report.k92_gate))} / {_text(_translate_misc_text(report.k92_regime))}</li>
          <li>证据截止：{_text(report.evidence_end_date)}</li>
          <li>选择：{_text(_strategy_name(report.selected_strategy_id))} / {_text(_action_name(report.selected_action))}</li>
          <li>角色：{_text(_role_name(report.selected_role))}</li>
          <li>{_text(_translate_misc_text(report.regime_rationale))}</li>
          <li>{_text(_translate_misc_text(report.k92_rationale))}</li>
        </ul>
        <ul class="detail-list compact">
          {options}
        </ul>
      </section>
    """


def render_paper_decision_panel(report: PaperTradingDecisionReport | None) -> str:
    if report is None:
        return ""
    guard = report.guard_decision
    holding_html = ""
    if report.holding_instruction is not None:
        holding = report.holding_instruction
        holding_html = f"""
        <h3 class="panel-subtitle">持仓处置指令</h3>
        <ul class="detail-list compact">
          <li>动作：{_text(_holding_action_name(holding.action))} / {_text(_holding_status_name(holding.status))}</li>
          <li>标的：{_text(holding.name)}（{_text(holding.symbol)}），{holding.quantity} 股，T+1：{_text(_bool_name(holding.can_sell_today))}</li>
          <li>成本：{holding.entry_price}，现价：{holding.latest_price}，浮盈：{holding.unrealized_pnl:.2f} ({holding.unrealized_pnl_pct:.2%})</li>
          <li>锁盈价：{holding.positive_lock_price}，止损价：{holding.stop_loss}，第一止盈：{holding.first_take_profit_price}</li>
          <li>持仓：{holding.holding_trade_days} 个交易日，硬上限：{holding.hard_exit_trade_days} 个交易日</li>
          <li>{_text(_translate_misc_text(holding.rationale))}</li>
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in holding.sell_triggers)}
          <li>{_text(_translate_misc_text(holding.next_command))}</li>
        </ul>
        """
    if report.instruction is not None:
        instruction = report.instruction
        instruction_html = f"""
        <ul class="detail-list compact">
          <li>买入：{_text(instruction.name)}（{_text(instruction.symbol)}）</li>
          <li>窗口：{_text(instruction.entry_window)} / {_text(_timing_name(instruction.timing))}</li>
          <li>价格：买入 {_text(instruction.entry_price)}，止损 {_text(instruction.stop_loss)}，第一止盈 {_text(instruction.first_take_profit_price)}</li>
          <li>仓位：{instruction.position_pct:.0%}，预算 {instruction.cash_budget:.2f}，数量 {instruction.quantity}</li>
          <li>入场风控：止损风险 {instruction.planned_stop_risk_pct:.2%}，第一目标收益 {instruction.planned_first_target_return_pct:.2%}，预设盈亏比 {instruction.planned_reward_risk_ratio:.2f}R，允许过程回撤 {instruction.max_intratrade_drawdown_budget_pct:.2%}</li>
          <li>置信：{_text(_confidence_name(instruction.confidence))}</li>
          <li>触发：{_text(_translate_misc_text(instruction.entry_trigger))}</li>
        </ul>
        <h3 class="panel-subtitle">取消条件</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in instruction.invalidation_rules)}
        </ul>
        <h3 class="panel-subtitle">风险提示</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in instruction.risk_notes)}
        </ul>
        <h3 class="panel-subtitle">卖点纪律</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in instruction.sell_rules)}
        </ul>
        """
    else:
        instruction_html = """
        <ul class="detail-list compact">
          <li>买入：今日不生成新的模拟买入。</li>
          <li>纪律：空仓也是策略，不用低质量交易补次数。</li>
        </ul>
        """
    return f"""
      <section class="panel one-to-two-panel">
        <h2>模拟盘交易指挥单</h2>
        <p class="next-action">{_text(_translate_misc_text(report.summary))}</p>
        <ul class="detail-list compact">
          <li>状态：{_text(_decision_status_name(report.status))}</li>
          <li>市场状态：{_text(_regime_name(report.market_regime))}</li>
          <li>执行轨道：{_text(_execution_track_name(report.execution_track))}</li>
          <li>策略：{_text(_strategy_name(report.selected_strategy_id))} / {_text(_action_name(report.selected_action))}</li>
          <li>候选：{report.candidate_count}，可执行 {report.ready_count}，硬剔除 {report.blocked_count}</li>
          <li>账户：权益 {report.account_equity:.2f}，现金 {report.account_cash:.2f}，持仓 {report.existing_position_count}</li>
        </ul>
        <h3 class="panel-subtitle">收益守门</h3>
        <ul class="detail-list compact">
          <li>状态：{_text(_guard_status_name(guard.status))} / {_text(_guard_action_name(guard.action))}</li>
          <li>样本：{guard.review_sample_count}，胜率 {guard.win_rate:.2%}，平均收益 {guard.average_return_pct:.2%}</li>
          <li>最大回撤：{guard.max_drawdown_pct:.2%}，连续亏损：{guard.consecutive_losses}，建议仓位：{guard.suggested_position_pct:.0%}</li>
          <li>质量连败：{guard.consecutive_quality_failures}，盈利覆盖回撤达标率：{guard.risk_quality_pass_rate:.2%}</li>
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in guard.reasons)}
        </ul>
        {holding_html}
        {instruction_html}
        <h3 class="panel-subtitle">决策纪律</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in report.decision_rules)}
        </ul>
      </section>
    """


def render_trust_overview(
    *,
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    paper_report: PaperTradingDecisionReport | None,
    paper_database_report: PaperTradeDatabaseReport | None,
    doctor_report: OneToTwoDoctorReport | None,
    schedule_run: OneToTwoScheduleRun | None,
    notification_records: tuple[NotificationRecord, ...],
    schedule_health_report: OneToTwoScheduleHealthReport | None = None,
) -> str:
    trust = build_trust_status_card(
        report=report,
        watch_report=watch_report,
        paper_report=paper_report,
        doctor_report=doctor_report,
        schedule_run=schedule_run,
        schedule_health_report=schedule_health_report,
        notification_records=notification_records,
    )
    performance = build_performance_status_card(paper_database_report)
    trust_flow = _render_trust_flow(
        report=report,
        schedule_health_report=schedule_health_report,
        trust_tone=trust.tone,
    )
    return f"""
      <section class="trust-overview">
        <article class="trust-card" data-tone="{_text(trust.tone)}">
          <span>{_text(trust.title)}</span>
          <strong>{_text(trust.headline)}</strong>
          {trust_flow}
          <div class="trust-short-lines">
            <b>{_text(_translate_misc_text(trust.details[1] if len(trust.details) > 1 else trust.headline))}</b>
            <small>{_text(_translate_misc_text(trust.details[4] if len(trust.details) > 4 else "只推早评、真实模拟买入/卖出、晚评。"))}</small>
          </div>
          <p>下一步：{_text(_translate_misc_text(trust.next_action))}</p>
        </article>
        <article class="trust-card" data-tone="{_text(performance.tone)}">
          <span>{_text(performance.title)}</span>
          <strong>{_text(performance.headline)}</strong>
          <div class="permission-line">{_text(_translate_misc_text(performance.trade_permission))}</div>
          <div class="trust-metrics guard-meter-grid">
            {"".join(_render_guard_metric(label, value) for label, value in performance.metrics)}
          </div>
          <p>{_text(_translate_misc_text(performance.next_action))}</p>
        </article>
      </section>
    """


def render_pre_trade_acceptance(
    paper_report: PaperTradingDecisionReport | None,
    paper_database_report: PaperTradeDatabaseReport | None,
) -> str:
    if paper_report is None:
        return ""
    guard = paper_report.guard_decision
    instruction = paper_report.instruction
    closed_sample_count = (
        paper_database_report.closed_trade_count
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.review_sample_count
    )
    win_rate = (
        paper_database_report.win_rate
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.win_rate
    )
    profit_drawdown_ratio = (
        paper_database_report.average_profit_drawdown_ratio
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.average_profit_drawdown_ratio
    )
    realized_return = (
        paper_database_report.total_realized_return_pct
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.average_return_pct
    )
    friction_label, friction_tone, friction_detail = _execution_friction_gate(instruction)
    tone = _pre_trade_acceptance_tone(paper_report, friction_tone)
    headline = _pre_trade_acceptance_headline(paper_report, friction_tone)
    final_action = _pre_trade_acceptance_action(paper_report, friction_tone)
    target = (
        _text(f"{instruction.name}（{instruction.symbol}）")
        if instruction is not None
        else "今日暂无新开仓标的"
    )
    reason = (
        guard.reasons[0]
        if guard.reasons
        else paper_report.summary
    )
    metrics = (
        ("真实闭环", f"{closed_sample_count}", min(100.0, closed_sample_count / 30.0 * 100.0)),
        ("胜率", f"{win_rate:.0%}", min(100.0, max(0.0, win_rate * 100.0))),
        ("累计收益", f"{realized_return:.2%}", min(100.0, max(0.0, realized_return * 100.0))),
        ("赚撤比", f"{profit_drawdown_ratio:.2f}R", min(100.0, max(0.0, profit_drawdown_ratio / 3.0 * 100.0))),
    )
    metric_html = "".join(
        f"""
          <div class="acceptance-meter" style="--meter: {meter:.0f}%">
            <span>{_text(label)}</span>
            <strong>{_text(value)}</strong>
            <i aria-hidden="true"></i>
          </div>
        """
        for label, value, meter in metrics
    )
    return f"""
      <section class="pre-trade-acceptance" data-tone="{_text(tone)}" aria-label="开仓硬验收">
        <div class="acceptance-head">
          <span>开仓硬验收</span>
          <strong>{_text(headline)}</strong>
        </div>
        <div class="acceptance-target">
          <span>{target}</span>
          <b>{_text(_guard_action_name(guard.action))} / 建议仓位 {guard.suggested_position_pct:.0%}</b>
        </div>
        <div class="acceptance-metrics">
          {metric_html}
        </div>
        <div class="acceptance-gates">
          <div data-tone="{_text(_guard_gate_tone(guard.action))}">
            <span>真实收益守门</span>
            <strong>{_text(_guard_status_name(guard.status))}</strong>
          </div>
          <div data-tone="{_text(friction_tone)}">
            <span>执行摩擦</span>
            <strong>{_text(friction_label)}</strong>
          </div>
        </div>
        <p>{_text(_translate_misc_text(reason))}</p>
        <footer>
          <span>{_text(_translate_misc_text(friction_detail))}</span>
          <strong>{_text(final_action)}</strong>
        </footer>
      </section>
    """


def render_home_execution_panel(
    *,
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    paper_report: PaperTradingDecisionReport | None,
    paper_database_report: PaperTradeDatabaseReport | None,
    doctor_report: OneToTwoDoctorReport | None,
    schedule_run: OneToTwoScheduleRun | None,
    schedule_health_report: OneToTwoScheduleHealthReport | None,
    notification_records: tuple[NotificationRecord, ...],
) -> str:
    trust = build_trust_status_card(
        report=report,
        watch_report=watch_report,
        paper_report=paper_report,
        doctor_report=doctor_report,
        schedule_run=schedule_run,
        schedule_health_report=schedule_health_report,
        notification_records=notification_records,
    )
    runtime_label, runtime_tone, runtime_detail = _home_runtime_summary(
        schedule_health_report,
        doctor_report,
        trust.tone,
    )
    notification_label, notification_tone = _home_notification_summary(notification_records)
    if paper_report is None:
        tone = "danger" if runtime_tone == "danger" else "warning"
        return f"""
      <section class="home-execution-panel" data-tone="{_text(tone)}" aria-label="今日执行闸门">
        <div class="home-execution-head">
          <span>今日执行闸门</span>
          <strong>等待纸面指挥单，先不交易</strong>
        </div>
        <div class="home-execution-target">
          <b>今日暂无可执行标的</b>
          <span>首页只显示执行摘要；候选、账本和回测放到证据中心。</span>
        </div>
        <div class="home-execution-kpis">
          {_home_kpi("动作", "等待", "warning")}
          {_home_kpi("标的", "无", "neutral")}
          {_home_kpi("仓位", "0%", "neutral")}
          {_home_kpi("飞书", notification_label, notification_tone)}
        </div>
        <div class="home-execution-gates">
          {_home_gate("运行链路", runtime_label, runtime_tone, runtime_detail)}
          {_home_gate("收益守门", "待生成", "warning", "没有指挥单前，不做临盘交易。")}
        </div>
        <p>先让系统把买点、仓位、止损和取消条件生成完整，再决定是否执行。</p>
        <footer>
          <span>证据中心保留完整候选、指挥单、账本和回测。</span>
          <button type="button" data-open-evidence data-evidence-open-target="evidence-command">看完整指挥单</button>
        </footer>
      </section>
        """

    guard = paper_report.guard_decision
    instruction = paper_report.instruction
    holding = paper_report.holding_instruction
    friction_label, friction_tone, friction_detail = _execution_friction_gate(instruction)
    tone = _home_execution_tone(paper_report, runtime_tone, friction_tone)
    headline = _home_execution_headline(paper_report, runtime_tone, friction_tone)
    final_action = _home_execution_action(paper_report, friction_tone)
    target, target_detail = _home_execution_target(paper_report)
    position = _home_position_label(paper_report)
    closed_sample_count = (
        paper_database_report.closed_trade_count
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.review_sample_count
    )
    win_rate = (
        paper_database_report.win_rate
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.win_rate
    )
    profit_drawdown_ratio = (
        paper_database_report.average_profit_drawdown_ratio
        if paper_database_report is not None and paper_database_report.closed_trade_count > 0
        else guard.average_profit_drawdown_ratio
    )
    reason = _home_execution_reason(paper_report, friction_tone, runtime_tone)
    guard_tone = _guard_gate_tone(guard.action)
    return f"""
      <section class="home-execution-panel" data-tone="{_text(tone)}" aria-label="今日执行闸门">
        <div class="home-execution-head">
          <span>今日执行闸门</span>
          <strong>{_text(headline)}</strong>
        </div>
        <div class="home-execution-target">
          <b>{_text(target)}</b>
          <span>{_text(_translate_misc_text(target_detail))}</span>
        </div>
        <div class="home-execution-kpis">
          {_home_kpi("动作", final_action, tone)}
          {_home_kpi("标的", target, "neutral")}
          {_home_kpi("仓位", position, guard_tone)}
          {_home_kpi("飞书", notification_label, notification_tone)}
        </div>
        <div class="home-execution-gates">
          {_home_gate("收益守门", _guard_status_name(guard.status), guard_tone, f"闭环 {closed_sample_count}，胜率 {win_rate:.0%}，赚撤比 {profit_drawdown_ratio:.2f}R。")}
          {_home_gate("执行摩擦", friction_label, friction_tone, friction_detail)}
          {_home_gate("运行链路", runtime_label, runtime_tone, runtime_detail)}
        </div>
        <p>{_text(_translate_misc_text(reason))}</p>
        <footer>
          <span>首页不堆全文；买入价、止损、取消条件和证据下沉到证据中心。</span>
          <button type="button" data-open-evidence data-evidence-open-target="evidence-command">看完整指挥单</button>
        </footer>
      </section>
    """


def _home_execution_tone(
    report: PaperTradingDecisionReport,
    runtime_tone: str,
    friction_tone: str,
) -> str:
    if runtime_tone == "danger" or friction_tone == "danger":
        return "danger"
    if not report.should_buy or report.guard_decision.action == "stand_aside":
        return "warning"
    if (
        runtime_tone == "warning"
        or friction_tone == "warning"
        or report.guard_decision.action == "allow_reduced"
    ):
        return "warning"
    return "success"


def _home_execution_headline(
    report: PaperTradingDecisionReport,
    runtime_tone: str,
    friction_tone: str,
) -> str:
    if runtime_tone == "danger":
        return "运行链路阻断，先不交易"
    if report.holding_instruction is not None and not report.should_buy:
        return "已有持仓，先管卖点"
    if not report.should_buy or report.guard_decision.action == "stand_aside":
        return "条件不够，今天宁可空仓"
    return _pre_trade_acceptance_headline(report, friction_tone)


def _home_execution_action(
    report: PaperTradingDecisionReport,
    friction_tone: str,
) -> str:
    if report.holding_instruction is not None and not report.should_buy:
        return _translate_misc_text(report.holding_instruction.next_command or "按持仓纪律")
    return _pre_trade_acceptance_action(report, friction_tone).replace("最终动作：", "")


def _home_execution_target(report: PaperTradingDecisionReport) -> tuple[str, str]:
    instruction = report.instruction
    if instruction is not None:
        return (
            f"{instruction.name}（{instruction.symbol}）",
            f"买入 {instruction.entry_price:.2f} / 止损 {instruction.stop_loss:.2f} / 第一止盈 {instruction.first_take_profit_price:.2f}；沪深主板优先。",
        )
    holding = report.holding_instruction
    if holding is not None:
        return (
            f"{holding.name}（{holding.symbol}）",
            f"成本 {holding.entry_price:.2f} / 最新 {holding.latest_price:.2f} / 浮盈 {holding.unrealized_pnl_pct:.2%}。",
        )
    return ("今日不新开仓", report.summary)


def _home_position_label(report: PaperTradingDecisionReport) -> str:
    if report.should_buy and report.instruction is not None:
        return f"{report.instruction.position_pct:.0%}"
    if report.holding_instruction is not None:
        return f"持仓 {report.existing_position_count}"
    return "0%"


def _home_execution_reason(
    report: PaperTradingDecisionReport,
    friction_tone: str,
    runtime_tone: str,
) -> str:
    if runtime_tone == "danger":
        return "运行链路没过，不因为信号好看而交易。"
    if not report.should_buy or report.guard_decision.action == "stand_aside":
        return "没有同时满足买点、收益守门和执行条件，今天保护本金。"
    if report.guard_decision.action == "allow_reduced":
        return "收益样本未完全达标，只允许小仓验证。"
    if friction_tone == "warning":
        return "信号可买，但必须先确认封板质量、排队和滑点。"
    if report.holding_instruction is not None:
        return "已有持仓优先管卖点，不叠加无纪律仓位。"
    return "买点、仓位、止损和取消条件已生成，按指挥单执行。"


def _home_runtime_summary(
    schedule_health_report: OneToTwoScheduleHealthReport | None,
    doctor_report: OneToTwoDoctorReport | None,
    trust_tone: str,
) -> tuple[str, str, str]:
    status_text = " ".join(
        str(item or "")
        for item in (
            getattr(schedule_health_report, "status", ""),
            getattr(doctor_report, "status", ""),
            trust_tone,
        )
    ).lower()
    if not status_text.strip():
        return ("待检查", "warning", "缺少运行健康报告，先跑 doctor 和 schedule。")
    if any(token in status_text for token in ("failed", "blocked", "danger", "失败", "阻断")):
        return ("有阻断", "danger", "行情源、飞书、账本或调度存在阻断，先修复再交易。")
    if any(token in status_text for token in ("warning", "pending", "expired", "等待", "留意", "过期")):
        return ("待确认", "warning", "运行链路可用但仍有等待项，按小仓或空仓纪律处理。")
    return ("正常", "success", "早评、值守、账本和晚评链路当前可用。")


def _home_notification_summary(records: tuple[NotificationRecord, ...]) -> tuple[str, str]:
    key_records = tuple(record for record in records if record.workflow in {"morning", "watch", "eod"})
    if not key_records:
        return ("无记录", "warning")
    sent = sum(1 for record in key_records if _notification_status_value(record.status) == "sent")
    ratio = sent / max(len(key_records), 1)
    tone = "success" if ratio >= 0.9 else "warning" if sent else "danger"
    return (f"{sent}/{len(key_records)}", tone)


def _home_kpi(label: str, value: str, tone: str) -> str:
    return f"""
          <div class="home-execution-kpi" data-tone="{_text(tone)}">
            <span>{_text(label)}</span>
            <strong>{_text(_translate_misc_text(value))}</strong>
          </div>
    """


def _home_gate(label: str, value: str, tone: str, detail: str) -> str:
    return f"""
          <div class="home-execution-gate" data-tone="{_text(tone)}">
            <span>{_text(label)}</span>
            <strong>{_text(_translate_misc_text(value))}</strong>
            <small>{_text(_translate_misc_text(detail))}</small>
          </div>
    """


def _pre_trade_acceptance_tone(
    report: PaperTradingDecisionReport,
    friction_tone: str,
) -> str:
    guard_action = report.guard_decision.action
    if not report.should_buy or guard_action == "stand_aside":
        return "danger"
    if friction_tone == "danger":
        return "danger"
    if guard_action == "allow_reduced" or friction_tone == "warning":
        return "warning"
    return "success"


def _pre_trade_acceptance_headline(
    report: PaperTradingDecisionReport,
    friction_tone: str,
) -> str:
    guard_action = report.guard_decision.action
    if not report.should_buy or guard_action == "stand_aside":
        return "不满足开仓硬验收，先空仓"
    if friction_tone == "warning":
        return "信号可买，但执行摩擦提示降速"
    if friction_tone == "danger":
        return "信号触发但摩擦过高，暂停开仓"
    if guard_action == "allow_reduced":
        return "只允许小仓验证，不因样例好看加仓"
    return "通过硬验收，可按指挥单执行"


def _pre_trade_acceptance_action(
    report: PaperTradingDecisionReport,
    friction_tone: str,
) -> str:
    if not report.should_buy or report.guard_decision.action == "stand_aside":
        return "最终动作：不买"
    if friction_tone == "danger":
        return "最终动作：跳过"
    if report.guard_decision.action == "allow_reduced":
        return "最终动作：小仓验证"
    if friction_tone == "warning":
        return "最终动作：降速确认"
    return "最终动作：按计划买入"


def _guard_gate_tone(action: str) -> str:
    if action == "allow_full":
        return "success"
    if action == "allow_reduced":
        return "warning"
    return "danger"


def _execution_friction_gate(instruction: Any | None) -> tuple[str, str, str]:
    if instruction is None:
        return "未触发买点", "neutral", "没有买入指挥单时，不做无效交易。"
    notes = " ".join(str(item) for item in (*instruction.risk_notes, instruction.entry_trigger))
    danger_tokens = ("暂停开仓", "守门阻断", "硬剔除", "不可买", "禁止")
    warning_tokens = ("摩擦", "排队", "炸板", "滑点", "封板", "撤单", "拥挤", "冲高", "买不到", "跳过")
    if any(token in notes for token in danger_tokens):
        return "摩擦过高", "danger", "执行条件提示可能买不到或应跳过，先保护本金。"
    if any(token in notes for token in warning_tokens):
        return "需要二次确认", "warning", "开盘确认封板质量、排队和滑点，不追高抢单。"
    return "未见明显摩擦", "success", "仍按买入价、止损价和取消条件执行，不临盘扩大仓位。"


def render_commercial_readiness_panel(
    report: CommercialReadinessReport | None,
) -> str:
    if report is None:
        return ""
    gate_html = "".join(_render_commercial_gate(gate) for gate in report.gates)
    next_actions = "".join(
        f"<li>{_text(_translate_misc_text(action))}</li>"
        for action in report.next_actions
    )
    return f"""
      <section class="panel one-to-two-panel commercial-readiness" data-tone="{_text(_commercial_status_tone(report.status))}">
        <div class="commercial-readiness__hero">
          <div>
            <span>商用上线验收</span>
            <strong>{_text(report.headline)}</strong>
            <p>{_text(report.summary)}</p>
          </div>
          <div class="commercial-readiness__score" style="--meter: {report.score * 100:.0f}%">
            <b>{report.score:.0%}</b>
            <small>{_text(report.stage)}</small>
            <i aria-hidden="true"></i>
          </div>
        </div>
        <div class="commercial-gate-grid">
          {gate_html}
        </div>
        <ul class="detail-list compact commercial-next-actions">
          {next_actions}
        </ul>
      </section>
    """


def _notification_status_value(value: object) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _commercial_status_tone(status: str) -> str:
    return {
        "ready": "success",
        "beta_only": "warning",
        "blocked": "danger",
    }.get(status, "warning")


def _render_commercial_gate(gate) -> str:
    metrics = getattr(gate, "metrics", None) or {}
    metrics_html = ""
    if metrics:
        metrics_html = f"""
          <div class="commercial-gate__metrics">
            {"".join(f'<b>{_text(label)}<span>{_text(value)}</span></b>' for label, value in metrics.items())}
          </div>
        """
    return f"""
        <article class="commercial-gate" data-tone="{_text(gate.tone)}" style="--meter: {gate.score:.0f}%">
          <span>{_text(gate.title)}</span>
          <strong>{_text(gate.status)}</strong>
          <i aria-hidden="true"></i>
          {metrics_html}
          <p>{_text(_translate_misc_text(gate.detail))}</p>
        </article>
    """


def render_candidate_carousel(report: OneToTwoMorningReport) -> str:
    candidates = tuple(report.candidates[:12])
    if not candidates:
        return '<p class="empty-note">暂无重点候选，今天先防守。</p>'
    cards = "".join(_render_candidate_slide(candidate, index) for index, candidate in enumerate(candidates, 1))
    return f"""
      <section class="candidate-carousel" aria-label="重点候选卡片">
        <div class="candidate-carousel__track">
          {cards}
        </div>
      </section>
    """


def _render_candidate_slide(candidate, index: int) -> str:
    blocker = candidate.blockers[0] if candidate.blockers else ""
    warning = candidate.warnings[0] if candidate.warnings else ""
    primary_note = blocker or warning or candidate.next_action
    market_cap = _candidate_market_cap_line(candidate)
    status_label = {
        "ready": "可通测",
        "blocked": "硬剔除",
        "watch_only": "观察",
        "reduced": "降仓",
    }.get(candidate.status, candidate.status)
    return f"""
          <article class="candidate-slide" data-status="{_text(candidate.status)}" data-slide-index="{index - 1}">
            <div class="candidate-slide__rank">#{index}</div>
            <div>
              <h3>{_text(candidate.name)}（{_text(candidate.symbol)}）</h3>
              <p>{_text(status_label)} / {_text(_translate_misc_text(candidate.leader_label or candidate.position_profile.label))}</p>
            </div>
            <div class="candidate-slide__score">
              <strong>{candidate.score:.0f}</strong>
              <span>综合分</span>
            </div>
            <div class="candidate-slide__bars">
              {_render_candidate_bar("封板", candidate.sealing_score, 20)}
              {_render_candidate_bar("主线", candidate.mainline_score, 20)}
              {_render_candidate_bar("龙头", candidate.leader_score, 20)}
              {_render_candidate_bar("换手", candidate.turnover_quality_score, 100)}
            </div>
            <ul class="candidate-slide__facts">
              <li>买入 {_text(candidate.entry_price)} / 止损 {_text(candidate.stop_loss)}</li>
              <li>{market_cap}</li>
              <li>{_text(_translate_misc_text(primary_note))}</li>
            </ul>
          </article>
    """


def _render_candidate_bar(label: str, value: float, total: float) -> str:
    width = max(0.0, min(100.0, (value / max(total, 0.0001)) * 100.0))
    return f"""
              <div class="candidate-mini-bar" style="--bar: {width:.0f}%">
                <span>{_text(label)}</span>
                <b>{value:.0f}</b>
                <i aria-hidden="true"></i>
              </div>
    """


def _render_trust_flow(
    *,
    report: OneToTwoMorningReport,
    schedule_health_report: OneToTwoScheduleHealthReport | None,
    trust_tone: str,
) -> str:
    morning_label, morning_tone = _schedule_health_step(schedule_health_report, "morning")
    eod_label, eod_tone = _schedule_health_step(schedule_health_report, "eod")
    guard_label = "交易日" if report.trade_context.is_trading_day else "休市"
    guard_tone = trust_tone if report.trade_context.is_trading_day else "neutral"
    steps = (
        ("morning", "早评", morning_label, morning_tone),
        ("guard", "交易", guard_label, guard_tone),
        ("eod", "晚评", eod_label, eod_tone),
        ("beta", "Beta", "待检", "neutral"),
    )
    return f"""
          <div class="trust-flow" aria-label="运行链路">
            {"".join(_render_trust_step(step, label, value, tone) for step, label, value, tone in steps)}
          </div>
    """


def _render_trust_step(step: str, label: str, value: str, tone: str) -> str:
    return f"""
            <div class="trust-step" data-step="{_text(step)}" data-tone="{_text(tone)}">
              <span>{_text(label)}</span>
              <b class="trust-step-value">{_text(_translate_misc_text(value))}</b>
            </div>
    """


def _schedule_health_step(
    report: OneToTwoScheduleHealthReport | None,
    workflow: str,
) -> tuple[str, str]:
    if report is None:
        return "暂无", "neutral"
    item = next((entry for entry in report.items if entry.workflow == workflow), None)
    if item is None:
        return "暂无", "neutral"
    status = item.notification_status if item.required_notification else item.status
    return _compact_status_label(status), _status_tone(item.status or status)


def _compact_status_label(value: object) -> str:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    labels = {
        "sent": "已发送",
        "ready": "正常",
        "completed": "完成",
        "pending": "等待",
        "warning": "留意",
        "blocked": "阻断",
        "failed": "失败",
        "closed": "休市",
        "expired": "过期",
        "skipped": "跳过",
    }
    return labels.get(raw, raw[:10] or "暂无")


def _status_tone(value: object) -> str:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    if any(token in raw for token in ("failed", "blocked", "danger", "失败", "阻断")):
        return "danger"
    if any(token in raw for token in ("warning", "pending", "expired", "等待", "留意", "过期")):
        return "warning"
    if any(token in raw for token in ("ready", "sent", "completed", "success", "正常", "已发送")):
        return "success"
    return "neutral"


def _render_guard_metric(label: str, value: str) -> str:
    meter = _guard_metric_meter_pct(label, value)
    return f"""
            <div class="guard-meter" style="--meter: {meter:.0f}%">
              <small>{_text(label)}</small>
              <b>{_text(value)}</b>
              <i aria-hidden="true"></i>
            </div>
    """


def _guard_metric_meter_pct(label: str, value: str) -> float:
    raw = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".-")
    try:
        number = float(raw)
    except ValueError:
        return 0.0
    if label == "闭环样本":
        return max(0.0, min(100.0, number / 30.0 * 100.0))
    if label == "赚撤比":
        return max(0.0, min(100.0, number / 3.0 * 100.0))
    return max(0.0, min(100.0, number))


def render_decision_cockpit(
    strategy_report: StrategyDecisionReport | None,
    paper_report: PaperTradingDecisionReport | None,
    watch_report: OneToTwoMorningReport,
) -> str:
    view = build_decision_cockpit_view(strategy_report, paper_report, watch_report)
    return f"""
      <section class="decision-cockpit" data-action="{_text(view.action_state)}">
        <div class="cockpit-primary">
          <div class="mode-label">今日决策驾驶舱</div>
          <h2>{_text(view.action_label)}</h2>
          <p class="cockpit-summary">{_text(_translate_misc_text(view.execution_summary))}</p>
          <p class="cockpit-data-mode">{_text(_translate_misc_text(view.data_mode_line))}</p>
          <div class="command-strip">
            <span>下一步命令</span>
            <strong>{_text(_translate_misc_text(view.next_step))}</strong>
          </div>
          <div class="command-strip">
            <span>运行状态</span>
            <strong>{_text(_translate_misc_text(view.run_state))}</strong>
          </div>
          <div class="command-strip">
            <span>今日战法</span>
            <strong>{_text(_translate_misc_text(view.regime_line))}</strong>
          </div>
        </div>
        <div class="cockpit-grid">
          <article class="cockpit-card" data-kind="strategy">
            <span>策略选择</span>
            <strong>{_text(_translate_misc_text(view.strategy_line))}</strong>
          </article>
          <article class="cockpit-card" data-kind="buy">
            <span>模拟盘动作</span>
            <strong>{_text(_translate_misc_text(view.buy_line))}</strong>
            <small>{_text(_translate_misc_text(view.buy_evidence_line))}；范围：沪深主板 10cm，非主板只观察。</small>
          </article>
          <article class="cockpit-card" data-kind="sell">
            <span>持仓卖点</span>
            <strong>{_text(_translate_misc_text(view.sell_line))}</strong>
          </article>
          <article class="cockpit-card" data-kind="risk">
            <span>风险守门</span>
            <strong>{_text(_translate_misc_text(view.risk_line))}</strong>
          </article>
        </div>
      </section>
    """


def render_paper_database_panel(report: PaperTradeDatabaseReport | None) -> str:
    if report is None:
        return ""
    positions = "".join(
        f"""
        <li>
          <strong>{_text(position.name)}（{_text(position.symbol)}）</strong>
          <span>{position.quantity} 股 / {_text(_translate_misc_text(position.status))}</span>
          <span>浮盈 {position.unrealized_pnl:.2f} / {position.unrealized_pnl_pct:.2%}</span>
        </li>
        """
        for position in report.positions
    ) or "<li>暂无持仓</li>"
    trades = "".join(
        f"""
        <li>
          <strong>{_text(trade.name)}（{_text(trade.symbol)}）</strong>
          <span>{_text(trade.closed_at)} / {_text(_translate_misc_text(trade.exit_reason))}</span>
          <span>{trade.realized_pnl:.2f} / {trade.realized_pnl_pct:.2%}</span>
          <span>赚撤比 {trade.profit_drawdown_ratio:.2f}R / 回撤 {trade.max_adverse_pct:.2%}</span>
        </li>
        """
        for trade in report.recent_trades[:5]
    ) or "<li>暂无闭环交易</li>"
    daily_audits = "".join(
        f"""
        <li data-action="{_text(audit.action)}">
          <strong>{_text(audit.trade_date)} · {_text(audit.action_label)}</strong>
          <span>{_text(audit.summary)}</span>
          <span>赚撤比 {audit.average_profit_drawdown_ratio:.2f}R / 质量达标 {audit.risk_quality_pass_rate:.2%}</span>
          <span>{_text(audit.next_action)}</span>
        </li>
        """
        for audit in report.daily_audits[:5]
    ) or "<li>暂无每日运行审计</li>"
    return f"""
      <section class="panel one-to-two-panel">
        <h2>模拟盘数据库</h2>
        <p class="next-action">本地账本已记录模拟盘买入、卖出、持仓、收益和每日运行审计，用于复盘赚钱质量。</p>
        <ul class="detail-list compact">
          <li>状态：{_text(_database_status_name(report.status))}</li>
          <li>账本：{_text(_safe_database_label(report.database_path))}</li>
          <li>权益：{report.equity:.2f}，现金：{report.cash:.2f}</li>
          <li>已实现收益：{report.total_realized_pnl:.2f} / {report.total_realized_return_pct:.2%}</li>
          <li>闭环交易：{report.closed_trade_count}，胜率 {report.win_rate:.2%}，平均单笔 {report.average_realized_return_pct:.2%}</li>
          {_paper_quality_line(report)}
          <li>事件：{report.event_count}，快照：{report.snapshot_count}</li>
        </ul>
        <h3 class="panel-subtitle">每日运行审计</h3>
        <ul class="detail-list compact">
          {daily_audits}
        </ul>
        <h3 class="panel-subtitle">当前持仓</h3>
        <ul class="detail-list compact">
          {positions}
        </ul>
        <h3 class="panel-subtitle">最近闭环交易</h3>
        <ul class="detail-list compact">
          {trades}
        </ul>
      </section>
    """


def render_doctor_panel(doctor_report: OneToTwoDoctorReport | None) -> str:
    if doctor_report is None:
        return ""
    labels = {
        "ready": "可运行",
        "warning": "需留意",
        "blocked": "先处理",
    }
    ready_checks = tuple(check for check in doctor_report.checks if check.status == "ready")
    warning_checks = tuple(check for check in doctor_report.checks if check.status == "warning")
    blocked_checks = tuple(check for check in doctor_report.checks if check.status == "blocked")
    headline = {
        "ready": "今天可以开值守",
        "warning": "今天能值守，但先盯住风险项",
        "blocked": "今天先别开值守，先修阻断项",
    }.get(doctor_report.status, "先看值守结果")
    summary_line = {
        "ready": "核心链路已通，主线值守可以继续推进。",
        "warning": "核心链路可用，但还有可选项未就绪，今天要边值守边留意。",
        "blocked": "当前还有关键阻断，直接上值守容易失真或漏报。",
    }.get(doctor_report.status, doctor_report.summary)
    highlight_lines = [
        f"可运行 {len(ready_checks)} 项",
        f"需留意 {len(warning_checks)} 项",
        f"阻断 {len(blocked_checks)} 项",
    ]
    key_actions = [
        "先看结论：今天能不能开值守、卡在哪里、下一步先做什么。",
        "彩排会走隔离账本，不发飞书、不污染真实模拟盘。",
        "体检只做联通和门禁检查，不会触发模拟买入或卖出。",
        f"下一步：{_text(_translate_misc_text(doctor_report.next_action))}",
    ]
    return f"""
      <section class="panel one-to-two-panel">
        <h2>值守预检</h2>
        <p class="next-action">{_text(_translate_misc_text(doctor_report.summary))}</p>
        <ul class="detail-list compact">
          <li>结论：{headline}</li>
          <li>当前判断：{summary_line}</li>
          <li>{highlight_lines[0]}；{highlight_lines[1]}；{highlight_lines[2]}。</li>
          {"".join(f"<li>{_text(item)}</li>" for item in key_actions)}
        </ul>
        <h3 class="panel-subtitle">重点检查项</h3>
        <ul class="doctor-list">
          {"".join(
              f'''
              <li class="doctor-item" data-status="{_text(check.status)}">
                <span class="doctor-label">{_text(_translate_misc_text(check.label))}</span>
                <span class="doctor-status">{_text(labels.get(check.status, check.status))}</span>
                <span class="doctor-detail">{_text(_translate_misc_text(check.detail))}</span>
              </li>
              '''
              for check in doctor_report.checks
          )}
        </ul>
      </section>
    """


def render_notification_message(title: str, message: str) -> str:
    lines = highlight_notification_lines(message)
    return f"""
      <article class="notification-card">
        <div class="notification-title">{_text(title)}</div>
        <ul class="notification-lines">
          {"".join(_render_notification_line(line) for line in lines)}
        </ul>
      </article>
    """


def _render_notification_line(line) -> str:
    return f"""
      <li data-tone="{_text(line.tone)}">
        <span class="notification-chip">{_text(line.label)}</span>
        <span class="notification-text">{_text(_translate_misc_text(line.text))}</span>
      </li>
    """


def render_notification_records(records: tuple[NotificationRecord, ...]) -> str:
    if not records:
        return '<p class="empty-note">暂无通知记录。</p>'
    return "\n".join(
        f"""
        <li class="notification-record" data-status="{_text(record.status.value)}">
          <span>{_text(_translate_misc_text(notification_display_title(record)))}</span>
          <span>{_text(_workflow_name(record.workflow))}</span>
          <span>{_text(_notification_status_name(record.status.value))}</span>
          <span>{_text(record.created_at)}</span>
        </li>
        """
        for record in records[:6]
    )


def render_distribution(values: dict[str, int]) -> str:
    if not values:
        return "暂无样本"
    return "、".join(
        f"{_text(_translate_misc_text(label))} {count}"
        for label, count in list(values.items())[:4]
    )


def render_board_shadow_system_panel(system_report) -> str:
    yearly = "".join(
        f"<li>{_text(year)}：{value:.2%}</li>"
        for year, value in system_report.yearly_dynamic_position_returns.items()
    )
    return f"""
      <section class="panel one-to-two-panel">
        <h2>封板波段体系</h2>
        <p class="next-action">{_text(_translate_misc_text(system_report.summary))}</p>
        <ul class="detail-list compact">
          <li>先看结论：当前默认经营线仍是封板波段体系，先守低回撤，再争取更高复合收益。</li>
          <li>观察区间：{_text(system_report.start_date)} -> {_text(system_report.end_date)}</li>
          <li>固定 8% 仓位：样本 {system_report.fixed_position_summary.sample_count}，胜率 {system_report.fixed_position_summary.win_rate:.2%}，复合 {system_report.fixed_position_summary.position_weighted_return_pct:.2%}</li>
          <li>动态 8%/12% 仓位：样本 {system_report.dynamic_position_summary.sample_count}，胜率 {system_report.dynamic_position_summary.win_rate:.2%}，复合 {system_report.dynamic_position_summary.position_weighted_return_pct:.2%}</li>
          <li>验证段表现：动态仓位 {system_report.dynamic_position_validation.position_weighted_return_pct:.2%}</li>
          <li>复盘用法：重点只看买点、卖点、仓位和近年收益，不把非主线研究项重新带回默认经营面。</li>
        </ul>
        <h3 class="panel-subtitle">买点</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in system_report.buy_rules)}
        </ul>
        <h3 class="panel-subtitle">卖点</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in system_report.sell_rules)}
        </ul>
        <h3 class="panel-subtitle">仓位</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in system_report.position_rules)}
        </ul>
        <h3 class="panel-subtitle">动态仓位分年复合</h3>
        <ul class="detail-list compact">
          {yearly}
        </ul>
      </section>
    """


def _render_backtest_equity_curve(report: PaperBacktestReport) -> str:
    if not report.monthly:
        return """
          <div class="backtest-chart is-empty">
            <strong>收益曲线</strong>
            <span>暂无月度收益样本，暂不能绘制曲线。</span>
          </div>
        """
    width = 720
    height = 220
    pad_left = 44
    pad_right = 18
    pad_top = 18
    pad_bottom = 34
    equity = 1.0
    points: list[tuple[str, float, float, str]] = []
    for item in report.monthly:
        equity *= max(0.0, 1 + item.position_weighted_return_pct)
        points.append((item.month, equity, item.position_weighted_return_pct, item.status))
    equities = [1.0, *(item[1] for item in points)]
    min_equity = min(equities)
    max_equity = max(equities)
    if max_equity <= min_equity:
        max_equity = min_equity + 0.01
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom

    def x_at(index: int) -> float:
        if len(points) <= 1:
            return pad_left + plot_width
        return pad_left + plot_width * index / (len(points) - 1)

    def y_at(value: float) -> float:
        return pad_top + plot_height * (max_equity - value) / (max_equity - min_equity)

    polyline = " ".join(
        f"{x_at(index):.1f},{y_at(value):.1f}"
        for index, (_, value, _, _) in enumerate(points)
    )
    base_y = y_at(1.0)
    grid_values = (min_equity, (min_equity + max_equity) / 2, max_equity)
    grid_html = "".join(
        f"""
        <g class="equity-grid">
          <line x1="{pad_left}" y1="{y_at(value):.1f}" x2="{width - pad_right}" y2="{y_at(value):.1f}"></line>
          <text x="8" y="{y_at(value) + 4:.1f}">{value:.1f}x</text>
        </g>
        """
        for value in grid_values
    )
    last_month, last_equity, _, last_status = points[-1]
    best_month = max(points, key=lambda item: item[2])
    worst_month = min(points, key=lambda item: item[2])
    markers = "".join(
        f"""
        <circle class="equity-marker" data-status="{_text(status)}" cx="{x_at(index):.1f}" cy="{y_at(value):.1f}" r="3.2">
          <title>{_text(month)}：{value:.2f}x，月收益 {monthly_return:.2%}</title>
        </circle>
        """
        for index, (month, value, monthly_return, status) in enumerate(points)
        if index == len(points) - 1 or status in {"warning", "blocked"}
    )
    return f"""
      <div class="backtest-chart">
        <div class="chart-head">
          <div>
            <strong>收益曲线（月度复利）</strong>
            <span>{_text(report.start_date)} -> {_text(report.end_date)}</span>
          </div>
          <b>{last_equity:.2f}x</b>
        </div>
        <svg class="equity-chart" viewBox="0 0 {width} {height}" role="img" aria-label="模拟盘买入算法月度收益曲线">
          {grid_html}
          <line class="equity-base" x1="{pad_left}" y1="{base_y:.1f}" x2="{width - pad_right}" y2="{base_y:.1f}"></line>
          <polyline class="equity-line" points="{polyline}"></polyline>
          {markers}
          <text class="equity-axis-label" x="{pad_left}" y="{height - 8}">{_text(points[0][0])}</text>
          <text class="equity-axis-label" x="{width - 92}" y="{height - 8}">{_text(last_month)}</text>
        </svg>
        <div class="chart-metrics">
          <span>最佳月 {_text(best_month[0])} {best_month[2]:.2%}</span>
          <span>最差月 {_text(worst_month[0])} {worst_month[2]:.2%}</span>
          <span>最大回撤 {report.overall.max_drawdown_pct:.2%}</span>
          <span>最新状态 {_text(_paper_backtest_status_name(last_status))}</span>
        </div>
      </div>
    """


def _render_yearly_return_bars(report: PaperBacktestReport) -> str:
    yearly = tuple(item for item in report.yearly if item.sample_count > 0)
    if not yearly:
        return ""
    max_abs_return = max(0.01, *(abs(item.position_weighted_return_pct) for item in yearly))
    rows = "".join(
        f"""
        <li data-status="{_text(item.status)}" data-positive="{_text(str(item.position_weighted_return_pct >= 0).lower())}">
          <span>{_text(item.year)}</span>
          <div class="year-return-track">
            <i style="--bar-width: {min(100.0, abs(item.position_weighted_return_pct) / max_abs_return * 100):.1f}%"></i>
          </div>
          <strong>{item.position_weighted_return_pct:.2%}</strong>
        </li>
        """
        for item in yearly
    )
    return f"""
      <div class="yearly-return-bars">
        <div class="chart-head">
          <div>
            <strong>年度收益</strong>
            <span>先看弱年，再看总收益</span>
          </div>
        </div>
        <ul>{rows}</ul>
      </div>
    """


def _render_backtest_visuals(report: PaperBacktestReport) -> str:
    return f"""
      <div class="backtest-visuals">
        {_render_backtest_equity_curve(report)}
        {_render_yearly_return_bars(report)}
      </div>
    """


def render_backtest_snapshot(report: PaperBacktestReport | None) -> str:
    if report is None:
        return ""
    current_month = report.current_month_notes[0] if report.current_month_notes else ""
    monthly_note = (
        f'<p class="snapshot-note">{_text(_translate_misc_text(current_month))}</p>'
        if current_month
        else ""
    )
    return f"""
      <section class="backtest-snapshot-card panel one-to-two-panel">
        <div class="snapshot-title">
          <div>
            <span>收益曲线</span>
            <strong>回测证据先看图，不只看表格</strong>
          </div>
          <b>{report.overall.position_weighted_return_pct:.2%}</b>
        </div>
        {_render_backtest_visuals(report)}
        {monthly_note}
      </section>
    """


def render_paper_backtest_panel(report: PaperBacktestReport | None) -> str:
    if report is None:
        return ""
    yearly_rows = "".join(
        f"""
        <tr data-status="{_text(item.status)}">
          <td>{_text(item.year)}</td>
          <td>{_text(_paper_backtest_status_name(item.status))}</td>
          <td>{item.sample_count}</td>
          <td>{item.win_rate:.2%}</td>
          <td>{item.position_weighted_return_pct:.2%}</td>
          <td>{item.max_drawdown_pct:.2%}</td>
          <td>{_text(_translate_misc_text(item.conclusion))}</td>
        </tr>
        """
        for item in report.yearly
    )
    monthly_rows = "".join(
        f"""
        <tr data-status="{_text(item.status)}">
          <td>{_text(item.month)}</td>
          <td>{item.position_weighted_return_pct:.2%}</td>
          <td>{_text(_paper_backtest_status_name(item.status))}</td>
          <td>{_text(_translate_misc_text(item.conclusion))}</td>
        </tr>
        """
        for item in report.monthly
    )
    friction_rows = "".join(
        f"""
        <tr data-status="{_text(item.status)}">
          <td>{_text(_translate_misc_text(item.label))}</td>
          <td>{item.roundtrip_cost_pct:.2%}</td>
          <td>{item.win_rate:.2%}</td>
          <td>{item.position_weighted_return_pct:.2%}</td>
          <td>{item.max_drawdown_pct:.2%}</td>
          <td>{item.validation_return_pct:.2%}</td>
          <td>{_text(item.weakest_year or '无')} {item.weakest_year_return_pct:.2%}</td>
          <td>{_text(_paper_backtest_status_name(item.status))}</td>
        </tr>
        """
        for item in report.friction_scenarios
    )
    weak_line = "无" if not report.weak_years else "、".join(report.weak_years)
    negative_line = "无" if not report.negative_years else "、".join(report.negative_years)
    return f"""
      <section class="panel one-to-two-panel paper-backtest-panel" data-status="{_text(report.status)}">
        <h2>模拟盘买入算法年度回测</h2>
        <p class="next-action">{_text(_translate_misc_text(report.summary))}</p>
        {_render_backtest_visuals(report)}
        <ul class="detail-list compact">
          <li>先看结论：这套买入算法能不能继续经营，先看验证段、最大回撤和弱年份，不只看总收益。</li>
          <li>回测区间：{_text(report.start_date)} -> {_text(report.end_date)}</li>
          <li>数据覆盖：{_text(report.data_coverage_start or "未知")} -> {_text(report.data_coverage_end or "未知")}</li>
          {"".join(f"<li>本月状态：{_text(_translate_misc_text(item))}</li>" for item in report.current_month_notes)}
          <li>经营主线：{_text(_translate_misc_text(report.strategy_id))}</li>
          <li>全区间结果：样本 {report.overall.sample_count}，胜率 {report.overall.win_rate:.2%}，仓位复合 {report.overall.position_weighted_return_pct:.2%}，最大回撤 {report.overall.max_drawdown_pct:.2%}</li>
          <li>训练段 / 验证段：{report.train.position_weighted_return_pct:.2%} / {report.validation.position_weighted_return_pct:.2%}</li>
          <li>重点盯住：亏损年份 {_text(negative_line)}；弱年份 {_text(weak_line)}</li>
        </ul>
        <div class="yearly-backtest-table-wrap">
          <table class="yearly-backtest-table">
            <thead>
              <tr>
                <th>年份</th>
                <th>状态</th>
                <th>样本</th>
                <th>胜率</th>
                <th>收益</th>
                <th>回撤</th>
                <th>结论</th>
              </tr>
            </thead>
            <tbody>{yearly_rows}</tbody>
          </table>
        </div>
        <h3 class="panel-subtitle">本轮算法纪律优化</h3>
        <ul class="detail-list compact">
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in report.improvement_notes)}
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in report.data_coverage_notes)}
        </ul>
        <h3 class="panel-subtitle">月度收益明细</h3>
        <div class="yearly-backtest-table-wrap">
          <table class="yearly-backtest-table">
            <thead>
              <tr>
                <th>月份</th>
                <th>收益</th>
                <th>状态</th>
                <th>结论</th>
              </tr>
            </thead>
            <tbody>{monthly_rows}</tbody>
          </table>
        </div>
        <h3 class="panel-subtitle">执行摩擦压力测试</h3>
        <div class="yearly-backtest-table-wrap">
          <table class="yearly-backtest-table">
            <thead>
              <tr>
                <th>场景</th>
                <th>成本</th>
                <th>胜率</th>
                <th>收益</th>
                <th>回撤</th>
                <th>验证段</th>
                <th>最弱年份</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>{friction_rows}</tbody>
          </table>
        </div>
      </section>
    """


def render_recent_samples(samples: tuple[OneToTwoRecentSample, ...]) -> str:
    if not samples:
        return '<li class="sample-empty">暂无完成样本，继续按一进二闭环观察。</li>'
    return "\n".join(
        f"""
        <li class="sample-item" data-success="{_text(str(sample.success).lower())}">
          <span class="sample-name">{_text(sample.name)}（{_text(sample.symbol)}）</span>
          <span class="sample-pnl">{sample.realized_pnl_pct:.2%}</span>
          <span class="sample-detail">{_text(_translate_misc_text(sample.position_label))} / {_text(_translate_misc_text(sample.exit_reason))} / 持仓 {sample.holding_trade_days} 日</span>
        </li>
        """
        for sample in samples
    )


def render_eod_review_panel(eod_review: OneToTwoEndOfDayReview) -> str:
    return f"""
      <section class="panel one-to-two-panel">
        <h2>尾盘复盘</h2>
        <p class="next-action">{_text(_translate_misc_text(eod_review.summary))}</p>
        <ul class="detail-list compact">
          <li>先看结论：今天复盘最重要的是，样本有没有闭环、有没有赚钱、风险有没有失控。</li>
          <li>完成样本：{eod_review.sample_count}，成功样本：{eod_review.success_count}</li>
          <li>已实现盈亏：{eod_review.realized_pnl:.2f}，最大回撤：{eod_review.max_drawdown:.2f}</li>
          <li>风险预警：{eod_review.warning_count}</li>
          <li>稳定性阶段：{_text(_translate_misc_text(eod_review.stability_stage))}，下一门槛：{_text(eod_review.next_milestone or "滚动复盘")}</li>
          <li>边界建议：{_text(_translate_misc_text(eod_review.strategy_boundary_suggestion))}</li>
          {"".join(f"<li>{_text(_translate_misc_text(item))}</li>" for item in eod_review.focus_points)}
        </ul>
      </section>
    """


def render_stability_panel(stability_report: OneToTwoStabilityReport) -> str:
    return f"""
      <section class="panel one-to-two-panel">
        <h2>稳定性观察</h2>
        <p class="next-action">{_text(_translate_misc_text(stability_report.summary))}</p>
        <ul class="detail-list compact">
          <li>先看结论：样本是否开始稳定，关键看成功率、平均收益、止损预警率和退出原因。</li>
          <li>样本数：{stability_report.sample_count}</li>
          <li>阶段：{_text(_translate_misc_text(stability_report.sample_stage))}，下一门槛：{_text(stability_report.next_milestone or "滚动复盘")}</li>
          <li>成功率：{stability_report.success_rate:.2%}</li>
          <li>平均收益：{stability_report.average_return_pct:.2%}</li>
          <li>止损预警率：{stability_report.stop_warning_rate:.2%}</li>
          <li>位置分布：{render_distribution(stability_report.position_label_distribution)}</li>
          <li>退出原因：{render_distribution(stability_report.exit_reason_distribution)}</li>
          <li>边界建议：{_text(_translate_misc_text(stability_report.strategy_boundary_suggestion))}</li>
          <li>下一步：{_text(_translate_misc_text(stability_report.next_action))}</li>
        </ul>
        <h3 class="panel-subtitle">最近样本</h3>
        <ul class="sample-list">
          {render_recent_samples(stability_report.recent_samples)}
        </ul>
      </section>
    """


def render_backtest_audit_panel(backtest_audit: OneToTwoBacktestAuditReport) -> str:
    checks = "".join(
        f"<li>{_text(_translate_misc_text(check.label))}：{_text(_translate_misc_text(check.status))}，{_text(_translate_misc_text(check.detail))}</li>"
        for check in backtest_audit.data_quality_checks
    )
    return f"""
      <section class="panel one-to-two-panel">
        <h2>回测准入</h2>
        <p class="next-action">{_text(_translate_misc_text(backtest_audit.summary))}</p>
        <ul class="detail-list compact">
          <li>先看结论：这段回测能不能作为升级依据，先看样本、数据窗口和幸存者偏差，不先看收益。</li>
          <li>检查区间：{_text(backtest_audit.start_date)} -> {_text(backtest_audit.end_date)}</li>
          <li>可用交易日：{backtest_audit.usable_trade_days}/{backtest_audit.requested_trade_days}</li>
          <li>闭环样本：{backtest_audit.stability_report.sample_count}，当前胜率 {backtest_audit.stability_report.success_rate:.2%}</li>
          {checks}
          <li>下一步：{_text(_translate_misc_text(backtest_audit.recommended_next_action))}</li>
        </ul>
      </section>
    """


__all__ = [
    "render_after_hours_radar",
    "render_backtest_audit_panel",
    "render_backtest_snapshot",
    "render_candidate_carousel",
    "render_commercial_readiness_panel",
    "render_board_shadow_system_panel",
    "render_decision_cockpit",
    "render_distribution",
    "render_doctor_panel",
    "render_eod_review_panel",
    "render_home_execution_panel",
    "render_mainline_candidates",
    "render_mainline_continuity",
    "render_notification_message",
    "render_notification_records",
    "render_one_to_two_candidates",
    "render_one_to_two_position",
    "render_paper_backtest_panel",
    "render_paper_database_panel",
    "render_paper_decision_panel",
    "render_pre_trade_acceptance",
    "render_recent_samples",
    "render_schedule_panel",
    "render_stability_panel",
    "render_strategy_decision_panel",
    "render_trust_overview",
]
