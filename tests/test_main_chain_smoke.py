import json
import tempfile
import unittest
from pathlib import Path

from client.desktop.firemoney_client import FireMoneyShell, LocalMainChainAdapter
from client.desktop.firemoney_client.content import load_client_content
from client.desktop.firemoney_client.preview import build_preview
from client.desktop.firemoney_client.renderer import render_core_workflow_html
from server.firemoney_server import MainChainService
from server.firemoney_server.domain.message_catalog import load_domain_messages
from server.firemoney_server.domain.signal_scan import SignalScanPolicy
from server.firemoney_server.infrastructure.archive_store import TradeArchiveStore
from server.firemoney_server.infrastructure.fill_import import (
    BrokerExitRecord,
    BrokerFillImporter,
    BrokerFillRecord,
)
from server.firemoney_server.infrastructure.order_export import CsvOrderExporter
from server.firemoney_server.infrastructure.receipt_import import (
    BrokerReceiptImporter,
    BrokerReceiptRecord,
)
from server.firemoney_server.infrastructure.sample_data import (
    sample_market_context,
    sample_opportunity_candidates,
    sample_strategy_config,
)
from server.firemoney_server.infrastructure.strategy_store import StrategyConfigStore
from shared.contracts import (
    AdjustmentStatus,
    ConfirmationStatus,
    ExecutionReceiptStatus,
    ExecutionRoute,
    ExitExecution,
    FillExecution,
    OutcomeCard,
    ReviewDecision,
    TradeArchiveRecord,
    WorkflowStage,
    contract_to_dict,
)


def _build_service(
    root: Path,
    receipt_importer: BrokerReceiptImporter | None = None,
    fill_importer: BrokerFillImporter | None = None,
    strategy_store: StrategyConfigStore | None = None,
    archive_store: TradeArchiveStore | None = None,
) -> MainChainService:
    return MainChainService(
        order_exporter=CsvOrderExporter(root / "orders"),
        receipt_importer=receipt_importer or BrokerReceiptImporter(root / "receipts"),
        fill_importer=fill_importer or BrokerFillImporter(root / "fills"),
        strategy_store=strategy_store or StrategyConfigStore(root / "strategy_config.json"),
        archive_store=archive_store or TradeArchiveStore(root / "trade_archives.json"),
    )


def _seed_broker_receipt(receipt_importer: BrokerReceiptImporter) -> None:
    receipt_importer.save_record(
        BrokerReceiptRecord(
            order_id="draft-600001",
            status=ExecutionReceiptStatus.ACCEPTED,
            submitted_at="2026-05-01T09:36:00+08:00",
            message="broker receipt accepted",
            next_action="wait for fill result",
        )
    )


def _seed_entry_fill(fill_importer: BrokerFillImporter) -> None:
    fill_importer.save_record(
        BrokerFillRecord(
            order_id="draft-600001",
            symbol="600001",
            filled_quantity=100,
            avg_price=12.43,
            filled_at="2026-05-01T09:41:00+08:00",
            message="entry fill imported",
        )
    )


def _seed_exit_fill(fill_importer: BrokerFillImporter) -> None:
    fill_importer.save_exit_record(
        BrokerExitRecord(
            order_id="draft-600001",
            symbol="600001",
            exited_quantity=100,
            avg_price=12.92,
            exited_at="2026-05-01T10:18:00+08:00",
            reason="target_follow",
            message="exit fill imported",
        )
    )


class MainChainSmokeTest(unittest.TestCase):
    def test_first_vertical_slice_waits_for_user_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _build_service(Path(temp_dir)).build_first_slice_snapshot()

            self.assertEqual(snapshot.next_stage, WorkflowStage.ORDER_DRAFT)
            self.assertEqual(snapshot.signal_scan.stage, WorkflowStage.SIGNAL_SCAN)
            self.assertGreaterEqual(snapshot.signal_scan.candidate_count, 2)
            self.assertIsNotNone(snapshot.signal_scan.focus_opportunity)
            self.assertGreaterEqual(len(snapshot.opportunities), 2)
            self.assertIsNotNone(snapshot.selected_opportunity)
            self.assertIsNotNone(snapshot.risk_review)
            self.assertIsNotNone(snapshot.order_ticket)
            self.assertEqual(
                snapshot.order_ticket.confirmation_status,
                ConfirmationStatus.WAITING_USER,
            )
            self.assertIsNone(snapshot.execution_receipt)
            self.assertIsNone(snapshot.recap)
            self.assertEqual(snapshot.recent_archives, ())
            self.assertIn(
                snapshot.risk_review.decision,
                (ReviewDecision.NEEDS_REVIEW, ReviewDecision.APPROVE_FOR_CONFIRMATION),
            )

    def test_confirmed_vertical_slice_reaches_strategy_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _build_service(Path(temp_dir)).build_first_slice_snapshot(
                user_confirmed=True,
            )

            self.assertEqual(snapshot.next_stage, WorkflowStage.STRATEGY_IMPROVEMENT)
            self.assertEqual(
                snapshot.order_ticket.confirmation_status,
                ConfirmationStatus.CONFIRMED,
            )
            self.assertIsNotNone(snapshot.execution_receipt)
            self.assertEqual(
                snapshot.execution_receipt.status,
                ExecutionReceiptStatus.PREPARED,
            )
            self.assertEqual(snapshot.execution_receipt.route, ExecutionRoute.CSV_EXPORT)
            self.assertFalse(snapshot.execution_receipt.accepted)
            self.assertTrue(snapshot.execution_receipt.confirmed_by_user)
            self.assertIsNone(snapshot.execution_receipt.failure_reason)
            self.assertTrue(Path(snapshot.execution_receipt.exported_path).exists())
            csv_content = Path(snapshot.execution_receipt.exported_path).read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("draft-600001", csv_content)
            self.assertIn("600001", csv_content)
            self.assertIn("buy", csv_content)
            self.assertIsNotNone(snapshot.recap)
            self.assertGreaterEqual(len(snapshot.recap.strategy_adjustments), 1)
            self.assertEqual(
                snapshot.recap.strategy_adjustments[0].key,
                "max_position_pct",
            )
            self.assertEqual(
                snapshot.strategy_config.adjustment_status,
                AdjustmentStatus.WAITING_USER,
            )
            self.assertEqual(snapshot.strategy_config.parameters["max_position_pct"], 0.12)
            self.assertEqual(snapshot.recent_archives, ())

    def test_submitted_vertical_slice_imports_broker_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)

            snapshot = _build_service(
                root,
                receipt_importer=receipt_importer,
            ).build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
            )

            self.assertIsNotNone(snapshot.execution_receipt)
            self.assertEqual(snapshot.execution_receipt.status, ExecutionReceiptStatus.ACCEPTED)
            self.assertTrue(snapshot.execution_receipt.accepted)
            self.assertEqual(
                snapshot.execution_receipt.submitted_at,
                "2026-05-01T09:36:00+08:00",
            )
            self.assertEqual(snapshot.execution_receipt.message, "broker receipt accepted")
            self.assertIsNone(snapshot.fill_execution)
            self.assertIsNotNone(snapshot.recap)
            self.assertEqual(snapshot.recent_archives, ())

    def test_filled_vertical_slice_imports_deal_detail_for_recap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)

            snapshot = _build_service(
                root,
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
            ).build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
            )

            self.assertIsInstance(snapshot.fill_execution, FillExecution)
            self.assertIsInstance(snapshot.outcome_card, OutcomeCard)
            self.assertEqual(snapshot.fill_execution.filled_quantity, 100)
            self.assertEqual(snapshot.fill_execution.avg_price, 12.43)
            self.assertGreater(snapshot.fill_execution.slippage_pct, 0.005)
            self.assertEqual(snapshot.fill_execution.message, "entry fill imported")
            self.assertEqual(snapshot.outcome_card.current_price, 12.68)
            self.assertEqual(snapshot.outcome_card.unrealized_pnl, 25.0)
            self.assertIsNone(snapshot.outcome_card.realized_pnl)
            self.assertIsNone(snapshot.exit_execution)
            self.assertIsNotNone(snapshot.recap)
            self.assertGreaterEqual(len(snapshot.recap.lessons), 1)
            self.assertTrue(
                any(
                    adjustment.key == "max_slippage_pct"
                    for adjustment in snapshot.recap.strategy_adjustments
                )
            )

    def test_closed_vertical_slice_imports_exit_fill_for_realized_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)
            _seed_exit_fill(fill_importer)
            archive_store = TradeArchiveStore(root / "trade_archives.json")

            snapshot = _build_service(
                root,
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
                archive_store=archive_store,
            ).build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
                exit_received=True,
            )

            self.assertIsInstance(snapshot.exit_execution, ExitExecution)
            self.assertIsInstance(snapshot.archive_record, TradeArchiveRecord)
            self.assertEqual(snapshot.exit_execution.message, "exit fill imported")
            self.assertEqual(snapshot.exit_execution.realized_pnl, 49.0)
            self.assertEqual(snapshot.exit_execution.realized_pnl_pct, 0.0394)
            self.assertEqual(snapshot.outcome_card.realized_pnl, 49.0)
            self.assertEqual(snapshot.outcome_card.unrealized_pnl, 0.0)
            self.assertEqual(snapshot.archive_record.archive_id, "archive-draft-600001")
            self.assertEqual(snapshot.archive_record.outcome, "profit")
            self.assertEqual(snapshot.archive_record.realized_pnl, 49.0)
            self.assertTrue(any(tag.startswith("decision:") for tag in snapshot.archive_record.tags))
            self.assertEqual(len(snapshot.recent_archives), 1)
            self.assertTrue(archive_store.path.exists())
            self.assertEqual(
                archive_store.load_recent()[0].archive_id,
                "archive-draft-600001",
            )

            reloaded = _build_service(root, archive_store=archive_store).build_first_slice_snapshot()
            self.assertEqual(len(reloaded.recent_archives), 1)
            self.assertEqual(reloaded.recent_archives[0].archive_id, "archive-draft-600001")

    def test_archive_store_exports_and_clears_recent_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)
            _seed_exit_fill(fill_importer)
            archive_store = TradeArchiveStore(
                root / "trade_archives.json",
                export_dir=root / "archive_exports",
            )
            service = _build_service(
                root,
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
                archive_store=archive_store,
            )
            service.build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
                exit_received=True,
            )

            json_export = service.export_trade_archives(format="json")
            csv_export = service.export_trade_archives(format="csv")

            self.assertEqual(json_export.name, "trade_archives.json")
            self.assertEqual(csv_export.name, "trade_archives.csv")
            self.assertEqual(
                json.loads(json_export.read_text(encoding="utf-8"))[0]["archive_id"],
                "archive-draft-600001",
            )
            csv_content = csv_export.read_text(encoding="utf-8-sig")
            self.assertIn("archive_id", csv_content)
            self.assertIn("archive-draft-600001", csv_content)
            self.assertIn("risk:medium", csv_content)

            self.assertTrue(service.clear_trade_archives())
            self.assertFalse(archive_store.path.exists())
            self.assertEqual(archive_store.load_recent(), ())
            self.assertFalse(service.clear_trade_archives())

    def test_bad_archive_store_file_is_treated_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            archive_store.path.write_text("{", encoding="utf-8")

            self.assertEqual(archive_store.load_recent(), ())
            exported = archive_store.export_recent(root / "empty_archives.csv", format="csv")

            self.assertTrue(exported.exists())
            self.assertIn("archive_id", exported.read_text(encoding="utf-8-sig"))

    def test_adjustment_confirmation_updates_next_strategy_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store)
            snapshot = service.build_first_slice_snapshot(
                user_confirmed=True,
                adjustments_confirmed=True,
            )

            self.assertEqual(snapshot.next_stage, WorkflowStage.SIGNAL_SCAN)
            self.assertEqual(
                snapshot.strategy_config.adjustment_status,
                AdjustmentStatus.APPLIED,
            )
            self.assertEqual(snapshot.strategy_config.version, "0.1.1")
            self.assertEqual(snapshot.strategy_config.parameters["max_position_pct"], 0.08)
            self.assertEqual(snapshot.strategy_config.parameters["min_score"], 75)
            self.assertTrue(store.path.exists())
            self.assertEqual(snapshot.strategy_config.recent_changes[0].action, "apply")
            self.assertTrue(
                any(
                    "min_score" in change
                    for change in snapshot.strategy_config.recent_changes[0].changes
                )
            )

            reloaded = _build_service(root, strategy_store=store).build_first_slice_snapshot()
            self.assertEqual(reloaded.strategy_config.version, "0.1.1")
            self.assertEqual(reloaded.strategy_config.source, "local")
            self.assertEqual(reloaded.strategy_config.parameters["min_score"], 75)
            self.assertEqual(reloaded.strategy_config.recent_changes[0].action, "apply")

            self.assertTrue(service.reset_strategy_config())
            reset = _build_service(root, strategy_store=store).build_first_slice_snapshot()
            self.assertEqual(reset.strategy_config.version, "0.1.0")
            self.assertEqual(reset.strategy_config.source, "default")
            self.assertEqual(reset.strategy_config.parameters["min_score"], 70)
            self.assertEqual(reset.strategy_config.recent_changes[0].action, "reset")

    def test_signal_scan_policy_filters_to_executable_focus(self) -> None:
        report = SignalScanPolicy().build_report(
            opportunities=sample_opportunity_candidates(),
            strategy_config=sample_strategy_config(),
            universe_size=218,
            report_id="scan-test",
        )

        self.assertEqual(report.universe_size, 218)
        self.assertEqual(report.candidate_count, 2)
        self.assertEqual(report.focus_opportunity.symbol, "600001")
        self.assertEqual(len(report.ranked_opportunities), 3)
        self.assertGreaterEqual(len(report.watch_notes), 1)

    def test_domain_messages_load_from_json_config(self) -> None:
        config_path = Path("server/firemoney_server/domain/messages/zh_CN.json")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        messages = load_domain_messages()

        self.assertIn("execution", payload)
        self.assertIn("outcome", payload)
        self.assertEqual(
            messages.text("execution", "confirmation_waiting"),
            payload["execution"]["confirmation_waiting"],
        )
        self.assertIn(
            "25.00",
            messages.format(
                "outcome",
                "floating_summary",
                current_price=12.68,
                pnl=25.0,
                pnl_pct=0.0201,
            ),
        )

    def test_sample_trading_data_comes_from_json_config(self) -> None:
        config_path = Path(
            "server/firemoney_server/infrastructure/config/sample_trading_data.zh_CN.json"
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["market_context"]["trade_date"], "2026-05-01")
        self.assertEqual(payload["opportunities"][0]["symbol"], "600001")
        self.assertEqual(payload["strategy_config"]["parameters"]["min_score"], 70)
        self.assertEqual(payload["current_prices"]["600001"], 12.68)
        self.assertEqual(sample_market_context().summary, payload["market_context"]["summary"])
        self.assertEqual(
            sample_opportunity_candidates()[0].name,
            payload["opportunities"][0]["name"],
        )

    def test_contract_snapshot_is_json_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _build_service(Path(temp_dir)).build_first_slice_snapshot()
            payload = contract_to_dict(snapshot)

            self.assertEqual(payload["market_context"]["risk_level"], "medium")
            self.assertEqual(payload["signal_scan"]["stage"], "signal_scan")
            self.assertEqual(
                payload["order_ticket"]["confirmation_status"],
                "waiting_user",
            )
            self.assertEqual(payload["next_stage"], "order_draft")
            self.assertIsInstance(payload["opportunities"], list)

        with tempfile.TemporaryDirectory() as temp_dir:
            confirmed_payload = contract_to_dict(
                _build_service(Path(temp_dir)).build_first_slice_snapshot(user_confirmed=True)
            )
        self.assertEqual(
            confirmed_payload["execution_receipt"]["status"],
            "prepared",
        )
        self.assertEqual(
            confirmed_payload["execution_receipt"]["route"],
            "csv_export",
        )
        self.assertIsNone(confirmed_payload["fill_execution"])
        self.assertIsNone(confirmed_payload["exit_execution"])
        self.assertIsNone(confirmed_payload["outcome_card"])
        self.assertIsNone(confirmed_payload["archive_record"])
        self.assertEqual(confirmed_payload["recent_archives"], [])

    def test_content_catalog_loads_localizable_client_text(self) -> None:
        content = load_client_content()

        self.assertEqual(len(content.workspaces), 3)
        self.assertTrue(all(item["title"] for item in content.workspaces))
        self.assertIn("app_name", content.labels)
        self.assertIn("market_question", content.sections)
        self.assertIn("no_focus", content.empty_states)
        self.assertIn("shell_labeled_value", content.templates)
        self.assertIn("shell_signal_scan", content.templates)

    def test_client_shell_consumes_snapshot_without_business_logic(self) -> None:
        content = load_client_content()
        adapter = LocalMainChainAdapter()
        shell = FireMoneyShell()

        rendered = shell.render_snapshot(adapter.load_snapshot())

        self.assertEqual(
            shell.workspace_titles(),
            tuple(item["title"] for item in content.workspaces),
        )
        self.assertIn(content.labels["market_judgment"], rendered)
        self.assertIn(content.labels["execution_review"], rendered)
        self.assertIn(content.labels["recap_improvement"], rendered)

    def test_core_workflow_html_renders_three_step_interface(self) -> None:
        content = load_client_content()
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = _build_service(Path(temp_dir)).build_first_slice_snapshot()

            html = render_core_workflow_html(snapshot)

            self.assertIn("FireMoney", html)
            self.assertIn(content.labels["market_judgment"], html)
            self.assertIn(content.labels["execution_review"], html)
            self.assertIn(content.labels["recap_improvement"], html)
            self.assertIn('data-action="confirm-order"', html)
            self.assertIn("waiting_user", html)

    def test_preview_file_can_be_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "core_workflow.html"

            output = build_preview(target)

            self.assertTrue(output.exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("FireMoney", html)
            self.assertIn('data-kind="initial"', html)
            self.assertIn('data-kind="confirmed"', html)
            self.assertIn('data-kind="submitted"', html)
            self.assertIn('data-kind="filled"', html)
            self.assertIn('data-kind="closed"', html)
            self.assertIn('data-kind="adjusted"', html)
            self.assertIn('data-kind="reset"', html)
            self.assertIn('data-action="confirm-order"', html)
            self.assertIn('data-action="import-receipt"', html)
            self.assertIn('data-action="import-fill"', html)
            self.assertIn('data-action="import-exit"', html)
            self.assertIn('data-action="apply-adjustments"', html)
            self.assertIn('data-action="reset-strategy"', html)
            self.assertIn("accepted", html)
            self.assertIn("archive-draft-600001", html)
            self.assertIn("archive-item", html)
            self.assertIn("49.00", html)
            self.assertIn("25.00", html)
            self.assertIn("orders/draft-600001.csv", html)
            self.assertNotIn("AppData/Local/Temp", html)
            self.assertIn("max_position_pct", html)


if __name__ == "__main__":
    unittest.main()
