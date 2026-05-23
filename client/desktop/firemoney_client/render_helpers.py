"""Shared formatting helpers for FireMoney preview section renderers."""

from __future__ import annotations

from html import escape
import re
from typing import Any


def text(value: object) -> str:
    return escape(str(value), quote=True)


def format_yi(value: float) -> str:
    if value <= 0:
        return "未知"
    return f"{value / 100_000_000:.0f}亿"


def candidate_brief(candidate: Any) -> str:
    return f"{candidate.name}（{candidate.symbol}）"


def strategy_name(strategy_id: str) -> str:
    return {
        "board-shadow-system": "封板波段主线",
        "cash": "空仓防守",
    }.get(strategy_id, strategy_id)


def action_name(action: str) -> str:
    return {
        "operate_when_signal_exists": "有信号才出手",
        "stand_aside": "空仓等待",
    }.get(action, action)


def regime_name(regime: str) -> str:
    return {
        "market_data_unavailable_day": "行情异常暂停",
        "trend_main_rise_day": "趋势主升日",
        "defense_stand_aside_day": "防守空仓日",
    }.get(regime, regime)


def execution_track_name(track: str) -> str:
    return {
        "board_shadow_system_execution": "封板波段主线执行",
        "cash_stand_aside": "空仓等待",
    }.get(track, track)


def timing_name(timing: str) -> str:
    return {
        "early_session": "早盘确认",
        "late_session": "尾盘复核",
    }.get(timing, timing)


def guard_action_name(action: str) -> str:
    return {
        "allow_full": "允许进攻仓位",
        "allow_reduced": "只允许降仓试错",
        "stand_aside": "暂停开仓",
    }.get(action, action)


def regime_action_name(action: str) -> str:
    return {
        "attack_trend_main_rise": "主升进攻",
        "defense_stand_aside": "防守等待",
        "pause_until_market_data_ready": "暂停修复行情",
    }.get(action, action)


def k92_gate_name(gate: str) -> str:
    return {
        "confirm": "K92确认主线",
        "observe": "K92观察通过",
        "block": "K92退潮阻断",
        "not_available": "K92未接入",
    }.get(gate, gate)


def role_name(role: str) -> str:
    return {
        "main_operating_line": "主经营主线",
        "risk_control": "风险控制",
        "cash_waiting_line": "空仓等待线",
    }.get(role, role)


def decision_status_name(status: str) -> str:
    return {
        "ready": "就绪",
        "blocked": "阻断",
        "warning": "预警",
        "ready_to_buy": "可买入",
        "no_signal": "无有效信号",
        "stand_aside": "空仓等待",
        "guard_blocked": "守门拦截",
        "holding": "持仓中",
        "data_unavailable": "数据缺失降级",
    }.get(status, status)


def guard_status_name(status: str) -> str:
    return {
        "ready": "守门通过",
        "full": "守门通过",
        "reduced": "降仓试错",
        "blocked": "守门阻断",
        "stand_aside": "暂停开仓",
        "warning": "风险预警",
        "observation": "观察期",
    }.get(status, status)


def holding_action_name(action: str) -> str:
    return {
        "hold": "继续持有",
        "sell_signal": "卖出信号",
        "watch_sell": "观察卖点",
    }.get(action, action)


def holding_status_name(status: str) -> str:
    return {
        "main_rise_runner_hold": "主升持有中",
        "main_rise_runner_protect": "主升保护止盈",
        "profit_lock": "正收益锁盈",
        "weak_timeout_watch": "弱转强超时观察",
        "holding": "持仓中",
    }.get(status, decision_status_name(status))


def confidence_name(confidence: str) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(confidence, confidence)


def bool_name(value: bool) -> str:
    return "可卖" if value else "不可卖"


def score_text(value: float) -> str:
    return f"{value:.0f}分"


def phase_name(phase: str | None) -> str:
    if not phase:
        return ""
    return {
        "scan": "盘前扫描",
        "auction": "竞价确认",
        "open": "开盘确认",
        "risk": "风险复核",
    }.get(phase, phase)


def notification_status_name(status: str) -> str:
    return {
        "prepared": "已生成",
        "sent": "已发送",
        "failed": "发送失败",
        "skipped": "已跳过",
    }.get(status, status)


def workflow_name(workflow: str) -> str:
    return {
        "morning": "早评",
        "watch:open": "盘中买点",
        "watch:risk": "盘中卖点",
        "eod": "晚评",
    }.get(workflow, workflow)


def database_status_name(status: str) -> str:
    return {
        "ready": "运行正常",
        "warning": "需留意",
        "blocked": "需处理",
    }.get(status, status)


def paper_backtest_status_name(status: str) -> str:
    return {
        "ready": "通过",
        "warning": "观察",
        "blocked": "不通过",
        "no_sample": "样本不足",
    }.get(status, status)


def trade_context_note(note: str) -> str:
    return translate_misc_text(note).replace(
        "请求日期为 A 股交易日",
        "当前日期为 A 股交易日",
    )


def safe_database_label(path: str) -> str:
    lower = path.lower()
    if lower.endswith("paper_trades.sqlite3"):
        return "本地模拟盘账本"
    return path


def expected_return_label(text_value: str) -> str:
    translated = translate_misc_text(text_value)
    translated = translated.replace("2024+ ", "2024年以来 ")
    translated = translated.replace("8%/12% ", "8%/12%仓位 ")
    translated = translated.replace("复合收益 ", "复合收益 ")
    translated = translated.replace("验证段 ", "验证段收益 ")
    translated = translated.replace("最大回撤 ", "最大回撤 ")
    translated = translated.replace(" / ", "；")
    translated = translated.replace(
        "2024年以来 动态 8%/12%仓位 复合收益 ",
        "2024年以来动态 8%/12%仓位复合收益 ",
    )
    return translated


def translate_misc_text(text_value: str) -> str:
    replacements = {
        "board-shadow-system": "封板波段主线",
        "board-shadow validated mainline": "主线验证通过",
        "mainline candidate": "主线候选",
        "ready_to_buy": "可买入",
        "no_signal": "无有效信号",
        "stand_aside": "空仓等待",
        "ready": "就绪",
        "blocked": "阻断",
        "warning": "需留意",
        "no_sample": "样本不足",
        "holding": "持仓中",
        "trend_main_rise_day": "趋势主升日",
        "defense_stand_aside_day": "防守空仓日",
        "operate_when_signal_exists": "有信号才出手",
        "allow_full": "允许进攻仓位",
        "allow_reduced": "只允许降仓试错",
        "early_session": "早盘确认",
        "late_session": "尾盘复核",
        "discipline_take_profit": "纪律止盈",
        "first_take_profit": "第一止盈",
        "main_rise_runner_trailing_lock": "主升保护止盈",
        "rank score": "排序分",
        "rank=": "排序分 ",
        "heat=": "热度 ",
        "advance=": "上涨占比 ",
        "watch --phase open": "盘中值守开盘阶段",
        "shadow": "影子样本",
        "main_operating_line": "主经营主线",
        "risk_control": "风险控制",
        "risk": "风险复核",
        "PIT pass": "点时数据校验通过",
        "strong": "强势",
        "observation": "观察期",
        "attack_trend_main_rise": "主升进攻",
        "requested date is an A-share trading day": "请求日期为 A 股交易日",
        "only this main line can open a paper trade.": "只有这条主线允许生成模拟买入。",
        "selected ": "锁定 ",
        "first target": "第一止盈",
        "trade day": "个交易日",
        "board-影子样本 exit:": "影子样本纪律：",
        "封板波段主线 主线候选": "主线龙头候选",
        "watch_only": "仅观察",
        "positive_profit_lock": "正收益锁盈",
        "trailing_take_profit": "强势回撤止盈",
        "20d volume ratio": "20日量比",
        "recent gain": "近20日涨幅",
        "AkShare": "免费行情源",
        "Point-in-Time": "逐日快照",
        "Tick": "逐笔成交",
        "SQLite": "本地账本",
        "Beta": "值守",
        "Top": "重点",
        "compound": "复合收益",
        "validation": "验证段",
        "drawdown": "回撤",
        "dynamic": "动态",
        "auction": "竞价",
        "brief": "简报",
        "ratio": "比例",
        "volume": "量能",
        "scan/auction/open/risk": "扫描 / 竞价 / 开盘 / 风险复核",
        "strategy-decision": "策略决策简报",
        "paper-decision": "模拟盘指挥单",
        "beta ": "值守 ",
        "scan/竞价/open/risk": "扫描 / 竞价 / 开盘 / 风险复核",
        "scan/auction/open/risk,": "扫描 / 竞价 / 开盘 / 风险复核，",
        " / shadow": " / 影子样本",
        "point-in-time": "逐日快照",
        "baseline_cost_0.15pct": "基准成本 0.15%",
        "stress_cost_0.30pct": "压力成本 0.30%",
        "stress_cost_0.50pct": "压力成本 0.50%",
        "stress_cost_0.80pct": "压力成本 0.80%",
        "stress_cost_1.00pct": "压力成本 1.00%",
        "equity=": "权益 ",
        "positions=": "持仓数 ",
        "closed_samples=": "已完成样本 ",
        "recent_records=": "最近记录 ",
        "completed_tasks=": "已完成任务 ",
        "min_score=": "最低分 ",
        "execution_score=": "执行分带 ",
        "initial_cash=": "初始资金 ",
        "max_position_pct=": "最大仓位 ",
        "max_daily_trades=": "单日最多交易 ",
        "confirm_open=": "开盘确认区间 ",
        "prepared": "已生成",
        "sent": "已发送",
        "failed": "发送失败",
        "morning": "早评",
        "watch:open": "盘中买点",
        "watch:risk": "盘中卖点",
        "eod": "晚评",
    }
    translated = text_value
    for old, new in replacements.items():
        translated = translated.replace(old, new)
    translated = re.sub(
        r"封板波段主线 selected ([^（(]+)[（(](\d{6})[）)]\s*排序分=?\s*([0-9.]+),\s*热度=?\s*([0-9.]+),\s*上涨占比\s*([0-9.]+%);?\s*只有这条主线允许生成模拟买入。",
        r"主线已锁定：\1（\2），排序分 \3，热度 \4，上涨占比 \5。只有这条主线允许生成模拟买入。",
        translated,
    )
    translated = re.sub(
        r"封板波段主线[:：]\s*stop\s*([0-9.]+),\s*first target\s*([0-9.]+),\s*max hold\s*([0-9]+)\s*trade day[s]?\.?",
        r"封板波段主线：止损 \1，第一止盈 \2，最长持有 \3 个交易日。",
        translated,
    )
    translated = translated.replace("封板波段主线:", "封板波段主线：")
    translated = translated.replace("stop ", "止损 ")
    translated = translated.replace(", first target ", "，第一止盈 ")
    translated = translated.replace(", max hold ", "，最长持有 ")
    translated = translated.replace(" / attack_trend_main_rise / ", " / 主升进攻 / ")
    translated = translated.replace(" / watch_only", " / 仅观察")
    return re.sub(
        r"([A-Za-z0-9_\u4e00-\u9fff\-]+)\((\d{6})\)",
        r"\1（\2）",
        translated,
    )


def candidate_market_cap_line(candidate: Any) -> str:
    source = {
        "total": "总市值",
        "float": "流通市值",
        "missing": "市值",
    }.get(getattr(candidate, "market_cap_source", ""), "市值")
    value = candidate.market_cap or candidate.float_market_cap
    return f"{source} {format_yi(value)}"


def paper_quality_line(report: Any) -> str:
    return (
        f"<li>收益质量：平均赚撤比 {report.average_profit_drawdown_ratio:.2f}R，"
        f"盈利覆盖回撤达标率 {report.risk_quality_pass_rate:.2%}</li>"
    )


__all__ = [
    "action_name",
    "bool_name",
    "candidate_brief",
    "candidate_market_cap_line",
    "confidence_name",
    "database_status_name",
    "decision_status_name",
    "execution_track_name",
    "expected_return_label",
    "format_yi",
    "guard_action_name",
    "guard_status_name",
    "holding_action_name",
    "holding_status_name",
    "k92_gate_name",
    "notification_status_name",
    "paper_backtest_status_name",
    "paper_quality_line",
    "phase_name",
    "regime_action_name",
    "regime_name",
    "role_name",
    "safe_database_label",
    "score_text",
    "strategy_name",
    "text",
    "timing_name",
    "trade_context_note",
    "translate_misc_text",
    "workflow_name",
]
