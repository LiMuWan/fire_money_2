"""HTML renderer for the simplified FireMoney desktop experience."""

from __future__ import annotations

from html import escape
from pathlib import Path

from shared.contracts import MainChainSnapshot

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
