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
from server.firemoney_server.domain.strategy_config import StrategyConfigPolicy
from server.firemoney_server.infrastructure.archive_store import TradeArchiveStore
from server.firemoney_server.infrastructure.archive_review_export import (
    MarkdownArchiveReviewExporter,
)
from server.firemoney_server.infrastructure.broker_adapter import (
    BrokerExecutionAdapter,
    LocalCsvBrokerAdapter,
)
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
from server.firemoney_server.infrastructure.strategy_audit_export import (
    MarkdownStrategyAuditExporter,
)
from server.firemoney_server.infrastructure.sample_data import (
    sample_market_context,
    sample_opportunity_candidates,
    sample_strategy_config,
)
from server.firemoney_server.infrastructure.strategy_store import StrategyConfigStore
from shared.contracts import (
    AdjustmentStatus,
    ArchiveReviewQuality,
    ConfirmationStatus,
    ExecutionReceiptStatus,
    ExecutionRoute,
    ExitExecution,
    FillExecution,
    OutcomeCard,
    ReviewDecision,
    StrategyAdjustment,
    StrategyBoundaryAction,
    StrategyBoundaryReview,
    TradeArchiveRecord,
    WorkflowStage,
    contract_to_dict,
)


def _build_service(
    root: Path,
    receipt_importer: BrokerReceiptImporter | None = None,
    fill_importer: BrokerFillImporter | None = None,
    strategy_store: StrategyConfigStore | None = None,
    strategy_audit_exporter: MarkdownStrategyAuditExporter | None = None,
    archive_store: TradeArchiveStore | None = None,
    archive_review_exporter: MarkdownArchiveReviewExporter | None = None,
    broker_adapter: BrokerExecutionAdapter | None = None,
) -> MainChainService:
    return MainChainService(
        broker_adapter=broker_adapter,
        order_exporter=CsvOrderExporter(root / "orders"),
        receipt_importer=receipt_importer or BrokerReceiptImporter(root / "receipts"),
        fill_importer=fill_importer or BrokerFillImporter(root / "fills"),
        strategy_store=strategy_store or StrategyConfigStore(root / "strategy_config.json"),
        strategy_audit_exporter=(
            strategy_audit_exporter
            or MarkdownStrategyAuditExporter(root / "strategy_exports")
        ),
        archive_store=archive_store or TradeArchiveStore(root / "trade_archives.json"),
        archive_review_exporter=(
            archive_review_exporter
            or MarkdownArchiveReviewExporter(root / "archive_exports")
        ),
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


def _archive_record(
    archive_id: str,
    symbol: str,
    realized_pnl: float,
    realized_pnl_pct: float,
    outcome: str,
    next_action: str,
) -> TradeArchiveRecord:
    return TradeArchiveRecord(
        archive_id=archive_id,
        order_id=archive_id.replace("archive-", "draft-"),
        symbol=symbol,
        name=f"{outcome} sample",
        trade_date="2026-05-01",
        opened_at="2026-05-01T09:30:00+08:00",
        closed_at="2026-05-01T10:30:00+08:00",
        realized_pnl=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        outcome=outcome,
        signal_summary=f"{outcome} signal",
        risk_summary="risk",
        execution_summary="execution",
        recap_summary="recap",
        next_action=next_action,
        tags=("risk:medium" if outcome == "loss" else "risk:low",),
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

    def test_main_chain_uses_broker_adapter_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)
            _seed_exit_fill(fill_importer)
            broker_adapter = LocalCsvBrokerAdapter(
                order_exporter=CsvOrderExporter(root / "orders"),
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
            )

            snapshot = _build_service(
                root,
                broker_adapter=broker_adapter,
            ).build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
                exit_received=True,
            )

            self.assertEqual(snapshot.execution_receipt.status, ExecutionReceiptStatus.ACCEPTED)
            self.assertIsInstance(snapshot.fill_execution, FillExecution)
            self.assertIsInstance(snapshot.exit_execution, ExitExecution)
            self.assertEqual(snapshot.exit_execution.realized_pnl, 49.0)

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

    def test_trade_archive_review_summarizes_recent_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)
            _seed_exit_fill(fill_importer)
            service = _build_service(
                root,
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
            )
            service.build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
                exit_received=True,
            )

            review = service.build_trade_archive_review()

            self.assertEqual(review.record_count, 1)
            self.assertEqual(review.profit_count, 1)
            self.assertEqual(review.loss_count, 0)
            self.assertEqual(review.flat_count, 0)
            self.assertEqual(
                review.sample_quality,
                ArchiveReviewQuality.INSUFFICIENT_SAMPLE,
            )
            self.assertEqual(
                review.strategy_boundary_action,
                StrategyBoundaryAction.COLLECT_MORE_SAMPLES,
            )
            self.assertEqual(review.win_rate, 1.0)
            self.assertEqual(review.total_realized_pnl, 49.0)
            self.assertEqual(review.average_realized_pnl_pct, 0.0394)
            self.assertEqual(review.best_archive_id, "archive-draft-600001")
            self.assertEqual(review.worst_archive_id, "archive-draft-600001")
            self.assertGreaterEqual(len(review.focus_points), 3)
            self.assertIn("49.00", review.summary)

    def test_trade_archive_review_can_be_exported_as_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            receipt_importer = BrokerReceiptImporter(root / "receipts")
            _seed_broker_receipt(receipt_importer)
            fill_importer = BrokerFillImporter(root / "fills")
            _seed_entry_fill(fill_importer)
            _seed_exit_fill(fill_importer)
            service = _build_service(
                root,
                receipt_importer=receipt_importer,
                fill_importer=fill_importer,
            )
            service.build_first_slice_snapshot(
                user_confirmed=True,
                broker_submitted=True,
                fill_received=True,
                exit_received=True,
            )

            exported = service.export_trade_archive_review()

            self.assertEqual(exported.name, "trade_archive_review.md")
            content = exported.read_text(encoding="utf-8")
            self.assertIn("# Trade Archive Review", content)
            self.assertIn("archive-draft-600001", content)
            self.assertIn("49.00", content)
            self.assertIn("## Focus Points", content)
            self.assertIn("## Sample Quality", content)
            self.assertIn("collect_more_samples", content)

    def test_trade_archive_review_flags_reviewable_loss_sample_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for record in (
                _archive_record(
                    "archive-loss",
                    "600003",
                    -18.0,
                    -0.012,
                    "loss",
                    "review stop discipline",
                ),
                _archive_record(
                    "archive-flat",
                    "600002",
                    0.0,
                    0.0,
                    "flat",
                    "keep watching",
                ),
                _archive_record(
                    "archive-profit",
                    "600001",
                    42.0,
                    0.028,
                    "profit",
                    "keep boundary",
                ),
            ):
                archive_store.save(record)
            service = _build_service(root, archive_store=archive_store)

            review = service.build_trade_archive_review()
            payload = contract_to_dict(review)

            self.assertEqual(review.record_count, 3)
            self.assertEqual(review.profit_count, 1)
            self.assertEqual(review.loss_count, 1)
            self.assertEqual(review.flat_count, 1)
            self.assertEqual(review.sample_quality, ArchiveReviewQuality.REVIEWABLE)
            self.assertEqual(
                review.strategy_boundary_action,
                StrategyBoundaryAction.REVIEW_LOSSES_FIRST,
            )
            self.assertEqual(review.win_rate, 0.3333)
            self.assertEqual(review.total_realized_pnl, 24.0)
            self.assertEqual(review.average_realized_pnl_pct, 0.0053)
            self.assertEqual(review.best_archive_id, "archive-profit")
            self.assertEqual(review.worst_archive_id, "archive-loss")
            self.assertEqual(payload["sample_quality"], "reviewable")
            self.assertEqual(payload["strategy_boundary_action"], "review_losses_first")
            self.assertIn("亏损样本", review.strategy_boundary_note)

    def test_strategy_boundary_review_waits_for_user_after_reviewable_loss_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for record in (
                _archive_record(
                    "archive-loss",
                    "600003",
                    -18.0,
                    -0.012,
                    "loss",
                    "review stop discipline",
                ),
                _archive_record(
                    "archive-flat",
                    "600002",
                    0.0,
                    0.0,
                    "flat",
                    "keep watching",
                ),
                _archive_record(
                    "archive-profit",
                    "600001",
                    42.0,
                    0.028,
                    "profit",
                    "keep boundary",
                ),
            ):
                archive_store.save(record)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store, archive_store=archive_store)

            review = service.build_strategy_boundary_review()
            payload = contract_to_dict(review)

            self.assertIsInstance(review, StrategyBoundaryReview)
            self.assertEqual(review.adjustment_status, AdjustmentStatus.WAITING_USER)
            self.assertEqual(review.source_action, StrategyBoundaryAction.REVIEW_LOSSES_FIRST)
            self.assertEqual(review.sample_quality, ArchiveReviewQuality.REVIEWABLE)
            self.assertEqual(review.blockers, ())
            self.assertEqual(len(review.adjustments), 2)
            self.assertEqual(review.adjustments[0].key, "max_position_pct")
            self.assertEqual(review.adjustments[0].suggested_value, 0.08)
            self.assertEqual(review.adjustments[1].key, "min_score")
            self.assertEqual(review.adjustments[1].suggested_value, 75)
            self.assertFalse(store.path.exists())
            self.assertEqual(payload["adjustment_status"], "waiting_user")
            self.assertEqual(payload["source_action"], "review_losses_first")

    def test_strategy_boundary_review_requires_confirmation_before_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for record in (
                _archive_record(
                    "archive-loss",
                    "600003",
                    -18.0,
                    -0.012,
                    "loss",
                    "review stop discipline",
                ),
                _archive_record(
                    "archive-flat",
                    "600002",
                    0.0,
                    0.0,
                    "flat",
                    "keep watching",
                ),
                _archive_record(
                    "archive-profit",
                    "600001",
                    42.0,
                    0.028,
                    "profit",
                    "keep boundary",
                ),
            ):
                archive_store.save(record)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store, archive_store=archive_store)

            unchanged = service.apply_strategy_boundary_review(confirm=False)

            self.assertEqual(unchanged.version, "0.1.0")
            self.assertEqual(unchanged.parameters["max_position_pct"], 0.12)
            self.assertFalse(store.path.exists())

    def test_confirmed_strategy_boundary_review_persists_adjustments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for record in (
                _archive_record(
                    "archive-loss",
                    "600003",
                    -18.0,
                    -0.012,
                    "loss",
                    "review stop discipline",
                ),
                _archive_record(
                    "archive-flat",
                    "600002",
                    0.0,
                    0.0,
                    "flat",
                    "keep watching",
                ),
                _archive_record(
                    "archive-profit",
                    "600001",
                    42.0,
                    0.028,
                    "profit",
                    "keep boundary",
                ),
            ):
                archive_store.save(record)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store, archive_store=archive_store)

            applied = service.apply_strategy_boundary_review(confirm=True)
            reloaded = _build_service(
                root,
                strategy_store=store,
                archive_store=archive_store,
            ).build_first_slice_snapshot()

            self.assertEqual(applied.adjustment_status, AdjustmentStatus.APPLIED)
            self.assertEqual(applied.version, "0.1.1")
            self.assertEqual(applied.parameters["max_position_pct"], 0.08)
            self.assertEqual(applied.parameters["min_score"], 75)
            self.assertTrue(store.path.exists())
            self.assertEqual(applied.recent_changes[0].action, "apply")
            self.assertIn("归档复查", applied.recent_changes[0].reason)
            self.assertEqual(reloaded.strategy_config.source, "local")
            self.assertEqual(reloaded.strategy_config.parameters["max_position_pct"], 0.08)
            self.assertEqual(reloaded.strategy_config.parameters["min_score"], 75)

    def test_strategy_boundary_audit_exports_current_change_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for record in (
                _archive_record(
                    "archive-loss",
                    "600003",
                    -18.0,
                    -0.012,
                    "loss",
                    "review stop discipline",
                ),
                _archive_record(
                    "archive-flat",
                    "600002",
                    0.0,
                    0.0,
                    "flat",
                    "keep watching",
                ),
                _archive_record(
                    "archive-profit",
                    "600001",
                    42.0,
                    0.028,
                    "profit",
                    "keep boundary",
                ),
            ):
                archive_store.save(record)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store, archive_store=archive_store)
            service.apply_strategy_boundary_review(confirm=True)

            exported = service.export_strategy_boundary_audit()

            self.assertEqual(exported.name, "strategy_boundary_audit.md")
            content = exported.read_text(encoding="utf-8")
            self.assertIn("# Strategy Boundary Audit", content)
            self.assertIn("intraday-mainline-v1", content)
            self.assertIn("0.1.1", content)
            self.assertIn("max_position_pct: 0.12 -> 0.08", content)
            self.assertIn("min_score: 70 -> 75", content)
            self.assertIn("归档复查", content)

    def test_strategy_boundary_audit_exports_reset_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store)
            service.build_first_slice_snapshot(
                user_confirmed=True,
                adjustments_confirmed=True,
            )
            self.assertTrue(service.reset_strategy_config())

            exported = service.export_strategy_boundary_audit()

            content = exported.read_text(encoding="utf-8")
            self.assertIn("reset", content)
            self.assertIn("恢复默认策略边界", content)
            self.assertIn("apply", content)

    def test_confirmed_strategy_boundary_review_skips_blocked_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            archive_store.save(
                _archive_record(
                    "archive-one",
                    "600001",
                    20.0,
                    0.018,
                    "profit",
                    "keep boundary",
                )
            )
            store = StrategyConfigStore(root / "strategy_config.json")
            service = _build_service(root, strategy_store=store, archive_store=archive_store)

            unchanged = service.apply_strategy_boundary_review(confirm=True)

            self.assertEqual(unchanged.version, "0.1.0")
            self.assertEqual(unchanged.parameters["max_position_pct"], 0.12)
            self.assertFalse(store.path.exists())

    def test_strategy_boundary_review_blocks_insufficient_archive_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            archive_store.save(
                _archive_record(
                    "archive-one",
                    "600001",
                    20.0,
                    0.018,
                    "profit",
                    "keep boundary",
                )
            )
            service = _build_service(root, archive_store=archive_store)

            review = service.build_strategy_boundary_review()

            self.assertEqual(review.adjustment_status, AdjustmentStatus.NOT_AVAILABLE)
            self.assertEqual(
                review.source_action,
                StrategyBoundaryAction.COLLECT_MORE_SAMPLES,
            )
            self.assertEqual(
                review.sample_quality,
                ArchiveReviewQuality.INSUFFICIENT_SAMPLE,
            )
            self.assertEqual(review.adjustments, ())
            self.assertGreaterEqual(len(review.blockers), 1)

    def test_strategy_boundary_review_keeps_boundary_for_reviewable_profit_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_store = TradeArchiveStore(root / "trade_archives.json")
            for index, pnl in enumerate((12.0, 20.0, 32.0), start=1):
                archive_store.save(
                    _archive_record(
                        f"archive-profit-{index}",
                        f"60000{index}",
                        pnl,
                        0.01 * index,
                        "profit",
                        "keep boundary",
                    )
                )
            service = _build_service(root, archive_store=archive_store)

            review = service.build_strategy_boundary_review()

            self.assertEqual(review.adjustment_status, AdjustmentStatus.NOT_AVAILABLE)
            self.assertEqual(
                review.source_action,
                StrategyBoundaryAction.KEEP_CURRENT_BOUNDARY,
            )
            self.assertEqual(review.sample_quality, ArchiveReviewQuality.REVIEWABLE)
            self.assertEqual(review.adjustments, ())
            self.assertEqual(review.blockers, ())
            self.assertIn("保留", review.summary)

    def test_empty_trade_archive_review_has_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _build_service(Path(temp_dir))

            review = service.build_trade_archive_review()
            exported = service.export_trade_archive_review()

            self.assertEqual(review.record_count, 0)
            self.assertEqual(review.win_rate, 0.0)
            self.assertEqual(review.sample_quality, ArchiveReviewQuality.EMPTY)
            self.assertEqual(
                review.strategy_boundary_action,
                StrategyBoundaryAction.COLLECT_MORE_SAMPLES,
            )
            self.assertIsNone(review.best_archive_id)
            self.assertIsNone(review.worst_archive_id)
            self.assertTrue(exported.exists())
            self.assertIn(
                "No completed archive records yet.",
                exported.read_text(encoding="utf-8"),
            )

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

    def test_local_strategy_config_is_validated_before_next_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = StrategyConfigStore(root / "strategy_config.json")
            store.path.write_text(
                json.dumps(
                    {
                        "strategy_id": "intraday-mainline-v1",
                        "name": "盘中主线机会",
                        "version": "0.9.0",
                        "risk_profile": "semi_auto_review_required",
                        "parameters": {
                            "min_score": 130,
                            "max_position_pct": 0.8,
                            "confidence_floor": 0.2,
                            "unknown_toggle": "on",
                        },
                        "impact_summary": "unsafe local override",
                        "adjustment_status": "applied",
                        "adjustment_message": "unsafe",
                        "source": "local",
                        "recent_changes": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            snapshot = _build_service(root, strategy_store=store).build_first_slice_snapshot()

            self.assertEqual(snapshot.strategy_config.version, "0.9.0")
            self.assertEqual(snapshot.strategy_config.source, "local")
            self.assertEqual(snapshot.strategy_config.adjustment_status, AdjustmentStatus.NOT_AVAILABLE)
            self.assertEqual(snapshot.strategy_config.parameters["min_score"], 70)
            self.assertEqual(snapshot.strategy_config.parameters["max_position_pct"], 0.12)
            self.assertEqual(snapshot.strategy_config.parameters["confidence_floor"], 0.72)
            self.assertNotIn("unknown_toggle", snapshot.strategy_config.parameters)
            self.assertIn("unknown_toggle", snapshot.strategy_config.impact_summary)

    def test_invalid_strategy_store_file_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = StrategyConfigStore(root / "strategy_config.json")
            store.path.write_text("{", encoding="utf-8")

            snapshot = _build_service(root, strategy_store=store).build_first_slice_snapshot()

            self.assertEqual(snapshot.strategy_config.version, "0.1.0")
            self.assertEqual(snapshot.strategy_config.source, "default")
            self.assertEqual(snapshot.strategy_config.parameters["min_score"], 70)

    def test_strategy_adjustment_policy_filters_invalid_suggestions(self) -> None:
        base_config = sample_strategy_config()
        adjusted = StrategyConfigPolicy().apply_adjustments(
            strategy_config=base_config,
            adjustments=(
                StrategyAdjustment(
                    key="min_score",
                    label="有效评分门槛",
                    current_value=70,
                    suggested_value=75,
                    reason="valid",
                    impact="valid",
                ),
                StrategyAdjustment(
                    key="max_position_pct",
                    label="危险仓位",
                    current_value=0.12,
                    suggested_value=0.9,
                    reason="invalid",
                    impact="invalid",
                ),
                StrategyAdjustment(
                    key="unknown_toggle",
                    label="未知参数",
                    current_value="off",
                    suggested_value="on",
                    reason="invalid",
                    impact="invalid",
                ),
            ),
        )

        self.assertEqual(adjusted.adjustment_status, AdjustmentStatus.APPLIED)
        self.assertEqual(adjusted.parameters["min_score"], 75)
        self.assertEqual(adjusted.parameters["max_position_pct"], 0.12)
        self.assertNotIn("unknown_toggle", adjusted.parameters)

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
