"""Application workflow for the FireMoney one-to-two product line."""

from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from urllib.parse import urlparse

from server.firemoney_server.domain.one_to_two import (
    HistoricalPriceBar,
    OneToTwoPolicy,
)
from server.firemoney_server.infrastructure.feishu_notifier import FeishuNotifier
from server.firemoney_server.infrastructure.market_data import (
    AkshareMarketDataProvider,
    MarketDataProvider,
)
from server.firemoney_server.infrastructure.one_to_two_config import (
    OneToTwoStrategySettings,
    load_one_to_two_settings,
)
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import (
    AkshareTradingCalendar,
    TradingCalendar,
)
from shared.contracts import (
    BacktestDataQualityCheck,
    FeishuNotificationResult,
    MainlineContinuity,
    MainlineNewsItem,
    NotificationStatus,
    NotificationRecord,
    OneToTwoBetaReadinessReport,
    OneToTwoBacktestAuditReport,
    OneToTwoCandidate,
    OneToTwoDoctorCheck,
    OneToTwoDoctorReport,
    OneToTwoEventType,
    OneToTwoEndOfDayReview,
    OneToTwoHistoricalReplayReport,
    OneToTwoHistoricalReplayTrade,
    OneToTwoMorningReport,
    OneToTwoRecentSample,
    OneToTwoStabilityReport,
    PaperAccount,
    TradingDayContext,
)


class MainChainService:
    """Orchestrates only the mainboard 10cm one-to-two validation loop."""

    def __init__(
        self,
        one_to_two_settings: OneToTwoStrategySettings | None = None,
        market_data_provider: MarketDataProvider | None = None,
        paper_store: PaperTradeStore | None = None,
        feishu_notifier: FeishuNotifier | None = None,
        notification_store: NotificationRecordStore | None = None,
        scheduler_state_store: SchedulerStateStore | None = None,
        scheduler_run_store: SchedulerRunStore | None = None,
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
        self._notification_store = notification_store or NotificationRecordStore()
        self._scheduler_state_store = scheduler_state_store or SchedulerStateStore()
        self._scheduler_run_store = scheduler_run_store or SchedulerRunStore()
        self._trading_calendar = trading_calendar or AkshareTradingCalendar()

    def resolve_trading_day(self, trade_date: str | None = None) -> TradingDayContext:
        """Resolve a requested date with the same calendar used by workflows."""

        return self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        ).to_contract()

    def build_one_to_two_morning_report(
        self,
        trade_date: str | None = None,
        notify: bool = True,
        record_notification: bool = True,
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
            "主线首板早盘：行情数据不可用，禁止生成模拟买入。"
            if data_unavailable
            else f"主线首板早盘：{len(candidates)} 个首板龙头候选样本，{ready_count} 个进入模拟盘观察。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 主线首板早盘",
            message=self._morning_notification_message(
                report_date=report_date,
                market_temperature=rows[0].market_temperature if rows else 0,
                data_unavailable=data_unavailable,
                candidates=candidates,
                account=account,
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
            record_notification=False,
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
                matched = self._with_live_mainline_continuity(matched, report.candidates)
                account = self._paper_store.update_risk(matched)
                if account.positions and phase == "risk":
                    account = self._exit_if_discipline_requires(matched)
        elif ready and phase == "scan":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "主线首板候选入池，等待封板纪律和竞价确认。",
            )
        elif ready and phase == "auction":
            account = self._paper_store.record_candidate_event(
                ready[0],
                "竞价确认，主线首板候选进入一进二确认观察。",
                event_type=OneToTwoEventType.AUCTION_CONFIRMED,
            )
        elif ready and phase == "open":
            account = self._paper_store.buy_candidate(ready[0])

        latest_event = account.events[0].message if account.events else "暂无模拟盘事件"
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 主线首板盘中",
            message=self._watch_notification_message(
                phase=phase,
                report=report,
                ready=ready,
                account=account,
                latest_event=latest_event,
            ),
        )
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

    def _exit_if_discipline_requires(
        self,
        candidate: OneToTwoCandidate,
    ) -> PaperAccount:
        account = self._paper_store.load()
        if not account.positions:
            return account
        position = account.positions[0]
        if not position.can_sell_today:
            return account
        if (
            position.mainline_continuity
            and position.mainline_continuity.score < self._one_to_two_settings.mainline_fade_score
        ):
            return self._paper_store.exit_position(
                candidate,
                exit_reason="mainline_fade_exit",
                message=(
                    "主线持续性跌破纪律阈值，T+1 已到，模拟退出保住本金。"
                ),
                event_type=OneToTwoEventType.MAINLINE_FADE_EXIT,
                holding_trade_days=self._holding_trade_days(
                    opened_at=position.opened_at,
                    trade_date=candidate.trade_date,
                ),
            )
        if position.exit_plan:
            peak_price = position.peak_price or position.latest_price
            strong_take_profit_price = position.entry_price * (
                1 + position.exit_plan.strong_take_profit_pct
            )
            trailing_stop_price = round(
                peak_price * (1 - position.exit_plan.trailing_stop_pct),
                2,
            )
            if (
                peak_price >= strong_take_profit_price
                and candidate.latest_price <= trailing_stop_price
            ):
                return self._paper_store.exit_position(
                    candidate,
                    exit_reason="trailing_take_profit",
                    message=(
                        "强势涨幅已到 "
                        f"{self._format_pct(position.exit_plan.strong_take_profit_pct)}，"
                        "回撤触发 "
                        f"{self._format_pct(position.exit_plan.trailing_stop_pct)} "
                        "保护，T+1 已到，模拟止盈。"
                    ),
                    event_type=OneToTwoEventType.TAKE_PROFIT,
                    holding_trade_days=self._holding_trade_days(
                        opened_at=position.opened_at,
                        trade_date=candidate.trade_date,
                    ),
                )
        if (
            position.exit_plan
            and position.unrealized_pnl_pct >= position.exit_plan.first_take_profit_pct
        ):
            return self._paper_store.exit_position(
                candidate,
                exit_reason="take_profit_first_target",
                message=(
                    f"浮盈达到 {self._format_pct(position.exit_plan.first_take_profit_pct)} "
                    "第一止盈纪律，T+1 已到，模拟落袋。"
                ),
                event_type=OneToTwoEventType.TAKE_PROFIT,
                holding_trade_days=self._holding_trade_days(
                    opened_at=position.opened_at,
                    trade_date=candidate.trade_date,
                ),
            )
        holding_trade_days = self._holding_trade_days(
            opened_at=position.opened_at,
            trade_date=candidate.trade_date,
        )
        if holding_trade_days < self._one_to_two_settings.max_holding_trade_days:
            return account
        if position.unrealized_pnl_pct >= self._one_to_two_settings.discipline_exit_min_gain_pct:
            return account
        return self._paper_store.exit_position(
            candidate,
            exit_reason="discipline_weak_after_2_days",
            message="持仓超过 2 个交易日未继续走强，按主线首板纪律退出。",
            holding_trade_days=holding_trade_days,
        )

    def _with_live_mainline_continuity(
        self,
        candidate: OneToTwoCandidate,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> OneToTwoCandidate:
        base = candidate.mainline_continuity
        if base is None:
            return candidate
        symbols = tuple(item.symbol for item in candidates[:8])
        news = self._load_mainline_news(base.theme, symbols)
        hot_stock_count = sum(
            1
            for item in candidates
            if item.mainline_continuity
            and item.mainline_continuity.theme == base.theme
        )
        limit_up_count = sum(
            1 for item in candidates if item.latest_price >= item.limit_up_price * 0.995
        )
        news_bonus = min(len(news) * 3, 12)
        breadth_bonus = min(hot_stock_count * 4 + limit_up_count * 3, 18)
        adjusted_score = min(100.0, base.score + news_bonus + breadth_bonus)
        risk_notes = list(base.risk_notes)
        if not news:
            risk_notes.append("未抓取到新的主线消息，只按价格和封板持续性观察")
        status = (
            "strong"
            if adjusted_score >= 75
            else "watch"
            if adjusted_score >= self._one_to_two_settings.mainline_fade_score
            else "fading"
        )
        continuity = MainlineContinuity(
            theme=base.theme,
            score=round(adjusted_score, 2),
            status=status,
            hot_stock_count=hot_stock_count,
            limit_up_count=limit_up_count,
            news_count=len(news),
            latest_news=news[:5],
            reasons=(
                *base.reasons,
                f"同主线候选 {hot_stock_count} 个",
                f"近涨停强度 {limit_up_count} 个",
                f"消息证据 {len(news)} 条",
            ),
            risk_notes=tuple(dict.fromkeys(risk_notes)),
            next_action=(
                "主线仍有持续性，按止盈和回撤纪律观察。"
                if status == "strong"
                else "主线仍需确认，达到第一止盈优先落袋。"
                if status == "watch"
                else "主线持续性衰减，T+1 已到优先退出。"
            ),
        )
        return self._replace_candidate_continuity(candidate, continuity)

    def _load_mainline_news(
        self,
        theme: str,
        symbols: tuple[str, ...],
    ) -> tuple[MainlineNewsItem, ...]:
        try:
            return self._market_data_provider.load_mainline_news(theme, symbols)
        except Exception:
            return ()

    def _replace_candidate_continuity(
        self,
        candidate: OneToTwoCandidate,
        continuity: MainlineContinuity,
    ) -> OneToTwoCandidate:
        return OneToTwoCandidate(
            symbol=candidate.symbol,
            name=candidate.name,
            trade_date=candidate.trade_date,
            score=candidate.score,
            status=candidate.status,
            latest_price=candidate.latest_price,
            limit_up_price=candidate.limit_up_price,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            position_limit_pct=candidate.position_limit_pct,
            first_board_score=candidate.first_board_score,
            auction_score=candidate.auction_score,
            position_score=candidate.position_score,
            theme_score=candidate.theme_score,
            liquidity_score=candidate.liquidity_score,
            position_profile=candidate.position_profile,
            blockers=candidate.blockers,
            warnings=candidate.warnings,
            rationale=candidate.rationale,
            next_action=candidate.next_action,
            mainline_score=candidate.mainline_score,
            sealing_score=candidate.sealing_score,
            leader_score=candidate.leader_score,
            leader_label=candidate.leader_label,
            strategy_tags=candidate.strategy_tags,
            discipline_summary=candidate.discipline_summary,
            exit_plan=candidate.exit_plan,
            mainline_continuity=continuity,
        )

    def _holding_trade_days(self, opened_at: str, trade_date: str) -> int:
        if opened_at >= trade_date:
            return 0
        current = opened_at
        count = 0
        while current < trade_date:
            next_context = self._trading_calendar.resolve(current)
            next_date = next_context.next_trade_date
            if next_date <= current:
                break
            current = next_date
            count += 1
        return count

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
        t1_sell_count = sum(
            1
            for event in account.events
            if event.event_type == OneToTwoEventType.T1_SELL
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
        stability_report = self._stability_from_account(account)
        summary = (
            f"主线首板尾盘：完成样本 {len(closed_trades)} 笔，"
            f"成功 {success_count} 笔，已实现盈亏 {realized_pnl:.2f}。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 主线首板尾盘",
            message=self._end_of_day_notification_message(
                report_date=report_date,
                account=account,
                warning_count=warning_count,
                t1_sell_count=t1_sell_count,
                realized_pnl=realized_pnl,
                stability_report=stability_report,
            ),
        )
        self._record_notification("eod", report_date, notification)
        return OneToTwoEndOfDayReview(
            review_id=f"one-to-two-eod-{report_date}",
            trade_date=report_date,
            trade_context=trade_context.to_contract(),
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
            ),
            account=account,
            notification=notification,
            next_action="收盘后归档样本，明早继续扫描主线首板候选池。",
        )

    def build_one_to_two_stability_report(self) -> OneToTwoStabilityReport:
        """Summarize current paper-trading stability observations."""

        account = self._paper_store.load()
        return self._stability_from_account(account)

    def send_one_to_two_feishu_test(
        self,
        trade_date: str | None = None,
        notify: bool = True,
    ) -> FeishuNotificationResult:
        """Send or prepare a Feishu connectivity test for the one-to-two loop."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        message = "\n".join(
            (
                f"交易日：{trade_context.trade_date}",
                "用途：模拟盘 Beta 飞书联通测试",
                "说明：这不是交易信号，不触发模拟买入或卖出。",
                "后续：收到后再运行 doctor --beta 和 beta-start。",
            )
        )
        result = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 主线首板飞书测试",
            message=message,
        )
        self._record_notification("feishu:test", trade_context.trade_date, result)
        return result

    def build_one_to_two_beta_readiness_report(
        self,
        trade_date: str | None = None,
    ) -> OneToTwoBetaReadinessReport:
        """Run the non-trading Beta readiness gate for the one-to-two loop."""

        requested_date = trade_date or self._default_trade_date()
        trade_context = self._trading_calendar.resolve(requested_date)
        preflight_report = self.build_one_to_two_doctor_report(
            trade_date=requested_date,
            beta=False,
        )
        not_ready_preflight_checks = tuple(
            check
            for check in preflight_report.checks
            if check.status != "ready" and check.check_id != "feishu"
        )
        feishu_shape_check = self._doctor_feishu_check(
            trade_context.trade_date,
            beta=False,
        )
        should_send_feishu = (
            trade_context.is_trading_day
            and not not_ready_preflight_checks
            and feishu_shape_check.status == "ready"
        )
        feishu_test = (
            self.send_one_to_two_feishu_test(
                trade_date=trade_context.trade_date,
                notify=True,
            )
            if should_send_feishu
            else FeishuNotificationResult(
                status=NotificationStatus.PREPARED,
                title="FireMoney 主线首板飞书测试",
                message="Beta 预检未发送飞书测试，不触发模拟买入或卖出。",
                webhook_configured=self._has_feishu_delivery_config(),
                error=self._beta_readiness_skip_reason(
                    trade_context.is_trading_day,
                    not_ready_preflight_checks,
                    feishu_shape_check,
                ),
            )
        )
        doctor_report = self.build_one_to_two_doctor_report(
            trade_date=requested_date,
            beta=True,
        )
        status = "ready" if doctor_report.status == "ready" else "blocked"
        summary = (
            "模拟盘 Beta 预检通过，可以启动主线首板值守。"
            if status == "ready"
            else "模拟盘 Beta 预检未通过，先修复阻断项再启动值守。"
        )
        return OneToTwoBetaReadinessReport(
            report_id=f"one-to-two-beta-readiness-{trade_context.trade_date}",
            trade_date=trade_context.trade_date,
            status=status,
            summary=summary,
            feishu_test=feishu_test,
            doctor_report=doctor_report,
            next_action=(
                "运行 beta-start --loop --interval-seconds 60。"
                if status == "ready"
                else "按 doctor_report.checks 修复 blocked 项后重新运行 beta-check。"
            ),
        )

    def _beta_readiness_skip_reason(
        self,
        is_trading_day: bool,
        not_ready_preflight_checks: tuple[OneToTwoDoctorCheck, ...],
        feishu_shape_check: OneToTwoDoctorCheck,
    ) -> str:
        if not is_trading_day:
            return "non-trading day"
        if not_ready_preflight_checks:
            return f"preflight not ready: {not_ready_preflight_checks[0].check_id}"
        if feishu_shape_check.status != "ready":
            return f"feishu not ready: {feishu_shape_check.detail}"
        return "preflight blocked"

    def build_one_to_two_doctor_report(
        self,
        trade_date: str | None = None,
        beta: bool = False,
    ) -> OneToTwoDoctorReport:
        """Check whether the one-to-two loop is ready to run locally."""

        trade_context = self._trading_calendar.resolve(
            trade_date or self._default_trade_date()
        )
        checks = (
            self._doctor_strategy_check(),
            self._doctor_trading_day_check(trade_context, beta=beta),
            self._doctor_market_data_check(trade_context.trade_date),
            self._doctor_paper_store_check(),
            self._doctor_notification_store_check(),
            self._doctor_scheduler_state_store_check(),
            self._doctor_feishu_check(trade_context.trade_date, beta=beta),
            self._doctor_scheduler_check(),
            self._doctor_scheduler_run_store_check(),
        )
        has_blocked = any(check.status == "blocked" for check in checks)
        has_warning = any(check.status == "warning" for check in checks)
        status = "blocked" if has_blocked else ("warning" if has_warning else "ready")
        summary = (
                "主线首板运行体检未通过，先修复阻断项再启动模拟盘。"
            if status == "blocked"
            else (
                "主线首板运行体检有可选项未就绪，核心模拟盘可以继续。"
                if status == "warning"
                else "主线首板运行体检通过，可以按早盘、盘中、尾盘主线运行。"
            )
        )
        return OneToTwoDoctorReport(
            report_id=f"one-to-two-doctor-{trade_context.trade_date}",
            trade_date=trade_context.trade_date,
            status=status,
            summary=summary,
            checks=checks,
            next_action=(
                "修复 blocked 检查项后再运行 morning/watch/schedule。"
                if status == "blocked"
                else "继续按 morning -> watch -> eod -> stability 验证主线首板。"
            ),
        )

    def load_notification_records(
        self,
        workflow: str | None = None,
        status: str | NotificationStatus | None = None,
        limit: int | None = None,
    ) -> tuple[NotificationRecord, ...]:
        """Return recent one-to-two notification delivery records."""

        records = self._notification_store.load()
        if workflow:
            records = tuple(record for record in records if record.workflow == workflow)
        if status:
            expected = status if isinstance(status, NotificationStatus) else NotificationStatus(status)
            records = tuple(record for record in records if record.status == expected)
        if limit is not None:
            records = records[: max(0, limit)]
        return records

    def run_one_to_two_backtest(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoStabilityReport:
        """Replay one-to-two samples over historical dates in an isolated ledger."""

        dates = self._resolve_backtest_dates(start_date, end_date, max_trade_days)

        with TemporaryDirectory() as temp_dir:
            paper_store = PaperTradeStore(
                Path(temp_dir) / "paper_trades.json",
                initial_cash=self._one_to_two_settings.initial_cash,
                max_position_pct=self._one_to_two_settings.max_position_pct,
                max_daily_trades=self._one_to_two_settings.max_daily_trades,
            )
            policy = OneToTwoPolicy(self._one_to_two_settings)
            for trade_date in dates:
                try:
                    rows = self._market_data_provider.load_one_to_two_rows(trade_date)
                except Exception:
                    continue
                candidates = policy.build_candidates(rows)
                ready = next(
                    (candidate for candidate in candidates if candidate.status == "ready"),
                    None,
                )
                if not ready:
                    continue
                account = paper_store.load()
                if account.positions:
                    position = account.positions[0]
                    matched = next(
                        (
                            candidate
                            for candidate in candidates
                            if candidate.symbol == position.symbol
                        ),
                        None,
                    )
                    if matched and position.can_sell_today:
                        paper_store.exit_position(
                            matched,
                            exit_reason="backtest_discipline",
                            message="历史回放纪律退出，完成一笔主线首板样本。",
                            holding_trade_days=1,
                        )
                if not paper_store.load().positions:
                    paper_store.buy_candidate(ready)
            account = paper_store.load()
            if account.positions and dates:
                position = account.positions[0]
                last_date = dates[-1]
                paper_store.prepare_for_trade_date(last_date)
                synthetic_exit = self._candidate_for_position(position, last_date)
                paper_store.exit_position(
                    synthetic_exit,
                    exit_reason="backtest_forced_close",
                    message="历史回放结束，强制按最新价归档样本。",
                    holding_trade_days=1,
                )
            return self._stability_from_account(paper_store.load())

    def build_one_to_two_backtest_audit(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_trade_days: int = 30,
    ) -> OneToTwoBacktestAuditReport:
        """Run the backtest and wrap it with data-quality admission checks."""

        dates = self._resolve_backtest_dates(start_date, end_date, max_trade_days)
        stability_report = self.run_one_to_two_backtest(
            start_date=start_date,
            end_date=end_date,
            max_trade_days=max_trade_days,
        )
        quality_checks = self._backtest_data_quality_checks(
            dates=dates,
            stability_report=stability_report,
        )
        blocked = any(check.status == "blocked" for check in quality_checks)
        warning = any(check.status == "warning" for check in quality_checks)
        status = "blocked" if blocked else "warning" if warning else "ready"
        sample_count = stability_report.sample_count
        summary = (
            f"回测准入未通过：{sample_count} 笔样本，存在数据或样本阻断项。"
            if status == "blocked"
            else f"回测仍处观察期：{sample_count} 笔样本，尚不足以证明长期稳定。"
            if status == "warning"
            else f"回测准入通过：{sample_count} 笔样本，可进入模拟盘 Beta 验证。"
        )
        return OneToTwoBacktestAuditReport(
            report_id=f"one-to-two-backtest-audit-{dates[0] if dates else 'none'}-{dates[-1] if dates else 'none'}",
            start_date=dates[0] if dates else "",
            end_date=dates[-1] if dates else "",
            requested_trade_days=max_trade_days,
            usable_trade_days=len(dates),
            data_quality_checks=quality_checks,
            stability_report=stability_report,
            status=status,
            summary=summary,
            limitations=(
                "AkShare 免费数据不等同专业 Point-in-Time 数据，退市和历史成分偏差仍需后续加强。",
                "当前回测以日线/涨停池事件近似，不能替代 Tick 或逐笔成交验证。",
                "少于 30 笔闭环样本只允许观察，不允许宣称策略稳定盈利。",
            ),
            recommended_next_action=(
                "修复 blocked 项后重新运行 backtest-audit。"
                if status == "blocked"
                else "继续扩大回测窗口到 5-8 年或接入更干净的历史数据源。"
                if status == "warning"
                else "进入 beta-check 和 beta-start，只做模拟盘实盘跟踪验证。"
            ),
        )

    def run_one_to_two_historical_replay(
        self,
        as_of_date: str | None = None,
        holding_days: int = 5,
    ) -> OneToTwoHistoricalReplayReport:
        """Replay one historical decision without using future bars for selection."""

        trade_context = self._trading_calendar.resolve(
            as_of_date or self._default_trade_date()
        )
        entry_date = trade_context.trade_date
        data_mode = self._market_data_provider.__class__.__name__
        no_future_notes = (
            f"选股只读取 {entry_date} 当时的一进二候选池和策略配置。",
            "后续日线只用于模拟卖点、盈亏和盈亏比，不参与候选评分。",
            "日线无法还原盘中先后顺序，同日触发止损和止盈时按保守止损优先。",
        )
        quality_checks: list[BacktestDataQualityCheck] = [
            BacktestDataQualityCheck(
                check_id="no_future_selection",
                label="无未来函数",
                status="ready",
                detail=f"候选选择阶段截止到 {entry_date}，未读取后续价格柱。",
                next_action="正式研究时继续使用逐日快照或 Point-in-Time 数据源复核。",
            )
        ]
        if isinstance(self._market_data_provider, AkshareMarketDataProvider):
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="point_in_time_data",
                    label="PIT 数据",
                    status="warning",
                    detail="AkShare 免费数据适合验证流程，但不等同专业 Point-in-Time 快照。",
                    next_action="正式评价长期胜率前，接入退市样本和逐日快照数据。",
                )
            )

        try:
            rows = self._market_data_provider.load_one_to_two_rows(entry_date)
        except Exception as exc:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="candidate_pool",
                    label="候选池",
                    status="blocked",
                    detail=f"{entry_date} 候选池不可用：{exc}",
                    next_action="先修复行情源或改用 --sample-data 验证链路。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：候选池不可用。",
                next_action="修复行情源后重新运行 replay。",
            )

        candidates = self._one_to_two_policy.build_candidates(rows)
        candidate = next(
            (item for item in candidates if item.status == "ready"),
            None,
        )
        if candidate is None:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="candidate_pool",
                    label="候选池",
                    status="blocked",
                    detail=f"{entry_date} 没有达到执行分数和硬过滤的候选。",
                    next_action="保留空样本，不生成模拟买入。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放无交易：当日没有合格候选。",
                next_action="换一个历史交易日，或先扩大回放窗口做样本统计。",
            )

        replay_dates = self._replay_trade_dates(
            entry_date=entry_date,
            holding_days=holding_days,
        )
        if len(replay_dates) < 2:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_window",
                    label="价格窗口",
                    status="blocked",
                    detail="缺少 T+1 之后的交易日，无法计算卖出和盈亏比。",
                    next_action="选择更早的历史日期或等待后续交易日数据。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：没有足够后续交易日。",
                candidate=candidate,
                next_action="选择更早的历史日期重新运行 replay。",
            )

        try:
            bars = self._market_data_provider.load_price_bars(
                candidate.symbol,
                replay_dates[0],
                replay_dates[-1],
            )
        except Exception as exc:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_bars",
                    label="日线价格",
                    status="blocked",
                    detail=f"{candidate.symbol} 后续日线不可用：{exc}",
                    next_action="修复历史日线源后重新运行 replay。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：后续价格不可用。",
                candidate=candidate,
                next_action="修复历史日线源后重新运行 replay。",
            )

        expected_dates = set(replay_dates)
        bars = tuple(bar for bar in bars if bar.trade_date in expected_dates)
        if len(bars) < 2:
            quality_checks.append(
                BacktestDataQualityCheck(
                    check_id="price_bars",
                    label="日线价格",
                    status="blocked",
                    detail=f"{candidate.symbol} 只取得 {len(bars)} 根价格柱，无法完成 T+1 回放。",
                    next_action="选择更早日期，或检查历史日线是否缺失。",
                )
            )
            return self._historical_replay_blocked_report(
                entry_date=entry_date,
                data_mode=data_mode,
                quality_checks=tuple(quality_checks),
                no_future_notes=no_future_notes,
                summary="历史逐日回放被阻断：日线样本不足。",
                candidate=candidate,
                next_action="补齐历史价格后重新运行 replay。",
            )

        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="price_bars",
                label="日线价格",
                status="ready",
                detail=f"取得 {candidate.symbol} {bars[0].trade_date} 到 {bars[-1].trade_date} 的 {len(bars)} 根日线。",
                next_action="用后续价格柱执行卖点，不回灌选股。",
            )
        )
        quality_checks.append(
            BacktestDataQualityCheck(
                check_id="daily_bar_sequence",
                label="日内顺序",
                status="warning",
                detail="日线只有高低收，无法证明盘中先止盈还是先止损；当前按保守止损优先。",
                next_action="后续若接入分钟线或 Tick，可把执行价精度升级。",
            )
        )
        trade = self._simulate_historical_trade(
            candidate=candidate,
            bars=bars,
            data_mode=data_mode,
        )
        warning = any(check.status == "warning" for check in quality_checks)
        status = "warning" if warning else "ready"
        summary = (
            f"历史逐日回放完成：{candidate.name}({candidate.symbol}) "
            f"{trade.entry_date} 买入，{trade.exit_date} 按 {trade.exit_reason} 卖出，"
            f"收益 {trade.realized_pnl_pct:.2%}，盈亏比 {trade.risk_reward_ratio:.2f}R。"
        )
        return OneToTwoHistoricalReplayReport(
            report_id=f"one-to-two-replay-{entry_date}-{candidate.symbol}",
            as_of_date=entry_date,
            entry_date=trade.entry_date,
            exit_date=trade.exit_date,
            data_mode=data_mode,
            status=status,
            summary=summary,
            candidate=candidate,
            trade=trade,
            quality_checks=tuple(quality_checks),
            no_future_leakage_notes=no_future_notes,
            next_action=(
                "这是一笔单点回放；下一步应扩大到连续历史窗口，统计 30/50/100 笔样本。"
            ),
        )

    def _historical_replay_blocked_report(
        self,
        entry_date: str,
        data_mode: str,
        quality_checks: tuple[BacktestDataQualityCheck, ...],
        no_future_notes: tuple[str, ...],
        summary: str,
        next_action: str,
        candidate: OneToTwoCandidate | None = None,
    ) -> OneToTwoHistoricalReplayReport:
        return OneToTwoHistoricalReplayReport(
            report_id=f"one-to-two-replay-{entry_date}-blocked",
            as_of_date=entry_date,
            entry_date=entry_date,
            exit_date="",
            data_mode=data_mode,
            status="blocked",
            summary=summary,
            candidate=candidate,
            trade=None,
            quality_checks=quality_checks,
            no_future_leakage_notes=no_future_notes,
            next_action=next_action,
        )

    def _replay_trade_dates(self, entry_date: str, holding_days: int) -> list[str]:
        dates = [entry_date]
        current = entry_date
        for _index in range(max(1, holding_days)):
            context = self._trading_calendar.resolve(current)
            next_date = context.next_trade_date
            if next_date <= current:
                break
            dates.append(next_date)
            current = next_date
        return dates

    def _simulate_historical_trade(
        self,
        candidate: OneToTwoCandidate,
        bars: tuple[HistoricalPriceBar, ...],
        data_mode: str,
    ) -> OneToTwoHistoricalReplayTrade:
        entry_price = candidate.entry_price
        exit_plan = candidate.exit_plan
        stop_loss = exit_plan.stop_loss if exit_plan else candidate.stop_loss
        first_take_profit_price = (
            exit_plan.first_take_profit_price
            if exit_plan
            else round(entry_price * (1 + self._one_to_two_settings.first_take_profit_pct), 2)
        )
        strong_take_profit_pct = (
            exit_plan.strong_take_profit_pct
            if exit_plan
            else self._one_to_two_settings.strong_take_profit_pct
        )
        trailing_stop_pct = (
            exit_plan.trailing_stop_pct
            if exit_plan
            else self._one_to_two_settings.trailing_stop_pct
        )
        max_holding_trade_days = min(
            len(bars) - 1,
            exit_plan.max_holding_trade_days if exit_plan else self._one_to_two_settings.max_holding_trade_days,
        )
        position_cash = self._one_to_two_settings.initial_cash * candidate.position_limit_pct
        quantity = int(position_cash // (entry_price * 100)) * 100 if entry_price else 0
        if quantity <= 0 and entry_price > 0:
            quantity = 100

        exit_bar = bars[min(max_holding_trade_days, len(bars) - 1)]
        exit_price = exit_bar.close_price
        exit_reason = "replay_forced_close"
        peak_price = entry_price
        max_favorable_pct = 0.0
        max_adverse_pct = 0.0
        notes = [
            "严格 T+1：买入当天不模拟卖出。",
            "选股完成后才读取后续价格柱计算盈亏。",
        ]

        for holding_day, bar in enumerate(bars[1:], start=1):
            peak_price = max(peak_price, bar.high_price)
            favorable_pct = (bar.high_price - entry_price) / entry_price
            adverse_pct = (bar.low_price - entry_price) / entry_price
            max_favorable_pct = max(max_favorable_pct, favorable_pct)
            max_adverse_pct = min(max_adverse_pct, adverse_pct)

            if bar.low_price <= stop_loss:
                exit_bar = bar
                exit_price = stop_loss
                exit_reason = "stop_loss_t1"
                break

            strong_reached = (peak_price - entry_price) / entry_price >= strong_take_profit_pct
            trailing_stop = round(peak_price * (1 - trailing_stop_pct), 2)
            if strong_reached and bar.low_price <= trailing_stop:
                exit_bar = bar
                exit_price = trailing_stop
                exit_reason = "trailing_take_profit"
                break

            if bar.high_price >= first_take_profit_price:
                exit_bar = bar
                exit_price = first_take_profit_price
                exit_reason = "take_profit_first_target"
                break

            if holding_day >= max_holding_trade_days:
                exit_bar = bar
                exit_price = bar.close_price
                exit_reason = "max_holding_close"
                break

        gross_return_pct = (
            (exit_price - entry_price) / entry_price if entry_price else 0.0
        )
        realized_pnl = round((exit_price - entry_price) * quantity, 2)
        stop_risk_pct = (
            exit_plan.stop_loss_pct
            if exit_plan and exit_plan.stop_loss_pct > 0
            else max((entry_price - stop_loss) / entry_price, 0.0001)
            if entry_price
            else 0.0001
        )
        risk_reward_ratio = gross_return_pct / max(stop_risk_pct, 0.0001)
        return OneToTwoHistoricalReplayTrade(
            symbol=candidate.symbol,
            name=candidate.name,
            entry_date=bars[0].trade_date,
            exit_date=exit_bar.trade_date,
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=quantity,
            gross_return_pct=round(gross_return_pct, 6),
            realized_pnl=realized_pnl,
            realized_pnl_pct=round(gross_return_pct, 6),
            holding_trade_days=self._holding_trade_days(
                opened_at=bars[0].trade_date,
                trade_date=exit_bar.trade_date,
            ),
            exit_reason=exit_reason,
            risk_reward_ratio=round(risk_reward_ratio, 4),
            max_favorable_pct=round(max_favorable_pct, 6),
            max_adverse_pct=round(max_adverse_pct, 6),
            candidate_score=candidate.score,
            position_label=candidate.position_profile.label,
            evidence_date=candidate.trade_date,
            data_mode=data_mode,
            notes=tuple(notes),
        )

    def _resolve_backtest_dates(
        self,
        start_date: str | None,
        end_date: str | None,
        max_trade_days: int,
    ) -> list[str]:
        end_context = self._trading_calendar.resolve(end_date or self._default_trade_date())
        end_trade_date = date.fromisoformat(end_context.trade_date)
        start_trade_date = (
            date.fromisoformat(self._trading_calendar.resolve(start_date).trade_date)
            if start_date
            else end_trade_date - timedelta(days=max_trade_days * 2)
        )
        dates: list[str] = []
        cursor = start_trade_date
        while cursor <= end_trade_date:
            context = self._trading_calendar.resolve(cursor.isoformat())
            if context.trade_date == cursor.isoformat():
                dates.append(context.trade_date)
                if start_date and len(dates) >= max_trade_days:
                    break
            cursor += timedelta(days=1)
        if start_date:
            return dates
        return dates[-max_trade_days:]

    def _backtest_data_quality_checks(
        self,
        dates: list[str],
        stability_report: OneToTwoStabilityReport,
    ) -> tuple[BacktestDataQualityCheck, ...]:
        checks: list[BacktestDataQualityCheck] = []
        checks.append(
            BacktestDataQualityCheck(
                check_id="data_window",
                label="数据窗口",
                status="ready" if len(dates) >= 20 else "blocked",
                detail=f"可用交易日 {len(dates)} 天；建议正式研究覆盖 5-8 年多轮牛熊。",
                next_action=(
                    "继续执行回测。"
                    if len(dates) >= 20
                    else "扩大 --max-trade-days 或指定更长 start/end 日期。"
                ),
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="sample_size",
                label="样本数",
                status=(
                    "ready"
                    if stability_report.sample_count >= self._one_to_two_settings.minimum_sample_for_stability
                    else "warning"
                    if stability_report.sample_count > 0
                    else "blocked"
                ),
                detail=(
                    f"闭环样本 {stability_report.sample_count} 笔，"
                    f"最低观察门槛 {self._one_to_two_settings.minimum_sample_for_stability} 笔。"
                ),
                next_action=(
                    "样本达到初评门槛，可进入策略边界复核。"
                    if stability_report.sample_count >= self._one_to_two_settings.minimum_sample_for_stability
                    else "样本不足，只能观察，不能宣称稳定盈利。"
                ),
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="survivorship_bias",
                label="幸存者偏差",
                status="warning",
                detail="当前 AkShare 回测未完全保证历史退市股票和成分股 Point-in-Time 覆盖。",
                next_action="后续接入专业 PIT 数据源或维护本地退市股票历史池。",
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="execution_granularity",
                label="执行颗粒度",
                status="warning",
                detail="当前按日线/涨停池事件近似执行，无法模拟排队、炸板瞬时成交和 Tick 级滑点。",
                next_action="模拟盘 Beta 先验证流程，正式研究再引入分钟线或 Tick 数据。",
            )
        )
        checks.append(
            BacktestDataQualityCheck(
                check_id="rule_version",
                label="规则版本",
                status="ready",
                detail=(
                    "规则已固化为主线首板龙头候选、T+1、32% 第一止盈、4.25%/结构止损、"
                    "8.25% 强势阈值后 0.10% 回撤保护、主线持续性衰减退出。"
                ),
                next_action="回测结果只对当前规则版本负责，改规则后必须重跑。",
            )
        )
        return tuple(checks)

    def _stability_from_account(self, account) -> OneToTwoStabilityReport:
        sample_count = len(account.closed_trades)
        sell_count = sum(1 for record in account.closed_trades if record.success)
        warning_count = sum(record.warning_count for record in account.closed_trades)
        total_return = sum(record.realized_pnl_pct for record in account.closed_trades)
        position_label_distribution = self._count_by(
            record.position_label for record in account.closed_trades
        )
        exit_reason_distribution = self._count_by(
            record.exit_reason for record in account.closed_trades
        )
        recent_samples = tuple(
            OneToTwoRecentSample(
                trade_id=record.trade_id,
                symbol=record.symbol,
                name=record.name,
                opened_at=record.opened_at,
                closed_at=record.closed_at,
                realized_pnl=record.realized_pnl,
                realized_pnl_pct=record.realized_pnl_pct,
                holding_trade_days=record.holding_trade_days,
                exit_reason=record.exit_reason,
                position_label=record.position_label,
                success=record.success,
                warning_count=record.warning_count,
            )
            for record in account.closed_trades[:5]
        )
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
        sample_stage = self._stability_sample_stage(sample_count)
        next_milestone = self._stability_next_milestone(sample_count)
        strategy_boundary_suggestion = self._strategy_boundary_suggestion(
            sample_count=sample_count,
            success_rate=round(sell_count / sample_count, 4) if sample_count else 0.0,
            average_return_pct=round(total_return / sample_count, 4)
            if sample_count
            else 0.0,
            low_breakout_success_rate=(
                round(low_breakout_success / len(low_breakout_records), 4)
                if low_breakout_records
                else 0.0
            ),
            stop_warning_rate=(
                round(warning_count / sample_count, 4) if sample_count else 0.0
            ),
        )
        return OneToTwoStabilityReport(
            report_id="one-to-two-stability",
            sample_count=sample_count,
            sample_stage=sample_stage,
            next_milestone=next_milestone,
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
            position_label_distribution=position_label_distribution,
            exit_reason_distribution=exit_reason_distribution,
            recent_samples=recent_samples,
            status=status,
            summary=(
                "样本处于观察期，暂不自动给出策略边界结论。"
                if status == "observation"
                else "样本达到复查门槛，可以进入策略边界评估。"
            ),
            strategy_boundary_suggestion=strategy_boundary_suggestion,
            next_action=(
                f"继续积累至 {next_milestone} 笔主线首板样本。"
                if next_milestone
                else "进入 100 笔以上复盘，固定可执行边界并继续滚动验证。"
            ),
        )

    def _count_by(self, values) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            key = str(value or "未标记")
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def _stability_sample_stage(self, sample_count: int) -> str:
        if sample_count < self._one_to_two_settings.minimum_sample_for_stability:
            return "观察期"
        if sample_count < 50:
            return "30 笔初评"
        if sample_count < 100:
            return "50 笔复评"
        return "100 笔定边界"

    def _stability_next_milestone(self, sample_count: int) -> int:
        for milestone in (30, 50, 100):
            if sample_count < milestone:
                return milestone
        return 0

    def _strategy_boundary_suggestion(
        self,
        sample_count: int,
        success_rate: float,
        average_return_pct: float,
        low_breakout_success_rate: float,
        stop_warning_rate: float,
    ) -> str:
        if sample_count < self._one_to_two_settings.minimum_sample_for_stability:
            return "样本少于 30 笔，只记录现象，不自动收窄或放宽策略边界。"
        if success_rate >= 0.55 and average_return_pct > 0 and low_breakout_success_rate >= 0.55:
            return "优先保留低位平台突破样本，继续排除高位接力和左侧压力过近样本。"
        if stop_warning_rate >= 0.4 or average_return_pct < 0:
            return "先收紧入池条件：降低高位样本权重，提高压力位距离和承接确认要求。"
        return "维持现有边界，继续积累到下一阶段后再决定是否调整仓位或评分阈值。"

    def _doctor_strategy_check(self) -> OneToTwoDoctorCheck:
        settings = self._one_to_two_settings
        valid = (
            settings.min_score > 0
            and settings.initial_cash > 0
            and 0 < settings.max_position_pct <= 1
            and settings.max_daily_trades >= 1
            and 0 <= settings.min_confirm_open_pct <= settings.max_confirm_open_pct < 0.095
        )
        return OneToTwoDoctorCheck(
            check_id="strategy_config",
            label="主线首板策略配置",
            status="ready" if valid else "blocked",
            detail=(
                f"min_score={settings.min_score:g}, "
                f"initial_cash={settings.initial_cash:.2f}, "
                f"max_position_pct={settings.max_position_pct:.0%}, "
                f"max_daily_trades={settings.max_daily_trades}, "
                f"confirm_open={self._format_pct(settings.min_confirm_open_pct)}-"
                f"{self._format_pct(settings.max_confirm_open_pct)}"
            ),
            next_action=(
                "配置有效，继续保持单一主线首板主线。"
                if valid
                else "修复 one_to_two_strategy JSON 后再运行策略。"
            ),
        )

    def _format_pct(self, value: float) -> str:
        text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"

    def _doctor_trading_day_check(
        self,
        trade_context,
        beta: bool = False,
    ) -> OneToTwoDoctorCheck:
        if trade_context.is_trading_day:
            return OneToTwoDoctorCheck(
                check_id="trading_day",
                label="交易日",
                status="ready",
                detail=f"{trade_context.requested_date} 是 A 股交易日。",
                next_action="可以按当日主线首板主线运行。",
            )
        return OneToTwoDoctorCheck(
            check_id="trading_day",
            label="交易日",
            status="blocked" if beta else "warning",
            detail=(
                f"{trade_context.requested_date} 非交易日，"
                f"当前只解析到上一交易日 {trade_context.trade_date}。"
            ),
            next_action=(
                "模拟盘 Beta 只在真实交易日启动；如需演示请指定交易日并使用 --sample-data。"
                if beta
                else "非交易日不会触发 schedule 实际交易任务，可指定交易日做本地演示。"
            ),
        )

    def _doctor_market_data_check(self, trade_date: str) -> OneToTwoDoctorCheck:
        if importlib.util.find_spec("akshare") is None and isinstance(
            self._market_data_provider,
            AkshareMarketDataProvider,
        ):
            return OneToTwoDoctorCheck(
                check_id="market_data",
                label="行情源",
                status="blocked",
                detail="AkShare 未安装，真实行情入口不可用。",
                next_action="运行 python -m pip install -r requirements.txt 后重新执行 doctor。",
            )
        try:
            rows = self._market_data_provider.load_one_to_two_rows(trade_date)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="market_data",
                label="行情源",
                status="blocked",
                detail=f"无法读取 {trade_date} 主线首板行情：{exc}",
                next_action="检查 AkShare 网络、接口可用性，或改用 --sample-data 预览。",
            )
        return OneToTwoDoctorCheck(
            check_id="market_data",
            label="行情源",
            status="ready" if rows else "warning",
            detail=f"{trade_date} 已读取 {len(rows)} 条候选原始行。",
            next_action=(
                "行情源可用。"
                if rows
                else "数据可读但没有候选，盘前继续观察或换交易日验证。"
            ),
        )

    def _doctor_paper_store_check(self) -> OneToTwoDoctorCheck:
        try:
            account = self._paper_store.load()
            self._ensure_parent_directory(self._paper_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="paper_store",
                label="模拟盘账本",
                status="blocked",
                detail=f"账本读取失败：{exc}",
                next_action="修复 .firemoney/paper_trades.json 权限或内容后再运行。",
            )
        return OneToTwoDoctorCheck(
            check_id="paper_store",
            label="模拟盘账本",
            status="ready",
            detail=(
                f"equity={account.equity:.2f}, "
                f"positions={len(account.positions)}, "
                f"closed_samples={len(account.closed_trades)}"
            ),
            next_action="账本可用，继续用事件驱动模拟盘记录样本。",
        )

    def _doctor_notification_store_check(self) -> OneToTwoDoctorCheck:
        try:
            records = self._notification_store.load()
            self._ensure_parent_directory(self._notification_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="notification_store",
                label="通知归档",
                status="blocked",
                detail=f"无法读取或准备 {self._notification_store.path}：{exc}",
                next_action="修复 .firemoney/notifications.json 权限或路径后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="notification_store",
            label="通知归档",
            status="ready",
            detail=f"通知归档可读写，recent_records={len(records)}。",
            next_action="值守后用 notifications 查看飞书触达记录。",
        )

    def _doctor_scheduler_state_store_check(self) -> OneToTwoDoctorCheck:
        try:
            completed = self._scheduler_state_store.load()
            self._ensure_parent_directory(self._scheduler_state_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="scheduler_state",
                label="调度状态",
                status="blocked",
                detail=f"无法读取或准备 {self._scheduler_state_store.path}：{exc}",
                next_action="修复 .firemoney/scheduler_state.json 权限或路径后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="scheduler_state",
            label="调度状态",
            status="ready",
            detail=f"调度状态可读写，completed_tasks={len(completed)}。",
            next_action="状态可用，schedule --loop 不会重复触发同日任务。",
        )

    def _doctor_feishu_check(
        self,
        trade_date: str,
        beta: bool = False,
    ) -> OneToTwoDoctorCheck:
        enabled = os.environ.get("FEISHU_ENABLED", "").lower() == "true"
        webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
        webhook_configured = bool(webhook)
        app_configured = self._has_feishu_app_config()
        app_partial = self._has_feishu_app_partial_config()
        if enabled and not webhook_configured and not app_configured:
            status = "blocked" if beta else "warning"
            detail = "FEISHU_ENABLED=true，但飞书 webhook 或应用机器人配置不完整。"
            next_action = (
                "模拟盘 Beta 必须配置 FEISHU_WEBHOOK_URL，或者 FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_RECEIVE_ID。"
                if beta
                else "配置飞书 webhook 或应用机器人，或运行时使用 --no-notify。"
            )
            if app_partial:
                detail = "飞书应用机器人环境变量已部分配置，但缺少必需项。"
        elif enabled and webhook_configured:
            valid_webhook = self._is_feishu_webhook(webhook)
            if not valid_webhook:
                status = "blocked" if beta else "warning"
                detail = "FEISHU_WEBHOOK_URL 不是有效的飞书群机器人 webhook。"
                next_action = "使用 https://open.feishu.cn/open-apis/bot/v2/hook/... 格式的群机器人地址。"
            elif beta and not self._has_sent_feishu_test(trade_date):
                status = "blocked"
                detail = "飞书通知已配置，但当前交易日还没有 feishu-test sent 记录。"
                next_action = "先运行 feishu-test 并确认返回 sent，再重新执行 doctor --beta。"
            else:
                status = "ready"
                detail = "飞书通知已启用，webhook 已配置。"
                next_action = (
                    "飞书联通已验证，可以进入 Beta 值守。"
                    if beta
                    else "盘前先用 feishu-test 验证消息能到群。"
                )
        elif enabled and app_configured:
            if beta and not self._has_sent_feishu_test(trade_date):
                status = "blocked"
                detail = "飞书应用机器人已配置，但当前交易日还没有 feishu-test sent 记录。"
                next_action = "先运行 feishu-test 并确认返回 sent，再重新执行 doctor --beta。"
            else:
                status = "ready"
                detail = "飞书应用机器人已配置，receive_id 已配置。"
                next_action = (
                    "飞书联通已验证，可以进入 Beta 值守。"
                    if beta
                    else "盘前先用 feishu-test 验证消息能到群。"
                )
        elif beta:
            status = "blocked"
            detail = "模拟盘 Beta 需要飞书值守，但 FEISHU_ENABLED 未开启。"
            next_action = "设置 FEISHU_ENABLED=true 和飞书 webhook 或应用机器人后重新执行 doctor --beta。"
        else:
            status = "warning"
            detail = "飞书通知未启用，策略仍会生成 prepared 通知结果。"
            next_action = "模拟盘 Beta 必须设置 FEISHU_ENABLED=true 和飞书通知凭据后再值守。"
        return OneToTwoDoctorCheck(
            check_id="feishu",
            label="飞书通知",
            status=status,
            detail=detail,
            next_action=next_action,
        )

    def _has_sent_feishu_test(self, trade_date: str) -> bool:
        return any(
            record.workflow == "feishu:test"
            and record.trade_date == trade_date
            and record.status == NotificationStatus.SENT
            for record in self._notification_store.load()
        )

    def _is_feishu_webhook(self, value: str) -> bool:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme == "https"
            and parsed.netloc in {"open.feishu.cn", "open.larksuite.com"}
            and parsed.path.startswith("/open-apis/bot/v2/hook/")
            and len(parsed.path.rsplit("/", 1)[-1]) > 0
        )

    def _has_feishu_delivery_config(self) -> bool:
        return bool(os.environ.get("FEISHU_WEBHOOK_URL", "").strip()) or self._has_feishu_app_config()

    def _has_feishu_app_config(self) -> bool:
        return bool(
            os.environ.get("FEISHU_APP_ID", "").strip()
            and os.environ.get("FEISHU_APP_SECRET", "").strip()
            and (
                os.environ.get("FEISHU_RECEIVE_ID", "").strip()
                or os.environ.get("FEISHU_OPEN_CHAT_ID", "").strip()
            )
        )

    def _has_feishu_app_partial_config(self) -> bool:
        return any(
            os.environ.get(key, "").strip()
            for key in (
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "FEISHU_RECEIVE_ID",
                "FEISHU_OPEN_CHAT_ID",
            )
        )

    def _doctor_scheduler_check(self) -> OneToTwoDoctorCheck:
        return OneToTwoDoctorCheck(
            check_id="scheduler",
            label="本地调度",
            status="ready",
            detail=(
                f"早盘 {self._one_to_two_settings.morning_time}, "
                "盘中 scan/auction/open/risk, "
                f"尾盘 {self._one_to_two_settings.end_of_day_time}"
            ),
            next_action="可以手动运行 schedule，也可以用 --loop 常驻观察。",
        )

    def _doctor_scheduler_run_store_check(self) -> OneToTwoDoctorCheck:
        try:
            records = self._scheduler_run_store.load(limit=1)
            self._ensure_parent_directory(self._scheduler_run_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="scheduler_runs",
                label="调度审计",
                status="blocked",
                detail=f"无法读取或准备 {self._scheduler_run_store.path}：{exc}",
                next_action="修复 .firemoney 目录权限后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="scheduler_runs",
            label="调度审计",
            status="ready",
            detail=f"审计记录可读写，recent_records={len(records)}。",
            next_action="值守后用 scheduler-runs 查看每次调度覆盖情况。",
        )

    def _ensure_parent_directory(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.parent.is_dir():
            raise OSError(f"{path.parent} is not a directory")

    def _candidate_for_position(self, position, trade_date: str):
        from shared.contracts import OneToTwoCandidate, OneToTwoPositionProfile

        return OneToTwoCandidate(
            symbol=position.symbol,
            name=position.name,
            trade_date=trade_date,
            score=position.opened_score,
            status="ready",
            latest_price=position.latest_price,
            limit_up_price=position.latest_price,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            position_limit_pct=self._one_to_two_settings.max_position_pct,
            first_board_score=0,
            auction_score=0,
            position_score=0,
            theme_score=0,
            liquidity_score=0,
            position_profile=OneToTwoPositionProfile(
                label=position.position_label,
                low_position_score=0,
                breakout_score=0,
                pressure_score=0,
                moving_average_score=0,
                volume_score=0,
                summary=position.position_label,
                risk_notes=(),
            ),
            blockers=(),
            warnings=(),
            rationale="历史回放强制归档样本。",
            next_action="回放结束。",
            exit_plan=position.exit_plan,
            mainline_continuity=position.mainline_continuity,
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

    def _record_notification(
        self,
        workflow: str,
        trade_date: str,
        result: FeishuNotificationResult,
    ) -> None:
        self._notification_store.append(
            workflow=workflow,
            trade_date=trade_date,
            result=result,
        )

    def _morning_notification_message(
        self,
        report_date: str,
        market_temperature: int,
        data_unavailable: bool,
        candidates: tuple[OneToTwoCandidate, ...],
        account: PaperAccount,
    ) -> str:
        ready = tuple(item for item in candidates if item.status == "ready")
        blocked_count = sum(1 for item in candidates if item.status == "blocked")
        lines = [
            f"交易日：{report_date}",
            f"市场温度：{market_temperature}",
            f"主线首板候选：{len(candidates)}，可执行候选：{len(ready)}，硬拦截：{blocked_count}",
            f"模拟盘：权益 {account.equity:.2f}，当日已交易 {account.daily_trade_count}/{account.max_daily_trades}",
        ]
        if data_unavailable:
            lines.append("行情数据不可用：今日禁止生成模拟买入。")
            return "\n".join(lines)
        if ready:
            lines.append("主线首板候选入池：")
            for candidate in ready[:3]:
                lines.append(
                    f"- {candidate.name}({candidate.symbol}) 分数 {candidate.score}，"
                    f"{candidate.leader_label or candidate.position_profile.label}，"
                    f"封板 {candidate.sealing_score}/20，主线 {candidate.mainline_score}/20，"
                    f"龙头 {candidate.leader_score}/20，买入参考 {candidate.entry_price}，"
                    f"止损 {candidate.stop_loss}，仓位上限 {candidate.position_limit_pct:.0%}"
                )
                if candidate.exit_plan:
                    lines.append(f"  卖点纪律：{candidate.exit_plan.summary}")
                if candidate.mainline_continuity:
                    lines.append(
                        f"  主线持续性：{candidate.mainline_continuity.theme} "
                        f"{candidate.mainline_continuity.score}/100，"
                        f"{candidate.mainline_continuity.next_action}"
                    )
        else:
            lines.append("今日没有达到模拟买入条件的候选。")
        blockers = tuple(item for item in candidates if item.blockers)
        if blockers:
            lines.append("主要拦截：")
            for candidate in blockers[:2]:
                lines.append(f"- {candidate.name}({candidate.symbol})：{candidate.blockers[0]}")
        lines.append("纪律：只做主板 10cm 主线首板龙头候选；一进二只是确认点，当天跌破止损只预警，T+1 再处理。")
        return "\n".join(lines)

    def _watch_notification_message(
        self,
        phase: str,
        report: OneToTwoMorningReport,
        ready: tuple[OneToTwoCandidate, ...],
        account: PaperAccount,
        latest_event: str,
    ) -> str:
        lines = [
            f"交易日：{report.trade_date}",
            f"阶段：{phase}",
            f"最新事件：{latest_event}",
        ]
        latest_closed_sample = account.closed_trades[0] if account.closed_trades else None
        latest_event_type = account.events[0].event_type if account.events else None
        if (
            phase == "risk"
            and latest_closed_sample
            and latest_event_type in {OneToTwoEventType.T1_SELL, OneToTwoEventType.DISCIPLINE_EXIT}
        ):
            lines.extend(
                [
                    f"完成样本：{latest_closed_sample.name}({latest_closed_sample.symbol})",
                    f"退出原因：{latest_closed_sample.exit_reason}；持仓 {latest_closed_sample.holding_trade_days} 日",
                    f"实现盈亏：{latest_closed_sample.realized_pnl:.2f} ({latest_closed_sample.realized_pnl_pct:.2%})",
                    f"位置：{latest_closed_sample.position_label}；止损预警 {latest_closed_sample.warning_count} 次",
                ]
            )
        elif (
            phase == "risk"
            and latest_event_type == OneToTwoEventType.STOP_WARNING
            and account.positions
        ):
            position = account.positions[0]
            lines.extend(
                [
                    f"止损预警：{position.name}({position.symbol})",
                    f"当前价 {position.latest_price}，止损价 {position.stop_loss}",
                    f"浮动盈亏：{position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})",
                    f"位置：{position.position_label}",
                    "T+1 处理：当日只预警不卖出，下一交易日仍低于止损再模拟卖出。",
                ]
            )
            if position.mainline_continuity:
                lines.append(
                    f"主线持续性：{position.mainline_continuity.theme} "
                    f"{position.mainline_continuity.score}/100，"
                    f"消息 {position.mainline_continuity.news_count} 条，"
                    f"{position.mainline_continuity.next_action}"
                )
        elif account.positions:
            position = account.positions[0]
            sell_state = "可按纪律卖出" if position.can_sell_today else "T+1 未到，只预警不卖出"
            lines.extend(
                [
                    f"持仓：{position.name}({position.symbol}) {position.quantity} 股",
                    f"成本 {position.entry_price}，现价 {position.latest_price}，止损 {position.stop_loss}",
                    f"浮动盈亏：{position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.2%})",
                    f"纪律状态：{sell_state}",
                ]
            )
            if position.exit_plan:
                lines.append(f"卖点计划：{position.exit_plan.summary}")
            if position.mainline_continuity:
                lines.append(
                    f"主线持续性：{position.mainline_continuity.theme} "
                    f"{position.mainline_continuity.score}/100，"
                    f"状态 {position.mainline_continuity.status}，"
                    f"消息 {position.mainline_continuity.news_count} 条"
                )
                if position.mainline_continuity.latest_news:
                    lines.append(
                        f"最新消息：{position.mainline_continuity.latest_news[0].title}"
                    )
        elif ready:
            candidate = ready[0]
            lines.extend(
                [
                    f"观察候选：{candidate.name}({candidate.symbol}) 分数 {candidate.score}",
                    f"标签：{candidate.leader_label or candidate.position_profile.label}；封板 {candidate.sealing_score}/20；买入参考 {candidate.entry_price}；止损 {candidate.stop_loss}",
                    f"仓位上限：{candidate.position_limit_pct:.0%}；状态：{candidate.status}",
                ]
            )
            if candidate.exit_plan:
                lines.append(f"卖点计划：{candidate.exit_plan.summary}")
            if candidate.mainline_continuity:
                lines.append(
                    f"主线持续性：{candidate.mainline_continuity.theme} "
                    f"{candidate.mainline_continuity.score}/100，"
                    f"{candidate.mainline_continuity.next_action}"
                )
        else:
            lines.append("当前无可执行候选，不生成模拟买入。")
        lines.append("提醒：模拟盘不是实盘，不连接真实账户，不自动下单。")
        return "\n".join(lines)

    def _end_of_day_notification_message(
        self,
        report_date: str,
        account: PaperAccount,
        warning_count: int,
        t1_sell_count: int,
        realized_pnl: float,
        stability_report: OneToTwoStabilityReport,
    ) -> str:
        next_milestone = (
            f"{stability_report.next_milestone} 笔"
            if stability_report.next_milestone
            else "滚动复盘"
        )
        lines = [
            f"交易日：{report_date}",
            f"权益：{account.equity:.2f}，现金：{account.cash:.2f}，观察盈亏：{realized_pnl:.2f}",
            f"事件数：{len(account.events)}，止损预警：{warning_count}，当日 T+1 卖出：{t1_sell_count}",
            f"已归档样本：{len(account.closed_trades)}",
            f"稳定性阶段：{stability_report.sample_stage}，下一门槛：{next_milestone}",
            f"边界建议：{stability_report.strategy_boundary_suggestion}",
        ]
        if stability_report.recent_samples:
            sample = stability_report.recent_samples[0]
            lines.append(
                f"最新样本：{sample.name}({sample.symbol})，收益 {sample.realized_pnl_pct:.2%}，"
                f"退出 {sample.exit_reason}，位置 {sample.position_label}"
            )
        else:
            lines.append("最新样本：暂无完成样本，继续按主线首板闭环观察。")
        if account.positions:
            position = account.positions[0]
            lines.append(
                f"隔夜观察：{position.name}({position.symbol})，止损 {position.stop_loss}，"
                f"{'次日可卖' if position.can_sell_today else '仍受 T+1 约束'}"
            )
            if position.exit_plan:
                lines.append(f"隔夜卖点：{position.exit_plan.summary}")
            if position.mainline_continuity:
                lines.append(
                    f"主线持续性：{position.mainline_continuity.theme} "
                    f"{position.mainline_continuity.score}/100，"
                    f"{position.mainline_continuity.next_action}"
                )
        else:
            lines.append("当前无持仓，等待下一交易日重新扫描主线首板候选池。")
        lines.append("复盘纪律：尾盘只归档和评估边界，不改变当日交易。")
        return "\n".join(lines)

    def _default_trade_date(self) -> str:
        return date.today().isoformat()
