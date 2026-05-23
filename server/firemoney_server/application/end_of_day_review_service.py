"""End-of-day review orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable

from server.firemoney_server.application.one_to_two_notification_text import (
    one_to_two_end_of_day_notification_message,
)
from shared.contracts import (
    FeishuNotificationResult,
    OneToTwoEndOfDayReview,
    OneToTwoEventType,
    OneToTwoStabilityReport,
    PaperAccount,
    TradingDayContext,
)


NotifyOrPrepare = Callable[[bool, str, str], FeishuNotificationResult]
RecordNotification = Callable[[str, str, FeishuNotificationResult], None]
BuildStabilityReport = Callable[[PaperAccount], OneToTwoStabilityReport]
BoardShadowHint = Callable[[], str]
RegimeLabel = Callable[[str], str]


class EndOfDayReviewService:
    """Builds the 15:10 review without loading stores or sending Feishu directly."""

    def __init__(
        self,
        *,
        notify_or_prepare: NotifyOrPrepare,
        record_notification: RecordNotification,
        build_stability_report: BuildStabilityReport,
        board_shadow_hint: BoardShadowHint,
        regime_label: RegimeLabel,
    ) -> None:
        self._notify_or_prepare = notify_or_prepare
        self._record_notification = record_notification
        self._build_stability_report = build_stability_report
        self._board_shadow_hint = board_shadow_hint
        self._regime_label = regime_label

    def build_review(
        self,
        *,
        report_date: str,
        trade_context: TradingDayContext,
        account: PaperAccount,
        data_unavailable: bool = False,
        regime_label: str = "",
        notify: bool = True,
        record_notification: bool = True,
    ) -> OneToTwoEndOfDayReview:
        warning_count = self._open_position_warning_count(account)
        t1_sell_count = sum(
            1
            for event in account.events
            if self._event_type_matches(event.event_type, OneToTwoEventType.T1_SELL)
            and event.trade_date == report_date
        )
        closed_trades = account.closed_trades
        success_count = sum(1 for record in closed_trades if record.success)
        realized_pnl = round(sum(record.realized_pnl for record in closed_trades), 2)
        realized_curve = []
        current = 0.0
        for record in reversed(closed_trades):
            current += record.realized_pnl
            realized_curve.append(current)
        max_drawdown = min(realized_curve, default=0.0)
        stability_report = self._build_stability_report(account)
        board_shadow_hint = self._board_shadow_hint()
        summary = (
            f"主线首板尾盘：完成样本 {len(closed_trades)} 笔，"
            f"成功 {success_count} 笔，已实现盈亏 {realized_pnl:.2f}。"
        )
        title_action = (
            "暂停"
            if data_unavailable
            else "持仓观察"
            if account.positions
            else "防守空仓"
        )
        notification = self._notify_or_prepare(
            notify,
            f"FireMoney 尾盘 | {title_action} | {report_date}",
            one_to_two_end_of_day_notification_message(
                report_date=report_date,
                account=account,
                warning_count=warning_count,
                t1_sell_count=t1_sell_count,
                realized_pnl=realized_pnl,
                stability_report=stability_report,
                board_shadow_hint=board_shadow_hint,
                data_unavailable=data_unavailable,
                regime_label=regime_label or self._regime_label("defense_stand_aside_day" if data_unavailable else ""),
            ),
        )
        if record_notification:
            self._record_notification("eod", report_date, notification)
        return OneToTwoEndOfDayReview(
            review_id=f"one-to-two-eod-{report_date}",
            trade_date=report_date,
            trade_context=trade_context,
            sample_count=len(closed_trades),
            success_count=success_count,
            warning_count=warning_count,
            realized_pnl=realized_pnl,
            max_drawdown=min(0.0, max_drawdown),
            stability_stage=stability_report.sample_stage,
            next_milestone=stability_report.next_milestone,
            strategy_boundary_suggestion=stability_report.strategy_boundary_suggestion,
            summary=summary,
            focus_points=(
                "尾盘只归档和评估完成样本，不改变当日交易。",
                "继续区分低位突破与高位接力样本。",
                board_shadow_hint,
            ),
            account=account,
            notification=notification,
            next_action=(
                "收盘后归档样本，明早继续扫描主线首板候选池。"
                f" {board_shadow_hint}"
            ),
        )

    def _event_type_matches(self, event_type: object, expected: OneToTwoEventType) -> bool:
        if event_type == expected:
            return True
        return getattr(event_type, "value", str(event_type)) == expected.value

    def _open_position_warning_count(self, account: PaperAccount) -> int:
        open_symbols = {position.symbol for position in account.positions}
        if not open_symbols:
            return 0
        return sum(
            1
            for event in account.events
            if event.symbol in open_symbols
            and self._event_type_matches(event.event_type, OneToTwoEventType.STOP_WARNING)
        )
