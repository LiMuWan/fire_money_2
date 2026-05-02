"""HTML renderer for the FireMoney one-to-two desktop preview."""

from __future__ import annotations

from html import escape
from pathlib import Path

from shared.contracts import (
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoScheduleRun,
    OneToTwoStabilityReport,
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
            <li>买入价 {_text(candidate.entry_price)}，仓位上限 {candidate.position_limit_pct:.0%}，严格 T+1</li>
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
    return f"""
      <article class="one-to-two-card">
        <div class="candidate-head">
          <div>
            <div class="candidate-name">{_text(position.name)}</div>
            <div class="candidate-code">{_text(position.symbol)} / {_text(position.status.value)}</div>
          </div>
          <div class="candidate-score">{position.unrealized_pnl_pct:.2%}</div>
        </div>
        <p>持仓 {position.quantity} 股，现价 {_text(position.latest_price)}，止损 {_text(position.stop_loss)}。</p>
        <p>{_text(position.risk_note)}</p>
      </article>
    """


def _render_schedule_run(schedule_run: OneToTwoScheduleRun) -> str:
    labels = {
        "completed": "已执行",
        "skipped": "已跳过",
        "pending": "待触发",
        "closed": "休市闭锁",
        "failed": "失败",
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


def render_one_to_two_workflow_html(
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    eod_review: OneToTwoEndOfDayReview,
    stability_report: OneToTwoStabilityReport,
    schedule_run: OneToTwoScheduleRun | None = None,
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
          </section>
          <section class="panel one-to-two-panel">
            <h2>尾盘测评</h2>
            <p class="next-action">{_text(eod_review.summary)}</p>
            <ul class="detail-list compact">
              {"".join(f"<li>{_text(item)}</li>" for item in eod_review.focus_points)}
            </ul>
          </section>
          <section class="panel one-to-two-panel">
            <h2>稳定性观察</h2>
            <p class="next-action">{_text(stability_report.summary)}</p>
            <ul class="detail-list compact">
              <li>样本数：{stability_report.sample_count}</li>
              <li>成功率：{stability_report.success_rate:.2%}</li>
              <li>平均收益：{stability_report.average_return_pct:.2%}</li>
              <li>止损预警率：{stability_report.stop_warning_rate:.2%}</li>
              <li>{_text(stability_report.next_action)}</li>
            </ul>
          </section>
        </aside>
      </div>
    </div>
  </main>
</body>
</html>
""")
