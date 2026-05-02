"""Application workflow for the FireMoney one-to-two product line."""

from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from urllib.parse import urlparse

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
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.scheduler_run_store import SchedulerRunStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import (
    AkshareTradingCalendar,
    TradingCalendar,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    NotificationRecord,
    OneToTwoBetaReadinessReport,
    OneToTwoCandidate,
    OneToTwoDoctorCheck,
    OneToTwoDoctorReport,
    OneToTwoEventType,
    OneToTwoEndOfDayReview,
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
            "一进二早盘：行情数据不可用，禁止生成模拟买入。"
            if data_unavailable
            else f"一进二早盘：{len(candidates)} 个昨日首板样本，{ready_count} 个进入模拟盘观察。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二早盘",
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
                account = self._paper_store.update_risk(matched)
                if account.positions and phase == "risk":
                    account = self._exit_if_discipline_requires(matched)
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
            next_action="继续盯住止损位和 T+1 纪律。",
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
            message="持仓超过 2 个交易日未继续走强，按一进二纪律退出。",
            holding_trade_days=holding_trade_days,
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
            f"一进二尾盘：完成样本 {len(closed_trades)} 笔，"
            f"成功 {success_count} 笔，已实现盈亏 {realized_pnl:.2f}。"
        )
        notification = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二尾盘",
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
            next_action="收盘后归档样本，明早继续扫描昨日首板池。",
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
                "后续：收到后再运行 doctor --beta 和 schedule --beta。",
            )
        )
        result = self._notify_or_prepare(
            notify=notify,
            title="FireMoney 一进二飞书测试",
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
                title="FireMoney 一进二飞书测试",
                message="Beta 预检未发送飞书测试，不触发模拟买入或卖出。",
                webhook_configured=bool(os.environ.get("FEISHU_WEBHOOK_URL", "")),
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
            "模拟盘 Beta 预检通过，可以启动一进二值守。"
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
                "运行 schedule --beta --loop --interval-seconds 60。"
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
            "一进二运行体检未通过，先修复阻断项再启动模拟盘。"
            if status == "blocked"
            else (
                "一进二运行体检有可选项未就绪，核心模拟盘可以继续。"
                if status == "warning"
                else "一进二运行体检通过，可以按早盘、盘中、尾盘主线运行。"
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
                else "继续按 morning -> watch -> eod -> stability 验证一进二。"
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

        end_context = self._trading_calendar.resolve(end_date or self._default_trade_date())
        end_trade_date = date.fromisoformat(end_context.trade_date)
        start_trade_date = (
            date.fromisoformat(self._trading_calendar.resolve(start_date).trade_date)
            if start_date
            else end_trade_date - timedelta(days=max_trade_days * 2)
        )
        dates: list[str] = []
        cursor = start_trade_date
        while cursor <= end_trade_date and len(dates) < max_trade_days:
            context = self._trading_calendar.resolve(cursor.isoformat())
            if context.trade_date == cursor.isoformat():
                dates.append(context.trade_date)
            cursor += timedelta(days=1)

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
                            message="历史回放纪律退出，完成一笔一进二样本。",
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
                f"继续积累至 {next_milestone} 笔一进二样本。"
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
        )
        return OneToTwoDoctorCheck(
            check_id="strategy_config",
            label="一进二策略配置",
            status="ready" if valid else "blocked",
            detail=(
                f"min_score={settings.min_score:g}, "
                f"initial_cash={settings.initial_cash:.2f}, "
                f"max_position_pct={settings.max_position_pct:.0%}, "
                f"max_daily_trades={settings.max_daily_trades}"
            ),
            next_action=(
                "配置有效，继续保持单一一进二主线。"
                if valid
                else "修复 one_to_two_strategy JSON 后再运行策略。"
            ),
        )

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
                next_action="可以按当日一进二主线运行。",
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
                detail=f"无法读取 {trade_date} 一进二行情：{exc}",
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
        webhook_configured = bool(os.environ.get("FEISHU_WEBHOOK_URL", ""))
        if enabled and not webhook_configured:
            status = "blocked" if beta else "warning"
            detail = "FEISHU_ENABLED=true，但 FEISHU_WEBHOOK_URL 未配置。"
            next_action = (
                "模拟盘 Beta 必须配置 webhook；否则无法值守盘中事件。"
                if beta
                else "配置 webhook，或运行时使用 --no-notify。"
            )
        elif enabled:
            valid_webhook = self._is_feishu_webhook(
                os.environ.get("FEISHU_WEBHOOK_URL", "")
            )
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
        elif beta:
            status = "blocked"
            detail = "模拟盘 Beta 需要飞书值守，但 FEISHU_ENABLED 未开启。"
            next_action = "设置 FEISHU_ENABLED=true 和 FEISHU_WEBHOOK_URL 后重新执行 doctor --beta。"
        else:
            status = "warning"
            detail = "飞书通知未启用，策略仍会生成 prepared 通知结果。"
            next_action = "模拟盘 Beta 必须设置 FEISHU_ENABLED=true 和 FEISHU_WEBHOOK_URL 后再值守。"
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
            f"昨日首板样本：{len(candidates)}，可执行候选：{len(ready)}，硬拦截：{blocked_count}",
            f"模拟盘：权益 {account.equity:.2f}，当日已交易 {account.daily_trade_count}/{account.max_daily_trades}",
        ]
        if data_unavailable:
            lines.append("行情数据不可用：今日禁止生成模拟买入。")
            return "\n".join(lines)
        if ready:
            lines.append("候选入池：")
            for candidate in ready[:3]:
                lines.append(
                    f"- {candidate.name}({candidate.symbol}) 分数 {candidate.score}，"
                    f"{candidate.position_profile.label}，买入参考 {candidate.entry_price}，"
                    f"止损 {candidate.stop_loss}，仓位上限 {candidate.position_limit_pct:.0%}"
                )
        else:
            lines.append("今日没有达到模拟买入条件的候选。")
        blockers = tuple(item for item in candidates if item.blockers)
        if blockers:
            lines.append("主要拦截：")
            for candidate in blockers[:2]:
                lines.append(f"- {candidate.name}({candidate.symbol})：{candidate.blockers[0]}")
        lines.append("纪律：只做主板 10cm 一进二；当天跌破止损只预警，T+1 再处理。")
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
        elif ready:
            candidate = ready[0]
            lines.extend(
                [
                    f"观察候选：{candidate.name}({candidate.symbol}) 分数 {candidate.score}",
                    f"位置：{candidate.position_profile.label}；买入参考 {candidate.entry_price}；止损 {candidate.stop_loss}",
                    f"仓位上限：{candidate.position_limit_pct:.0%}；状态：{candidate.status}",
                ]
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
            lines.append("最新样本：暂无完成样本，继续按一进二闭环观察。")
        if account.positions:
            position = account.positions[0]
            lines.append(
                f"隔夜观察：{position.name}({position.symbol})，止损 {position.stop_loss}，"
                f"{'次日可卖' if position.can_sell_today else '仍受 T+1 约束'}"
            )
        else:
            lines.append("当前无持仓，等待下一交易日重新扫描昨日首板池。")
        lines.append("复盘纪律：尾盘只归档和评估边界，不改变当日交易。")
        return "\n".join(lines)

    def _default_trade_date(self) -> str:
        return date.today().isoformat()
