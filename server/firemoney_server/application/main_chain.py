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
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
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

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Build the 08:50 one-to-two report and optional Feishu notice."""

        report_date = trade_date or self._default_trade_date()
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
            market_temperature=rows[0].market_temperature if rows else 0,
            status=status,
            summary=summary,
            candidates=candidates,
            account=self._paper_store.load(),
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
        notify: bool = True,
    ) -> OneToTwoMorningReport:
        """Advance one-to-two watch events and paper-trading state."""

        report = self.build_one_to_two_morning_report(
            trade_date=trade_date,
            notify=False,
        )
        ready = tuple(item for item in report.candidates if item.status == "ready")
        account = self._paper_store.load()
        if ready and not account.positions:
            account = self._paper_store.buy_candidate(ready[0])
        elif account.positions:
            matched = next(
                (
                    candidate
                    for candidate in report.candidates
                    if candidate.symbol == account.positions[0].symbol
                ),
                None,
            )
            if matched:
                account = self._paper_store.update_risk(matched)

        latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二盘中",
            message=latest_event,
        )
        return OneToTwoMorningReport(
            report_id=report.report_id,
            trade_date=report.trade_date,
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

        report_date = trade_date or self._default_trade_date()
        account = self._paper_store.load()
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
            sample_count=len(account.events),
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
        sample_count = len(account.events)
        sell_count = sum(
            1 for event in account.events if event.event_type.value == "t1_sell"
        )
        warning_count = sum(
            1 for event in account.events if event.event_type.value == "stop_warning"
        )
        status = (
            "observation"
            if sample_count < self._one_to_two_settings.minimum_sample_for_stability
            else "reviewable"
        )
        return OneToTwoStabilityReport(
            report_id="one-to-two-stability",
            sample_count=sample_count,
            success_rate=round(sell_count / sample_count, 4) if sample_count else 0.0,
            average_return_pct=0.0,
            max_drawdown=min(0.0, account.equity - account.initial_cash),
            stop_warning_rate=(
                round(warning_count / sample_count, 4) if sample_count else 0.0
            ),
            low_breakout_success_rate=0.0,
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
