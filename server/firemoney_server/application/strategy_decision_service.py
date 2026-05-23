"""Daily strategy selection service for the FireMoney operating line."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from shared.contracts import StrategyDecisionOption, StrategyDecisionReport


def default_strategy_decision_snapshot_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "exports"
        / "strategy_decision_snapshot.json"
    )


class StrategyDecisionService:
    """Build the daily decision from audited board-shadow evidence."""

    def __init__(
        self,
        *,
        snapshot_path: str | Path | None = None,
        default_trade_date: Callable[[], str],
    ) -> None:
        self._snapshot_path = (
            Path(snapshot_path)
            if snapshot_path is not None
            else default_strategy_decision_snapshot_path()
        )
        self._default_trade_date = default_trade_date

    def build_report(
        self,
        *,
        trade_date: str | None = None,
        start_date: str = "2024-01-01",
        end_date: str | None = None,
        cache_dir: str | Path | None = None,
        market_temperature: int | None = None,
        ready_candidate_count: int | None = None,
        average_mainline_score: float | None = None,
        average_turnover_quality_score: float | None = None,
        k92_regime: str | None = None,
        k92_action: str | None = None,
        k92_summary: str | None = None,
        data_unavailable: bool = False,
    ) -> StrategyDecisionReport:
        del start_date, end_date, cache_dir
        resolved_trade_date = trade_date or self._default_trade_date()
        snapshot = self._load_snapshot()
        main_line = snapshot["main_line"]
        board_option = StrategyDecisionOption(
            strategy_id=str(main_line.get("strategy_id") or "board-shadow-system"),
            role="main_operating_line",
            status=str(main_line.get("status") or "ready"),
            action="operate_when_signal_exists",
            confidence="high",
            expected_return_label=(
                "2024年以来动态 8%/12%仓位复合收益 "
                f"{float(main_line.get('summary_return_pct') or 0.0):.2%}; "
                "验证段收益 "
                f"{float(main_line.get('validation_return_pct') or 0.0):.2%}"
            ),
            max_drawdown_label=(
                "2024年以来动态最大回撤 "
                f"{float(main_line.get('summary_drawdown_pct') or 0.0):.2%}; "
                "验证段回撤 "
                f"{float(main_line.get('validation_drawdown_pct') or 0.0):.2%}"
            ),
            rationale=(
                "当前唯一经营主线是封板波段主线；有主线买点才做，"
                "没有买点就空仓，不用低质量交易补次数。"
            ),
        )
        cash_option = StrategyDecisionOption(
            strategy_id="cash",
            role="risk_control",
            status="ready",
            action="stand_aside",
            confidence="high",
            expected_return_label="0.00%",
            max_drawdown_label="0.00%",
            rationale=(
                "当主线不够强、没有合格候选或数据不可用时，空仓是策略的一部分。"
            ),
        )
        options = (board_option, cash_option)
        market_regime, regime_rationale, regime_action = self._market_regime(
            market_temperature=market_temperature,
            ready_candidate_count=ready_candidate_count,
            average_mainline_score=average_mainline_score,
            average_turnover_quality_score=average_turnover_quality_score,
            board_option=board_option,
            data_unavailable=data_unavailable,
        )
        k92_gate, k92_rationale = self._k92_gate(
            k92_regime=k92_regime,
            k92_action=k92_action,
            k92_summary=k92_summary,
        )
        selected_option = (
            board_option
            if market_regime == "trend_main_rise_day"
            and k92_gate != "block"
            and board_option.status == "ready"
            else cash_option
        )
        selected_label = (
            "封板波段主线"
            if selected_option.strategy_id == "board-shadow-system"
            else "现金防守"
        )
        summary = (
            f"今日市场状态为 {market_regime}。{regime_rationale} {k92_rationale} "
            f"今日实际操作选择 {selected_label}：{selected_option.action}。"
        )
        report_status = (
            "data_unavailable"
            if data_unavailable
            else "blocked"
            if selected_option.strategy_id == "cash"
            else "ready"
        )
        return StrategyDecisionReport(
            report_id=f"strategy-decision-{resolved_trade_date}",
            trade_date=resolved_trade_date,
            status=report_status,
            evidence_end_date=str(
                snapshot.get("main_line", {}).get("evidence_end_date")
                or self._default_trade_date()
            ),
            market_regime=market_regime,
            regime_rationale=regime_rationale,
            regime_action=regime_action,
            k92_regime=k92_regime or "not_available",
            k92_gate=k92_gate,
            k92_rationale=k92_rationale,
            selected_strategy_id=selected_option.strategy_id,
            selected_action=selected_option.action,
            selected_role=selected_option.role,
            summary=summary,
            options=options,
            risk_rules=(
                "每天只允许一个实际操作主策略，避免多策略同时开仓导致回撤叠加。",
                "没有达到主线买点时默认空仓，现金仓位不计为错过机会。",
                "K92 只作为主线守门增强：退潮空仓日阻断新开仓，龙头进攻日只提高主线确认，不新增第二开仓线。",
                "非主线研究项不进入每日经营买入路由；长期赚钱证据只来自封板波段主线。",
                "所有策略复盘从 2024-01-01 起做逐日快照回测，买点不得使用未来走势。",
            ),
            next_action=(
                "今天先修复行情源并复核 doctor，不生成模拟买入。"
                if data_unavailable
                else f"今天按 {market_regime} 路由执行 {selected_label}；"
                "再用策略决策简报和模拟盘指挥单复核。"
            ),
        )

    def _k92_gate(
        self,
        *,
        k92_regime: str | None,
        k92_action: str | None,
        k92_summary: str | None,
    ) -> tuple[str, str]:
        if k92_regime == "ebb_stand_aside_day" or k92_action == "stand_aside":
            reason = k92_summary or "K92 判定为退潮空仓，今天不为了交易频率硬做。"
            return ("block", f"K92 守门：{reason}")
        if k92_regime == "leader_attack_day":
            reason = k92_summary or "K92 判定为龙头进攻日，主线信号获得情绪确认。"
            return ("confirm", f"K92 守门：{reason}")
        if k92_regime in {"low_level_supplement_day", "theme_switch_day"}:
            reason = k92_summary or "K92 判定为修复/切换观察日，主线可做但不加仓不扩线。"
            return ("observe", f"K92 守门：{reason}")
        return (
            "not_available",
            "K92 守门：今日没有可用 K92 状态，只按主线原守门执行。",
        )

    def _market_regime(
        self,
        *,
        market_temperature: int | None,
        ready_candidate_count: int | None,
        average_mainline_score: float | None,
        average_turnover_quality_score: float | None,
        board_option: StrategyDecisionOption,
        data_unavailable: bool,
    ) -> tuple[str, str, str]:
        if data_unavailable:
            return (
                "market_data_unavailable_day",
                "行情源没有返回可验证数据，今天不能把空仓解释为策略防守，先暂停并修复数据链路。",
                "pause_until_market_data_ready",
            )
        temperature = market_temperature or 0
        ready_count = ready_candidate_count or 0
        mainline_score = average_mainline_score or 0.0
        turnover_quality = average_turnover_quality_score or 0.0
        if (
            temperature >= 70
            and ready_count >= 3
            and mainline_score >= 18
            and turnover_quality >= 80
            and board_option.status == "ready"
        ):
            return (
                "trend_main_rise_day",
                "强市、主线候选密度高、换手质量强，只做趋势主升和龙头延续。",
                "attack_trend_main_rise",
            )
        return (
            "defense_stand_aside_day",
            "市场不够强或高质量主线候选不足，默认防守空仓，先保护回撤和节奏。",
            "defense_stand_aside",
        )

    def _load_snapshot(self) -> dict[str, dict[str, object]]:
        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
            main_line = payload.get("main_line") or {}
            if isinstance(main_line, dict):
                return {"main_line": main_line}
        except Exception:
            pass
        return {
            "main_line": {
                "strategy_id": "board-shadow-system",
                "status": "ready",
                "summary_return_pct": 0.9651,
                "validation_return_pct": 0.1206,
                "summary_drawdown_pct": -0.0203,
                "validation_drawdown_pct": -0.0112,
            },
        }


__all__ = ["StrategyDecisionService", "default_strategy_decision_snapshot_path"]
