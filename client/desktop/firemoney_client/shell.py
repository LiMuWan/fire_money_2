"""Minimal client shell for the FireMoney main workflow."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import MainChainSnapshot

from .content import load_client_content


@dataclass(frozen=True)
class WorkspaceDescriptor:
    key: str
    title: str
    purpose: str


class FireMoneyShell:
    """Renders workflow state without making business decisions."""

    def __init__(self, locale: str = "zh_CN") -> None:
        self._content = load_client_content(locale)
        self._labels = self._content.labels
        self._empty = self._content.empty_states
        self._templates = self._content.templates
        self._workspaces = tuple(
            WorkspaceDescriptor(
                key=item["key"],
                title=item["title"],
                purpose=item["purpose"],
            )
            for item in self._content.workspaces
        )

    def render_snapshot(self, snapshot: MainChainSnapshot) -> str:
        signal_scan = snapshot.signal_scan
        selected = snapshot.selected_opportunity
        review = snapshot.risk_review
        ticket = snapshot.order_ticket
        receipt = snapshot.execution_receipt
        recap = snapshot.recap

        focus_name = (
            signal_scan.focus_opportunity.name
            if signal_scan.focus_opportunity
            else self._empty["no_focus"]
        )
        opportunity_value = (
            self._format(
                "shell_opportunity",
                name=selected.name,
                symbol=selected.symbol,
                score=f"{selected.score:.0f}",
            )
            if selected
            else self._empty["no_executable_candidate"]
        )
        review_value = (
            self._format(
                "shell_review",
                decision=review.decision.value,
                next_action=review.next_action,
            )
            if review
            else self._empty["waiting_opportunity"]
        )
        order_value = (
            self._format(
                "shell_order",
                status=ticket.status,
                route=ticket.route,
            )
            if ticket
            else self._empty["no_order_ticket"]
        )
        receipt_value = (
            self._format(
                "shell_receipt",
                status=receipt.status,
                message=receipt.message,
            )
            if receipt
            else self._empty["waiting_submission_result"]
        )
        recap_value = (
            self._format(
                "shell_recap",
                conclusion=recap.conclusion,
                next_strategy_action=recap.next_strategy_action,
            )
            if recap
            else self._empty["waiting_execution_sample"]
        )
        watch_notes = self._templates["shell_note_separator"].join(
            signal_scan.watch_notes
        )
        lines = [
            self._line("market_judgment", snapshot.market_context.summary),
            self._line(
                "signal_scan",
                self._format(
                    "shell_signal_scan",
                    candidate_count=signal_scan.candidate_count,
                    focus_name=focus_name,
                    summary=signal_scan.summary,
                ),
            ),
            self._line("opportunity_pool", opportunity_value),
            self._line("execution_review", review_value),
            self._line("order_confirmation", order_value),
            self._line("receipt_tracking", receipt_value),
            self._line("recap_improvement", recap_value),
            self._line("watch_notes", watch_notes),
            self._line("next_step", signal_scan.next_action),
            self._line("strategy_boundary", snapshot.strategy_config.impact_summary),
        ]
        return "\n".join(lines)

    def workspace_titles(self) -> tuple[str, ...]:
        return tuple(workspace.title for workspace in self._workspaces)

    def _line(self, label_key: str, value: str) -> str:
        return self._format(
            "shell_labeled_value",
            label=self._labels[label_key],
            value=value,
        )

    def _format(self, template_key: str, **values: object) -> str:
        return self._templates[template_key].format(**values)
