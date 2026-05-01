import unittest

from client.desktop.firemoney_client import FireMoneyShell, LocalMainChainAdapter
from server.firemoney_server import MainChainService
from shared.contracts import ReviewDecision, WorkflowStage, contract_to_dict


class MainChainSmokeTest(unittest.TestCase):
    def test_first_vertical_slice_reaches_strategy_improvement(self) -> None:
        snapshot = MainChainService().build_first_slice_snapshot()

        self.assertEqual(snapshot.next_stage, WorkflowStage.STRATEGY_IMPROVEMENT)
        self.assertGreaterEqual(len(snapshot.opportunities), 2)
        self.assertIsNotNone(snapshot.selected_opportunity)
        self.assertIsNotNone(snapshot.risk_review)
        self.assertIsNotNone(snapshot.order_ticket)
        self.assertIsNotNone(snapshot.execution_receipt)
        self.assertIsNotNone(snapshot.recap)
        self.assertIn(
            snapshot.risk_review.decision,
            (ReviewDecision.NEEDS_REVIEW, ReviewDecision.APPROVE_FOR_CONFIRMATION),
        )

    def test_contract_snapshot_is_json_friendly(self) -> None:
        snapshot = MainChainService().build_first_slice_snapshot()
        payload = contract_to_dict(snapshot)

        self.assertEqual(payload["market_context"]["risk_level"], "medium")
        self.assertEqual(payload["next_stage"], "strategy_improvement")
        self.assertIsInstance(payload["opportunities"], list)

    def test_client_shell_consumes_snapshot_without_business_logic(self) -> None:
        adapter = LocalMainChainAdapter()
        shell = FireMoneyShell()

        rendered = shell.render_snapshot(adapter.load_snapshot())

        self.assertIn("全局态势", rendered)
        self.assertIn("信号扫描", rendered)
        self.assertIn("机会池", rendered)
        self.assertIn("执行审查", rendered)
        self.assertIn("回执跟踪", rendered)
        self.assertIn("复盘改进", rendered)


if __name__ == "__main__":
    unittest.main()
