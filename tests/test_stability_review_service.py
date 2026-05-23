from __future__ import annotations

import unittest
from dataclasses import dataclass

from server.firemoney_server.application.stability_review_service import (
    StabilityReviewService,
)
from shared.contracts import (
    PaperAccount,
    PaperTradeRecord,
)


@dataclass(frozen=True)
class Settings:
    minimum_sample_for_stability: int = 30


def _account(records: tuple[PaperTradeRecord, ...]) -> PaperAccount:
    return PaperAccount(
        account_id="paper",
        last_trade_date="2026-05-08",
        cash=100000.0,
        initial_cash=100000.0,
        equity=100000.0,
        max_position_pct=0.08,
        max_daily_trades=1,
        daily_trade_count=0,
        positions=(),
        events=(),
        closed_trades=records,
    )


def _record(index: int, realized_pnl_pct: float = 0.02) -> PaperTradeRecord:
    entry_price = 10.0
    quantity = 100
    entry_amount = entry_price * quantity
    exit_price = round(entry_price * (1 + realized_pnl_pct), 2)
    exit_amount = exit_price * quantity
    return PaperTradeRecord(
        trade_id=f"sample-{index}",
        symbol=f"600{index % 1000:03d}",
        name=f"样本{index}",
        opened_at="2026-05-06",
        closed_at="2026-05-08",
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_amount=entry_amount,
        exit_amount=exit_amount,
        realized_pnl=round(exit_amount - entry_amount, 2),
        realized_pnl_pct=realized_pnl_pct,
        holding_trade_days=2,
        exit_reason="take_profit" if realized_pnl_pct > 0 else "stop_loss_t1",
        position_label="低位平台突破",
        success=realized_pnl_pct > 0,
        warning_count=0 if realized_pnl_pct > 0 else 1,
        max_favorable_pct=max(0.0, realized_pnl_pct + 0.01),
        max_adverse_pct=0.01 if realized_pnl_pct < 0 else 0.004,
        profit_drawdown_ratio=5.0 if realized_pnl_pct > 0 else 0.0,
    )


class StabilityReviewServiceTest(unittest.TestCase):
    def test_build_report_summarizes_closed_trade_quality(self) -> None:
        service = StabilityReviewService(Settings())
        loss = _record(1, -0.04)

        report = service.build_report(_account((loss,)))

        self.assertEqual(report.sample_count, 1)
        self.assertEqual(report.sample_stage, "观察期")
        self.assertEqual(report.next_milestone, 30)
        self.assertEqual(report.status, "observation")
        self.assertEqual(report.stop_warning_rate, 1.0)
        self.assertLess(report.average_return_pct, 0)
        self.assertEqual(report.position_label_distribution["低位平台突破"], 1)
        self.assertEqual(report.exit_reason_distribution["stop_loss_t1"], 1)
        self.assertEqual(report.recent_samples[0].symbol, "600001")
        self.assertIn("少于 30", report.strategy_boundary_suggestion)

    def test_build_report_adds_stage_guidance_and_recent_sample_cap(self) -> None:
        service = StabilityReviewService(Settings())

        stage_30 = service.build_report(
            _account(tuple(_record(index) for index in range(30)))
        )
        self.assertEqual(stage_30.status, "reviewable")
        self.assertEqual(stage_30.sample_stage, "30 笔初评")
        self.assertEqual(stage_30.next_milestone, 50)
        self.assertEqual(len(stage_30.recent_samples), 5)
        self.assertIn("低位平台突破", stage_30.strategy_boundary_suggestion)

        stage_50 = service.build_report(
            _account(tuple(_record(index) for index in range(50)))
        )
        self.assertEqual(stage_50.sample_stage, "50 笔复评")
        self.assertEqual(stage_50.next_milestone, 100)

        stage_100 = service.build_report(
            _account(tuple(_record(index) for index in range(100)))
        )
        self.assertEqual(stage_100.sample_stage, "100 笔定边界")
        self.assertEqual(stage_100.next_milestone, 0)
        self.assertIn("100 笔以上复盘", stage_100.next_action)

    def test_build_report_recommends_tightening_when_quality_is_weak(self) -> None:
        service = StabilityReviewService(Settings())
        weak_records = tuple(_record(index, -0.01) for index in range(30))

        report = service.build_report(_account(weak_records))

        self.assertIn("先收紧入池条件", report.strategy_boundary_suggestion)


if __name__ == "__main__":
    unittest.main()
