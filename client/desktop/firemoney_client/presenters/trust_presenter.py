"""User-facing trust and paper-performance summary helpers."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import (
    NotificationRecord,
    OneToTwoDoctorReport,
    OneToTwoMorningReport,
    OneToTwoScheduleHealthReport,
    OneToTwoScheduleRun,
    PaperTradeDatabaseReport,
    PaperTradingDecisionReport,
)


@dataclass(frozen=True)
class TrustStatusCard:
    title: str
    tone: str
    headline: str
    details: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class PerformanceStatusCard:
    title: str
    tone: str
    headline: str
    trade_permission: str
    metrics: tuple[tuple[str, str], ...]
    details: tuple[str, ...]
    next_action: str


def build_trust_status_card(
    *,
    report: OneToTwoMorningReport,
    watch_report: OneToTwoMorningReport,
    paper_report: PaperTradingDecisionReport | None,
    doctor_report: OneToTwoDoctorReport | None,
    schedule_run: OneToTwoScheduleRun | None,
    notification_records: tuple[NotificationRecord, ...],
    schedule_health_report: OneToTwoScheduleHealthReport | None = None,
) -> TrustStatusCard:
    trading_line = (
        f"交易日 {report.trade_context.trade_date}，今天允许按主线值守。"
        if report.trade_context.is_trading_day
        else f"{report.trade_context.requested_date} 非交易日，早评/晚评不应发送。"
    )
    doctor_blockers = tuple(
        check for check in (doctor_report.checks if doctor_report else ()) if check.status == "blocked"
    )
    failed_tasks = tuple(
        task for task in (schedule_run.tasks if schedule_run else ()) if task.status == "failed"
    )
    expired_tasks = tuple(
        task for task in (schedule_run.tasks if schedule_run else ()) if task.status == "expired"
    )
    schedule_health_blockers = tuple(
        item
        for item in (schedule_health_report.items if schedule_health_report else ())
        if item.status == "blocked"
    )
    schedule_health_warnings = tuple(
        item
        for item in (schedule_health_report.items if schedule_health_report else ())
        if item.status == "warning"
    )
    real_action_count = sum(
        1
        for record in notification_records
        if record.workflow in {"morning", "eod"}
        or record.workflow.startswith("watch:")
    )
    data_unavailable = (
        paper_report is not None and paper_report.status == "data_unavailable"
    ) or "行情数据不可用" in report.summary
    if doctor_blockers or failed_tasks or schedule_health_blockers or data_unavailable:
        tone = "danger"
        headline = "值守有阻断，今天不能盲目相信买点。"
    elif expired_tasks or schedule_health_warnings:
        tone = "warning"
        headline = "通知覆盖有待确认，先修值守再谈加仓。"
    elif not report.trade_context.is_trading_day:
        tone = "neutral"
        headline = "休市日正常静默，系统不应打扰。"
    else:
        tone = "success"
        headline = "主线值守正常，按指挥单和持仓纪律执行。"
    details = (
        trading_line,
        _schedule_health_line(schedule_health_report),
        _schedule_line(schedule_run),
        _doctor_line(doctor_report),
        f"飞书行动记录 {real_action_count} 条；只推早评、真实模拟买入/卖出、晚评。",
        f"最新盘中事件：{watch_report.account.events[0].message if watch_report.account.events else '暂无模拟盘事件'}",
    )
    next_action = (
        doctor_blockers[0].next_action
        if doctor_blockers
        else failed_tasks[0].message
        if failed_tasks
        else schedule_health_blockers[0].next_action
        if schedule_health_blockers
        else expired_tasks[0].message
        if expired_tasks
        else schedule_health_warnings[0].next_action
        if schedule_health_warnings
        else paper_report.next_action
        if paper_report is not None
        else "先生成模拟盘指挥单。"
    )
    return TrustStatusCard(
        title="运行信任",
        tone=tone,
        headline=headline,
        details=details,
        next_action=next_action,
    )


def build_performance_status_card(
    report: PaperTradeDatabaseReport | None,
) -> PerformanceStatusCard:
    if report is None:
        return PerformanceStatusCard(
            title="收益守门",
            tone="neutral",
            headline="暂无模拟盘账本报告。",
            trade_permission="开仓权限：观察档，没有闭环样本前只允许按默认小样本纪律模拟。",
            metrics=(("闭环样本", "0"), ("胜率", "--"), ("总收益", "--"), ("赚撤比", "--")),
            details=("先跑 paper-db 或生成预览账本，再看真实模拟盘收益质量。",),
            next_action="先生成模拟盘账本报告。",
        )
    tone = _performance_tone(report)
    headline = _performance_headline(report)
    latest_trade = report.recent_trades[0] if report.recent_trades else None
    latest_line = (
        f"最近闭环：{latest_trade.name}（{latest_trade.symbol}）收益 {latest_trade.realized_pnl_pct:.2%}，退出 {latest_trade.exit_reason}。"
        if latest_trade is not None
        else "最近闭环：暂无完成交易。"
    )
    quality_line = (
        f"盈利覆盖回撤达标率 {report.risk_quality_pass_rate:.2%}，平均赚撤比 {report.average_profit_drawdown_ratio:.2f}R。"
    )
    audit = report.daily_audits[0] if report.daily_audits else None
    audit_line = (
        f"最近交易日 {audit.trade_date}：{audit.action_label}，买入 {audit.buy_count}，卖出 {audit.sell_count}，预警 {audit.warning_count}。"
        if audit is not None
        else "最近交易日：暂无审计记录。"
    )
    return PerformanceStatusCard(
        title="收益守门",
        tone=tone,
        headline=headline,
        trade_permission=_trade_permission_line(report),
        metrics=(
            ("闭环样本", str(report.closed_trade_count)),
            ("胜率", f"{report.win_rate:.2%}"),
            ("总收益", f"{report.total_realized_return_pct:.2%}"),
            ("赚撤比", f"{report.average_profit_drawdown_ratio:.2f}R"),
        ),
        details=(latest_line, quality_line, audit_line),
        next_action=report.next_action,
    )


def _schedule_line(schedule_run: OneToTwoScheduleRun | None) -> str:
    if schedule_run is None:
        return "调度：暂无调度记录。"
    failed = sum(1 for task in schedule_run.tasks if task.status == "failed")
    expired = sum(1 for task in schedule_run.tasks if task.status == "expired")
    return (
        f"调度：应执行 {schedule_run.due_count}，已执行 {schedule_run.executed_count}，"
        f"跳过 {schedule_run.skipped_count}，失败 {failed}，过期 {expired}。"
    )


def _schedule_health_line(report: OneToTwoScheduleHealthReport | None) -> str:
    if report is None:
        return "早评/晚评覆盖：暂无健康检查。"
    item_text = "；".join(
        f"{item.workflow} {item.scheduled_time} {item.status}/{item.notification_status}"
        for item in report.items
    )
    return f"早评/晚评覆盖：{report.status}，{item_text}。"


def _doctor_line(doctor_report: OneToTwoDoctorReport | None) -> str:
    if doctor_report is None:
        return "体检：暂无运行体检。"
    blocked = sum(1 for check in doctor_report.checks if check.status == "blocked")
    warning = sum(1 for check in doctor_report.checks if check.status == "warning")
    return f"体检：{doctor_report.status}，阻断 {blocked}，警告 {warning}。"


def _performance_tone(report: PaperTradeDatabaseReport) -> str:
    if report.closed_trade_count <= 0:
        return "neutral"
    if report.total_realized_pnl < 0 or report.average_profit_drawdown_ratio < 1.0:
        return "danger"
    if report.win_rate < 0.55 or report.risk_quality_pass_rate < 0.6:
        return "warning"
    return "success"


def _performance_headline(report: PaperTradeDatabaseReport) -> str:
    if report.closed_trade_count <= 0:
        return "还没有闭环样本，不能评价赚钱能力。"
    if report.total_realized_pnl < 0:
        return "当前真实模拟盘仍在亏损，必须先降仓和复盘买点。"
    if report.average_profit_drawdown_ratio < 1.0:
        return "虽然有盈利，但利润还没有稳定覆盖过程回撤。"
    if report.win_rate < 0.55:
        return "收益为正，但胜率仍偏低，继续小仓验证。"
    return "真实模拟盘收益质量暂时达标，继续按纪律经营。"


def _trade_permission_line(report: PaperTradeDatabaseReport) -> str:
    if report.closed_trade_count <= 0:
        return "开仓权限：观察档，先用小样本纪律验证，不因空白样本加仓。"
    if report.total_realized_pnl < 0:
        return "开仓权限：暂停开仓，先复盘亏损样本和买点质量。"
    if report.average_profit_drawdown_ratio < 1.0:
        return "开仓权限：降仓验证，盈利还没有覆盖过程回撤。"
    if report.win_rate < 0.55 or report.risk_quality_pass_rate < 0.6:
        return "开仓权限：谨慎试错，胜率或收益质量还没有稳定。"
    return "开仓权限：允许按指挥单执行，但仍坚持每天最多一笔。"


__all__ = [
    "PerformanceStatusCard",
    "TrustStatusCard",
    "build_performance_status_card",
    "build_trust_status_card",
]
