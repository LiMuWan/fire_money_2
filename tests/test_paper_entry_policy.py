from __future__ import annotations

import unittest
from dataclasses import dataclass, replace

from server.firemoney_server.application.paper_entry_policy import PaperEntryPolicy
from server.firemoney_server.application.paper_trading_guard import PaperTradingGuardResult
from shared.contracts import (
    BreakoutStructureProfile,
    MainlineContinuity,
    OneToTwoCandidate,
    OneToTwoExitPlan,
    OneToTwoPositionProfile,
)


@dataclass(frozen=True)
class EntrySettings:
    minimum_reward_risk_ratio: float = 2.0
    paper_entry_mainboard_only: bool = True
    paper_guard_min_profit_drawdown_ratio: float = 1.0
    min_turnover_dragon_score: float = 72.0
    min_volume_ratio_5: float = 1.0
    min_rsi_14: float = 55.0
    max_rsi_14: float = 85.0
    min_position_percentile_60: float = 0.55
    min_breakout_structure_score: float = 70.0
    paper_guard_reduced_position_pct: float = 0.04
    mainline_fade_score: float = 45.0
    small_account_mode_enabled: bool = True
    small_account_min_lot_shares: int = 100
    small_account_target_position_pct: float = 0.18
    small_account_reduced_target_position_pct: float = 0.12
    small_account_max_position_pct: float = 0.35
    small_account_reduced_max_position_pct: float = 0.2


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


def _candidate(**overrides) -> OneToTwoCandidate:
    profile = OneToTwoPositionProfile(
        label="low breakout",
        low_position_score=20.0,
        breakout_score=20.0,
        pressure_score=20.0,
        moving_average_score=20.0,
        volume_score=20.0,
        summary="test profile",
        risk_notes=(),
        volume_ratio=1.5,
        rsi_14=65.0,
        position_percentile_60=0.75,
    )
    values = {
        "symbol": "600001",
        "name": "mainline candidate",
        "trade_date": "2026-05-09",
        "score": 100.0,
        "status": "ready",
        "latest_price": 10.52,
        "limit_up_price": 10.52,
        "entry_price": 10.52,
        "stop_loss": 10.1,
        "position_limit_pct": 0.08,
        "first_board_score": 20.0,
        "auction_score": 20.0,
        "position_score": 20.0,
        "theme_score": 20.0,
        "liquidity_score": 20.0,
        "position_profile": profile,
        "blockers": (),
        "warnings": (),
        "rationale": "test rationale",
        "next_action": "test",
        "mainline_score": 20.0,
        "sealing_score": 20.0,
        "leader_score": 19.0,
        "leader_label": "leader",
        "strategy_tags": (),
        "discipline_summary": "test",
        "exit_plan": _exit_plan(),
        "mainline_continuity": None,
        "turnover_quality_score": 92.0,
        "turnover_quality_label": "strong quality",
        "turnover_quality_notes": (),
        "breakout_structure": BreakoutStructureProfile(
            score=82.0,
            label="强结构突破",
            breakout_line=10.2,
            distance_pct=0.0314,
            base_tightness_score=24.0,
            volume_surge_score=20.0,
            overhead_supply_score=18.0,
            relative_strength_score=20.0,
            passed=True,
            summary="强结构突破 82/100",
            risk_notes=(),
        ),
    }
    values.update(overrides)
    return OneToTwoCandidate(**values)


def _guard_result(action: str = "allow_reduced") -> PaperTradingGuardResult:
    return PaperTradingGuardResult(
        status="reduced",
        action=action,
        review_sample_count=5,
        win_rate=0.6,
        average_return_pct=0.01,
        max_drawdown_pct=0.02,
        consecutive_losses=0,
        consecutive_quality_failures=0,
        average_profit_drawdown_ratio=1.2,
        risk_quality_pass_rate=0.8,
        suggested_position_pct=0.04,
        reasons=("test guard",),
        next_action="test",
    )


class PaperEntryPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PaperEntryPolicy(EntrySettings())

    def test_ready_high_quality_candidate_passes_positive_expectancy_gate(self) -> None:
        candidate = _candidate()

        self.assertTrue(self.policy.is_positive_expectancy_candidate(candidate))
        self.assertEqual(self.policy.positive_expectancy_candidates((candidate,)), (candidate,))
        quality = self.policy.candidate_entry_quality(candidate)
        self.assertEqual(quality.risk_pct, 0.0399)
        self.assertEqual(quality.reward_pct, 0.1198)
        self.assertAlmostEqual(quality.reward_risk_ratio, 3.0)

    def test_blocks_low_quality_or_poor_structure_candidates(self) -> None:
        low_turnover = _candidate(turnover_quality_score=60.0)
        high_rsi_profile = replace(_candidate().position_profile, rsi_14=82.0)
        high_rsi = _candidate(position_profile=high_rsi_profile)
        low_position_profile = replace(
            _candidate().position_profile,
            position_percentile_60=0.6,
        )
        low_position = _candidate(position_profile=low_position_profile)

        self.assertFalse(self.policy.is_positive_expectancy_candidate(low_turnover))
        self.assertFalse(self.policy.is_positive_expectancy_candidate(high_rsi))
        self.assertFalse(self.policy.is_positive_expectancy_candidate(low_position))

    def test_blocks_candidates_without_enough_reward_risk(self) -> None:
        weak_plan = replace(
            _exit_plan(),
            first_take_profit_price=10.8,
            first_take_profit_pct=0.0266,
        )
        candidate = _candidate(exit_plan=weak_plan)

        self.assertFalse(self.policy.is_positive_expectancy_candidate(candidate))
        self.assertLess(
            self.policy.candidate_reward_risk_ratio(candidate),
            2.0,
        )

    def test_blocks_candidate_without_valid_breakout_structure(self) -> None:
        weak_structure = replace(
            _candidate().breakout_structure,
            score=60.0,
            label="结构突破不足",
            passed=False,
        )
        candidate = _candidate(breakout_structure=weak_structure)

        self.assertFalse(self.policy.is_positive_expectancy_candidate(candidate))

    def test_blocks_candidate_when_mainline_continuity_fades(self) -> None:
        fading = MainlineContinuity(
            theme="AI",
            score=40.0,
            status="fading",
            hot_stock_count=1,
            limit_up_count=0,
            news_count=0,
            latest_news=(),
            reasons=("主线退潮",),
            risk_notes=("消息和宽度都不足",),
            next_action="空仓",
        )
        candidate = _candidate(mainline_continuity=fading)

        self.assertFalse(self.policy.is_positive_expectancy_candidate(candidate))

    def test_blocks_non_mainboard_candidates_by_default(self) -> None:
        chinext = _candidate(symbol="300001", name="创业板样本")
        star = _candidate(symbol="688001", name="科创板样本")
        bse = _candidate(symbol="920001", name="北交所样本")

        self.assertFalse(self.policy.is_positive_expectancy_candidate(chinext))
        self.assertFalse(self.policy.is_positive_expectancy_candidate(star))
        self.assertFalse(self.policy.is_positive_expectancy_candidate(bse))

    def test_guard_reduced_entry_caps_position_and_keeps_warning(self) -> None:
        candidate = _candidate(warnings=("existing warning",))
        reduced = self.policy.candidate_with_guard_position_limit(
            candidate,
            _guard_result("allow_reduced"),
            format_pct=lambda value: f"{value:.0%}",
        )
        unchanged = self.policy.candidate_with_guard_position_limit(
            candidate,
            _guard_result("allow_full"),
            format_pct=lambda value: f"{value:.0%}",
        )

        self.assertEqual(reduced.position_limit_pct, 0.04)
        self.assertIn("existing warning", reduced.warnings)
        self.assertIn("模拟盘收益守门降仓至 4%。", reduced.warnings)
        self.assertIs(unchanged, candidate)

    def test_execution_friction_warning_caps_position(self) -> None:
        candidate = _candidate(
            warnings=("封板资金刚过线，盘中炸板风险需要重点盯",),
        )

        reduced = self.policy.candidate_with_execution_friction_position_limit(
            candidate,
            format_pct=lambda value: f"{value:.0%}",
        )

        self.assertEqual(reduced.position_limit_pct, 0.04)
        self.assertIn("封板资金刚过线，盘中炸板风险需要重点盯", reduced.warnings)
        self.assertTrue(any("执行摩擦风险触发降仓" in item for item in reduced.warnings))


if __name__ == "__main__":
    unittest.main()
