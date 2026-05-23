from __future__ import annotations

import unittest

from server.firemoney_server.application.k92_emotion_liquidity_service import (
    K92EmotionLiquidityService,
)
from shared.contracts import OneToTwoCandidate, OneToTwoExitPlan, OneToTwoPositionProfile


def _profile(position_percentile_60: float) -> OneToTwoPositionProfile:
    return OneToTwoPositionProfile(
        label="test",
        low_position_score=8,
        breakout_score=8,
        pressure_score=6,
        moving_average_score=8,
        volume_score=8,
        summary="test profile",
        risk_notes=(),
        position_percentile_60=position_percentile_60,
    )


def _candidate(
    symbol: str,
    *,
    status: str = "ready",
    turnover_quality_score: float = 88.0,
    mainline_score: float = 18.5,
    position_percentile_60: float = 0.72,
    blockers: tuple[str, ...] = (),
) -> OneToTwoCandidate:
    return OneToTwoCandidate(
        symbol=symbol,
        name=f"测试{symbol}",
        trade_date="2026-05-15",
        score=96.0,
        status=status,
        latest_price=10.0,
        limit_up_price=10.0,
        entry_price=10.0,
        stop_loss=9.4,
        position_limit_pct=0.08,
        first_board_score=18.0,
        auction_score=15.0,
        position_score=18.0,
        theme_score=9.0,
        liquidity_score=9.0,
        position_profile=_profile(position_percentile_60),
        blockers=blockers,
        warnings=(),
        rationale="测试候选",
        next_action="只观察",
        mainline_score=mainline_score,
        sealing_score=18.0,
        leader_score=18.0,
        leader_label="test leader",
        exit_plan=OneToTwoExitPlan(
            stop_loss=9.4,
            stop_loss_pct=0.06,
            first_take_profit_price=10.55,
            first_take_profit_pct=0.055,
            strong_take_profit_price=10.8,
            strong_take_profit_pct=0.08,
            trailing_stop_pct=0.02,
            max_holding_trade_days=1,
            summary="test exit",
        ),
        turnover_quality_score=turnover_quality_score,
        turnover_quality_label="正向换手",
        market_cap=12_000_000_000,
        float_market_cap=9_000_000_000,
    )


class K92EmotionLiquidityServiceTest(unittest.TestCase):
    def test_routes_strong_market_to_leader_attack_day(self) -> None:
        service = K92EmotionLiquidityService()

        report = service.build_report(
            trade_date="2026-05-15",
            market_temperature=76,
            candidates=(
                _candidate("600001"),
                _candidate("600002", turnover_quality_score=86.0),
            ),
        )

        self.assertEqual(report.regime, "leader_attack_day")
        self.assertEqual(report.action, "watch_leader_attack")
        self.assertEqual(report.status, "watch_only")
        self.assertEqual(report.leader_candidates[0].name, "测试600001")
        self.assertIn("未完成历史逐日回测前", report.limitations[-1])

    def test_routes_mid_market_to_low_level_supplement_day(self) -> None:
        service = K92EmotionLiquidityService()

        report = service.build_report(
            trade_date="2026-05-15",
            market_temperature=62,
            candidates=(
                _candidate(
                    "600003",
                    turnover_quality_score=80.0,
                    mainline_score=16.5,
                    position_percentile_60=0.52,
                ),
            ),
        )

        self.assertEqual(report.regime, "low_level_supplement_day")
        self.assertEqual(report.action, "watch_low_level_supplement")
        self.assertEqual(report.supplement_candidates[0].symbol, "600003")

    def test_routes_weak_or_empty_market_to_stand_aside(self) -> None:
        service = K92EmotionLiquidityService()

        report = service.build_report(
            trade_date="2026-05-15",
            market_temperature=42,
            candidates=(
                _candidate(
                    "600004",
                    status="blocked",
                    turnover_quality_score=65.0,
                    blockers=("换手龙质量不足",),
                ),
            ),
        )

        self.assertEqual(report.regime, "ebb_stand_aside_day")
        self.assertEqual(report.action, "stand_aside")
        self.assertEqual(report.status, "blocked")
        self.assertTrue(report.stand_aside_reasons)
        self.assertEqual(report.risk_candidates[0].name, "测试600004")

    def test_overheated_high_position_does_not_confirm_leader_attack(self) -> None:
        service = K92EmotionLiquidityService()

        report = service.build_report(
            trade_date="2026-05-15",
            market_temperature=78,
            candidates=(
                _candidate("600005", position_percentile_60=0.95),
                _candidate("600006", position_percentile_60=0.96),
            ),
        )

        self.assertNotEqual(report.regime, "leader_attack_day")
        self.assertNotEqual(report.action, "watch_leader_attack")
        self.assertEqual(report.regime, "ebb_stand_aside_day")
        self.assertEqual(report.action, "stand_aside")


if __name__ == "__main__":
    unittest.main()
