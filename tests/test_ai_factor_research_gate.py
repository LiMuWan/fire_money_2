from __future__ import annotations

import unittest

from server.firemoney_server.application.ai_factor_research_gate import (
    AIFactorResearchEvidence,
    AIFactorResearchGate,
    AIFactorYearEvidence,
)


def _evidence(**overrides: object) -> AIFactorResearchEvidence:
    payload = {
        "factor_id": "ai-mainline-risk-words",
        "factor_name": "AI mainline risk words",
        "hypothesis": "AI summarizes mainline risk words before board failure.",
        "source": "ai",
        "deterministic_rule": "risk_word_count <= 1 and theme_consistency_score >= 80",
        "point_in_time_safe": True,
        "total_sample_count": 240,
        "validation_sample_count": 42,
        "validation_return_pct": 0.12,
        "validation_win_rate": 0.64,
        "validation_max_drawdown_pct": -0.012,
        "baseline_validation_return_pct": 0.1117,
        "baseline_max_drawdown_pct": -0.0169,
        "challenger_weak_year_return_pct": 0.12,
        "baseline_weak_year_return_pct": 0.11,
        "average_profit_drawdown_ratio": 1.4,
        "yearly": (
            AIFactorYearEvidence(
                year="2020",
                sample_count=30,
                return_pct=0.08,
                win_rate=0.61,
                max_drawdown_pct=-0.01,
            ),
            AIFactorYearEvidence(
                year="2021",
                sample_count=34,
                return_pct=0.12,
                win_rate=0.59,
                max_drawdown_pct=-0.012,
            ),
        ),
    }
    payload.update(overrides)
    return AIFactorResearchEvidence(**payload)


class AIFactorResearchGateTest(unittest.TestCase):
    def test_rejects_ai_factor_without_pit_and_enough_samples(self) -> None:
        gate = AIFactorResearchGate()

        decision = gate.evaluate(
            _evidence(
                deterministic_rule="",
                point_in_time_safe=False,
                total_sample_count=18,
                validation_sample_count=3,
                validation_win_rate=0.44,
                average_profit_drawdown_ratio=0.4,
                yearly=(
                    AIFactorYearEvidence(
                        year="2021",
                        sample_count=3,
                        return_pct=-0.02,
                        win_rate=0.33,
                        max_drawdown_pct=-0.03,
                    ),
                ),
            )
        )

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(decision.action, "reject_factor")
        self.assertFalse(decision.can_affect_trading)
        self.assertTrue(any("future leakage" in item for item in decision.blockers))
        self.assertTrue(any("Total samples" in item for item in decision.blockers))
        self.assertTrue(any("negative" in item for item in decision.blockers))
        self.assertIn("hypothesis only", decision.warnings[0])

    def test_allows_only_shadow_research_when_evidence_passes(self) -> None:
        gate = AIFactorResearchGate()

        decision = gate.evaluate(_evidence())

        self.assertEqual(decision.status, "shadow_research_only")
        self.assertEqual(decision.action, "allow_shadow_research")
        self.assertFalse(decision.can_affect_trading)
        self.assertEqual(decision.blockers, ())
        self.assertIn("cannot trigger buy/sell", decision.warnings[0])
        self.assertTrue(any("without writing the paper ledger" in item for item in decision.next_steps))


if __name__ == "__main__":
    unittest.main()
