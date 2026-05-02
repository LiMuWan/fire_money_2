"""HTML renderer for the FireMoney one-to-two desktop preview."""

from __future__ import annotations

from html import escape
from pathlib import Path

from shared.contracts import (
    NotificationRecord,
    OneToTwoDoctorReport,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoRecentSample,
    OneToTwoScheduleRun,
    OneToTwoStabilityReport,
    PaperTradeStatus,
)


_STATIC_DIR = Path(__file__).with_name("static")


def _clean_document(document: str) -> str:
    """Keep generated preview files stable for git diff checks."""

    return "\n".join(line.rstrip() for line in document.splitlines()) + "\n"


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _render_one_to_two_candidates(report: OneToTwoMorningReport) -> str:
    if not report.candidates:
        return '<p class="empty-note">行情不可用或今日没有符合条件的一进二候选。</p>'
    return "\n".join(
        f"""
        <article class="one-to-two-card" data-status="{_text(candidate.status)}">
          <div class="candidate-head">
            <div>
              <div class="candidate-name">{_text(candidate.name)}</div>
              <div class="candidate-code">{_text(candidate.symbol)} / {_text(candidate.position_profile.label)}</div>
            </div>
            <div class="candidate-score">{_text(candidate.score)}</div>
          </div>
          <div class="tags">
            <span class="tag">{_text(candidate.status)}</span>
            <span class="tag">{_text(candidate.position_profile.summary)}</span>
            <span class="tag is-risk">止损 {_text(candidate.stop_loss)}</span>
          </div>
          <p>{_text(candidate.rationale)}</p>
          <ul class="detail-list compact">
            <li>首板 {candidate.first_board_score}/25，竞价 {candidate.auction_score}/20，位置 {candidate.position_score}/25，流动性 {candidate.liquidity_score}/15</li>
            <li>买入价 {_text(candidate.entry_price)}，仓位上限 {candidate.position_limit_pct:.0%}，严格 T+1，2 个交易日不走强则纪律退出</li>
            {"".join(f"<li>{_text(item)}</li>" for item in candidate.blockers[:3])}
            {"".join(f"<li>{_text(item)}</li>" for item in candidate.warnings[:2])}
          </ul>
        </article>
        """
        for candidate in report.candidates
    )


def _render_one_to_two_position(report: OneToTwoMorningReport) -> str:
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
            <div class="candidate-code">{_text(position.symbol)} / {_text(position.position_label)}</div>
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
          <li><span>当前纪律</span><strong>{_text(position.risk_note)}</strong></li>
          <li><span>下一步</span><strong>{_text(action)}</strong></li>
        </ul>
      </article>
    """


def _render_schedule_run(schedule_run: OneToTwoScheduleRun) -> str:
    labels = {
        "completed": "已执行",
        "skipped": "已跳过",
        "pending": "待触发",
        "closed": "休市闭锁",
        "failed": "失败",
        "expired": "已过期",
    }
    items = []
    for task in schedule_run.tasks:
        phase = f" / {_text(task.phase)}" if task.phase else ""
        items.append(
            f"""
            <li class="schedule-item" data-status="{_text(task.status)}">
              <span class="schedule-time">{_text(task.scheduled_time)}</span>
              <span class="schedule-name">{_text(task.mode)}{phase}</span>
              <span class="schedule-status">{_text(labels.get(task.status, task.status))}</span>
            </li>
            """
        )
    return "\n".join(items)


def _render_schedule_panel(schedule_run: OneToTwoScheduleRun | None) -> str:
    if schedule_run is None:
        return ""
    return f"""
      <section class="panel one-to-two-panel">
        <h2>本地调度</h2>
        <p class="next-action">已到 {schedule_run.requested_time}，应执行 {schedule_run.due_count} 项，已执行 {schedule_run.executed_count} 项，跳过 {schedule_run.skipped_count} 项。</p>
        <ul class="schedule-list">
          {_render_schedule_run(schedule_run)}
        </ul>
      </section>
    """


def _render_doctor_panel(doctor_report: OneToTwoDoctorReport | None) -> str:
    if doctor_report is None:
        return ""
    labels = {
        "ready": "可运行",
        "warning": "需留意",
        "blocked": "先处理",
    }
    return f"""
      <section class="panel one-to-two-panel">
        <h2>运行体检</h2>
        <p class="next-action">{_text(doctor_report.summary)}</p>
        <ul class="doctor-list">
          {"".join(
              f'''
              <li class="doctor-item" data-status="{_text(check.status)}">
                <span class="doctor-label">{_text(check.label)}</span>
                <span class="doctor-status">{_text(labels.get(check.status, check.status))}</span>
                <span class="doctor-detail">{_text(check.detail)}</span>
              </li>
              '''
              for check in doctor_report.checks
          )}
        </ul>
      </section>
    """


def _render_notification_message(title: str, message: str) -> str:
    lines = [line for line in message.splitlines() if line.strip()]
    return f"""
      <article class="notification-card">
        <div class="notification-title">{_text(title)}</div>
        <ul class="notification-lines">
          {"".join(f"<li>{_text(line)}</li>" for line in lines)}
        </ul>
      </article>
    """


def _render_notification_records(records: tuple[NotificationRecord, ...]) -> str:
    if not records:
        return '<p class="empty-note">暂无通知记录。</p>'
    return "\n".join(
        f"""
        <li class="notification-record" data-status="{_text(record.status.value)}">
          <span>{_text(record.workflow)}</span>
          <span>{_text(record.status.value)}</span>
          <span>{_text(record.created_at)}</span>
        </li>
        """
        for record in records[:6]
    )


def _render_distribution(values: dict[str, int]) -> str:
    if not values:
        return "暂无样本"
    return "，".join(f"{_text(label)} {count}" for label, count in list(values.items())[:4])


def _render_recent_samples(samples: tuple[OneToTwoRecentSample, ...]) -> str:
    if not samples:
        return '<li class="sample-empty">暂无完成样本，继续按一进二闭环观察。</li>'
    return "\n".join(
        f"""
        <li class="sample-item" data-success="{_text(str(sample.success).lower())}">
          <span class="sample-name">{_text(sample.name)}({_text(sample.symbol)})</span>
          <span class="sample-pnl">{sample.realized_pnl_pct:.2%}</span>
          <span class="sample-detail">{_text(sample.position_label)} / {_text(sample.exit_reason)} / 持仓 {sample.holding_trade_days} 日</span>
        </li>
        """
        for sample in samples
    )


def render_one_to_two_workflow_html(
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    eod_review: OneToTwoEndOfDayReview,
    stability_report: OneToTwoStabilityReport,
    doctor_report: OneToTwoDoctorReport | None = None,
    schedule_run: OneToTwoScheduleRun | None = None,
    notification_records: tuple[NotificationRecord, ...] = (),
) -> str:
    """Render the current one-to-two product surface only."""

    css = (_STATIC_DIR / "core.css").read_text(encoding="utf-8")
    account = watch_report.account
    latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
    position_count = len(account.positions)
    notification = watch_report.notification
    webhook_state = "已配置" if notification.webhook_configured else "未配置"
    return _clean_document(f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FireMoney 一进二</title>
  <style>
{css}
  </style>
</head>
<body>
  <main class="app-shell one-to-two-app">
    <header class="topbar">
      <div class="brand">
        <div class="brand-row">
          <h1 class="app-name">FireMoney 一进二</h1>
          <span class="subtitle">主板 10cm 模拟盘验证</span>
        </div>
        <div class="core-path">早盘判断 -> 盘中模拟 -> 尾盘复盘 -> 稳定性观察</div>
      </div>
      <nav class="nav" aria-label="一进二产品阶段">
        <button class="nav-item is-active" type="button">一进二专项台</button>
      </nav>
    </header>
    <div class="one-to-two-dashboard">
      <section class="one-to-two-hero">
        <div>
          <div class="mode-label">今日策略边界</div>
          <h2>只做主板 10cm 一进二</h2>
          <p>{_text(report.summary)}</p>
        </div>
        <div class="one-to-two-kpis">
          <div class="metric"><span class="metric-label">市场温度</span><span class="metric-value">{_text(report.market_temperature)}</span></div>
          <div class="metric"><span class="metric-label">交易日</span><span class="metric-value">{_text(report.trade_context.trade_date)}</span></div>
          <div class="metric"><span class="metric-label">候选数</span><span class="metric-value">{len(report.candidates)}</span></div>
          <div class="metric"><span class="metric-label">模拟权益</span><span class="metric-value">{account.equity:.2f}</span></div>
          <div class="metric"><span class="metric-label">持仓数</span><span class="metric-value">{position_count}</span></div>
        </div>
      </section>
      <div class="one-to-two-main-grid">
        <section class="panel one-to-two-panel">
          <h2>候选池与位置评分</h2>
          <div class="one-to-two-candidate-grid">
            {_render_one_to_two_candidates(report)}
          </div>
        </section>
        <aside class="side-panel">
          {_render_doctor_panel(doctor_report)}
          {_render_schedule_panel(schedule_run)}
          <section class="panel one-to-two-panel">
            <h2>模拟盘与风险</h2>
            {_render_one_to_two_position(watch_report)}
          </section>
          <section class="panel one-to-two-panel">
            <h2>飞书通知</h2>
            <ul class="detail-list compact">
              <li>请求日期：{_text(report.trade_context.requested_date)} / {_text(report.trade_context.note)}</li>
              <li>状态：{_text(notification.status.value)} / Webhook {_text(webhook_state)}</li>
              <li>最新事件：{_text(latest_event)}</li>
            </ul>
            <div class="notification-stack">
              {_render_notification_message("08:50 早盘判断", report.notification.message)}
              {_render_notification_message("盘中事件", watch_report.notification.message)}
              {_render_notification_message("15:10 尾盘测评", eod_review.notification.message)}
            </div>
            <h3 class="panel-subtitle">通知记录</h3>
            <ul class="notification-records">
              {_render_notification_records(notification_records)}
            </ul>
          </section>
          <section class="panel one-to-two-panel">
            <h2>尾盘测评</h2>
            <p class="next-action">{_text(eod_review.summary)}</p>
            <ul class="detail-list compact">
              <li>完成样本：{eod_review.sample_count}，成功样本：{eod_review.success_count}</li>
              <li>已实现盈亏：{eod_review.realized_pnl:.2f}，最大回撤：{eod_review.max_drawdown:.2f}</li>
              <li>风险预警：{eod_review.warning_count}</li>
              <li>稳定性阶段：{_text(eod_review.stability_stage)}，下一门槛：{_text(eod_review.next_milestone or "滚动复盘")}</li>
              <li>边界建议：{_text(eod_review.strategy_boundary_suggestion)}</li>
              {"".join(f"<li>{_text(item)}</li>" for item in eod_review.focus_points)}
            </ul>
          </section>
          <section class="panel one-to-two-panel">
            <h2>稳定性观察</h2>
            <p class="next-action">{_text(stability_report.summary)}</p>
            <ul class="detail-list compact">
              <li>样本数：{stability_report.sample_count}</li>
              <li>阶段：{_text(stability_report.sample_stage)}，下一门槛：{_text(stability_report.next_milestone or "滚动复盘")}</li>
              <li>成功率：{stability_report.success_rate:.2%}</li>
              <li>平均收益：{stability_report.average_return_pct:.2%}</li>
              <li>止损预警率：{stability_report.stop_warning_rate:.2%}</li>
              <li>位置分布：{_render_distribution(stability_report.position_label_distribution)}</li>
              <li>退出原因：{_render_distribution(stability_report.exit_reason_distribution)}</li>
              <li>边界建议：{_text(stability_report.strategy_boundary_suggestion)}</li>
              <li>{_text(stability_report.next_action)}</li>
            </ul>
            <h3 class="panel-subtitle">最近样本</h3>
            <ul class="sample-list">
              {_render_recent_samples(stability_report.recent_samples)}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  </main>
</body>
</html>
""")
