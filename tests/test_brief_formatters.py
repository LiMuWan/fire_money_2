from __future__ import annotations

import unittest

from client.desktop.firemoney_client.cli.output import emit_result
from client.desktop.firemoney_client.presenters.brief_formatters import (
    format_broker_connection_brief,
    format_broker_order_plan_brief,
    format_doctor_brief,
    format_mainline_trend_watch_brief,
    format_morning_brief,
    format_scheduler_runs_brief,
    format_watch_brief,
)
from shared.contracts import (
    BrokerConnectionReport,
    BrokerOrderPlan,
    BrokerPosition,
    FeishuNotificationResult,
    MainlineTrendWatchItem,
    MainlineTrendWatchReport,
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


def _trend_watch_report() -> MainlineTrendWatchReport:
    return MainlineTrendWatchReport(
        report_id="mainline-trend-watch-2026-05-27",
        trade_date="2026-05-27",
        status="watch_only",
        summary="全市场主升根因扫描：输出 1 只观察。",
        items=(
            MainlineTrendWatchItem(
                symbol="603256",
                name="宏和科技",
                board="主板",
                theme="AI服务器PCB上游",
                status="prime_watch",
                action="主升共振观察",
                strategy_type="龙头主升候选",
                strategy_fit="产业逻辑强、成交容量够、趋势还没有过度远离均线。",
                score=82.0,
                latest_price=12.18,
                ma5=11.9,
                ma10=11.6,
                ma20=10.9,
                high_60=12.5,
                low_20=10.8,
                recent_gain_pct=0.18,
                distance_to_ma10_pct=0.05,
                distance_to_high_60_pct=-0.03,
                volume_ratio_5=1.4,
                position_percentile_120=0.62,
                distance_to_ma20_pct=0.12,
                base_tightness_pct=0.18,
                turnover_amount=680_000_000,
                logic_score=88,
                value_score=72,
                capital_attraction_score=76,
                sustainability_score=80,
                timing_score=74,
                pullback_entry_low=11.2,
                pullback_entry_high=11.9,
                breakout_price=12.63,
                stop_loss=10.55,
                logic="AI服务器PCB升级带来电子布需求弹性。",
                value_case="价值：ROE 8.4%，净利增速 42.0%。",
                capital_case="资金：成交额 6.8亿，换手 7.8%。",
                sustainability_case="持续：趋势多头，业绩接力。",
                industry_chain_case="AI服务器产业链：AI服务器 -> 高速PCB -> 电子布。",
                profit_driver_case="经济利益来自净利增长带来的利润弹性。",
                pre_breakout_case="启动前箱体收敛，等放量突破确认。",
                t_plan="有底仓才做T，靠近10日线承接，冲高降仓。",
                risk_control_case="回撤控制线 10.55，跌破移出观察。",
                why_watch_case="产业逻辑、资金容量和结构位置同时出现。",
                main_wave_stage="主升确认前段，适合找回踩确认。",
                confirmation_case="等缩量回踩不破后再转强。",
                holding_plan="站稳10日线且20日线上行时保留核心仓。",
                failure_signal="跌破平台或板块不再扩散。",
                position_plan="确认后再加到计划仓。",
                entry_plan="等 11.20-11.90 缩量回踩后再转强。",
                reasons=("主线逻辑清楚",),
                risks=("缺财务快照时需复核",),
                next_action="列入主升观察池。",
            ),
        ),
        rules=("全市场扫描只输出观察，不写入模拟盘。",),
        limitations=("财务快照依赖行情源。",),
        next_action="先看主升根因，再看买点。",
    )


def _trend_watch_timeout_report() -> MainlineTrendWatchReport:
    return MainlineTrendWatchReport(
        report_id="mainline-trend-watch-2026-05-27",
        trade_date="2026-05-27",
        status="timeout",
        summary=(
            "全市场主升根因扫描（timeout）：全市场行情源 8 秒内未返回；"
            "本次不输出主升候选，也不把缓存候选伪装成实时全市场扫描。"
        ),
        items=(),
        rules=("全市场扫描只输出观察，不写入模拟盘。",),
        limitations=(
            "本次未完成全市场行情扫描；宁可显示不可用，也不生成看起来很真的假结论。",
        ),
        next_action="等待下一轮刷新。",
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

    def test_mainline_trend_watch_brief_explains_root(self) -> None:
        text = format_mainline_trend_watch_brief(_trend_watch_report())

        self.assertIn("FireMoney 全市场主升根因扫描：watch_only", text)
        self.assertIn("宏和科技（603256）", text)
        self.assertIn("逻辑/价值/资金/持续/买点", text)
        self.assertIn("战法：龙头主升候选", text)
        self.assertIn("AI服务器PCB升级", text)
        self.assertIn("持续：", text)
        self.assertIn("看重原因：产业逻辑", text)
        self.assertIn("主升阶段：主升确认前段", text)
        self.assertIn("产业链：AI服务器产业链", text)
        self.assertIn("利益驱动：经济利益来自", text)
        self.assertIn("确认：等缩量回踩", text)
        self.assertIn("持有：站稳10日线", text)
        self.assertIn("失效：跌破平台", text)
        self.assertIn("仓位：确认后再加", text)
        self.assertIn("做T：", text)
        self.assertIn("风控：回撤控制线", text)
        self.assertIn("等 11.20-11.90", text)
        self.assertNotIn('"items"', text)

    def test_mainline_trend_watch_brief_is_honest_on_timeout(self) -> None:
        text = format_mainline_trend_watch_brief(_trend_watch_timeout_report())

        self.assertIn("timeout", text)
        self.assertIn("候选：无", text)
        self.assertIn("不把缓存候选伪装成实时全市场扫描", text)
        self.assertIn("宁可显示不可用", text)

    def test_cli_brief_routes_mainline_trend_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(_trend_watch_report(), mode="mainline-trend", brief=True, printer=output.append)

        self.assertEqual(len(output), 1)
        self.assertIn("全市场主升根因扫描", output[0])
        self.assertIn("宏和科技（603256）", output[0])
        self.assertNotIn('"report_id"', output[0])

    def test_qmt_connection_brief_is_human_readable(self) -> None:
        text = format_broker_connection_brief(
            BrokerConnectionReport(
                broker="qmt",
                status="ready",
                account_id="12345678",
                cash=10000.0,
                available_cash=9000.0,
                total_asset=12000.0,
                market_value=2000.0,
                positions=(
                    BrokerPosition(
                        symbol="600001.SH",
                        name="北辰科技",
                        quantity=100,
                        available_quantity=0,
                        market_value=1052.0,
                        cost_price=10.52,
                        latest_price=10.52,
                    ),
                ),
                message="QMT 已连接。",
                next_action="先跑 qmt-plan。",
            )
        )

        self.assertIn("FireMoney QMT 连接检查：ready", text)
        self.assertIn("账号：12345678", text)
        self.assertIn("北辰科技（600001.SH）", text)
        self.assertNotIn('"positions"', text)

    def test_cli_brief_routes_qmt_plan_to_formatter(self) -> None:
        output: list[str] = []

        emit_result(
            BrokerOrderPlan(
                broker="qmt",
                status="ready",
                dry_run=True,
                trade_date="2026-05-26",
                action="buy",
                symbol="600001.SH",
                name="北辰科技",
                side="buy",
                quantity=100,
                price=10.52,
                price_type="FIX_PRICE",
                account_id="12345678",
                summary="QMT dry-run 拟委托。",
                warnings=("严格 T+1",),
                next_action="核对后再提交。",
            ),
            mode="qmt-plan",
            brief=True,
            printer=output.append,
        )

        self.assertEqual(len(output), 1)
        self.assertIn("FireMoney QMT 拟委托：ready", output[0])
        self.assertIn("北辰科技（600001.SH）", output[0])
        self.assertIn("严格 T+1", output[0])
        self.assertNotIn('"summary"', output[0])


if __name__ == "__main__":
    unittest.main()
