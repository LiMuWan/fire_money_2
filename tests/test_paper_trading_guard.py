from __future__ import annotations

import unittest

from server.firemoney_server.application.paper_trading_guard import (
    PaperTradingGuard,
    PaperTradingGuardSettings,
)
from shared.contracts import PaperAccount, PaperTradeRecord


def _settings() -> PaperTradingGuardSettings:
    return PaperTradingGuardSettings(
        review_sample=5,
        min_win_rate=0.6,
        min_average_return_pct=0.005,
        max_consecutive_losses=2,
        max_consecutive_quality_failures=2,
        max_drawdown_pct=0.03,
        max_position_pct=0.35,
        reduced_position_pct=0.12,
        min_profit_drawdown_ratio=1.0,
        min_quality_bucket_samples=3,
        quality_bucket_block_losses=2,
    )


def _empty_account() -> PaperAccount:
    return PaperAccount(
        account_id="paper",
        last_trade_date="2026-04-30",
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


def _trade(
    index: int,
    realized_pnl_pct: float = 0.02,
    quality_score: float = 92.0,
) -> PaperTradeRecord:
    entry_price = 10.0
    exit_price = entry_price * (1 + realized_pnl_pct)
    return PaperTradeRecord(
        trade_id=f"closed-{index}",
        symbol=f"600{index:03d}",
        name=f"样本{index}",
        opened_at="2026-04-30",
        closed_at="2026-05-06",
        entry_price=entry_price,
        exit_price=round(exit_price, 2),
        quantity=100,
        entry_amount=entry_price * 100,
        exit_amount=round(exit_price * 100, 2),
        realized_pnl=round((exit_price - entry_price) * 100, 2),
        realized_pnl_pct=realized_pnl_pct,
        holding_trade_days=1,
        exit_reason="take_profit",
        position_label="主线首板",
        success=realized_pnl_pct > 0,
        warning_count=0,
        max_favorable_pct=realized_pnl_pct + 0.01,
        max_adverse_pct=0.004,
        profit_drawdown_ratio=round(realized_pnl_pct / 0.004, 4),
        entry_turnover_quality_score=quality_score,
    )


def _account_with_closed_trades(count: int) -> PaperAccount:
    account = _empty_account()
    return PaperAccount(
        account_id=account.account_id,
        last_trade_date=account.last_trade_date,
        cash=account.cash,
        initial_cash=account.initial_cash,
        equity=account.equity,
        max_position_pct=account.max_position_pct,
        max_daily_trades=account.max_daily_trades,
        daily_trade_count=account.daily_trade_count,
        positions=account.positions,
        events=account.events,
        closed_trades=tuple(_trade(index) for index in range(1, count + 1)),
    )


class PaperTradingGuardTest(unittest.TestCase):
    def test_warmup_uses_reduced_position_until_real_closed_samples_exist(self) -> None:
        guard = PaperTradingGuard(_settings())

        result = guard.evaluate(_empty_account(), candidate_turnover_quality_score=92)

        self.assertEqual(result.status, "warmup")
        self.assertEqual(result.action, "allow_reduced")
        self.assertEqual(result.suggested_position_pct, 0.12)
        self.assertTrue(any("暂无真实闭环样本" in item for item in result.reasons))

    def test_less_than_review_sample_still_uses_reduced_position(self) -> None:
        guard = PaperTradingGuard(_settings())

        result = guard.evaluate(
            _account_with_closed_trades(3),
            candidate_turnover_quality_score=92,
        )

        self.assertEqual(result.status, "reduced")
        self.assertEqual(result.action, "allow_reduced")
        self.assertEqual(result.review_sample_count, 3)
        self.assertEqual(result.suggested_position_pct, 0.12)
        self.assertTrue(any("尚未达到复盘门槛" in item for item in result.reasons))

    def test_full_size_requires_enough_passing_closed_samples(self) -> None:
        guard = PaperTradingGuard(_settings())

        result = guard.evaluate(
            _account_with_closed_trades(5),
            candidate_turnover_quality_score=92,
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.action, "allow_full")
        self.assertEqual(result.review_sample_count, 5)
        self.assertEqual(result.suggested_position_pct, 0.35)

    def test_candidate_quality_bucket_needs_own_samples_before_full_size(self) -> None:
        guard = PaperTradingGuard(_settings())
        account = _empty_account()
        mixed_bucket_account = PaperAccount(
            account_id=account.account_id,
            last_trade_date=account.last_trade_date,
            cash=account.cash,
            initial_cash=account.initial_cash,
            equity=account.equity,
            max_position_pct=account.max_position_pct,
            max_daily_trades=account.max_daily_trades,
            daily_trade_count=account.daily_trade_count,
            positions=account.positions,
            events=account.events,
            closed_trades=(
                _trade(1, 0.02, quality_score=92.0),
                _trade(2, 0.021, quality_score=92.0),
                _trade(3, 0.022, quality_score=74.0),
                _trade(4, 0.023, quality_score=74.0),
                _trade(5, 0.024, quality_score=74.0),
            ),
        )

        result = guard.evaluate(
            mixed_bucket_account,
            candidate_turnover_quality_score=92,
        )

        self.assertEqual(result.status, "reduced")
        self.assertEqual(result.action, "allow_reduced")
        self.assertEqual(result.candidate_quality_bucket, "strong_turnover_dragon")
        self.assertEqual(result.candidate_quality_sample_count, 2)
        self.assertEqual(result.suggested_position_pct, 0.12)
        self.assertTrue(any("少于复核门槛" in item for item in result.reasons))


if __name__ == "__main__":
    unittest.main()
