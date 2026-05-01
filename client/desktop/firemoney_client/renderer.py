"""HTML renderer for the simplified FireMoney desktop experience."""

from __future__ import annotations

from html import escape
from pathlib import Path

from shared.contracts import (
    MainChainSnapshot,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoStabilityReport,
)

from .content import load_client_content
from .view_model import CoreWorkflowView, build_core_workflow_view


_STATIC_DIR = Path(__file__).with_name("static")


def _clean_document(document: str) -> str:
    """Keep generated preview files stable for git diff checks."""

    return "\n".join(line.rstrip() for line in document.splitlines()) + "\n"


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _render_metrics(step) -> str:
    return "\n".join(
        (
            f'<div class="metric" data-tone="{_text(metric.tone)}">'
            f'<span class="metric-label">{_text(metric.label)}</span>'
            f'<span class="metric-value">{_text(metric.value)}</span>'
            "</div>"
        )
        for metric in step.metrics
    )


def _render_details(step) -> str:
    return "\n".join(f"<li>{_text(item)}</li>" for item in step.details if item)


def _render_summary(step) -> str:
    if not step.summary:
        return ""
    items = "\n".join(
        (
            '<div class="summary-item">'
            f'<span>{_text(metric.label)}</span>'
            f'<strong>{_text(metric.value)}</strong>'
            "</div>"
        )
        for metric in step.summary
    )
    return f'<div class="order-summary">{items}</div>'


def _render_adjustments(step) -> str:
    if not step.adjustments:
        return ""
    cards = "\n".join(
        f"""
        <article class="adjustment">
          <div class="adjustment-head">
            <strong>{_text(item.label)}</strong>
            <span>{_text(item.current_value)} -> {_text(item.suggested_value)}</span>
          </div>
          <p>{_text(item.reason)}</p>
          <p>{_text(item.impact)}</p>
        </article>
        """
        for item in step.adjustments
    )
    return f'<div class="adjustments">{cards}</div>'


def _render_change_records(step) -> str:
    if not step.change_records:
        return ""
    cards = "\n".join(
        f"""
        <article class="change-record">
          <div class="change-head">
            <strong>{_text(item.action)}</strong>
            <span>{_text(item.version_range)}</span>
          </div>
          <p>{_text(item.reason)}</p>
          <ul>
            {"".join(f"<li>{_text(change)}</li>" for change in item.changes)}
          </ul>
        </article>
        """
        for item in step.change_records
    )
    return f'<div class="change-log">{cards}</div>'


def _render_step(step, index: int) -> str:
    button_class = "action-button" if step.action_enabled else "action-button is-muted"
    attrs = f' data-action="{_text(step.action_kind)}"' if step.action_kind else ""
    action = (
        f'<button class="{button_class}" type="button"{attrs}>{_text(step.action_label)}</button>'
        if step.action_label
        else ""
    )
    confirmation = (
        f'<span class="state-pill" data-state="{_text(step.confirmation_state)}">{_text(step.confirmation_state)}</span>'
        if step.confirmation_state
        else ""
    )
    return f"""
      <section class="step" id="{_text(step.key)}">
        <div class="step-label">
          <div class="step-index">{index}</div>
          <h2 class="step-title">{_text(step.title)}</h2>
          <p class="step-question">{_text(step.question)}</p>
          {confirmation}
        </div>
        <div class="step-main">
          <div class="status-row">
            <p class="status-text">{_text(step.status)}</p>
            {action}
          </div>
          {_render_summary(step)}
          <div class="metrics">
            {_render_metrics(step)}
          </div>
          <ul class="detail-list">
            {_render_details(step)}
          </ul>
          {_render_adjustments(step)}
          {_render_change_records(step)}
        </div>
      </section>
    """


def _render_candidates(view: CoreWorkflowView) -> str:
    cards: list[str] = []
    for candidate in view.candidates:
        classes = "candidate is-focus" if candidate.is_focus else "candidate"
        tags = "".join(f'<span class="tag">{_text(tag)}</span>' for tag in candidate.tags)
        risks = "".join(
            f'<span class="tag is-risk">{_text(flag)}</span>'
            for flag in candidate.risk_flags
        )
        cards.append(
            f"""
            <article class="{classes}">
              <div class="candidate-head">
                <div>
                  <div class="candidate-name">{_text(candidate.name)}</div>
                  <div class="candidate-code">{_text(candidate.symbol)} / {candidate.confidence}</div>
                </div>
                <div class="candidate-score">{_text(candidate.score)}</div>
              </div>
              <div class="tags">{tags}{risks}</div>
              <p>{_text(candidate.rationale)}</p>
            </article>
            """
        )
    return "\n".join(cards)


def _render_archives(view: CoreWorkflowView) -> str:
    if not view.recent_archives:
        return ""
    cards: list[str] = []
    for record in view.recent_archives:
        tags = "".join(f'<span class="tag">{_text(tag)}</span>' for tag in record.tags)
        cards.append(
            f"""
            <article class="archive-item" data-outcome="{_text(record.outcome)}">
              <div class="archive-head">
                <div>
                  <div class="archive-name">{_text(record.name)}</div>
                  <div class="archive-meta">{_text(record.symbol)} / {_text(record.trade_date)}</div>
                </div>
                <div class="archive-pnl">{_text(record.realized_pnl)}</div>
              </div>
              <div class="archive-summary">{_text(record.summary)}</div>
              <div class="archive-foot">
                <span>{_text(record.realized_pnl_pct)}</span>
                <span>{_text(record.archive_id)}</span>
              </div>
              <div class="tags">{tags}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_one_to_two_panel(
    report: OneToTwoMorningReport | None,
    watch_report: OneToTwoMorningReport | None,
    eod_review: OneToTwoEndOfDayReview | None,
    stability_report: OneToTwoStabilityReport | None,
) -> str:
    if not report:
        return ""

    account = (watch_report or report).account
    position = account.positions[0] if account.positions else None
    candidates = "\n".join(
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
            <li>首板 {candidate.first_board_score}/25，竞价 {candidate.auction_score}/20，位置 {candidate.position_score}/25</li>
            <li>仓位上限 {candidate.position_limit_pct:.0%}，买入价 {_text(candidate.entry_price)}，严格 T+1</li>
            {"".join(f"<li>{_text(item)}</li>" for item in candidate.blockers[:2])}
            {"".join(f"<li>{_text(item)}</li>" for item in candidate.warnings[:2])}
          </ul>
        </article>
        """
        for candidate in report.candidates[:4]
    )
    position_html = (
        f"""
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
        if position
        else '<p class="empty-note">当前没有模拟持仓，等待候选达到一进二触发条件。</p>'
    )
    notification = (watch_report or report).notification
    latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
    eod_summary = eod_review.summary if eod_review else "尾盘测评待生成。"
    stability_summary = stability_report.summary if stability_report else "稳定性报告待生成。"
    return f"""
      <section class="panel one-to-two-panel">
        <h2>一进二专项台</h2>
        <div class="one-to-two-kpis">
          <div class="metric"><span class="metric-label">市场温度</span><span class="metric-value">{_text(report.market_temperature)}</span></div>
          <div class="metric"><span class="metric-label">候选数</span><span class="metric-value">{len(report.candidates)}</span></div>
          <div class="metric"><span class="metric-label">模拟权益</span><span class="metric-value">{account.equity:.2f}</span></div>
        </div>
        <p class="next-action">{_text(report.summary)}</p>
        <div class="candidate-list">{candidates}</div>
        <h3>模拟盘与风险</h3>
        {position_html}
        <h3>飞书与复盘</h3>
        <ul class="detail-list compact">
          <li>通知状态：{_text(notification.status.value)} / Webhook {_text("已配置" if notification.webhook_configured else "未配置")}</li>
          <li>最新事件：{_text(latest_event)}</li>
          <li>{_text(eod_summary)}</li>
          <li>{_text(stability_summary)}</li>
        </ul>
      </section>
    """


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


def render_one_to_two_workflow_html(
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    eod_review: OneToTwoEndOfDayReview,
    stability_report: OneToTwoStabilityReport,
) -> str:
    """Render the current one-to-two product surface only."""

    css = (_STATIC_DIR / "core.css").read_text(encoding="utf-8")
    account = watch_report.account
    latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
    position_count = len(account.positions)
    notification = watch_report.notification
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
          <section class="panel one-to-two-panel">
            <h2>模拟盘与风险</h2>
            {_render_one_to_two_position(watch_report)}
          </section>
          <section class="panel one-to-two-panel">
            <h2>飞书通知</h2>
            <ul class="detail-list compact">
              <li>状态：{_text(notification.status.value)} / Webhook {_text("已配置" if notification.webhook_configured else "未配置")}</li>
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


def _render_view(view: CoreWorkflowView, content) -> str:
    steps = "\n".join(_render_step(step, index) for index, step in enumerate(view.steps, 1))
    return f"""
      <section class="mode-view" data-mode="{_text(view.mode_label)}" data-kind="{_text(view.mode_kind)}">
        <div class="mode-label">{_text(view.mode_label)}</div>
        <section class="workflow" aria-label="{_text(content.labels["workflow_aria_label"])}">
          {steps}
        </section>
      </section>
    """


def render_core_workflow_html(
    snapshot: MainChainSnapshot,
    confirmed_snapshot: MainChainSnapshot | None = None,
    submitted_snapshot: MainChainSnapshot | None = None,
    filled_snapshot: MainChainSnapshot | None = None,
    closed_snapshot: MainChainSnapshot | None = None,
    adjusted_snapshot: MainChainSnapshot | None = None,
    reset_snapshot: MainChainSnapshot | None = None,
    one_to_two_report: OneToTwoMorningReport | None = None,
    one_to_two_watch_report: OneToTwoMorningReport | None = None,
    one_to_two_eod_review: OneToTwoEndOfDayReview | None = None,
    one_to_two_stability_report: OneToTwoStabilityReport | None = None,
    locale: str = "zh_CN",
) -> str:
    """Render a self-contained HTML page for the core workflow."""

    content = load_client_content(locale)
    view = build_core_workflow_view(snapshot, content)
    confirmed_view = (
        build_core_workflow_view(confirmed_snapshot, content)
        if confirmed_snapshot
        else None
    )
    submitted_view = (
        build_core_workflow_view(submitted_snapshot, content)
        if submitted_snapshot
        else None
    )
    filled_view = (
        build_core_workflow_view(filled_snapshot, content)
        if filled_snapshot
        else None
    )
    closed_view = (
        build_core_workflow_view(closed_snapshot, content)
        if closed_snapshot
        else None
    )
    adjusted_view = (
        build_core_workflow_view(adjusted_snapshot, content)
        if adjusted_snapshot
        else None
    )
    reset_view = (
        build_core_workflow_view(reset_snapshot, content, mode_kind_override="reset")
        if reset_snapshot
        else None
    )
    css = (_STATIC_DIR / "core.css").read_text(encoding="utf-8")
    nav = "\n".join(
        (
            '<button class="nav-item is-active" type="button">'
            if index == 0
            else '<button class="nav-item" type="button">'
        )
        + _text(item["title"])
        + "</button>"
        for index, item in enumerate(view.workspaces)
    )
    views = _render_view(view, content)
    if confirmed_view:
        views += _render_view(confirmed_view, content)
    if submitted_view:
        views += _render_view(submitted_view, content)
    if filled_view:
        views += _render_view(filled_view, content)
    if closed_view:
        views += _render_view(closed_view, content)
    if adjusted_view:
        views += _render_view(adjusted_view, content)
    if reset_view:
        views += _render_view(reset_view, content)

    return _clean_document(f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(view.app_name)}</title>
  <style>
{css}
  </style>
</head>
<body>
  <main class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-row">
          <h1 class="app-name">{_text(view.app_name)}</h1>
          <span class="subtitle">{_text(view.subtitle)}</span>
        </div>
        <div class="core-path">{_text(view.core_path)}</div>
      </div>
      <nav class="nav" aria-label="{_text(content.labels["workspace_nav_aria_label"])}">
        {nav}
      </nav>
    </header>
    <div class="layout">
      <div class="workflow-shell">
        {views}
      </div>
      <aside class="side-panel">
        <section class="panel">
          <h2>{_text(view.leading_candidates_label)}</h2>
          <div class="candidate-list">
            {_render_candidates(view)}
          </div>
        </section>
        <section class="panel">
          <h2>{_text(view.recent_archives_label)}</h2>
          <div class="archive-list">
            {_render_archives(view)}
          </div>
        </section>
        {_render_one_to_two_panel(
            one_to_two_report,
            one_to_two_watch_report,
            one_to_two_eod_review,
            one_to_two_stability_report,
        )}
        <section class="panel">
          <h2>{_text(view.next_action_label)}</h2>
          <p class="next-action">{_text(view.next_action)}</p>
        </section>
      </aside>
    </div>
  </main>
  <script>
    const views = Array.from(document.querySelectorAll('.mode-view'));
    const confirmButton = document.querySelector('[data-action="confirm-order"]');
    const importReceiptButton = document.querySelector('[data-action="import-receipt"]');
    const importFillButton = document.querySelector('[data-action="import-fill"]');
    const importExitButton = document.querySelector('[data-action="import-exit"]');
    const applyButton = document.querySelector('[data-action="apply-adjustments"]');
    const resetButton = document.querySelector('[data-action="reset-strategy"]');
    function showMode(index) {{
      views.forEach((item, current) => {{
        item.hidden = current !== index;
      }});
    }}
    showMode(0);
    if (confirmButton && views.length > 1) {{
      confirmButton.addEventListener('click', () => showMode(1));
    }}
    if (importReceiptButton && views.length > 2) {{
      importReceiptButton.addEventListener('click', () => showMode(2));
    }}
    if (importFillButton && views.length > 3) {{
      importFillButton.addEventListener('click', () => showMode(3));
    }}
    if (importExitButton && views.length > 4) {{
      importExitButton.addEventListener('click', () => showMode(4));
    }}
    if (applyButton && views.length > 4) {{
      applyButton.addEventListener('click', () => showMode(views.length > 5 ? 5 : 4));
    }}
    if (resetButton && views.length > 5) {{
      resetButton.addEventListener('click', () => showMode(views.length > 6 ? 6 : 5));
    }}
  </script>
</body>
</html>
""")
