"""Minimal client shell for the FireMoney main workflow."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import MainChainSnapshot


@dataclass(frozen=True)
class WorkspaceDescriptor:
    key: str
    title: str
    purpose: str


class FireMoneyShell:
    """Renders workflow state without making business decisions."""

    WORKSPACES: tuple[WorkspaceDescriptor, ...] = (
        WorkspaceDescriptor("overview", "全局态势", "看市场状态和主线温度"),
        WorkspaceDescriptor("scanner", "信号扫描", "发现盘中候选和观察对象"),
        WorkspaceDescriptor("opportunities", "机会池", "过滤候选并形成交易计划"),
        WorkspaceDescriptor("execution", "执行中控", "审查风险、提交委托、跟踪回执"),
        WorkspaceDescriptor("recap", "单票复盘", "回放执行样本并沉淀改进"),
        WorkspaceDescriptor("config", "策略配置", "管理参数和风险边界"),
    )

    def render_snapshot(self, snapshot: MainChainSnapshot) -> str:
        selected = snapshot.selected_opportunity
        review = snapshot.risk_review
        ticket = snapshot.order_ticket
        receipt = snapshot.execution_receipt
        recap = snapshot.recap

        lines = [
            f"全局态势：{snapshot.market_context.summary}",
            f"信号扫描：发现 {len(snapshot.opportunities)} 个候选",
            "机会池："
            + (
                f"{selected.name}({selected.symbol}) 评分 {selected.score:.0f}"
                if selected
                else "暂无可执行候选"
            ),
            "执行审查："
            + (
                f"{review.decision.value}，下一步：{review.next_action}"
                if review
                else "等待机会池候选"
            ),
            "委托提交："
            + (
                f"{ticket.status}，{ticket.route}，需二次确认"
                if ticket
                else "未生成委托"
            ),
            "回执跟踪："
            + (
                f"{receipt.status}，{receipt.message}"
                if receipt
                else "等待提交结果"
            ),
            "复盘改进："
            + (
                f"{recap.conclusion}，{recap.next_strategy_action}"
                if recap
                else "等待执行样本"
            ),
            f"策略边界：{snapshot.strategy_config.impact_summary}",
        ]
        return "\n".join(lines)

    def workspace_titles(self) -> tuple[str, ...]:
        return tuple(workspace.title for workspace in self.WORKSPACES)
