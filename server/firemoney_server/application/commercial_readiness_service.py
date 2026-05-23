"""Commercial readiness gates for the FireMoney mainline product."""

from __future__ import annotations

from shared.contracts import (
    CommercialReadinessGate,
    CommercialReadinessReport,
    NotificationRecord,
    OneToTwoDoctorReport,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    PaperBacktestReport,
    PaperTradeDatabaseReport,
)

_MORNING_WORKFLOW = "morning"
_EOD_WORKFLOW = "eod"
_WATCH_WORKFLOWS = frozenset({"watch", "watch:open", "watch:risk"})
_KEY_NOTIFICATION_WORKFLOWS = frozenset(
    {_MORNING_WORKFLOW, _EOD_WORKFLOW, *_WATCH_WORKFLOWS}
)


class CommercialReadinessService:
    """Evaluates launch gates without depending on client rendering code."""

    def build_report(
        self,
        *,
        report: OneToTwoMorningReport,
        schedule_health_report: OneToTwoScheduleHealthReport | None,
        paper_database_report: PaperTradeDatabaseReport | None,
        paper_backtest_report: PaperBacktestReport | None,
        doctor_report: OneToTwoDoctorReport | None,
        notification_records: tuple[NotificationRecord, ...],
    ) -> CommercialReadinessReport:
        gates = (
            self._compliance_gate(),
            self._runtime_gate(schedule_health_report, doctor_report),
            self._operations_30d_gate(notification_records, paper_database_report),
            self._notification_gate(notification_records),
            self._paper_ledger_gate(paper_database_report),
            self._backtest_gate(paper_backtest_report),
            self._product_gate(report),
        )
        status = self._overall_status(gates)
        score = sum(self._gate_score(gate.tone) for gate in gates) / max(len(gates), 1)
        headline = {
            "ready": "可进入小范围试用，但仍需合规确认",
            "beta_only": "只适合内部 Beta，不建议收费上线",
            "blocked": "暂不能对外商用，先补硬门槛",
        }[status]
        stage = {
            "ready": "小范围试用候选",
            "beta_only": "内部 Beta",
            "blocked": "自用验证期",
        }[status]
        next_actions = (
            "未完成持牌/合规边界前，只能做内部自用研究或非收费内部试运行，不可包装成保证盈利荐股。",
            "连续跑满 30 个交易日，沉淀早评、买入、卖出、晚评、失败重试和真实模拟盘闭环。",
            "真实闭环样本、通知送达率、服务稳定性、回撤控制和风险揭示同时达标后，再考虑小范围试用。",
        )
        return CommercialReadinessReport(
            report_id=f"commercial-readiness-{report.trade_context.trade_date}",
            trade_date=report.trade_context.trade_date,
            status=status,
            headline=headline,
            stage=stage,
            score=score,
            gates=gates,
            next_actions=next_actions,
            summary="交易产品上线不是多几个界面，而是合规、稳定、真实收益和回撤证据都能过关。",
        )

    @staticmethod
    def _compliance_gate() -> CommercialReadinessGate:
        return CommercialReadinessGate(
            gate_id="compliance",
            title="合规边界",
            status="硬阻断",
            tone="danger",
            score=0.0,
            detail="未接入持牌投顾、用户协议和风险揭示前，不能对外收费给具体买卖点。",
        )

    @staticmethod
    def _runtime_gate(
        schedule_health_report: OneToTwoScheduleHealthReport | None,
        doctor_report: OneToTwoDoctorReport | None,
    ) -> CommercialReadinessGate:
        if schedule_health_report is None and doctor_report is None:
            return CommercialReadinessGate(
                gate_id="runtime",
                title="服务稳定",
                status="缺少检查",
                tone="danger",
                score=0.0,
                detail="没有运行健康报告，无法证明服务能持续常驻。",
            )
        raw_status = " ".join(
            str(item or "")
            for item in (
                getattr(schedule_health_report, "status", ""),
                getattr(doctor_report, "status", ""),
            )
        ).lower()
        if any(token in raw_status for token in ("blocked", "failed", "danger", "失败", "阻断")):
            return CommercialReadinessGate(
                gate_id="runtime",
                title="服务稳定",
                status="当前阻断",
                tone="danger",
                score=18.0,
                detail="先修复调度、行情源、飞书和值守链路，再谈上线。",
            )
        return CommercialReadinessGate(
            gate_id="runtime",
            title="服务稳定",
            status="当前可用，待30日",
            tone="warning",
            score=45.0,
            detail="当前检查可用，但商用还需要连续 30 个交易日不断档记录。",
        )

    @staticmethod
    def _notification_gate(
        notification_records: tuple[NotificationRecord, ...],
    ) -> CommercialReadinessGate:
        records = tuple(
            record
            for record in notification_records
            if record.workflow in _KEY_NOTIFICATION_WORKFLOWS
        )
        total = len(records)
        sent = sum(1 for record in records if _status_value(record.status) == "sent")
        ratio = sent / total if total else 0.0
        morning_sent = _sent_count(records, _MORNING_WORKFLOW)
        eod_sent = _sent_count(records, _EOD_WORKFLOW)
        watch_sent = _sent_watch_count(records)
        metrics = {
            "早评送达": str(morning_sent),
            "晚评送达": str(eod_sent),
            "买卖通知": str(watch_sent),
            "送达率": f"{ratio:.0%}" if total else "0%",
        }
        if total == 0:
            return CommercialReadinessGate(
                gate_id="notification",
                title="飞书送达",
                status="无记录",
                tone="danger",
                score=0.0,
                detail="没有早评、买卖点、晚评 sent 记录，不能证明通知链路。",
                metrics=metrics,
            )
        if total >= 60 and ratio >= 0.98:
            return CommercialReadinessGate(
                gate_id="notification",
                title="飞书送达",
                status=f"{ratio:.0%} 达标",
                tone="success",
                score=100.0,
                detail=f"关键通知 {sent}/{total} 已发送，达到小范围试用门槛。",
                metrics=metrics,
            )
        if ratio >= 0.9:
            return CommercialReadinessGate(
                gate_id="notification",
                title="飞书送达",
                status=f"{ratio:.0%} 待样本",
                tone="warning",
                score=min(85.0, max(25.0, ratio * 80.0)),
                detail=f"关键通知 {sent}/{total} 已发送，还需要更多交易日样本。",
                metrics=metrics,
            )
        return CommercialReadinessGate(
            gate_id="notification",
            title="飞书送达",
            status=f"{ratio:.0%} 不稳",
            tone="danger",
            score=max(8.0, ratio * 55.0),
            detail=f"关键通知 {sent}/{total} 已发送，商用会放大漏发风险。",
            metrics=metrics,
        )

    @staticmethod
    def _operations_30d_gate(
        notification_records: tuple[NotificationRecord, ...],
        paper_database_report: PaperTradeDatabaseReport | None,
    ) -> CommercialReadinessGate:
        trade_dates = _key_trade_dates(notification_records)
        sent_dates = _sent_workflow_dates(notification_records)
        full_coverage_dates = tuple(
            trade_date
            for trade_date in trade_dates
            if {_MORNING_WORKFLOW, _EOD_WORKFLOW}.issubset(
                sent_dates.get(trade_date, set())
            )
        )
        latest_streak = _latest_consecutive_trading_day_streak(full_coverage_dates)
        morning_sent = _sent_count(notification_records, _MORNING_WORKFLOW)
        eod_sent = _sent_count(notification_records, _EOD_WORKFLOW)
        watch_sent = _sent_watch_count(notification_records)
        buy_sell_event_count = (
            paper_database_report.event_count
            if paper_database_report is not None
            else 0
        )
        closed_count = (
            paper_database_report.closed_trade_count
            if paper_database_report is not None
            else 0
        )
        metrics = {
            "覆盖交易日": f"{len(full_coverage_dates)}/30",
            "连续覆盖": f"{latest_streak}/30",
            "早评送达": str(morning_sent),
            "晚评送达": str(eod_sent),
            "买卖通知": str(watch_sent),
            "闭环交易": f"{closed_count}/30",
            "账本事件": str(buy_sell_event_count),
        }
        if latest_streak >= 30 and closed_count >= 30:
            return CommercialReadinessGate(
                gate_id="operations_30d",
                title="30日值守",
                status="通过",
                tone="success",
                score=100.0,
                detail="早评、晚评和真实模拟盘闭环已连续覆盖 30 个交易日。",
                metrics=metrics,
            )
        if len(full_coverage_dates) >= 10 or latest_streak >= 5 or closed_count >= 10:
            return CommercialReadinessGate(
                gate_id="operations_30d",
                title="30日值守",
                status="积累中",
                tone="warning",
                score=min(82.0, max(latest_streak, len(full_coverage_dates), closed_count) / 30.0 * 100.0),
                detail="已经有部分交易日覆盖，但还没证明连续 30 日稳定值守。",
                metrics=metrics,
            )
        return CommercialReadinessGate(
            gate_id="operations_30d",
            title="30日值守",
            status="样本不足",
            tone="danger",
            score=min(28.0, max(latest_streak, len(full_coverage_dates), closed_count) / 30.0 * 100.0),
            detail="上线前必须先证明早评、晚评、真实账本能连续稳定运行。",
            metrics=metrics,
        )

    @staticmethod
    def _paper_ledger_gate(
        report: PaperTradeDatabaseReport | None,
    ) -> CommercialReadinessGate:
        if report is None:
            return CommercialReadinessGate(
                gate_id="paper_ledger",
                title="真实模拟盘",
                status="无账本",
                tone="danger",
                score=0.0,
                detail="没有真实模拟盘账本，无法证明买卖闭环。",
            )
        count = report.closed_trade_count
        if count >= 30 and report.win_rate >= 0.55 and report.average_profit_drawdown_ratio >= 1.0:
            return CommercialReadinessGate(
                gate_id="paper_ledger",
                title="真实模拟盘",
                status="闭环达标",
                tone="success",
                score=100.0,
                detail=(
                    f"闭环 {count} 笔，胜率 {report.win_rate:.0%}，"
                    f"赚撤比 {report.average_profit_drawdown_ratio:.2f}R。"
                ),
            )
        if count >= 10:
            return CommercialReadinessGate(
                gate_id="paper_ledger",
                title="真实模拟盘",
                status="样本不足",
                tone="warning",
                score=min(80.0, count / 30.0 * 100.0),
                detail=f"闭环 {count} 笔，还没到 30 笔硬验收；先继续跑真实模拟盘。",
            )
        return CommercialReadinessGate(
            gate_id="paper_ledger",
            title="真实模拟盘",
            status="样本过少",
            tone="danger",
            score=min(35.0, count / 30.0 * 100.0),
            detail=f"闭环仅 {count} 笔，不能把样例收益当商业证据。",
        )

    @staticmethod
    def _backtest_gate(report: PaperBacktestReport | None) -> CommercialReadinessGate:
        if report is None:
            return CommercialReadinessGate(
                gate_id="backtest",
                title="回测证据",
                status="缺少回测",
                tone="danger",
                score=0.0,
                detail="没有 2020 起逐年回测，不具备策略证据底座。",
            )
        validation_return = report.validation.position_weighted_return_pct
        drawdown = report.overall.max_drawdown_pct
        if report.status == "ready" and validation_return > 0 and drawdown <= 0.12:
            return CommercialReadinessGate(
                gate_id="backtest",
                title="回测证据",
                status="通过",
                tone="success",
                score=100.0,
                detail=f"验证段 {validation_return:.2%}，最大回撤 {drawdown:.2%}。",
            )
        if validation_return > 0:
            return CommercialReadinessGate(
                gate_id="backtest",
                title="回测证据",
                status="需复核",
                tone="warning",
                score=68.0,
                detail=f"验证段为正，但最大回撤 {drawdown:.2%} 或状态仍需复核。",
            )
        return CommercialReadinessGate(
            gate_id="backtest",
            title="回测证据",
            status="未通过",
            tone="danger",
            score=28.0,
            detail=f"验证段 {validation_return:.2%}，不能支撑上线。",
        )

    @staticmethod
    def _product_gate(report: OneToTwoMorningReport) -> CommercialReadinessGate:
        if report.trade_context.is_trading_day:
            return CommercialReadinessGate(
                gate_id="product_scope",
                title="产品边界",
                status="主线清晰",
                tone="success",
                score=90.0,
                detail="默认路径已收缩为主线首板、主板票、模拟盘和证据中心。",
            )
        return CommercialReadinessGate(
            gate_id="product_scope",
            title="产品边界",
            status="休市静默",
            tone="success",
            score=86.0,
            detail="非交易日不乱发早晚评，产品边界保持清楚。",
        )

    @staticmethod
    def _overall_status(gates: tuple[CommercialReadinessGate, ...]) -> str:
        tones = tuple(gate.tone for gate in gates)
        if "danger" in tones:
            return "blocked"
        if "warning" in tones:
            return "beta_only"
        return "ready"

    @staticmethod
    def _gate_score(tone: str) -> float:
        return {
            "success": 1.0,
            "warning": 0.55,
            "danger": 0.0,
        }.get(tone, 0.0)


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _sent_count(records: tuple[NotificationRecord, ...], workflow: str) -> int:
    return sum(
        1
        for record in records
        if record.workflow == workflow and _status_value(record.status) == "sent"
    )


def _sent_watch_count(records: tuple[NotificationRecord, ...]) -> int:
    return sum(
        1
        for record in records
        if record.workflow in _WATCH_WORKFLOWS and _status_value(record.status) == "sent"
    )


def _key_trade_dates(records: tuple[NotificationRecord, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                record.trade_date
                for record in records
                if record.workflow in _KEY_NOTIFICATION_WORKFLOWS and record.trade_date
            }
        )
    )


def _sent_workflow_dates(
    records: tuple[NotificationRecord, ...],
) -> dict[str, set[str]]:
    sent_dates: dict[str, set[str]] = {}
    for record in records:
        if record.workflow not in _KEY_NOTIFICATION_WORKFLOWS:
            continue
        if _status_value(record.status) != "sent":
            continue
        sent_dates.setdefault(record.trade_date, set()).add(record.workflow)
    return sent_dates


def _latest_consecutive_trading_day_streak(dates: tuple[str, ...]) -> int:
    if not dates:
        return 0
    streak = 1
    for index in range(len(dates) - 1, 0, -1):
        if _is_next_weekday(dates[index - 1], dates[index]):
            streak += 1
            continue
        break
    return streak


def _is_next_weekday(previous: str, current: str) -> bool:
    from datetime import date, timedelta

    try:
        previous_date = date.fromisoformat(previous)
        current_date = date.fromisoformat(current)
    except ValueError:
        return False
    probe = previous_date
    while True:
        probe += timedelta(days=1)
        if probe.weekday() >= 5:
            continue
        return probe == current_date


__all__ = ["CommercialReadinessService"]
