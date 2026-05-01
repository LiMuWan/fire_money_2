"""Presentation view models for the core FireMoney workflow."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import MainChainSnapshot, Opportunity


@dataclass(frozen=True)
class MetricView:
    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class CandidateView:
    symbol: str
    name: str
    score: str
    confidence: str
    tags: tuple[str, ...]
    risk_flags: tuple[str, ...]
    rationale: str
    is_focus: bool


@dataclass(frozen=True)
class AdjustmentView:
    label: str
    current_value: str
    suggested_value: str
    reason: str
    impact: str


@dataclass(frozen=True)
class ChangeRecordView:
    action: str
    version_range: str
    changes: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ArchiveRecordView:
    archive_id: str
    symbol: str
    name: str
    trade_date: str
    realized_pnl: str
    realized_pnl_pct: str
    outcome: str
    summary: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowStepView:
    key: str
    title: str
    question: str
    status: str
    metrics: tuple[MetricView, ...]
    details: tuple[str, ...]
    summary: tuple[MetricView, ...] = ()
    adjustments: tuple[AdjustmentView, ...] = ()
    change_records: tuple[ChangeRecordView, ...] = ()
    action_label: str | None = None
    action_kind: str | None = None
    action_enabled: bool = False
    confirmation_state: str | None = None


@dataclass(frozen=True)
class CoreWorkflowView:
    app_name: str
    subtitle: str
    core_path: str
    next_action: str
    mode_label: str
    mode_kind: str
    leading_candidates_label: str
    recent_archives_label: str
    next_action_label: str
    workspaces: tuple[dict[str, str], ...]
    steps: tuple[WorkflowStepView, ...]
    candidates: tuple[CandidateView, ...]
    recent_archives: tuple[ArchiveRecordView, ...]


def _risk_tone(value: str) -> str:
    if value in {"blocked", "high"}:
        return "danger"
    if value in {"medium", "needs_review"}:
        return "warning"
    return "success"


def _candidate_view(opportunity: Opportunity, focus_symbol: str | None) -> CandidateView:
    return CandidateView(
        symbol=opportunity.symbol,
        name=opportunity.name,
        score=f"{opportunity.score:.0f}",
        confidence=f"{opportunity.confidence:.0%}",
        tags=opportunity.strategy_tags,
        risk_flags=opportunity.risk_flags,
        rationale=opportunity.rationale,
        is_focus=opportunity.symbol == focus_symbol,
    )


def _format_adjustment_value(value: object) -> str:
    if isinstance(value, float) and 0 < value <= 1:
        return f"{value:.0%}"
    return str(value)


def _display_path(value: str | None) -> str:
    if not value:
        return ""
    parts = value.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return value


def _archive_view(record) -> ArchiveRecordView:
    return ArchiveRecordView(
        archive_id=record.archive_id,
        symbol=record.symbol,
        name=record.name,
        trade_date=record.trade_date,
        realized_pnl=f"{record.realized_pnl:.2f}",
        realized_pnl_pct=f"{record.realized_pnl_pct:.2%}",
        outcome=record.outcome,
        summary=record.execution_summary,
        tags=record.tags[:3],
    )


def build_core_workflow_view(
    snapshot: MainChainSnapshot,
    content,
    mode_kind_override: str | None = None,
) -> CoreWorkflowView:
    """Convert trusted workflow data into a display-only model."""

    labels = content.labels
    sections = content.sections
    empty = content.empty_states
    scan = snapshot.signal_scan
    focus = scan.focus_opportunity
    review = snapshot.risk_review
    ticket = snapshot.order_ticket
    receipt = snapshot.execution_receipt
    fill_execution = snapshot.fill_execution
    exit_execution = snapshot.exit_execution
    outcome_card = snapshot.outcome_card
    archive_record = snapshot.archive_record
    recap = snapshot.recap

    focus_symbol = focus.symbol if focus else None
    candidates = tuple(
        _candidate_view(item, focus_symbol)
        for item in scan.focus_opportunities
    )
    recent_archives = tuple(_archive_view(item) for item in snapshot.recent_archives[:3])

    market_metrics = (
        MetricView(labels["market_temperature"], str(snapshot.market_context.market_temperature), "success"),
        MetricView(labels["universe_size"], str(scan.universe_size), "neutral"),
        MetricView(labels["candidate_count"], str(scan.candidate_count), "accent"),
        MetricView(labels["risk_level"], snapshot.market_context.risk_level.value, _risk_tone(snapshot.market_context.risk_level.value)),
        MetricView(labels["focus_candidate"], focus.name if focus else empty["no_focus"], "accent"),
    )
    market_details = (
        snapshot.market_context.summary,
        scan.summary,
        *scan.watch_notes,
    )

    execution_metrics = (
        MetricView(
            labels["position_limit"],
            f"{review.position_limit_pct:.0%}" if review else "--",
            _risk_tone(review.risk_level.value) if review else "neutral",
        ),
        MetricView(labels["order_quantity"], str(ticket.quantity) if ticket else "--", "neutral"),
        MetricView(labels["limit_price"], f"{ticket.limit_price:.2f}" if ticket else "--", "neutral"),
        MetricView(
            labels["confirmation_status"],
            ticket.confirmation_status.value if ticket else "--",
            "success" if receipt else "warning",
        ),
    )
    execution_details: tuple[str, ...]
    if review:
        warnings = review.warnings or (sections["waiting_confirmation"],)
        execution_details = (
            review.next_action,
            ticket.confirmation_message if ticket else "",
            *review.blockers,
            *warnings,
        )
    else:
        execution_details = (empty["waiting_opportunity"],)
    execution_summary = (
        MetricView(labels["order_route"], ticket.route if ticket else "--", "neutral"),
        MetricView(labels["limit_price"], f"{ticket.limit_price:.2f}" if ticket else "--", "neutral"),
        MetricView(labels["order_quantity"], str(ticket.quantity) if ticket else "--", "neutral"),
    )

    receipt_tone = (
        "success"
        if receipt and receipt.status.value == "accepted"
        else "danger"
        if receipt and receipt.status.value == "failed"
        else "warning"
        if receipt
        else "neutral"
    )
    recap_metrics = (
        MetricView(
            labels["receipt_status"],
            receipt.status.value if receipt else empty["waiting_submission_result"],
            receipt_tone,
        ),
        MetricView(
            labels["receipt_route"],
            receipt.route.value if receipt else "--",
            "neutral",
        ),
        MetricView(labels["receipt_prepared_at"], receipt.prepared_at if receipt else "--", "neutral"),
        MetricView(labels["receipt_submitted_at"], receipt.submitted_at if receipt and receipt.submitted_at else "--", "neutral"),
        MetricView(labels["fill_quantity"], str(fill_execution.filled_quantity) if fill_execution else "--", "neutral"),
        MetricView(labels["fill_avg_price"], f"{fill_execution.avg_price:.2f}" if fill_execution else "--", "neutral"),
        MetricView(labels["exit_avg_price"], f"{exit_execution.avg_price:.2f}" if exit_execution else "--", "neutral"),
        MetricView(
            labels["fill_slippage"],
            f"{fill_execution.slippage_pct:.2%}" if fill_execution else "--",
            "warning"
            if fill_execution and fill_execution.slippage_pct > 0.005
            else "success"
            if fill_execution
            else "neutral",
        ),
        MetricView(labels["outcome_current_price"], f"{outcome_card.current_price:.2f}" if outcome_card else "--", "neutral"),
        MetricView(
            labels["outcome_unrealized_pnl"],
            f"{outcome_card.unrealized_pnl:.2f}" if outcome_card else "--",
            "success"
            if outcome_card and outcome_card.unrealized_pnl >= 0
            else "danger"
            if outcome_card
            else "neutral",
        ),
        MetricView(
            labels["outcome_unrealized_pnl_pct"],
            f"{outcome_card.unrealized_pnl_pct:.2%}" if outcome_card else "--",
            "success"
            if outcome_card and outcome_card.unrealized_pnl_pct >= 0
            else "danger"
            if outcome_card
            else "neutral",
        ),
        MetricView(
            labels["outcome_realized_pnl"],
            f"{outcome_card.realized_pnl:.2f}" if outcome_card and outcome_card.realized_pnl is not None else "--",
            "success"
            if outcome_card and outcome_card.realized_pnl is not None and outcome_card.realized_pnl >= 0
            else "danger"
            if outcome_card and outcome_card.realized_pnl is not None
            else "neutral",
        ),
        MetricView(
            labels["outcome_realized_pnl_pct"],
            f"{outcome_card.realized_pnl_pct:.2%}" if outcome_card and outcome_card.realized_pnl_pct is not None else "--",
            "success"
            if outcome_card and outcome_card.realized_pnl_pct is not None and outcome_card.realized_pnl_pct >= 0
            else "danger"
            if outcome_card and outcome_card.realized_pnl_pct is not None
            else "neutral",
        ),
        MetricView(labels["archive_outcome"], archive_record.outcome if archive_record else "--", "success" if archive_record and archive_record.outcome == "profit" else "neutral"),
        MetricView(labels["archive_id"], archive_record.archive_id if archive_record else "--", "neutral"),
        MetricView(labels["archive_saved_count"], str(len(snapshot.recent_archives)), "success" if snapshot.recent_archives else "neutral"),
        MetricView(labels["recap_lesson"], str(len(recap.lessons)) if recap else "0", "neutral"),
        MetricView(
            labels["strategy_adjustment_count"],
            str(len(recap.strategy_adjustments)) if recap else "0",
            "accent" if recap and recap.strategy_adjustments else "neutral",
        ),
        MetricView(
            labels["strategy_adjustment_status"],
            snapshot.strategy_config.adjustment_status.value,
            "success"
            if snapshot.strategy_config.adjustment_status.value == "applied"
            else "warning"
            if snapshot.strategy_config.adjustment_status.value == "waiting_user"
            else "neutral",
        ),
        MetricView(
            labels["strategy_version"],
            snapshot.strategy_config.version,
            "neutral",
        ),
        MetricView(
            labels["strategy_source"],
            snapshot.strategy_config.source,
            "success" if snapshot.strategy_config.source == "local" else "neutral",
        ),
    )
    recap_adjustments = (
        tuple(
            AdjustmentView(
                label=item.label,
                current_value=_format_adjustment_value(item.current_value),
                suggested_value=_format_adjustment_value(item.suggested_value),
                reason=item.reason,
                impact=item.impact,
            )
            for item in recap.strategy_adjustments
        )
        if recap
        else ()
    )
    change_records = tuple(
        ChangeRecordView(
            action=item.action,
            version_range=f"{item.from_version} -> {item.to_version}",
            changes=item.changes,
            reason=item.reason,
        )
        for item in snapshot.strategy_config.recent_changes[:3]
    )
    recap_details = (
        (
            recap.conclusion,
            recap.execution_deviation,
            receipt.message if receipt else "",
            _display_path(receipt.exported_path if receipt else None),
            receipt.failure_reason if receipt and receipt.failure_reason else "",
            receipt.next_action if receipt else "",
            fill_execution.message if fill_execution else "",
            fill_execution.filled_at if fill_execution else "",
            exit_execution.message if exit_execution else "",
            exit_execution.exited_at if exit_execution else "",
            outcome_card.summary if outcome_card else "",
            outcome_card.stop_discipline if outcome_card else "",
            outcome_card.next_action if outcome_card else "",
            archive_record.signal_summary if archive_record else "",
            archive_record.risk_summary if archive_record else "",
            archive_record.execution_summary if archive_record else "",
            archive_record.recap_summary if archive_record else "",
            archive_record.next_action if archive_record else "",
            *recap.lessons,
            recap.next_strategy_action,
        )
        if recap
        else (
            sections["waiting_receipt"],
            sections["no_recap_yet"],
            snapshot.strategy_config.impact_summary,
            snapshot.strategy_config.adjustment_message,
        )
    )
    is_applied = snapshot.strategy_config.adjustment_status.value == "applied"
    can_submit_receipt = bool(receipt and receipt.status.value == "prepared")
    can_import_fill = bool(receipt and receipt.accepted and not fill_execution)
    can_import_exit = bool(fill_execution and not exit_execution)
    recap_action_label = (
        labels["reset_strategy_action"]
        if is_applied
        else labels["import_exit_action"]
        if can_import_exit
        else labels["import_fill_action"]
        if can_import_fill
        else labels["import_receipt_action"]
        if can_submit_receipt
        else labels["apply_adjustments_action"]
        if recap and recap.strategy_adjustments
        else labels["secondary_action"]
    )
    recap_action_kind = (
        "reset-strategy"
        if is_applied
        else "import-exit"
        if can_import_exit
        else "import-fill"
        if can_import_fill
        else "import-receipt"
        if can_submit_receipt
        else "apply-adjustments"
        if recap and recap.strategy_adjustments
        else None
    )
    recap_action_enabled = (
        can_submit_receipt
        or can_import_fill
        or can_import_exit
        or snapshot.strategy_config.adjustment_status.value == "waiting_user"
        or is_applied
    )
    mode_kind = (
        "reset"
        if snapshot.strategy_config.source == "default"
        and receipt
        and snapshot.strategy_config.adjustment_status.value == "not_available"
        else "adjusted"
        if is_applied
        else "closed"
        if exit_execution
        else "filled"
        if fill_execution
        else "submitted"
        if receipt and receipt.status.value in {"submitted", "accepted", "failed"}
        else "confirmed"
        if receipt
        else "initial"
    )
    if mode_kind_override:
        mode_kind = mode_kind_override

    steps = (
        WorkflowStepView(
            key="market",
            title=labels["market_judgment"],
            question=sections["market_question"],
            status=scan.next_action,
            metrics=market_metrics,
            details=market_details,
            action_label=labels["refresh_action"],
            action_enabled=True,
        ),
        WorkflowStepView(
            key="execution",
            title=labels["execution_review"],
            question=sections["execution_question"],
            status=ticket.status if ticket else empty["no_order_ticket"],
            metrics=execution_metrics,
            details=execution_details,
            summary=execution_summary,
            action_label=labels["confirmed_action"] if receipt else labels["primary_action"],
            action_kind="confirm-order" if ticket and ticket.requires_confirmation and not receipt else None,
            action_enabled=bool(ticket and ticket.requires_confirmation and not receipt),
            confirmation_state=ticket.confirmation_status.value if ticket else None,
        ),
        WorkflowStepView(
            key="recap",
            title=labels["recap_improvement"],
            question=sections["recap_question"],
            status=recap.conclusion if recap else empty["waiting_execution_sample"],
            metrics=recap_metrics,
            details=recap_details,
            adjustments=recap_adjustments,
            change_records=change_records,
            action_label=recap_action_label,
            action_kind=recap_action_kind,
            action_enabled=recap_action_enabled,
        ),
    )

    return CoreWorkflowView(
        app_name=labels["app_name"],
        subtitle=labels["app_subtitle"],
        core_path=labels["core_path"],
        next_action=scan.next_action,
        mode_label=(
            labels["after_reset"]
            if mode_kind == "reset"
            else
            labels["after_adjustment"]
            if mode_kind == "adjusted"
            else labels["after_exit"]
            if mode_kind == "closed"
            else labels["after_fill"]
            if mode_kind == "filled"
            else labels["after_submission"]
            if mode_kind == "submitted"
            else labels["after_confirmation"]
            if mode_kind == "confirmed"
            else labels["before_confirmation"]
        ),
        mode_kind=mode_kind,
        leading_candidates_label=labels["leading_candidates"],
        recent_archives_label=labels["recent_archives"],
        next_action_label=labels["next_step"],
        workspaces=content.workspaces,
        steps=steps,
        candidates=candidates,
        recent_archives=recent_archives,
    )
