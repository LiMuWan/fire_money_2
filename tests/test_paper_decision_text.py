from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path

from server.firemoney_server.application.paper_decision_text import (
    execution_friction_guard_note,
    paper_decision_notification_message,
    paper_decision_rules,
    position_recovery_guard_note,
)


@dataclass(frozen=True)
class TextSettings:
    max_position_pct: float = 0.35
    initial_cash: float = 10000.0
    small_account_mode_enabled: bool = True
    small_account_min_lot_shares: int = 100
    small_account_target_position_pct: float = 0.18
    small_account_reduced_target_position_pct: float = 0.12
    small_account_max_position_pct: float = 0.35
    small_account_reduced_max_position_pct: float = 0.2
    positive_lock_profit_pct: float = 0.03
    positive_lock_min_profit_drawdown_ratio: float = 1.0
    paper_guard_min_profit_drawdown_ratio: float = 1.0
    paper_guard_max_consecutive_quality_failures: int = 2
    paper_guard_review_sample: int = 5
    paper_guard_min_win_rate: float = 0.6
    paper_guard_min_average_return_pct: float = 0.005
    paper_guard_reduced_position_pct: float = 0.12
    min_turnover_dragon_score: float = 72.0
    minimum_reward_risk_ratio: float = 2.0
    hard_max_holding_trade_days: int = 5


@dataclass(frozen=True)
class StrategyReport:
    selected_strategy_id: str = "board-shadow-system"
    selected_action: str = "trade"
    evidence_end_date: str = "2026-05-08"
    market_regime: str = "trend_main_rise_day"


@dataclass(frozen=True)
class Account:
    equity: float = 100000.0
    cash: float = 92000.0
    positions: tuple[object, ...] = (object(),)
    daily_trade_count: int = 0
    max_daily_trades: int = 1


@dataclass(frozen=True)
class GuardDecision:
    status: str = "ready"
    action: str = "allow"
    review_sample_count: int = 5
    win_rate: float = 0.6
    average_return_pct: float = 0.01
    max_drawdown_pct: float = -0.02
    suggested_position_pct: float = 0.08
    reasons: tuple[str, ...] = ("样本质量达标",)


@dataclass(frozen=True)
class BuyInstruction:
    name: str = "样本股份"
    symbol: str = "600001"
    entry_window: str = "早盘确认"
    entry_price: float = 10.52
    position_pct: float = 0.04
    cash_budget: float = 4000.0
    quantity: int = 300
    stop_loss: float = 10.1
    first_take_profit_price: float = 11.78
    planned_stop_risk_pct: float = 0.04
    planned_first_target_return_pct: float = 0.12
    planned_reward_risk_ratio: float = 3.0
    max_intratrade_drawdown_budget_pct: float = 0.04
    entry_trigger: str = "放量承接"
    rationale: str = "主线强，换手龙质量高"
    invalidation_rules: tuple[str, ...] = ("跌破触发价不买",)
    sell_rules: tuple[str, ...] = ("T+1 后按主升保护线处理",)
    risk_notes: tuple[str, ...] = (execution_friction_guard_note(),)


@dataclass(frozen=True)
class HoldingInstruction:
    action: str = "hold"
    status: str = "main_rise_runner_hold"
    name: str = "样本股份"
    symbol: str = "600001"
    quantity: int = 300
    entry_price: float = 10.52
    latest_price: float = 10.95
    unrealized_pnl: float = 129.0
    unrealized_pnl_pct: float = 0.0409
    positive_lock_price: float = 10.84
    stop_loss: float = 10.1
    first_take_profit_price: float = 11.78
    holding_trade_days: int = 1
    can_sell_today: bool = True
    rationale: str = "强信号未破保护线，继续吃主升"
    sell_triggers: tuple[str, ...] = ("跌破主升保护线卖出",)


class PaperDecisionTextTest(unittest.TestCase):
    def test_paper_decision_rules_keep_core_discipline_copy(self) -> None:
        rules = paper_decision_rules(
            TextSettings(),
            format_pct=lambda value: f"{value:.0%}",
        )

        self.assertEqual(len(rules), 16)
        self.assertTrue(any("T+1" in rule and "3%" in rule for rule in rules))
        self.assertTrue(any("封板波段主线" in rule and "72/100" in rule for rule in rules))
        self.assertTrue(any("执行摩擦守门" in rule for rule in rules))
        self.assertTrue(any("2024-01-01" in rule for rule in rules))
        self.assertTrue(any("逐日快照" in rule for rule in rules))
        self.assertTrue(any("小账户一手制" in rule and "10000" in rule for rule in rules))
        self.assertTrue(any("小账户仓位恢复纪律" in rule for rule in rules))

    def test_position_recovery_guard_note_explains_reduced_and_full_size(self) -> None:
        reduced_note = position_recovery_guard_note(
            current_position_pct=0.04,
            max_position_pct=0.08,
            format_pct=lambda value: f"{value:.0%}",
        )
        full_note = position_recovery_guard_note(
            current_position_pct=0.08,
            max_position_pct=0.08,
            format_pct=lambda value: f"{value:.0%}",
        )

        self.assertIn("暂不放大到 8%", reduced_note)
        self.assertIn("allow_full", reduced_note)
        self.assertIn("无执行摩擦降仓提示", reduced_note)
        self.assertIn("当前已是进攻档 8%", full_note)

    def test_notification_message_formats_buy_command_sheet(self) -> None:
        message = paper_decision_notification_message(
            report_date="2026-05-09",
            strategy_report=StrategyReport(),
            status="ready_to_buy",
            summary="今日有一个高赔率买点。",
            instruction=BuyInstruction(),
            holding_instruction=None,
            candidate_count=3,
            ready_count=1,
            blocked_count=2,
            account=Account(),
            guard_decision=GuardDecision(),
            next_action="等待早盘触发价。",
        )

        self.assertIn("交易日：2026-05-09", message)
        self.assertIn("买点：", message)
        self.assertIn("样本股份（600001）", message)
        self.assertIn("取消买入：", message)
        self.assertIn("风险提示：", message)
        self.assertIn("执行摩擦守门", message)
        self.assertIn("卖点纪律：", message)
        self.assertIn("边界：这是模拟盘指挥单", message)

    def test_notification_message_formats_holding_command_sheet(self) -> None:
        message = paper_decision_notification_message(
            report_date="2026-05-09",
            strategy_report=StrategyReport(),
            status="holding",
            summary="已有持仓，今日先处理卖点。",
            instruction=None,
            holding_instruction=HoldingInstruction(),
            candidate_count=0,
            ready_count=0,
            blocked_count=0,
            account=Account(),
            guard_decision=GuardDecision(),
            next_action="盘中观察主升保护线。",
        )

        self.assertIn("卖点/持仓处置：", message)
        self.assertIn("hold / main_rise_runner_hold", message)
        self.assertIn("T+1 可卖 True", message)
        self.assertIn("卖出触发：", message)

    def test_notification_message_formats_no_buy_command_sheet(self) -> None:
        message = paper_decision_notification_message(
            report_date="2026-05-09",
            strategy_report=StrategyReport(),
            status="no_trade",
            summary="没有高赔率窗口。",
            instruction=None,
            holding_instruction=None,
            candidate_count=1,
            ready_count=0,
            blocked_count=1,
            account=Account(positions=()),
            guard_decision=GuardDecision(reasons=()),
            next_action="继续空仓观察。",
        )

        self.assertIn("买点：今日不买。", message)
        self.assertIn("纪律：没有高赔率窗口时", message)
        self.assertIn("下一步：继续空仓观察。", message)

    def test_paper_decision_text_keeps_storage_and_notification_out(self) -> None:
        module = Path("server/firemoney_server/application/paper_decision_text.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server.infrastructure",
            "shared.contracts",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)
        self.assertNotIn("Feishu", source)
        self.assertNotIn("PaperTradeStore", source)


if __name__ == "__main__":
    unittest.main()
