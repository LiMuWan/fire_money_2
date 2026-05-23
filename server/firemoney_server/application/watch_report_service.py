"""Watch phase report wrapping and notification orchestration."""

from __future__ import annotations

from collections.abc import Callable

from server.firemoney_server.application.one_to_two_notification_text import (
    one_to_two_watch_notification_message,
    one_to_two_watch_notification_title,
)
from server.firemoney_server.application.notification_orchestrator import (
    OneToTwoNotificationOrchestrator,
)
from server.firemoney_server.application.watch_phase_service import WatchPhaseService
from shared.contracts import (
    FeishuNotificationResult,
    OneToTwoEventType,
    OneToTwoMorningReport,
    StrategyDecisionReport,
)


class WatchReportService:
    """Runs watch phases and returns the user-facing morning/watch report."""

    def __init__(
        self,
        *,
        watch_phase_service: WatchPhaseService,
        notification_orchestrator: OneToTwoNotificationOrchestrator,
        build_morning_report: Callable[..., OneToTwoMorningReport],
        build_strategy_decision_report: Callable[..., StrategyDecisionReport],
        notify_or_prepare: Callable[[bool, str, str], FeishuNotificationResult],
        record_notification: Callable[[str, str, FeishuNotificationResult], None],
        watch_sell_event_types: Callable[[], frozenset[OneToTwoEventType]],
    ) -> None:
        self._watch_phase_service = watch_phase_service
        self._notification_orchestrator = notification_orchestrator
        self._build_morning_report = build_morning_report
        self._build_strategy_decision_report = build_strategy_decision_report
        self._notify_or_prepare = notify_or_prepare
        self._record_notification = record_notification
        self._watch_sell_event_types = watch_sell_event_types

    def run(
        self,
        *,
        trade_date: str | None = None,
        phase: str = "scan",
        notify: bool = True,
        market_data_timeout_seconds: float | None = None,
    ) -> OneToTwoMorningReport:
        phase = self._watch_phase_service.normalize_phase(phase)
        report = self._build_morning_report(
            trade_date=trade_date,
            notify=False,
            record_notification=False,
            market_data_timeout_seconds=market_data_timeout_seconds,
            allow_cached_on_timeout=False,
        )
        strategy_report = (
            self._build_strategy_decision_report(
                trade_date=report.trade_date,
                market_rows=(),
                data_unavailable=True,
                candidates=(),
            )
            if report.status == "data_unavailable"
            else self._build_strategy_decision_report(
                trade_date=report.trade_date,
                candidates=report.candidates,
                market_temperature=report.market_temperature,
            )
        )
        allow_new_entry = (
            strategy_report.selected_strategy_id == "board-shadow-system"
            and strategy_report.selected_action == "operate_when_signal_exists"
        )
        phase_result = self._watch_phase_service.run_phase(
            report=report,
            phase=phase,
            allow_new_entry=allow_new_entry,
            entry_block_message=(
                f"主线守门要求空仓：{strategy_report.k92_rationale} "
                "今日策略为现金防守，盘中值守不写入新的模拟买入。"
            ),
        )
        account = phase_result.account
        latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
        should_send_watch_notification = self._notification_orchestrator.should_send_watch(
            phase=phase,
            account=account,
            trade_date=report.trade_date,
        )
        notification = self._notify_or_prepare(
            notify and should_send_watch_notification,
            one_to_two_watch_notification_title(
                phase=phase,
                trade_date=report.trade_date,
                latest_event_trade_date=(
                    account.events[0].trade_date if account.events else None
                ),
                is_buy_event=bool(account.events)
                and account.events[0].event_type == OneToTwoEventType.PAPER_BUY,
                is_sell_event=bool(account.events)
                and account.events[0].event_type in self._watch_sell_event_types(),
                latest_event_name=account.events[0].name if account.events else None,
                latest_event_symbol=account.events[0].symbol if account.events else None,
            ),
            one_to_two_watch_notification_message(
                phase=phase,
                trade_date=report.trade_date,
                ready=phase_result.ready,
                account=account,
                latest_event=latest_event,
                sell_event_types=self._watch_sell_event_types(),
                stop_warning_event_type=OneToTwoEventType.STOP_WARNING,
            ),
        )
        if should_send_watch_notification:
            self._record_notification(f"watch:{phase}", report.trade_date, notification)
        return OneToTwoMorningReport(
            report_id=report.report_id,
            trade_date=report.trade_date,
            trade_context=report.trade_context,
            market_temperature=report.market_temperature,
            status=report.status,
            summary=report.summary,
            candidates=report.candidates,
            account=account,
            notification=notification,
            next_action="继续盯住封板质量、止损位和 T+1 纪律。",
        )


__all__ = ["WatchReportService"]
