"""Recap policy for execution feedback."""

from __future__ import annotations

from shared.contracts import ExecutionReceipt, Recap


class RecapPolicy:
    """Builds recap guidance from execution receipts."""

    def build_recap(self, receipt: ExecutionReceipt) -> Recap:
        return Recap(
            recap_id=f"recap-{receipt.order_id}",
            order_id=receipt.order_id,
            conclusion="已形成可追踪执行样本",
            execution_deviation="当前为半自动准备态，真实成交偏差需等待券商回执写回",
            lessons=(
                "保留二次确认，避免无审查自动交易",
                "回执写回后再评估入场价格偏差和仓位执行质量",
            ),
            next_strategy_action="将该委托样本纳入日终复盘，更新策略参数影响说明",
        )
