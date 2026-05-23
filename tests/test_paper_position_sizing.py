from __future__ import annotations

import unittest
from dataclasses import dataclass

from server.firemoney_server.domain.paper_position_sizing import (
    resolve_paper_position_size,
    simulate_small_account_trades,
)
from shared.contracts import (
    OneToTwoCandidate,
    OneToTwoPositionProfile,
    PaperAccount,
)


@dataclass(frozen=True)
class SizingSettings:
    small_account_mode_enabled: bool = True
    small_account_min_lot_shares: int = 100
    small_account_target_position_pct: float = 0.18
    small_account_reduced_target_position_pct: float = 0.12
    small_account_max_position_pct: float = 0.35
    small_account_reduced_max_position_pct: float = 0.20
    paper_guard_reduced_position_pct: float = 0.12


@dataclass(frozen=True)
class Trade:
    entry_date: str
    symbol: str
    name: str
    entry_price: float
    net_return_pct: float


def _account() -> PaperAccount:
    return PaperAccount(
        account_id="test",
        last_trade_date="",
        cash=10000.0,
        initial_cash=10000.0,
        equity=10000.0,
        max_position_pct=0.35,
        max_daily_trades=1,
        daily_trade_count=0,
        positions=(),
        events=(),
        closed_trades=(),
    )


def _candidate(
    price: float,
    position_limit_pct: float = 0.35,
    warnings: tuple[str, ...] = (),
) -> OneToTwoCandidate:
    return OneToTwoCandidate(
        symbol="600001",
        name="小账户样本",
        trade_date="2026-05-21",
        score=100.0,
        status="ready",
        latest_price=price,
        limit_up_price=price,
        entry_price=price,
        stop_loss=round(price * 0.94, 2),
        position_limit_pct=position_limit_pct,
        first_board_score=20,
        auction_score=20,
        position_score=20,
        theme_score=20,
        liquidity_score=20,
        position_profile=OneToTwoPositionProfile(
            label="低位平台突破",
            low_position_score=20,
            breakout_score=20,
            pressure_score=20,
            moving_average_score=20,
            volume_score=20,
            summary="test",
            risk_notes=(),
        ),
        blockers=(),
        warnings=warnings,
        rationale="test",
        next_action="test",
    )


class PaperPositionSizingTest(unittest.TestCase):
    def test_small_account_buys_at_least_one_lot_when_affordable(self) -> None:
        size = resolve_paper_position_size(
            settings=SizingSettings(),
            account=_account(),
            candidate=_candidate(10.52),
        )

        self.assertEqual(size.quantity, 100)
        self.assertEqual(size.cash_budget, 1052.0)
        self.assertAlmostEqual(size.position_pct, 0.1052)
        self.assertIn("1万小账户一手制", size.note)

    def test_small_account_skips_when_one_lot_exceeds_cap(self) -> None:
        size = resolve_paper_position_size(
            settings=SizingSettings(),
            account=_account(),
            candidate=_candidate(40.0),
        )

        self.assertFalse(size.can_buy)
        self.assertIn("一手成本过高", size.note)

    def test_reduced_guard_uses_lower_hard_cap(self) -> None:
        size = resolve_paper_position_size(
            settings=SizingSettings(),
            account=_account(),
        candidate=_candidate(
            25.0,
            position_limit_pct=0.12,
            warnings=("模拟盘收益守门降仓至 12%。",),
        ),
        )

        self.assertFalse(size.can_buy)
        self.assertIn("超过上限 20%", size.note)

    def test_small_account_backtest_replays_lot_sizing(self) -> None:
        trades, skipped = simulate_small_account_trades(
            trades=[
                Trade("2026-01-02", "600001", "低价样本", 10.0, 0.10),
                Trade("2026-01-03", "600002", "高价样本", 40.0, 0.10),
            ],
            initial_cash=10000.0,
            lot_shares=100,
            target_position_pct=0.18,
            max_position_pct=0.35,
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(trades[0].quantity, 100)
        self.assertAlmostEqual(trades[0].account_return_pct, 0.01)


if __name__ == "__main__":
    unittest.main()
