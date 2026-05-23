from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server.firemoney_server.application.strategy_decision_service import (
    StrategyDecisionService,
)


class StrategyDecisionServiceTest(unittest.TestCase):
    def test_build_report_uses_snapshot_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "strategy_decision_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "main_line": {
                            "strategy_id": "board-shadow-system",
                            "status": "ready",
                            "summary_return_pct": 0.5,
                            "validation_return_pct": 0.12,
                            "summary_drawdown_pct": -0.02,
                            "validation_drawdown_pct": -0.01,
                            "evidence_end_date": "2026-05-05",
                        },
                        "side_line": {
                            "strategy_id": "legacy-research-line",
                            "status": "watch_only",
                        },
                    }
                ),
                encoding="utf-8",
            )
            service = StrategyDecisionService(
                snapshot_path=snapshot_path,
                default_trade_date=lambda: "2026-05-10",
            )

            report = service.build_report(trade_date="2026-05-08")

            self.assertEqual(report.trade_date, "2026-05-08")
            self.assertEqual(report.evidence_end_date, "2026-05-05")
            self.assertEqual(report.selected_strategy_id, "cash")
            self.assertEqual(report.selected_action, "stand_aside")
            self.assertEqual(report.market_regime, "defense_stand_aside_day")
            self.assertEqual({option.strategy_id for option in report.options}, {"board-shadow-system", "cash"})
            self.assertNotIn("legacy-research-line", {option.strategy_id for option in report.options})
            self.assertIn("50.00%", report.options[0].expected_return_label)
            self.assertIn("2024-01-01", report.risk_rules[-1])

    def test_build_report_falls_back_to_cash_when_main_line_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "strategy_decision_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "main_line": {
                            "strategy_id": "board-shadow-system",
                            "status": "blocked",
                        },
                        "side_line": {},
                    }
                ),
                encoding="utf-8",
            )
            service = StrategyDecisionService(
                snapshot_path=snapshot_path,
                default_trade_date=lambda: "2026-05-10",
            )

            report = service.build_report(trade_date="2026-05-08")

            self.assertEqual(report.status, "blocked")
            self.assertEqual(report.selected_strategy_id, "cash")
            self.assertEqual(report.selected_action, "stand_aside")
            self.assertEqual(report.market_regime, "defense_stand_aside_day")

    def test_missing_snapshot_uses_default_operating_line(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report()

        self.assertEqual(report.trade_date, "2026-05-10")
        self.assertEqual(report.selected_strategy_id, "cash")
        self.assertTrue(any(option.strategy_id == "cash" for option in report.options))
        self.assertEqual(report.market_regime, "defense_stand_aside_day")

    def test_build_report_routes_to_trend_main_rise_day(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report(
            trade_date="2026-05-08",
            market_temperature=78,
            ready_candidate_count=4,
            average_mainline_score=19.0,
            average_turnover_quality_score=85.0,
        )

        self.assertEqual(report.market_regime, "trend_main_rise_day")
        self.assertEqual(report.selected_strategy_id, "board-shadow-system")
        self.assertEqual(report.regime_action, "attack_trend_main_rise")
        self.assertEqual(report.k92_gate, "not_available")

    def test_build_report_keeps_mainline_when_k92_confirms_leader_attack(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report(
            trade_date="2026-05-08",
            market_temperature=78,
            ready_candidate_count=4,
            average_mainline_score=19.0,
            average_turnover_quality_score=85.0,
            k92_regime="leader_attack_day",
            k92_action="watch_leader_attack",
            k92_summary="K92 龙头进攻日，主线获得确认。",
        )

        self.assertEqual(report.k92_gate, "confirm")
        self.assertEqual(report.selected_strategy_id, "board-shadow-system")
        self.assertIn("K92 龙头进攻日", report.k92_rationale)

    def test_build_report_blocks_mainline_when_k92_stands_aside(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report(
            trade_date="2026-05-08",
            market_temperature=78,
            ready_candidate_count=4,
            average_mainline_score=19.0,
            average_turnover_quality_score=85.0,
            k92_regime="ebb_stand_aside_day",
            k92_action="stand_aside",
            k92_summary="K92 退潮空仓日，风险候选多于可交易候选。",
        )

        self.assertEqual(report.market_regime, "trend_main_rise_day")
        self.assertEqual(report.k92_gate, "block")
        self.assertEqual(report.selected_strategy_id, "cash")
        self.assertEqual(report.selected_action, "stand_aside")

    def test_build_report_routes_to_cash_when_mainline_is_not_strong(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report(
            trade_date="2026-05-08",
            market_temperature=58,
            ready_candidate_count=1,
            average_mainline_score=16.0,
            average_turnover_quality_score=74.0,
        )

        self.assertEqual(report.market_regime, "defense_stand_aside_day")
        self.assertEqual(report.selected_strategy_id, "cash")
        self.assertEqual(report.selected_action, "stand_aside")
        self.assertEqual(report.regime_action, "defense_stand_aside")

    def test_build_report_marks_market_data_unavailable_separately(self) -> None:
        service = StrategyDecisionService(
            snapshot_path=Path("missing-strategy-snapshot.json"),
            default_trade_date=lambda: "2026-05-10",
        )

        report = service.build_report(
            trade_date="2026-05-08",
            data_unavailable=True,
        )

        self.assertEqual(report.status, "data_unavailable")
        self.assertEqual(report.market_regime, "market_data_unavailable_day")
        self.assertEqual(report.regime_action, "pause_until_market_data_ready")
        self.assertEqual(report.selected_strategy_id, "cash")
        self.assertIn("行情源", report.regime_rationale)


if __name__ == "__main__":
    unittest.main()
