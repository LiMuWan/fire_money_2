from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path

from server.firemoney_server.application.one_to_two_notification_text import (
    board_shadow_notification_message,
    one_to_two_end_of_day_notification_message,
    one_to_two_morning_notification_message,
    one_to_two_watch_notification_title,
    one_to_two_watch_notification_message,
)


@dataclass(frozen=True)
class PositionProfile:
    label: str = "低位突破"


@dataclass(frozen=True)
class ExitPlan:
    summary: str = "T+1 后按主升保护线处理"


@dataclass(frozen=True)
class NewsItem:
    title: str = "主线消息继续发酵"


@dataclass(frozen=True)
class MainlineContinuity:
    theme: str = "AI 主线"
    score: float = 82.0
    status: str = "strong"
    news_count: int = 3
    next_action: str = "继续观察承接"
    latest_news: tuple[NewsItem, ...] = (NewsItem(),)


@dataclass(frozen=True)
class BreakoutStructure:
    summary: str = "强结构突破 82/100，突破线 10.20，距突破线 3.1%，量比 1.60"


@dataclass(frozen=True)
class Candidate:
    symbol: str = "600001"
    name: str = "样本股份"
    score: float = 96.0
    status: str = "ready"
    entry_price: float = 10.52
    stop_loss: float = 10.1
    position_limit_pct: float = 0.08
    position_profile: PositionProfile = PositionProfile()
    blockers: tuple[str, ...] = ()
    sealing_score: float = 20.0
    mainline_score: float = 20.0
    leader_score: float = 19.0
    leader_label: str = "主线龙头"
    exit_plan: ExitPlan | None = ExitPlan()
    mainline_continuity: MainlineContinuity | None = MainlineContinuity()
    turnover_quality_score: float = 92.0
    turnover_quality_notes: tuple[str, ...] = ("换手充分且承接强",)
    breakout_structure: BreakoutStructure | None = BreakoutStructure()


@dataclass(frozen=True)
class Event:
    event_type: str


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str = "600001"
    name: str = "样本股份"
    opened_at: str = "2026-05-08"
    closed_at: str = "2026-05-09"
    entry_price: float = 10.52
    exit_price: float = 11.2
    quantity: int = 300
    entry_amount: float = 3156.0
    exit_amount: float = 3360.0
    exit_reason: str = "main_rise_runner_trailing_lock"
    holding_trade_days: int = 2
    realized_pnl: float = 204.0
    realized_pnl_pct: float = 0.0646
    max_favorable_pct: float = 0.08
    max_adverse_pct: float = -0.01
    profit_drawdown_ratio: float = 6.4
    position_label: str = "低位突破"
    warning_count: int = 0


@dataclass(frozen=True)
class Position:
    symbol: str = "600001"
    name: str = "样本股份"
    quantity: int = 300
    entry_price: float = 10.52
    latest_price: float = 10.95
    stop_loss: float = 10.1
    position_value: float = 3156.0
    unrealized_pnl: float = 129.0
    unrealized_pnl_pct: float = 0.0409
    can_sell_today: bool = True
    position_label: str = "低位突破"
    exit_plan: ExitPlan | None = ExitPlan()
    mainline_continuity: MainlineContinuity | None = MainlineContinuity()


@dataclass(frozen=True)
class Account:
    equity: float = 10000.0
    cash: float = 10000.0
    initial_cash: float = 10000.0
    daily_trade_count: int = 0
    max_daily_trades: int = 1
    positions: tuple[Position, ...] = ()
    events: tuple[Event, ...] = ()
    closed_trades: tuple[ClosedTrade, ...] = ()


@dataclass(frozen=True)
class RecentSample:
    symbol: str = "600001"
    name: str = "样本股份"
    realized_pnl_pct: float = 0.0646
    exit_reason: str = "main_rise_runner_trailing_lock"
    position_label: str = "低位突破"


@dataclass(frozen=True)
class StabilityReport:
    sample_stage: str = "observation"
    next_milestone: int = 30
    strategy_boundary_suggestion: str = "继续积累样本"
    recent_samples: tuple[RecentSample, ...] = (RecentSample(),)


@dataclass(frozen=True)
class BoardShadowCandidate:
    symbol: str = "600001"
    name: str = "样本股份"
    rank_score: float = 91.5
    entry_price: float = 10.52
    stop_loss: float = 10.1
    take_profit_price: float = 11.78
    estimated_turnover_amount: float = 123456789.0
    volume_ratio_20: float = 2.3
    recent_gain_pct: float = 0.12
    market_seal_count: int = 40
    market_touch_count: int = 58
    market_advance_ratio: float = 0.61


@dataclass(frozen=True)
class BoardShadowTrade:
    exit_date: str = "2026-05-12"
    exit_reason: str = "first_take_profit"
    realized_pnl_pct: float = 0.12


@dataclass(frozen=True)
class QualityCheck:
    label: str = "PIT"
    status: str = "pass"
    detail: str = "未使用未来数据"


@dataclass(frozen=True)
class BoardShadowReport:
    as_of_date: str = "2026-05-09"
    status: str = "recorded"
    summary: str = "封板影子样本已闭环"
    candidate: BoardShadowCandidate | None = BoardShadowCandidate()
    trade: BoardShadowTrade | None = BoardShadowTrade()
    quality_checks: tuple[QualityCheck, ...] = (QualityCheck(),)
    limitations: tuple[str, ...] = ("缺少分钟级封单数据",)


@dataclass(frozen=True)
class BoardShadowStabilityReport:
    sample_count: int = 12
    sample_stage: str = "observation"
    next_milestone: int = 30
    success_rate: float = 0.58
    average_return_pct: float = 0.021
    max_drawdown: float = -0.03


class OneToTwoNotificationTextTest(unittest.TestCase):
    def test_morning_message_formats_candidates_and_blockers(self) -> None:
        blocked = Candidate(status="blocked", blockers=("高开超限",))
        message = one_to_two_morning_notification_message(
            report_date="2026-05-09",
            market_temperature=76,
            data_unavailable=False,
            candidates=(Candidate(), blocked),
            account=Account(),
        )

        self.assertIn("今日动作：买入观察", message)
        self.assertIn("候选池：主线首板 2", message)
        self.assertIn("买入候选：样本股份（600001）", message)
        self.assertIn("买点证据：封板", message)
        self.assertIn("主要拦截：", message)
        self.assertIn("纪律：只做主板 10cm", message)
        self.assertIn("下一步：09:31", message)

    def test_morning_data_unavailable_is_not_labeled_defense_day(self) -> None:
        message = one_to_two_morning_notification_message(
            report_date="2026-05-22",
            market_temperature=0,
            data_unavailable=True,
            candidates=(),
            account=Account(),
            regime_label="行情异常暂停",
        )

        self.assertIn("今日动作：暂停，行情不可用", message)
        self.assertIn("今日战法：行情异常暂停", message)
        self.assertIn("行情异常暂停不是防守空仓日", message)
        self.assertIn("这不是策略防守信号", message)
        self.assertIn("doctor --market-data-timeout-seconds 20", message)
        self.assertNotIn("今日战法：防守空仓日", message)

    def test_watch_message_formats_real_sell_event(self) -> None:
        message = one_to_two_watch_notification_message(
            phase="risk",
            trade_date="2026-05-09",
            ready=(),
            account=Account(
                events=(Event("take_profit"),),
                closed_trades=(ClosedTrade(),),
            ),
            latest_event="模拟卖出已写入",
            sell_event_types={"take_profit"},
            stop_warning_event_type="stop_warning",
        )

        self.assertIn("模拟卖出：样本股份（600001）", message)
        self.assertIn("退出原因：主升回撤保护止盈", message)
        self.assertNotIn("main_rise_runner_trailing_lock", message)
        self.assertIn("本笔结算：买入 10.52，卖出 11.20", message)
        self.assertIn("买入金额 3156.00，卖出金额 3360.00", message)
        self.assertIn("本月收益：2026-05 已闭环 1 笔", message)
        self.assertIn("本年收益：2026 已闭环 1 笔", message)
        self.assertIn("累计收益：已闭环 1 笔", message)
        self.assertIn("收益质量：顺风 8.00%", message)
        self.assertIn("提醒：模拟盘不是实盘", message)

    def test_watch_sell_message_summarizes_period_returns(self) -> None:
        message = one_to_two_watch_notification_message(
            phase="risk",
            trade_date="2026-05-27",
            ready=(),
            account=Account(
                events=(Event("take_profit"),),
                closed_trades=(
                    ClosedTrade(
                        symbol="000509",
                        name="华塑控股",
                        opened_at="2026-05-26",
                        closed_at="2026-05-27",
                        entry_price=4.70,
                        exit_price=4.74,
                        quantity=200,
                        entry_amount=940.0,
                        exit_amount=948.0,
                        realized_pnl=8.0,
                        realized_pnl_pct=0.0085,
                    ),
                    ClosedTrade(
                        closed_at="2026-05-12",
                        realized_pnl=204.0,
                        realized_pnl_pct=0.0646,
                    ),
                    ClosedTrade(
                        closed_at="2026-04-30",
                        realized_pnl=-40.0,
                        realized_pnl_pct=-0.012,
                    ),
                ),
            ),
            latest_event="模拟卖出已写入",
            sell_event_types={"take_profit"},
            stop_warning_event_type="stop_warning",
        )

        self.assertIn("实现盈亏：8.00 (0.85%)", message)
        self.assertIn("本笔结算：买入 4.70，卖出 4.74", message)
        self.assertIn("本月收益：2026-05 已闭环 2 笔，已实现 212.00 (2.12%)", message)
        self.assertIn("本年收益：2026 已闭环 3 笔，已实现 172.00 (1.72%)", message)
        self.assertIn("累计收益：已闭环 3 笔，已实现 172.00 (1.72%)", message)

    def test_watch_risk_holding_does_not_repeat_buy_message(self) -> None:
        message = one_to_two_watch_notification_message(
            phase="risk",
            trade_date="2026-05-09",
            ready=(),
            account=Account(
                positions=(Position(),),
                events=(Event("paper_buy"),),
            ),
            latest_event="模拟买入已写入",
            sell_event_types={"take_profit"},
            stop_warning_event_type="stop_warning",
        )

        self.assertIn("今日动作：持仓风控 样本股份（600001）", message)
        self.assertIn("持仓复核：样本股份（600001）", message)
        self.assertNotIn("今日动作：买入", message)
        self.assertNotIn("模拟买入：", message)

    def test_watch_title_formats_buy_and_sell_cards(self) -> None:
        buy_title = one_to_two_watch_notification_title(
            phase="open",
            trade_date="2026-05-09",
            latest_event_trade_date="2026-05-09",
            is_buy_event=True,
            is_sell_event=False,
            latest_event_name="样本股份",
            latest_event_symbol="600001",
        )
        sell_title = one_to_two_watch_notification_title(
            phase="risk",
            trade_date="2026-05-09",
            latest_event_trade_date="2026-05-09",
            is_buy_event=False,
            is_sell_event=True,
            latest_event_name="样本股份",
            latest_event_symbol="600001",
        )
        default_title = one_to_two_watch_notification_title(
            phase="risk",
            trade_date="2026-05-09",
            latest_event_trade_date="2026-05-08",
            is_buy_event=False,
            is_sell_event=True,
            latest_event_name="样本股份",
            latest_event_symbol="600001",
        )

        self.assertEqual(buy_title, "FireMoney 模拟买入：样本股份（600001）")
        self.assertEqual(sell_title, "FireMoney 模拟卖出：样本股份（600001）")
        self.assertEqual(default_title, "FireMoney 主线首板盘中")

    def test_end_of_day_message_formats_review_summary(self) -> None:
        message = one_to_two_end_of_day_notification_message(
            report_date="2026-05-09",
            account=Account(positions=(Position(),)),
            warning_count=1,
            t1_sell_count=0,
            realized_pnl=204.0,
            stability_report=StabilityReport(),
            board_shadow_hint="封板影子线继续观察。",
            data_unavailable=False,
        )

        self.assertIn("今日动作：持仓观察", message)
        self.assertIn("稳定性：已归档", message)
        self.assertIn("最近闭环：样本股份（600001）", message)
        self.assertIn("退出原因 主升回撤保护止盈", message)
        self.assertIn("隔夜观察：样本股份（600001）", message)
        self.assertIn("封板影子线继续观察。", message)
        self.assertIn("下一步：明日 08:50", message)

    def test_end_of_day_message_marks_market_data_unavailable(self) -> None:
        message = one_to_two_end_of_day_notification_message(
            report_date="2026-05-09",
            account=Account(),
            warning_count=0,
            t1_sell_count=0,
            realized_pnl=0.0,
            stability_report=StabilityReport(),
            board_shadow_hint="hint",
            data_unavailable=True,
        )

        self.assertIn("行情数据不可用", message)
        self.assertIn("今日动作：暂停", message)

    def test_board_shadow_message_formats_research_boundary(self) -> None:
        message = board_shadow_notification_message(
            report=BoardShadowReport(),
            stability_report=BoardShadowStabilityReport(),
            sample_recorded=True,
        )

        self.assertIn("样本记录：已写入独立影子样本账本", message)
        self.assertIn("候选：样本股份（600001）", message)
        self.assertIn("封板影子样本已闭环", message)
        self.assertIn("质量检查：PIT pass", message)

    def test_notification_text_keeps_storage_and_notifier_out(self) -> None:
        module = Path("server/firemoney_server/application/one_to_two_notification_text.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server.infrastructure",
            "shared.contracts",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)
        self.assertNotIn("Feishu", source)
        self.assertNotIn("PaperTradeStore", source)


if __name__ == "__main__":
    unittest.main()
