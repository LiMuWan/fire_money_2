"""Application workflow for the FireMoney one-to-two product line."""

from __future__ import annotations

from datetime import date

from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    MarketDataProvider,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
    load_one_to_two_settings,
)
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.trading_calendar import (
    AkshareTradingCalendar,
    TradingCalendar,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    OneToTwoEventType,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
    OneToTwoStabilityReport,
)


class MainChainService:
    """Orchestrates only the mainboard 10cm one-to-two validation loop."""

    def __init__(
        self,
        one_to_two_settings: OneToTwoStrategySettings | None = None,
        market_data_provider: MarketDataProvider | None = None,
        paper_store: PaperTradeStore | None = None,
        feishu_notifier: FeishuNotifier | None = None,
        trading_calendar: TradingCalendar | None = None,
    ) -> None:
        self._one_to_two_settings = one_to_two_settings or load_one_to_two_settings()
        self._one_to_two_policy = OneToTwoPolicy(self._one_to_two_settings)
        self._market_data_provider = market_data_provider or AkshareMarketDataProvider()
        self._paper_store = paper_store or PaperTradeStore(
            initial_cash=self._one_to_two_settings.initial_cash,
            max_position_pct=self._one_to_two_settings.max_position_pct,
            max_daily_trades=self._one_to_two_settings.max_daily_trades,
        )
        self._feishu_notifier = feishu_notifier or FeishuNotifier()
        self._trading_calendar = trading_calendar or AkshareTradingCalendar()

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Build the 08:50 one-to-two report and optional Feishu notice."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        account = self._paper_store.prepare_for_trade_date(report_date)
        try:
            rows = self._market_data_provider.load_one_to_two_rows(report_date)
            data_unavailable = False
        except Exception:
            rows = ()
            data_unavailable = True

        candidates = self._one_to_two_policy.build_candidates(rows)
        ready_count = sum(1 for item in candidates if item.status == "ready")
        status = "ready" if ready_count else "blocked"
        summary = (
            "一进二早盘：行情数据不可用，禁止生成模拟买入。"
            if data_unavailable
            else f"一进二早盘：{len(candidates)} 个昨日首板样本，{ready_count} 个进入模拟盘观察。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二早盘",
            message=summary,
        )
        return OneToTwoMorningReport(
            report_id=f"one-to-two-morning-{report_date}",
            trade_date=report_date,
            trade_context=trade_context.to_contract(),
            market_temperature=rows[0].market_temperature if rows else 0,
            status=status,
            summary=summary,
            candidates=candidates,
            account=account,
            notification=notification,
            next_action=(
                "等待竞价确认和事件驱动模拟盘。"
                if ready_count
                else "今日不触发模拟买入。"
            ),
        )

    def run_one_to_two_watch(
        self,
        trade_date: str | None = None,
        phase: str = "scan",
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Advance one-to-two watch events and paper-trading state."""

        if phase not in {"scan", "auction", "open", "risk"}:
            phase = "scan"
        report = self.build_one_to_two_morning_report(
            trade_date=trade_date,
            notify=False,
        )
        ready = tuple(item for item in report.candidates if item.status == "ready")
        account = self._paper_store.prepare_for_trade_date(report.trade_date)
        if account.positions:
            matched = next(
                (
                    candidate
                    for candidate in report.candidates
                    if candidate.symbol == account.positions[0].symbol
                ),
                None,
            )
            if matched and phase in {"open", "risk"}:
                account = self._paper_store.update_risk(matched)
        elif ready and phase == "scan":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "候选入池，等待竞价确认。",
            )
        elif ready and phase == "auction":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "竞价确认，一进二候选进入开盘触发观察。",
                event_type=OneToTwoEventType.AUCTION_CONFIRMED,
            )
        elif ready and phase == "open":
            account = self._paper_store.buy_candidate(ready[0])

        latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二盘中",
            message=latest_event,
        )
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
            next_action="继续盯住止损位和 T+1 纪律。",
        )

    def build_one_to_two_end_of_day_review(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoEndOfDayReview:
        """Build the 15:10 one-to-two review and optional Feishu notice."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        account = self._paper_store.prepare_for_trade_date(report_date)
        warning_count = sum(
            1 for event in account.events if event.event_type.value == "stop_warning"
        )
        sell_count = sum(
            1 for event in account.events if event.event_type.value == "t1_sell"
        )
        realized_pnl = round(account.equity - account.initial_cash, 2)
        summary = (
            f"一进二尾盘：权益 {account.equity:.2f}，"
            f"事件 {len(account.events)} 个，风险预警 {warning_count} 个。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二尾盘",
            message=summary,
        )
        return OneToTwoEndOfDayReview(
            review_id=f"one-to-two-eod-{report_date}",
            trade_date=report_date,
            trade_context=trade_context.to_contract(),
            sample_count=len(account.closed_trades),
            success_count=sell_count,
            warning_count=warning_count,
            realized_pnl=realized_pnl,
            max_drawdown=min(0.0, realized_pnl),
            summary=summary,
            focus_points=(
                "样本少于 30 笔时只观察，不自动调整策略边界。",
                "继续区分低位突破与高位接力样本。",
            ),
            account=account,
            notification=notification,
            next_action="收盘后归档样本，明早继续扫描昨日首板池。",
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        """Summarize current paper-trading stability observations."""

        account = self._paper_store.load()
        sample_count = len(account.closed_trades)
        sell_count = sum(1 for record in account.closed_trades if record.success)
        warning_count = sum(record.warning_count for record in account.closed_trades)
        total_return = sum(record.realized_pnl_pct for record in account.closed_trades)
        low_breakout_records = tuple(
            record
            for record in account.closed_trades
            if "低位" in record.position_label and "突破" in record.position_label
        )
        low_breakout_success = sum(1 for record in low_breakout_records if record.success)
        realized_curve = []
        current = 0.0
        for record in reversed(account.closed_trades):
            current += record.realized_pnl
            realized_curve.append(current)
        max_drawdown = min(realized_curve, default=0.0)
        status = (
            "observation"
            if sample_count < self._one_to_two_settings.minimum_sample_for_stability
            else "reviewable"
        )
        return OneToTwoStabilityReport(
            report_id="one-to-two-stability",
            sample_count=sample_count,
            success_rate=round(sell_count / sample_count, 4) if sample_count else 0.0,
            average_return_pct=round(total_return / sample_count, 4) if sample_count else 0.0,
            max_drawdown=min(0.0, max_drawdown),
            stop_warning_rate=(
                round(warning_count / sample_count, 4) if sample_count else 0.0
            ),
            low_breakout_success_rate=(
                round(low_breakout_success / len(low_breakout_records), 4)
                if low_breakout_records
                else 0.0
            ),
            status=status,
            summary=(
                "样本处于观察期，暂不自动给出策略边界结论。"
                if status == "observation"
                else "样本达到复查门槛，可以进入策略边界评估。"
            ),
            next_action="继续积累至少 30 笔一进二样本。",
        )

    def _notify_or_prepare(
        self,
        notify: bool,
        title: str,
        message: str,
    ) -> FeishuNotificationResult:
        if notify:
            return self._feishu_notifier.notify(title, message)
        return FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title=title,
            message=message,
            webhook_configured=False,
            error="notification skipped",
        )

    def _default_trade_date(self) -> str:
        return date.today().isoformat()
