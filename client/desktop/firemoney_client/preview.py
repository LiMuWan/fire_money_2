"""Generate a local preview of the one-to-two FireMoney interface."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from .adapter import LocalMainChainAdapter
from .renderer import render_one_to_two_workflow_html
from server.firemoney_server import MainChainService
from server.firemoney_server.application.one_to_two_scheduler import OneToTwoScheduler
from server.firemoney_server.infrastructure.paper_store import PaperTradeStore
from server.firemoney_server.infrastructure.market_data import SampleMarketDataProvider
from server.firemoney_server.infrastructure.notification_store import NotificationRecordStore
from server.firemoney_server.infrastructure.scheduler_state import SchedulerStateStore
from server.firemoney_server.infrastructure.trading_calendar import WeekdayTradingCalendar
from server.firemoney_server.domain.one_to_two import OneToTwoMarketRow
from shared.contracts import PaperAccount, PaperTradeRecord


PREVIEW_TRADE_DATE = "2026-04-30"
PREVIEW_CREATED_AT = "20260430093100"


class _PreviewRiskBreakMarketDataProvider:
    """Preview-only snapshot that shows the same-day stop-warning state."""

    def __init__(self, base_provider: SampleMarketDataProvider) -> None:
        self._base_provider = base_provider

    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        rows = self._base_provider.load_one_to_two_rows(trade_date)
        if not rows:
            return rows
        warning_row = replace(
            rows[0],
            latest_price=9.8,
            open_pct=0.03,
            ma_5=9.3,
            ma_10=9.2,
            ma_20=9.1,
            recent_gain_pct=0.12,
        )
        return (warning_row, *rows[1:])

    def load_mainline_news(self, theme: str, symbols: tuple[str, ...]):
        return self._base_provider.load_mainline_news(theme, symbols)


def _seed_preview_closed_sample(paper_store: PaperTradeStore) -> None:
    account = paper_store.load()
    paper_store.save(
        PaperAccount(
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
                PaperTradeRecord(
                    trade_id="preview-600018-20260428-20260429",
                    symbol="600018",
                    name="低位换手样本",
                    opened_at="2026-04-28",
                    closed_at="2026-04-29",
                    entry_price=10.0,
                    exit_price=10.38,
                    quantity=700,
                    entry_amount=7000.0,
                    exit_amount=7266.0,
                    realized_pnl=266.0,
                    realized_pnl_pct=0.038,
                    holding_trade_days=1,
                    exit_reason="discipline_take_profit",
                    position_label="低位平台突破",
                    success=True,
                    warning_count=0,
                ),
            ),
        )
    )


def build_preview(output_path: str | Path) -> Path:
    """Write the current one-to-two workflow interface to an HTML file."""

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        preview_root = Path(temp_dir)
        paper_store = PaperTradeStore(preview_root / "paper_trades.json")
        _seed_preview_closed_sample(paper_store)
        notification_store = NotificationRecordStore(
            preview_root / "notifications.json",
            created_at_provider=lambda: PREVIEW_CREATED_AT,
        )
        trading_calendar = WeekdayTradingCalendar()
        sample_provider = SampleMarketDataProvider()
        service = MainChainService(
            paper_store=paper_store,
            market_data_provider=sample_provider,
            notification_store=notification_store,
            trading_calendar=trading_calendar,
        )
        adapter = LocalMainChainAdapter(service)
        one_to_two_report = adapter.build_one_to_two_morning_report(
            trade_date=PREVIEW_TRADE_DATE,
            notify=False,
        )
        adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="scan",
            notify=False,
        )
        adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="auction",
            notify=False,
        )
        adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="open",
            notify=False,
        )
        risk_service = MainChainService(
            paper_store=paper_store,
            market_data_provider=_PreviewRiskBreakMarketDataProvider(sample_provider),
            notification_store=notification_store,
            trading_calendar=trading_calendar,
        )
        risk_adapter = LocalMainChainAdapter(risk_service)
        one_to_two_watch_report = risk_adapter.run_one_to_two_watch(
            trade_date=PREVIEW_TRADE_DATE,
            phase="risk",
            notify=False,
        )
        one_to_two_eod_review = risk_adapter.build_one_to_two_end_of_day_review(
            trade_date=PREVIEW_TRADE_DATE,
            notify=False,
        )
        one_to_two_stability_report = risk_adapter.build_one_to_two_stability_report()
        backtest_audit = risk_adapter.build_one_to_two_backtest_audit(
            end_date=PREVIEW_TRADE_DATE,
            max_trade_days=30,
        )
        doctor_report = risk_adapter.build_one_to_two_doctor_report(
            trade_date=PREVIEW_TRADE_DATE,
        )
        notification_records = adapter.load_notification_records()
        schedule_run = OneToTwoScheduler(
            service=risk_service,
            state_store=SchedulerStateStore(preview_root / "scheduler_state.json"),
        ).run_due(
            trade_date=PREVIEW_TRADE_DATE,
            at_time="15:20",
            notify=False,
        )
        target.write_text(
            render_one_to_two_workflow_html(
                report=one_to_two_report,
                watch_report=one_to_two_watch_report,
                eod_review=one_to_two_eod_review,
                stability_report=one_to_two_stability_report,
                doctor_report=doctor_report,
                schedule_run=schedule_run,
                notification_records=notification_records,
                backtest_audit=backtest_audit,
            ),
            encoding="utf-8",
        )
    return target


if __name__ == "__main__":
    build_preview(Path("client") / "desktop" / "preview" / "core_workflow.html")
