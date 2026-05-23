"""Intraday execution-quality evidence for the main one-to-two entry."""

from __future__ import annotations

from typing import Protocol

from server.firemoney_server.domain.one_to_two_types import IntradayPriceBar, TickSnapshot
from shared.contracts import OneToTwoExecutionQualityReport


class ExecutionQualityMarketDataProvider(Protocol):
    def load_intraday_bars(
        self,
        symbol: str,
        trade_date: str,
        *,
        interval_minutes: int = 1,
    ) -> tuple[IntradayPriceBar, ...]:
        """Load intraday bars for one symbol and trade date."""

    def load_tick_snapshots(
        self,
        symbol: str,
        trade_date: str,
    ) -> tuple[TickSnapshot, ...]:
        """Load tick snapshots for one symbol and trade date."""


class ExecutionQualityService:
    """Builds read-only intraday execution-quality reports."""

    def __init__(
        self,
        *,
        market_data_provider: ExecutionQualityMarketDataProvider,
    ) -> None:
        self._market_data_provider = market_data_provider

    def build_report(
        self,
        *,
        symbol: str,
        trade_date: str,
    ) -> OneToTwoExecutionQualityReport:
        minute_bars = ()
        tick_snapshots = ()
        intraday_error = ""
        tick_error = ""
        try:
            minute_bars = self._market_data_provider.load_intraday_bars(
                symbol,
                trade_date,
                interval_minutes=1,
            )
        except Exception as exc:
            intraday_error = str(exc)
        try:
            tick_snapshots = self._market_data_provider.load_tick_snapshots(
                symbol,
                trade_date,
            )
        except Exception as exc:
            tick_error = str(exc)
        if not minute_bars and not tick_snapshots:
            return self._blocked_report(
                symbol=symbol,
                trade_date=trade_date,
                intraday_error=intraday_error,
                tick_error=tick_error,
            )

        first_minute_range_pct = 0.0
        first_five_minute_range_pct = 0.0
        if minute_bars:
            first_minute = minute_bars[0]
            if first_minute.open_price > 0:
                first_minute_range_pct = (
                    first_minute.high_price - first_minute.low_price
                ) / first_minute.open_price
            first_five = minute_bars[:5]
            if first_five and first_five[0].open_price > 0:
                five_high = max(item.high_price for item in first_five)
                five_low = min(item.low_price for item in first_five)
                first_five_minute_range_pct = (
                    five_high - five_low
                ) / first_five[0].open_price

        tick_metrics = self._tick_metrics(tick_snapshots)
        summary = (
            f"{symbol} {trade_date} 的主线买点执行质量样例："
            f"{len(minute_bars)} 根分钟线，{len(tick_snapshots)} 条 Tick 快照。"
        )
        return OneToTwoExecutionQualityReport(
            report_id=f"one-to-two-exec-quality-{symbol}-{trade_date}",
            symbol=symbol,
            trade_date=trade_date,
            status="ready",
            summary=summary,
            minute_bar_count=len(minute_bars),
            tick_snapshot_count=len(tick_snapshots),
            first_minute_range_pct=round(first_minute_range_pct, 4),
            first_five_minute_range_pct=round(first_five_minute_range_pct, 4),
            first_tick_bid_ask_spread_pct=round(
                tick_metrics["first_tick_bid_ask_spread_pct"],
                4,
            ),
            max_bid_queue_volume=round(tick_metrics["max_bid_queue_volume"], 2),
            max_ask_queue_volume=round(tick_metrics["max_ask_queue_volume"], 2),
            first_five_minute_buy_amount_pct=round(
                tick_metrics["first_five_minute_buy_amount_pct"],
                4,
            ),
            first_five_minute_sell_amount_pct=round(
                tick_metrics["first_five_minute_sell_amount_pct"],
                4,
            ),
            max_single_tick_amount=round(tick_metrics["max_single_tick_amount"], 2),
            auction_window_amount=round(tick_metrics["auction_window_amount"], 2),
            open_window_amount=round(tick_metrics["open_window_amount"], 2),
            open_window_price_lift_pct=round(
                tick_metrics["open_window_price_lift_pct"],
                4,
            ),
            large_tick_amount_ratio=round(tick_metrics["large_tick_amount_ratio"], 4),
            buy_drive_score=round(tick_metrics["buy_drive_score"], 2),
            queue_imbalance_score=round(tick_metrics["queue_imbalance_score"], 2),
            entry_momentum_score=round(tick_metrics["entry_momentum_score"], 2),
            entry_momentum_signal=str(tick_metrics["entry_momentum_signal"]),
            entry_momentum_reasons=tuple(tick_metrics["entry_momentum_reasons"]),
            limitations=(
                "当前样例/骨架只证明接口和报告结构，不代表真实券商成交质量。",
                "要提高主线买点准确性，下一步必须接入真实分钟线、Tick 和封单排队数据。",
            ),
            next_action="把这个入口接到真实分钟线 / Tick 源，再验证主线买点执行质量。",
        )

    @staticmethod
    def _blocked_report(
        *,
        symbol: str,
        trade_date: str,
        intraday_error: str,
        tick_error: str,
    ) -> OneToTwoExecutionQualityReport:
        return OneToTwoExecutionQualityReport(
            report_id=f"one-to-two-exec-quality-{symbol}-{trade_date}",
            symbol=symbol,
            trade_date=trade_date,
            status="blocked",
            summary="当前没有可用的分钟线或 Tick 证据，无法判断主线买点执行质量。",
            minute_bar_count=0,
            tick_snapshot_count=0,
            first_minute_range_pct=0.0,
            first_five_minute_range_pct=0.0,
            first_tick_bid_ask_spread_pct=0.0,
            max_bid_queue_volume=0.0,
            max_ask_queue_volume=0.0,
            first_five_minute_buy_amount_pct=0.0,
            first_five_minute_sell_amount_pct=0.0,
            max_single_tick_amount=0.0,
            auction_window_amount=0.0,
            open_window_amount=0.0,
            open_window_price_lift_pct=0.0,
            large_tick_amount_ratio=0.0,
            buy_drive_score=0.0,
            queue_imbalance_score=0.0,
            entry_momentum_score=0.0,
            entry_momentum_signal="blocked",
            entry_momentum_reasons=(
                "分钟线 / Tick 不可用，无法判断主线买点是否存在抢筹承接。",
            ),
            limitations=(
                f"分钟线结果：{intraday_error or '无可用数据'}。",
                f"Tick 结果：{tick_error or '无可用数据'}。",
                "分钟线/Tick 真实源不稳定或未接入时，只能返回 blocked。",
            ),
            next_action="先接入分钟线 / Tick / 封单排队数据，再复核主线买点执行质量。",
        )

    @staticmethod
    def _tick_metrics(
        tick_snapshots: tuple[TickSnapshot, ...],
    ) -> dict[str, object]:
        first_tick_bid_ask_spread_pct = 0.0
        max_bid_queue_volume = 0.0
        max_ask_queue_volume = 0.0
        first_five_minute_buy_amount_pct = 0.0
        first_five_minute_sell_amount_pct = 0.0
        max_single_tick_amount = 0.0
        auction_window_amount = 0.0
        open_window_amount = 0.0
        open_window_price_lift_pct = 0.0
        large_tick_amount_ratio = 0.0
        buy_drive_score = 0.0
        queue_imbalance_score = 0.0
        entry_momentum_score = 0.0
        entry_momentum_signal = "watch"
        entry_momentum_reasons: list[str] = []
        if tick_snapshots:
            first_tick = tick_snapshots[0]
            if first_tick.last_price > 0:
                first_tick_bid_ask_spread_pct = (
                    first_tick.ask_price_1 - first_tick.bid_price_1
                ) / first_tick.last_price
            max_bid_queue_volume = max(item.bid_volume_1 for item in tick_snapshots)
            max_ask_queue_volume = max(item.ask_volume_1 for item in tick_snapshots)
            first_five = [
                item for item in tick_snapshots if item.timestamp <= "09:35:00"
            ]
            total_amount = sum(item.amount for item in first_five)
            if total_amount > 0:
                buy_amount = sum(
                    item.amount
                    for item in first_five
                    if "买" in item.side or item.side.lower() == "buy"
                )
                sell_amount = sum(
                    item.amount
                    for item in first_five
                    if "卖" in item.side or item.side.lower() == "sell"
                )
                first_five_minute_buy_amount_pct = buy_amount / total_amount
                first_five_minute_sell_amount_pct = sell_amount / total_amount
            max_single_tick_amount = max(item.amount for item in tick_snapshots)
            auction_window = [
                item
                for item in tick_snapshots
                if "09:25:00" <= item.timestamp < "09:30:00"
            ]
            open_window = [
                item
                for item in tick_snapshots
                if "09:30:00" <= item.timestamp <= "09:35:00"
            ]
            auction_window_amount = sum(item.amount for item in auction_window)
            open_window_amount = sum(item.amount for item in open_window)
            if open_window:
                first_price = open_window[0].last_price
                last_price = open_window[-1].last_price
                if first_price > 0:
                    open_window_price_lift_pct = (last_price - first_price) / first_price
            total_tick_amount = sum(item.amount for item in tick_snapshots)
            if total_tick_amount > 0:
                large_ticks = sum(
                    item.amount for item in tick_snapshots if item.amount >= 1_000_000
                )
                large_tick_amount_ratio = large_ticks / total_tick_amount
            buy_drive_score = (
                first_five_minute_buy_amount_pct * 45
                + max(0.0, open_window_price_lift_pct) * 350
                + min(open_window_amount / 5_000_000, 1.0) * 20
                + large_tick_amount_ratio * 20
            )
            queue_total = max_bid_queue_volume + max_ask_queue_volume
            if queue_total > 0:
                queue_imbalance_score = max(
                    0.0,
                    (max_bid_queue_volume - max_ask_queue_volume) / queue_total,
                ) * 100

            if first_five_minute_buy_amount_pct >= 0.60:
                entry_momentum_reasons.append("前五分钟买盘金额占比偏高")
            if open_window_price_lift_pct >= 0.002:
                entry_momentum_reasons.append("开盘后前五分钟价格被持续推高")
            if large_tick_amount_ratio >= 0.20:
                entry_momentum_reasons.append("大单成交额占比偏高")
            if queue_imbalance_score >= 20:
                entry_momentum_reasons.append("买一排队量明显强于卖一")

            entry_momentum_score = min(
                100.0,
                buy_drive_score * 0.7 + queue_imbalance_score * 0.3,
            )
            if entry_momentum_score >= 60:
                entry_momentum_signal = "candidate"
            elif entry_momentum_score >= 35:
                entry_momentum_signal = "watch"
            else:
                entry_momentum_signal = "weak"
            if not entry_momentum_reasons:
                entry_momentum_reasons.append("当前 Tick 结构更像普通波动，缺少明显抢筹证据")
        return {
            "first_tick_bid_ask_spread_pct": first_tick_bid_ask_spread_pct,
            "max_bid_queue_volume": max_bid_queue_volume,
            "max_ask_queue_volume": max_ask_queue_volume,
            "first_five_minute_buy_amount_pct": first_five_minute_buy_amount_pct,
            "first_five_minute_sell_amount_pct": first_five_minute_sell_amount_pct,
            "max_single_tick_amount": max_single_tick_amount,
            "auction_window_amount": auction_window_amount,
            "open_window_amount": open_window_amount,
            "open_window_price_lift_pct": open_window_price_lift_pct,
            "large_tick_amount_ratio": large_tick_amount_ratio,
            "buy_drive_score": buy_drive_score,
            "queue_imbalance_score": queue_imbalance_score,
            "entry_momentum_score": entry_momentum_score,
            "entry_momentum_signal": entry_momentum_signal,
            "entry_momentum_reasons": tuple(entry_momentum_reasons),
        }


__all__ = ["ExecutionQualityService"]
