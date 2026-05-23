from __future__ import annotations

import unittest

from client.desktop.firemoney_client.cli.output import emit_result
from client.desktop.firemoney_client.presenters.brief_formatters import (
    format_doctor_brief,
    format_morning_brief,
    format_scheduler_runs_brief,
    format_watch_brief,
)
from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    OneToTwoCandidate,
    OneToTwoExitPlan,
    OneToTwoDoctorCheck,
    OneToTwoDoctorReport,
    OneToTwoEventType,
    OneToTwoMorningReport,
    OneToTwoPositionProfile,
    OneToTwoScheduleRun,
    OneToTwoScheduleTask,
    PaperAccount,
    PaperPosition,
    PaperTradeEvent,
    PaperTradeStatus,
    TradingDayContext,
)


def _trade_context() -> TradingDayContext:
    return TradingDayContext(
        requested_date="2026-05-08",
        trade_date="2026-05-08",
        previous_trade_date="2026-05-07",
        next_trade_date="2026-05-11",
        is_trading_day=True,
        note="",
    )


def _account() -> PaperAccount:
    return PaperAccount(
        account_id="paper",
        last_trade_date="2026-05-08",
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


def _position() -> PaperPosition:
    return PaperPosition(
        symbol="600001",
        name="北辰科技",
        quantity=100,
        entry_price=10.52,
        latest_price=10.95,
        stop_loss=9.89,
        position_value=1095.0,
        unrealized_pnl=43.0,
        unrealized_pnl_pct=0.0409,
        opened_at="2026-05-08",
        position_label="主板首板",
        opened_score=90.0,
        can_sell_today=False,
        status=PaperTradeStatus.HOLDING,
        risk_note="T+1 未到",
        exit_plan=OneToTwoExitPlan(
            stop_loss=9.89,
            stop_loss_pct=0.0599,
            first_take_profit_price=11.36,
            first_take_profit_pct=0.0798,
            strong_take_profit_price=11.57,
            strong_take_profit_pct=0.1,
            trailing_stop_pct=0.02,
            max_holding_trade_days=2,
            summary="低回撤卖点",
        ),
    )


def _event() -> PaperTradeEvent:
    return PaperTradeEvent(
        event_id="paper_buy-1",
        event_type=OneToTwoEventType.PAPER_BUY,
        symbol="600001",
        name="北辰科技",
        trade_date="2026-05-08",
        price=10.52,
        quantity=100,
        amount=1052.0,
        message="模拟买入已写入",
        created_at="20260508093100",
    )


def _candidate(**overrides) -> OneToTwoCandidate:
    profile = OneToTwoPositionProfile(
        label="主板首板",
        low_position_score=20.0,
        breakout_score=20.0,
        pressure_score=18.0,
        moving_average_score=19.0,
        volume_score=20.0,
        summary="低位平台突破",
        risk_notes=(),
        volume_ratio=1.6,
        rsi_14=64.0,
        position_percentile_60=0.72,
        capital_style_label="机构型营业部",
    )
    values = {
        "symbol": "600001",
        "name": "北辰科技",
        "trade_date": "2026-05-08",
        "score": 90.0,
        "status": "ready",
        "latest_price": 10.52,
        "limit_up_price": 10.52,
        "entry_price": 10.52,
        "stop_loss": 9.89,
        "position_limit_pct": 0.18,
        "first_board_score": 20.0,
        "auction_score": 18.0,
        "position_score": 19.0,
        "theme_score": 18.0,
        "liquidity_score": 15.0,
        "position_profile": profile,
        "blockers": (),
        "warnings": (),
        "rationale": "强结构突破",
        "next_action": "早盘确认",
        "mainline_score": 88.0,
        "discipline_summary": "模拟盘严格 T+1，次日才模拟卖出",
        "turnover_quality_score": 92.0,
        "market_cap": 18_000_000_000.0,
        "exit_plan": OneToTwoExitPlan(
            stop_loss=9.89,
            stop_loss_pct=0.0599,
            first_take_profit_price=11.36,
            first_take_profit_pct=0.0798,
            strong_take_profit_price=11.57,
            strong_take_profit_pct=0.1,
            trailing_stop_pct=0.02,
            max_holding_trade_days=2,
            summary="低回撤卖点",
        ),
    }
    values.update(overrides)
    return OneToTwoCandidate(**values)


def _morning_report() -> OneToTwoMorningReport:
    return OneToTwoMorningReport(
        report_id="morning-2026-05-08",
        trade_date="2026-05-08",
        trade_context=_trade_context(),
        market_temperature=74,
        status="ready",
        summary="主线首板早盘：2 个首板龙头候选样本，1 个进入模拟盘观察。",
        candidates=(
            _candidate(),
            _candidate(symbol="300003", name="讯驰软件", status="blocked"),
        ),
        account=_account(),
        notification=FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title="FireMoney 早评 | 买入观察 | 2026-05-08",
            message=(
                "交易日：2026-05-08\n"
                "今日战法：趋势主升日 / 主线首板\n"
                "消息精华：主线新闻催化继续发酵。\n"
                "资金动向：市场温度 74，首板候选 2，只做主板 10cm。\n"
                "资金画像：北辰科技（600001）机构型营业部。\n"
                "操作解读：只在开盘确认后模拟买入。\n"
                "纪律：模拟盘严格 T+1，次日才模拟卖出。"
            ),
            webhook_configured=True,
        ),
        next_action="等待封板纪律、竞价和一进二确认。",
    )


def _watch_report() -> OneToTwoMorningReport:
    report = _morning_report()
    return OneToTwoMorningReport(
        report_id=report.report_id,
        trade_date=report.trade_date,
        trade_context=report.trade_context,
        market_temperature=report.market_temperature,
        status=report.status,
        summary=report.summary,
        candidates=report.candidates,
        account=PaperAccount(
            account_id="paper",
            last_trade_date="2026-05-08",
            cash=8948.0,
            initial_cash=10000.0,
            equity=10043.0,
            max_position_pct=0.35,
            max_daily_trades=1,
            daily_trade_count=1,
            positions=(_position(),),
            events=(_event(),),
            closed_trades=(),
        ),
        notification=FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title="FireMoney 模拟买入：北辰科技（600001）",
            message="今日动作：买入 北辰科技（600001）\n模拟买入：北辰科技（600001）",
            webhook_configured=True,
        ),
        next_action="继续盯住封板质量、止损位和 T+1 纪律。",
    )


def _doctor_report() -> OneToTwoDoctorReport:
    return OneToTwoDoctorReport(
        report_id="one-to-two-doctor-2026-05-08",
        trade_date="2026-05-08",
        status="ready",
        summary="主线首板运行体检通过，可以按早盘、盘中、尾盘主线运行。",
        checks=(
            OneToTwoDoctorCheck(
                check_id="market_data",
                label="行情源",
                status="ready",
                detail="2026-05-08 已读取 29 条候选原始行。",
                next_action="行情源可用。",
            ),
            OneToTwoDoctorCheck(
                check_id="feishu",
                label="飞书通知",
                status="warning",
                detail="未确认 sent 记录。",
                next_action="先运行 feishu-test。",
            ),
        ),
        next_action="继续按 morning -> watch -> eod -> stability 验证主线首板。",
    )


def _scheduler_runs_result() -> dict[str, object]:
    run = OneToTwoScheduleRun(
        run_id="one-to-two-schedule-2026-05-08-09:31",
        trade_date="2026-05-08",
        trade_context=_trade_context(),
        requested_time="09:31",
        due_count=3,
        executed_count=1,
        skipped_count=2,
        tasks=(
            OneToTwoScheduleTask(
                task_id="morning",
                mode="morning",
                phase=None,
                scheduled_time="08:50",
                status="skipped",
                message="already completed",
                notification_status=NotificationStatus.PREPARED,
            ),
            OneToTwoScheduleTask(
                task_id="watch-open",
                mode="watch",
                phase="open",
                scheduled_time="09:31",
                status="completed",
                message="completed",
                notification_status=NotificationStatus.SENT,
            ),
        ),
        next_action="keep running",
    )
    return {
        "mode": "scheduler-runs",
        "record_count": 1,
        "records": (
            {
                "record_id": "schedule-1",
                "created_at": "20260508093110",
                "trade_date": "2026-05-08",
                "requested_time": "09:31",
                "status": "observed",
                "run": run,
            },
        ),
        "next_action": "Review executed, skipped, expired, and failed tasks before trusting Beta watch coverage.",
    }


class BriefFormatterTest(unittest.TestCase):
    def test_morning_brief_is_human_readable_and_uses_stock_name(self) -> None:
        text = format_morning_brief(_morning_report())

        self.assertIn("FireMoney 早评 | 买入观察 | 2026-05-08", text)
        self.assertIn("早评精要", text)
        self.assertIn("消息精华", text)
        self.assertIn("资金动向", text)
        self.assertIn("北辰科技（600001）", text)
        self.assertIn("讯驰软件（300003）", text)
        self.assertNotIn('"report_id"', text)

    def test_cli_brief_routes_morning_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(_morning_report(), mode="morning", brief=True, printer=output.append)

        self.assertEqual(len(output), 1)
        self.assertIn("早评精要", output[0])
        self.assertIn("北辰科技（600001）", output[0])
        self.assertNotIn('"candidates"', output[0])

    def test_watch_brief_is_human_readable_and_uses_stock_name(self) -> None:
        text = format_watch_brief(_watch_report())

        self.assertIn("FireMoney 盘中值守", text)
        self.assertIn("北辰科技（600001）", text)
        self.assertIn("当前持仓", text)
        self.assertIn("最新事件：paper_buy", text)
        self.assertNotIn('"candidates"', text)

    def test_cli_brief_routes_watch_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(_watch_report(), mode="watch", brief=True, printer=output.append)

        self.assertEqual(len(output), 1)
        self.assertIn("FireMoney 盘中值守", output[0])
        self.assertIn("北辰科技（600001）", output[0])
        self.assertNotIn('"report_id"', output[0])

    def test_doctor_brief_lists_runtime_checks(self) -> None:
        text = format_doctor_brief(_doctor_report())

        self.assertIn("FireMoney 运行体检：ready", text)
        self.assertIn("行情源：ready", text)
        self.assertIn("飞书通知：warning", text)
        self.assertIn("先运行 feishu-test", text)
        self.assertNotIn('"checks"', text)

    def test_cli_brief_routes_doctor_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(_doctor_report(), mode="doctor", brief=True, printer=output.append)

        self.assertEqual(len(output), 1)
        self.assertIn("FireMoney 运行体检", output[0])
        self.assertNotIn('"report_id"', output[0])

    def test_scheduler_runs_brief_shows_task_and_notification_status(self) -> None:
        text = format_scheduler_runs_brief(_scheduler_runs_result())

        self.assertIn("FireMoney 调度审计：1 条", text)
        self.assertIn("09:31 executed 1/3", text)
        self.assertIn("morning 08:50 skipped / 通知 prepared", text)
        self.assertIn("watch/open 09:31 completed / 通知 sent", text)
        self.assertNotIn('"records"', text)

    def test_cli_brief_routes_scheduler_runs_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(_scheduler_runs_result(), mode="scheduler-runs", brief=True, printer=output.append)

        self.assertEqual(len(output), 1)
        self.assertIn("FireMoney 调度审计", output[0])
        self.assertNotIn('"records"', output[0])


if __name__ == "__main__":
    unittest.main()
