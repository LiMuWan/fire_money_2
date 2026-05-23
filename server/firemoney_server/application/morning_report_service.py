"""Morning report orchestration for the FireMoney mainline loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from server.firemoney_server.application.one_to_two_notification_text import (
    one_to_two_morning_notification_message,
)
from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from shared.contracts import (
    FeishuNotificationResult,
    OneToTwoCandidate,
    OneToTwoMorningReport,
    PaperAccount,
    StrategyDecisionReport,
)


class TradingCalendarLike(Protocol):
    def resolve(self, requested_date: str | None = None):
        """Resolve a requested date into the nearest trading context."""


class PaperStoreLike(Protocol):
    def prepare_for_trade_date(self, trade_date: str) -> PaperAccount:
        """Roll the paper account to one trade date."""


class MarketDataProviderLike(Protocol):
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        """Load one-to-two market rows."""


class MorningReportService:
    """Builds the morning report and optional low-noise Feishu notification."""

    def __init__(
        self,
        *,
        trading_calendar: TradingCalendarLike,
        paper_store: PaperStoreLike,
        market_data_provider: MarketDataProviderLike,
        load_market_rows_with_timeout: Callable[..., tuple[OneToTwoMarketRow, ...]],
        build_strategy_decision_report: Callable[..., StrategyDecisionReport],
        board_shadow_execution_candidates: Callable[..., tuple[OneToTwoCandidate, ...]],
        with_live_mainline_continuity: Callable[
            [OneToTwoCandidate, tuple[OneToTwoCandidate, ...]],
            OneToTwoCandidate,
        ]
        | None = None,
        notify_or_prepare: Callable[[bool, str, str], FeishuNotificationResult],
        record_notification: Callable[[str, str, FeishuNotificationResult], None],
        market_regime_label: Callable[[str], str],
        default_trade_date: Callable[[], str],
    ) -> None:
        self._trading_calendar = trading_calendar
        self._paper_store = paper_store
        self._market_data_provider = market_data_provider
        self._load_market_rows_with_timeout = load_market_rows_with_timeout
        self._build_strategy_decision_report = build_strategy_decision_report
        self._board_shadow_execution_candidates = board_shadow_execution_candidates
        self._with_live_mainline_continuity = with_live_mainline_continuity
        self._notify_or_prepare = notify_or_prepare
        self._record_notification = record_notification
        self._market_regime_label = market_regime_label
        self._default_trade_date = default_trade_date

    @staticmethod
    def market_unavailable_regime_label() -> str:
        return "行情异常暂停"

    def build_report(
        self,
        *,
        trade_date: str | None = None,
        notify: bool = True,
        record_notification: bool = True,
        market_data_timeout_seconds: float | None = None,
        allow_cached_on_timeout: bool = True,
    ) -> OneToTwoMorningReport:
        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        report_date = trade_context.trade_date
        account = self._paper_store.prepare_for_trade_date(report_date)
        try:
            rows = (
                self._load_market_rows_with_timeout(
                    report_date,
                    market_data_timeout_seconds,
                    allow_cached_on_timeout=allow_cached_on_timeout,
                )
                if market_data_timeout_seconds is not None
                else self._market_data_provider.load_one_to_two_rows(report_date)
            )
            data_unavailable = False
        except Exception:
            rows = ()
            data_unavailable = True

        candidates = (
            self._board_shadow_execution_candidates(
                report_date,
                rows=rows,
                include_blocked=True,
            )
            if rows and not data_unavailable
            else ()
        )
        if self._with_live_mainline_continuity and not market_data_timeout_seconds:
            candidates = tuple(
                self._with_live_mainline_continuity(candidate, candidates)
                for candidate in candidates
            )
        strategy_report = self._build_strategy_decision_report(
            trade_date=report_date,
            market_rows=rows,
            data_unavailable=data_unavailable,
            candidates=candidates,
        )
        ready_count = sum(1 for item in candidates if item.status == "ready")
        status = "data_unavailable" if data_unavailable else "ready" if ready_count else "blocked"
        summary = (
            "主线首板早盘：行情数据不可用，禁止生成模拟买入。"
            if data_unavailable
            else f"主线首板早盘：{len(candidates)} 个首板龙头候选样本，{ready_count} 个进入模拟盘观察。"
        )
        title_action = (
            "暂停"
            if data_unavailable
            else "买入观察"
            if ready_count
            else "防守空仓"
        )
        notification = self._notify_or_prepare(
            notify and trade_context.is_trading_day,
            f"FireMoney 早评 | {title_action} | {report_date}",
            one_to_two_morning_notification_message(
                report_date=report_date,
                market_temperature=rows[0].market_temperature if rows else 0,
                data_unavailable=data_unavailable,
                candidates=candidates,
                account=account,
                regime_label=(
                    self.market_unavailable_regime_label()
                    if data_unavailable
                    else self._market_regime_label(strategy_report.market_regime)
                ),
            ),
        )
        if record_notification:
            self._record_notification("morning", report_date, notification)
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
                "等待封板纪律、竞价和一进二确认。"
                if ready_count
                else "今日不触发模拟买入。"
            ),
        )


__all__ = ["MorningReportService"]
