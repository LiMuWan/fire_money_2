"""Application workflow for the FireMoney one-to-two product line."""

from __future__ import annotations

from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

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
from server.firemoney_server.infrastructure.trading_calendar import (
    AkshareTradingCalendar,
    TradingCalendar,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    NotificationRecord,
    OneToTwoCandidate,
    OneToTwoEventType,
    OneToTwoEndOfDayReview,
    OneToTwoMorningReport,
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
            message=self._end_of_day_notification_message(
                report_date=report_date,
                account=account,
                warning_count=warning_count,
                sell_count=sell_count,
                realized_pnl=realized_pnl,
            ),
        )
        self._record_notification("eod", report_date, notification)
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
        return self._stability_from_account(account)

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
        if account.positions:
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
        sell_count: int,
        realized_pnl: float,
    ) -> str:
        lines = [
            f"交易日：{report_date}",
            f"权益：{account.equity:.2f}，现金：{account.cash:.2f}，观察盈亏：{realized_pnl:.2f}",
            f"事件数：{len(account.events)}，止损预警：{warning_count}，T+1 卖出：{sell_count}",
            f"已归档样本：{len(account.closed_trades)}",
        ]
        if account.positions:
            position = account.positions[0]
            lines.append(
                f"隔夜观察：{position.name}({position.symbol})，止损 {position.stop_loss}，"
                f"{'次日可卖' if position.can_sell_today else '仍受 T+1 约束'}"
            )
        else:
            lines.append("当前无持仓，等待下一交易日重新扫描昨日首板池。")
        lines.append("复盘纪律：样本少于 30 笔只观察，不自动调整策略边界。")
        return "\n".join(lines)

    def _default_trade_date(self) -> str:
        return date.today().isoformat()
