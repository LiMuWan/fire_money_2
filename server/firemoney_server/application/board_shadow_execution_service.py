"""Board-shadow candidate adaptation for the daily mainline execution path."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from server.firemoney_server.domain.one_to_two import OneToTwoPolicy
from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from shared.contracts import OneToTwoCandidate, OneToTwoExitPlan
from tools import research_limit_up_board_profit_matrix as board_matrix


def _board_label_from_symbol(symbol: str) -> str:
    if symbol.startswith("300"):
        return "创业板"
    if symbol.startswith("688"):
        return "科创板"
    if symbol.startswith(("8", "4", "9")):
        return "北交所"
    return "主板"


def _format_market_cap(value: float) -> str:
    return f"{value / 100_000_000:.0f}亿"


class BoardShadowExecutionService:
    """Converts board-shadow evidence into executable one-to-two candidates."""

    def __init__(self, *, settings, policy: OneToTwoPolicy) -> None:
        self._settings = settings
        self._policy = policy

    def build_candidates(
        self,
        report_date: str,
        rows: tuple[OneToTwoMarketRow, ...] = (),
        cache_dir: str | Path | None = None,
        include_blocked: bool = False,
    ) -> tuple[OneToTwoCandidate, ...]:
        if rows:
            inherited_blockers = {
                (row.symbol, row.trade_date): self._inherited_execution_blockers(
                    self._policy._candidate_from_row(row).blockers
                )
                for row in rows
            }
            row_candidates = self._candidates_from_market_rows(rows)
            latest_price_by_key = {
                (row.symbol, row.trade_date): row.latest_price
                for row in rows
            }
            converted = tuple(
                self._to_execution_candidate(
                    item,
                    board_matrix.shadow_default_exit_case(),
                    latest_price=latest_price_by_key.get(
                        (item.symbol, item.board_date),
                        item.entry_price,
                    ),
                    inherited_blockers=inherited_blockers.get(
                        (item.symbol, item.board_date),
                        (),
                    ),
                )
                for item in row_candidates
            )
            converted = self._apply_ready_pool_gate(converted)
            if include_blocked:
                return converted
            return tuple(item for item in converted if item.status == "ready")[:1]

        cache_path = Path(cache_dir) if cache_dir else board_matrix.DEFAULT_CACHE_DIR
        try:
            universe, histories = board_matrix.load_cached_research_data(
                cache_path,
                board_matrix.sm.parse_iso_date(report_date),
                board_matrix.sm.parse_iso_date(report_date),
            )
        except Exception:
            return ()
        board_candidates = board_matrix.build_board_candidates(
            universe,
            histories,
            board_matrix.sm.parse_iso_date(report_date),
            board_matrix.sm.parse_iso_date(report_date),
        )
        entry_case = board_matrix.shadow_default_entry_case()
        exit_case = board_matrix.shadow_default_exit_case()
        filtered = [
            item
            for item in board_candidates
            if board_matrix.entry_case_allows(entry_case, item)
        ]
        selected = board_matrix.select_daily_top_candidates(filtered, "score")
        converted = tuple(
            self._to_execution_candidate(item, exit_case)
            for item in selected[:1]
        )
        if include_blocked:
            return converted
        return tuple(item for item in converted if item.status == "ready")

    def _apply_ready_pool_gate(
        self,
        candidates: tuple[OneToTwoCandidate, ...],
    ) -> tuple[OneToTwoCandidate, ...]:
        max_ready = self._settings.max_ready_candidates
        if max_ready <= 0:
            return candidates
        ready_count = sum(1 for item in candidates if item.status == "ready")
        if ready_count <= max_ready:
            return candidates

        reason = f"今日可执行候选 {ready_count} 个超过 {max_ready} 个，主线过散只观察"
        warning = "候选池过热过散，先不做唯一票模拟买入。"
        return tuple(
            replace(
                candidate,
                status="blocked",
                blockers=tuple(dict.fromkeys((*candidate.blockers, reason))),
                warnings=tuple(dict.fromkeys((*candidate.warnings, warning))),
                rationale=f"{candidate.name} 当日候选池过宽，资金主线不够集中，先观察不买入。",
                next_action="候选池过热闸门未通过，不生成模拟买入。",
            )
            if candidate.status == "ready"
            else candidate
            for candidate in candidates
        )

    @staticmethod
    def _candidates_from_market_rows(
        rows: tuple[OneToTwoMarketRow, ...],
    ) -> tuple[board_matrix.BoardCandidate, ...]:
        entry_case = board_matrix.shadow_default_entry_case()
        candidates: list[board_matrix.BoardCandidate] = []
        for index, row in enumerate(rows):
            if row.previous_close <= 0 or row.latest_price <= 0:
                continue
            market_seal_count = row.first_board_count or len(rows)
            candidate = board_matrix.BoardCandidate(
                symbol=row.symbol,
                name=row.name,
                board_date=row.trade_date,
                index=index,
                entry_price=round(row.limit_up_price or row.latest_price, 2),
                previous_close=round(row.previous_close, 2),
                close_pct=round(
                    (row.latest_price - row.previous_close) / row.previous_close,
                    4,
                ),
                high_pct=round(
                    ((row.limit_up_price or row.latest_price) - row.previous_close)
                    / row.previous_close,
                    4,
                ),
                estimated_turnover_amount=round(row.turnover_amount, 2),
                volume_ratio_20=round(row.volume_ratio_5 or 0.0, 4),
                recent_gain_pct=round(row.recent_gain_pct, 4),
                ma20_deviation_pct=round(
                    (row.latest_price - row.ma_20) / row.ma_20,
                    4,
                )
                if row.ma_20
                else 0.0,
                position_percentile_60=round(row.position_percentile_60, 4),
                first_board=True,
                ma_bullish=bool(row.ma_5 >= row.ma_10 >= row.ma_20),
                rank_score=0.0,
                market_seal_count=market_seal_count,
                market_touch_count=max(market_seal_count, len(rows)),
                market_advance_ratio=round(
                    max(0.0, min(row.market_temperature / 100, 1.0)),
                    4,
                ),
                market_cap=row.market_cap,
                float_market_cap=row.float_market_cap,
            )
            candidate = board_matrix.replace_rank_score(candidate)
            candidates.append(candidate)
        ranked = sorted(
            candidates,
            key=lambda item: board_matrix.candidate_rank_key(item, "score"),
            reverse=True,
        )
        allowed = [
            item for item in ranked if board_matrix.entry_case_allows(entry_case, item)
        ]
        blocked = [
            item
            for item in ranked
            if not board_matrix.entry_case_allows(entry_case, item)
        ]
        return tuple(allowed + blocked)

    def _to_execution_candidate(
        self,
        candidate: board_matrix.BoardCandidate,
        exit_case: board_matrix.ExitCase,
        latest_price: float | None = None,
        inherited_blockers: tuple[str, ...] = (),
    ) -> OneToTwoCandidate:
        stop_loss = round(candidate.entry_price * (1 - exit_case.stop_loss_pct), 2)
        take_profit_pct = board_matrix.resolve_take_profit_pct(candidate, exit_case)
        current_price = round(latest_price or candidate.entry_price, 2)
        position_pct = min(
            board_matrix.resolve_position_pct(candidate, exit_case),
            self._settings.max_position_pct,
        )
        market_temperature = min(100, max(0, int(candidate.market_advance_ratio * 100)))
        row = OneToTwoMarketRow(
            symbol=candidate.symbol,
            name=candidate.name,
            trade_date=candidate.board_date,
            board=_board_label_from_symbol(candidate.symbol),
            is_st=False,
            is_delisting=False,
            listing_days=9999,
            latest_price=current_price,
            previous_close=candidate.previous_close,
            limit_up_price=candidate.entry_price,
            first_limit_up_time="10:00",
            sealed_amount=max(candidate.estimated_turnover_amount * 0.16, 1.0),
            turnover_amount=max(candidate.estimated_turnover_amount, 1.0),
            turnover_rate=5.0,
            # Board-shadow is a board-day strategy; use a neutral next-open
            # confirmation proxy instead of reusing board-day high_pct.
            open_pct=min(self._settings.max_confirm_open_pct, 0.025),
            auction_amount=max(candidate.estimated_turnover_amount * 0.04, 1.0),
            low_20=round(candidate.entry_price * max(0.5, 1 - candidate.recent_gain_pct), 2),
            high_60=round(candidate.entry_price, 2),
            pressure_price=round(candidate.entry_price * 1.2, 2),
            ma_5=round(candidate.entry_price * 0.98, 2),
            ma_10=round(candidate.entry_price * 0.97, 2),
            ma_20=round(
                candidate.entry_price / max(1 + candidate.ma20_deviation_pct, 0.01),
                2,
            ),
            recent_gain_pct=candidate.recent_gain_pct,
            theme="board-shadow-system",
            market_temperature=market_temperature,
            first_board_count=candidate.market_seal_count,
            volume_ratio_5=max(candidate.volume_ratio_20, 1.5),
            rsi_14=68.0,
            position_percentile_60=round(candidate.position_percentile_60, 4),
            market_cap=candidate.market_cap,
            float_market_cap=candidate.float_market_cap,
        )
        base = self._policy._candidate_from_row(row)
        exit_plan = self._exit_plan(
            candidate.entry_price,
            stop_loss,
            take_profit_pct,
            exit_case,
        )
        entry_case = board_matrix.shadow_default_entry_case()
        status = "ready" if board_matrix.entry_case_allows(entry_case, candidate) else "blocked"
        blockers = (
            inherited_blockers
            + self._inherited_execution_blockers(base.blockers)
            + self._entry_blockers(candidate, entry_case)
        )
        turnover_quality_score = max(base.turnover_quality_score, 86.0)
        turnover_quality_label = "board-shadow validated mainline"
        turnover_quality_notes = (
            f"rank score {candidate.rank_score:.2f}",
            f"20d volume ratio {candidate.volume_ratio_20:.2f}",
            f"recent gain {candidate.recent_gain_pct:.2%}",
        )
        if self._has_turnover_quality_blocker(blockers):
            turnover_quality_score = min(base.turnover_quality_score, 71.0)
            turnover_quality_label = "换手龙质量未过线"
            turnover_quality_notes = tuple(
                dict.fromkeys(
                    (
                        *base.turnover_quality_notes,
                        "board-shadow 候选继承了实时换手/封单硬拦截",
                    )
                )
            )
        effective_market_cap = candidate.market_cap or candidate.float_market_cap
        if effective_market_cap > 0:
            if effective_market_cap < self._settings.min_market_cap:
                blockers = blockers + (
                    f"市值低于 {_format_market_cap(self._settings.min_market_cap)}，不做流动性过弱的小票",
                )
            elif effective_market_cap > self._settings.max_market_cap:
                blockers = blockers + (
                    f"市值高于 {_format_market_cap(self._settings.max_market_cap)}，不做弹性不足的大票",
                )
        elif candidate.market_cap == 0 and candidate.float_market_cap == 0:
            blockers = blockers + ("缺少总市值/流通市值，实时模拟盘不允许开仓",)
        return replace(
            base,
            score=max(base.score, 96.0),
            status="ready" if status == "ready" and not blockers else "blocked",
            latest_price=current_price,
            entry_price=round(candidate.entry_price, 2),
            stop_loss=stop_loss,
            position_limit_pct=position_pct,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(
                dict.fromkeys(
                    (
                        *base.warnings,
                        "board-shadow-system execution: daily cache candidate; intraday queue and slippage still require watch/open confirmation.",
                    )
                )
            ),
            rationale=(
                f"封板波段主线已锁定 {candidate.name}（{candidate.symbol}），"
                f"排序分 {candidate.rank_score:.2f}，热度 {candidate.market_seal_count}，"
                f"上涨占比 {candidate.market_advance_ratio:.2%}；"
                "只有这条主线允许生成模拟买入。"
            ),
            next_action="若开盘确认仍成立，就在盘中值守开盘阶段写入模拟买入。",
            mainline_score=max(base.mainline_score, 18.0),
            sealing_score=max(base.sealing_score, 18.0),
            leader_score=max(base.leader_score, 18.0),
            leader_label="board-shadow-system mainline candidate",
            strategy_tags=tuple(
                dict.fromkeys((*base.strategy_tags, "board-shadow-system"))
            ),
            discipline_summary=(
                f"封板影子样本纪律：止损 {exit_case.stop_loss_pct:.1%}，"
                f"止盈 {take_profit_pct:.1%}，最长持有 {exit_case.max_hold_days} 个交易日。"
            ),
            exit_plan=exit_plan,
            turnover_quality_score=turnover_quality_score,
            turnover_quality_label=turnover_quality_label,
            turnover_quality_notes=turnover_quality_notes,
        )

    @staticmethod
    def _entry_blockers(
        candidate: board_matrix.BoardCandidate,
        entry_case: board_matrix.EntryCase,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if entry_case.require_first_board and not candidate.first_board:
            blockers.append("封板波段只做首板候选")
        if candidate.estimated_turnover_amount < entry_case.min_turnover_amount:
            blockers.append("封板波段成交额低于入场门槛")
        if (
            entry_case.max_recent_gain_pct is not None
            and candidate.recent_gain_pct > entry_case.max_recent_gain_pct
        ):
            blockers.append("封板前 20 日涨幅过大，避免高位加速板")
        if (
            entry_case.max_ma20_deviation_pct is not None
            and candidate.ma20_deviation_pct > entry_case.max_ma20_deviation_pct
        ):
            blockers.append("距离 20 日均线过远，封板波段不追高")
        if candidate.volume_ratio_20 < entry_case.min_volume_ratio_20:
            blockers.append("20 日量比不足，封板波段承接不够")
        if entry_case.require_ma_bullish and not candidate.ma_bullish:
            blockers.append("均线未多头排列，封板波段不入场")
        if candidate.position_percentile_60 < entry_case.min_position_percentile_60:
            blockers.append("60 日位置不足，封板波段持续性不够")
        if candidate.market_seal_count < entry_case.min_market_seal_count:
            blockers.append(
                f"封板热度 {candidate.market_seal_count} 家低于 {entry_case.min_market_seal_count} 家"
            )
        if (
            entry_case.max_market_seal_count is not None
            and candidate.market_seal_count > entry_case.max_market_seal_count
        ):
            blockers.append(
                f"封板热度 {candidate.market_seal_count} 家高于 {entry_case.max_market_seal_count} 家，情绪过热"
            )
        effective_market_cap = candidate.market_cap or candidate.float_market_cap
        if (
            effective_market_cap > 0
            and entry_case.min_market_cap > 0
            and effective_market_cap < entry_case.min_market_cap
        ):
            blockers.append(
                f"市值低于 {_format_market_cap(entry_case.min_market_cap)}，不做流动性过弱的小票"
            )
        if (
            effective_market_cap > 0
            and entry_case.max_market_cap is not None
            and effective_market_cap > entry_case.max_market_cap
        ):
            blockers.append(
                f"市值高于 {_format_market_cap(entry_case.max_market_cap)}，不做弹性不足的大票"
            )
        return tuple(blockers)

    @staticmethod
    def _inherited_execution_blockers(
        blockers: tuple[str, ...],
    ) -> tuple[str, ...]:
        inherited_keywords = (
            "不在主板",
            "ST",
            "退市",
            "新股",
            "封板资金不足",
            "换手不足",
            "换手过高",
            "换手龙",
            "炸板风险",
            "未红盘",
            "高开超过",
            "一字板",
            "买不到",
        )
        return tuple(
            blocker
            for blocker in blockers
            if any(keyword in blocker for keyword in inherited_keywords)
        )

    @staticmethod
    def _has_turnover_quality_blocker(blockers: tuple[str, ...]) -> bool:
        turnover_keywords = (
            "封板资金不足",
            "换手不足",
            "换手过高",
            "换手龙",
            "炸板风险",
        )
        return any(
            any(keyword in blocker for keyword in turnover_keywords)
            for blocker in blockers
        )

    def _exit_plan(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_pct: float,
        exit_case: board_matrix.ExitCase,
    ) -> OneToTwoExitPlan:
        first_take_profit_price = round(entry_price * (1 + take_profit_pct), 2)
        strong_take_profit_pct = exit_case.strong_market_take_profit_pct or take_profit_pct
        return OneToTwoExitPlan(
            stop_loss=stop_loss,
            stop_loss_pct=exit_case.stop_loss_pct,
            first_take_profit_price=first_take_profit_price,
            first_take_profit_pct=take_profit_pct,
            strong_take_profit_price=round(entry_price * (1 + strong_take_profit_pct), 2),
            strong_take_profit_pct=strong_take_profit_pct,
            trailing_stop_pct=self._settings.trailing_stop_pct,
            max_holding_trade_days=exit_case.max_hold_days,
            summary=(
                f"封板波段主线：止损 {stop_loss}，第一止盈 "
                f"{first_take_profit_price}，最长持有 {exit_case.max_hold_days} 个交易日。"
            ),
        )


__all__ = ["BoardShadowExecutionService"]
