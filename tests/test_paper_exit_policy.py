from __future__ import annotations

import unittest
from dataclasses import dataclass, replace

from server.firemoney_server.application.paper_exit_policy import PaperExitPolicy
from shared.contracts import (
    MainlineContinuity,
    OneToTwoEventType,
    OneToTwoExitPlan,
    PaperPosition,
    PaperTradeStatus,
)


@dataclass(frozen=True)
class ExitSettings:
    mainline_fade_score: float = 45.0
    hard_max_holding_trade_days: int = 5
    max_holding_trade_days: int = 2
    discipline_exit_min_gain_pct: float = 0.02
    positive_lock_profit_pct: float = 0.03
    positive_lock_min_profit_drawdown_ratio: float = 1.0
    main_rise_runner_min_quality_score: float = 86.0
    main_rise_runner_min_opened_score: float = 90.0
    main_rise_runner_min_mainline_score: float = 75.0
    main_rise_runner_trailing_start_pct: float = 0.06
    main_rise_runner_trailing_stop_pct: float = 0.02
    main_rise_runner_profit_floor_pct: float = 0.015


def _exit_plan() -> OneToTwoExitPlan:
    return OneToTwoExitPlan(
        stop_loss=10.1,
        stop_loss_pct=0.0399,
        first_take_profit_price=11.78,
        first_take_profit_pct=0.12,
        strong_take_profit_price=11.57,
        strong_take_profit_pct=0.10,
        trailing_stop_pct=0.02,
        max_holding_trade_days=2,
        summary="test exit plan",
    )


def _exit_plan_with_max_days(max_days: int) -> OneToTwoExitPlan:
    plan = _exit_plan()
    return replace(plan, max_holding_trade_days=max_days)


def _mainline(score: float = 80.0) -> MainlineContinuity:
    return MainlineContinuity(
        theme="AI",
        score=score,
        status="strong" if score >= 75 else "weak",
        hot_stock_count=3,
        limit_up_count=2,
        news_count=1,
        latest_news=(),
        reasons=(),
        risk_notes=(),
        next_action="test",
    )


def _position(
    *,
    latest_price: float = 10.9,
    peak_price: float | None = None,
    trough_price: float | None = None,
    quality_score: float = 74.0,
    opened_score: float = 88.0,
    mainline_score: float = 80.0,
    with_exit_plan: bool = True,
    exit_plan: OneToTwoExitPlan | None = None,
) -> PaperPosition:
    entry_price = 10.52
    quantity = 100
    return PaperPosition(
        symbol="600001",
        name="mainline candidate",
        quantity=quantity,
        entry_price=entry_price,
        latest_price=latest_price,
        stop_loss=10.1,
        position_value=round(quantity * latest_price, 2),
        unrealized_pnl=round((latest_price - entry_price) * quantity, 2),
        unrealized_pnl_pct=round((latest_price - entry_price) / entry_price, 4),
        opened_at="2026-05-01",
        position_label="low breakout",
        opened_score=opened_score,
        can_sell_today=True,
        status=PaperTradeStatus.HOLDING,
        risk_note="test",
        exit_plan=exit_plan if exit_plan is not None else _exit_plan() if with_exit_plan else None,
        mainline_continuity=_mainline(mainline_score),
        peak_price=latest_price if peak_price is None else peak_price,
        trough_price=latest_price if trough_price is None else trough_price,
        entry_turnover_quality_score=quality_score,
        entry_turnover_quality_label="test quality",
    )


class PaperExitPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PaperExitPolicy(ExitSettings())

    def test_regular_signal_locks_positive_profit(self) -> None:
        decision = self.policy.decide(
            _position(latest_price=10.9, quality_score=74.0, opened_score=88.0),
            latest_price=10.9,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "positive_profit_lock")
        self.assertEqual(decision.event_type, OneToTwoEventType.TAKE_PROFIT)

    def test_main_rise_runner_holds_above_base_lock_before_first_target(self) -> None:
        position = _position(
            latest_price=10.95,
            peak_price=10.95,
            quality_score=92.0,
            opened_score=100.0,
            mainline_score=90.0,
        )

        self.assertTrue(self.policy.is_main_rise_runner(position))
        self.assertTrue(self.policy.is_quality_positive_lock_ready(position))
        self.assertIsNone(self.policy.decide(position, latest_price=10.95))

    def test_main_rise_runner_trailing_lock_after_six_percent_peak(self) -> None:
        position = _position(
            latest_price=11.0,
            peak_price=11.25,
            quality_score=92.0,
            opened_score=100.0,
            mainline_score=90.0,
        )

        self.assertEqual(self.policy.main_rise_runner_protect_price(position), 11.03)
        decision = self.policy.decide(position, latest_price=11.0)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "main_rise_runner_trailing_lock")
        self.assertEqual(decision.event_type, OneToTwoEventType.TAKE_PROFIT)

    def test_main_rise_runner_profit_floor_locks_before_round_trip(self) -> None:
        position = _position(
            latest_price=10.67,
            peak_price=10.95,
            quality_score=92.0,
            opened_score=100.0,
            mainline_score=90.0,
        )

        self.assertEqual(self.policy.main_rise_runner_protect_price(position), 10.68)
        decision = self.policy.decide(position, latest_price=10.67)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "main_rise_runner_trailing_lock")

    def test_first_target_exits_even_for_main_rise_runner(self) -> None:
        position = _position(
            latest_price=11.8,
            peak_price=11.8,
            quality_score=92.0,
            opened_score=100.0,
            mainline_score=90.0,
        )

        decision = self.policy.decide(position, latest_price=11.8)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "take_profit_first_target")
        self.assertEqual(decision.event_type, OneToTwoEventType.TAKE_PROFIT)

    def test_mainline_fade_has_priority_over_profit_locks(self) -> None:
        position = _position(
            latest_price=11.0,
            peak_price=11.25,
            quality_score=92.0,
            opened_score=100.0,
            mainline_score=30.0,
        )

        decision = self.policy.decide(position, latest_price=11.0)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "mainline_fade_profit_protect")
        self.assertEqual(decision.event_type, OneToTwoEventType.MAINLINE_FADE_EXIT)

    def test_time_exit_keeps_winner_but_exits_weak_or_weekly_positions(self) -> None:
        weak_position = _position(latest_price=10.6)
        winner = replace(weak_position, latest_price=10.9, unrealized_pnl_pct=0.0361)
        weekly_loser = replace(weak_position, latest_price=10.2, unrealized_pnl_pct=-0.0304)

        self.assertIsNone(self.policy.time_exit_decision(winner, holding_trade_days=2))
        weak_decision = self.policy.time_exit_decision(weak_position, holding_trade_days=2)
        weekly_decision = self.policy.time_exit_decision(
            weekly_loser,
            holding_trade_days=5,
        )

        self.assertIsNotNone(weak_decision)
        self.assertEqual(weak_decision.exit_reason, "discipline_weak_after_2_days")
        self.assertIsNotNone(weekly_decision)
        self.assertEqual(weekly_decision.exit_reason, "weekly_risk_timeout")

    def test_time_exit_uses_position_exit_plan_max_holding_days(self) -> None:
        position = _position(
            latest_price=10.52,
            exit_plan=_exit_plan_with_max_days(1),
        )

        decision = self.policy.time_exit_decision(position, holding_trade_days=1)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.exit_reason, "discipline_weak_after_1_days")
        self.assertIn("计划最长 1 个交易日", decision.message)


if __name__ == "__main__":
    unittest.main()
