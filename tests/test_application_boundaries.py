from __future__ import annotations

import ast
import unittest
from pathlib import Path


class ApplicationBoundaryTest(unittest.TestCase):
    def test_main_chain_delegates_strategy_decision_without_legacy_snapshot_logic(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._strategy_decision_service.build_report", source)
        self.assertNotIn("_load_strategy_decision_snapshot", source)
        self.assertNotIn("StrategyDecisionOption(", source)

    def test_main_chain_uses_notification_orchestrator_for_action_filter(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._notification_orchestrator.load_records", source)
        self.assertNotIn("def _is_action_notification", source)
        self.assertNotIn("title.startswith", source)

    def test_main_chain_delegates_paper_decision_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._paper_decision_service.build_report", source)
        self.assertIn("PaperTradingDecisionService", source)
        self.assertNotIn("paper_decision_notification_message", source)
        self.assertNotIn("paper_decision_rules", source)

    def test_main_chain_delegates_end_of_day_review_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._end_of_day_review_service.build_review", source)
        self.assertIn("EndOfDayReviewService", source)
        self.assertNotIn("one_to_two_end_of_day_notification_message", source)
        self.assertNotIn('self._record_notification("eod"', source)

    def test_main_chain_delegates_stability_review_calculation(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._stability_review_service.build_report", source)
        self.assertIn("StabilityReviewService", source)
        self.assertNotIn("def _stability_from_account", source)
        self.assertNotIn("OneToTwoRecentSample(", source)
        self.assertNotIn("def _strategy_boundary_suggestion", source)

    def test_main_chain_delegates_doctor_review_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._doctor_review_service.build_report", source)
        self.assertIn("DoctorReviewService", source)
        self.assertNotIn("def _doctor_strategy_check", source)
        self.assertNotIn("def _doctor_market_data_check", source)
        self.assertNotIn("def _doctor_feishu_check", source)

    def test_main_chain_delegates_morning_report_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._morning_report_service.build_report", source)
        self.assertIn("MorningReportService", source)
        morning_body = source.split("def build_one_to_two_morning_report", 1)[1].split(
            "def run_one_to_two_watch",
            1,
        )[0]
        self.assertNotIn("one_to_two_morning_notification_message", morning_body)
        self.assertNotIn("load_one_to_two_rows", morning_body)

    def test_main_chain_delegates_watch_report_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._watch_report_service.run", source)
        self.assertIn("WatchReportService", source)
        watch_body = source.split("def run_one_to_two_watch", 1)[1].split(
            "def _exit_if_discipline_requires",
            1,
        )[0]
        self.assertNotIn("self._watch_phase_service.run_phase", watch_body)
        self.assertNotIn("record_candidate_event(", watch_body)
        self.assertNotIn("buy_candidate(", watch_body)
        self.assertNotIn("update_risk(", watch_body)

    def test_main_chain_delegates_board_shadow_review_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._board_shadow_review_service.build_report", source)
        self.assertIn("self._board_shadow_review_service.record_sample", source)
        self.assertIn("self._board_shadow_review_service.build_system_report", source)
        self.assertIn("BoardShadowReviewService", source)
        self.assertNotIn("def _to_board_shadow_candidate", source)
        self.assertNotIn("board_shadow_notification_message", source)

    def test_main_chain_delegates_paper_backtest_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._paper_backtest_service.build_report", source)
        self.assertIn("PaperBacktestService", source)
        self.assertNotIn("def _paper_backtest_status", source)
        self.assertNotIn("def _paper_backtest_monthly_stability", source)
        self.assertNotIn("def _paper_backtest_efficiency_candidates", source)

    def test_main_chain_delegates_execution_quality_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._execution_quality_service.build_report", source)
        self.assertIn("ExecutionQualityService", source)
        execution_body = source.split(
            "def build_one_to_two_execution_quality_report",
            1,
        )[1].split("def run_scheduled_limit_up_board_shadow_record", 1)[0]
        self.assertNotIn("load_intraday_bars", execution_body)
        self.assertNotIn("load_tick_snapshots", execution_body)
        self.assertNotIn("entry_momentum_score", execution_body)

    def test_main_chain_delegates_historical_replay_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._historical_replay_service.run_backtest", source)
        self.assertIn("self._historical_replay_service.build_backtest_audit", source)
        self.assertIn("self._historical_replay_service.run_historical_replay", source)
        self.assertIn("HistoricalReplayService", source)
        self.assertNotIn("def _simulate_historical_trade", source)
        self.assertNotIn("def _backtest_data_quality_checks", source)
        self.assertNotIn("def _historical_replay_blocked_report", source)

    def test_main_chain_delegates_board_shadow_execution_adaptation(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._board_shadow_execution_service.build_candidates", source)
        self.assertIn("BoardShadowExecutionService", source)
        self.assertNotIn("def _board_shadow_candidate_to_execution_candidate", source)
        self.assertNotIn("def _board_shadow_entry_blockers", source)
        self.assertNotIn("def _apply_board_shadow_ready_pool_gate", source)
        self.assertNotIn("def _board_shadow_exit_plan", source)

    def test_main_chain_delegates_paper_instruction_building(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._paper_instruction_builder.build_holding_instruction", source)
        self.assertIn("self._paper_instruction_builder.build_trading_instruction", source)
        self.assertIn("PaperInstructionBuilder", source)
        self.assertNotIn("def _build_paper_trading_instruction", source)
        self.assertNotIn("def _build_holding_instruction", source)

    def test_main_chain_delegates_beta_readiness_orchestration(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("self._beta_readiness_service.build_report", source)
        self.assertIn("BetaReadinessService", source)
        self.assertNotIn("def _beta_readiness_skip_reason", source)
        self.assertNotIn("not_ready_preflight_checks = tuple", source)

    def test_main_chain_delegates_paper_runtime_adapters(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("PaperRuntimeService", source)
        self.assertIn("self._paper_runtime_service.account_view_for_trade_date", source)
        self.assertIn("self._paper_runtime_service.guard_contract", source)
        self.assertIn("self._paper_runtime_service.candidate_for_position", source)
        self.assertNotIn("def _paper_account_view_for_trade_date", source)
        self.assertNotIn("def _paper_guard_contract", source)
        self.assertNotIn("def _candidate_for_position", source)

    def test_main_chain_delegates_mainline_continuity_enrichment(self) -> None:
        source = Path("server/firemoney_server/application/main_chain.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("MainlineContinuityService", source)
        self.assertIn(
            "self._mainline_continuity_service.with_live_mainline_continuity",
            source,
        )
        self.assertNotIn("def _with_live_mainline_continuity", source)
        self.assertNotIn("def _replace_candidate_continuity", source)

    def test_notification_orchestrator_keeps_infrastructure_out(self) -> None:
        module = Path(
            "server/firemoney_server/application/notification_orchestrator.py"
        )
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server.infrastructure.feishu_notifier",
            "server.firemoney_server.infrastructure.paper_store",
            "server.firemoney_server.infrastructure.market_data",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_paper_decision_service_keeps_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/paper_decision_service.py")
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
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_end_of_day_review_service_keeps_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/end_of_day_review_service.py")
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
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_stability_review_service_keeps_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/stability_review_service.py")
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
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_doctor_review_service_keeps_client_and_main_chain_out(self) -> None:
        module = Path("server/firemoney_server/application/doctor_review_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_watch_phase_service_keeps_notifications_and_storage_out(self) -> None:
        module = Path("server/firemoney_server/application/watch_phase_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
            "server.firemoney_server.application.one_to_two_notification_text",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_morning_report_service_keeps_client_and_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/morning_report_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_watch_report_service_keeps_client_storage_and_market_data_out(self) -> None:
        module = Path("server/firemoney_server/application/watch_report_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_mainline_continuity_service_keeps_client_and_storage_out(self) -> None:
        module = Path("server/firemoney_server/application/mainline_continuity_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_paper_runtime_service_keeps_client_and_notifications_out(self) -> None:
        module = Path("server/firemoney_server/application/paper_runtime_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
            "server.firemoney_server.application.notification_orchestrator",
            "server.firemoney_server.application.one_to_two_notification_text",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_paper_store_and_database_codecs_stay_in_infrastructure(self) -> None:
        modules = (
            Path("server/firemoney_server/infrastructure/paper_store_codec.py"),
            Path("server/firemoney_server/infrastructure/paper_database_schema.py"),
        )
        for module in modules:
            source = module.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")

            forbidden = (
                "client.desktop",
                "server.firemoney_server.application.main_chain",
                "server.firemoney_server.infrastructure.market_data",
                "server.firemoney_server.infrastructure.feishu_notifier",
            )
            for imported in imports:
                self.assertFalse(imported.startswith(forbidden), imported)

    def test_market_data_keeps_sample_provider_in_dedicated_module(self) -> None:
        source = Path("server/firemoney_server/infrastructure/market_data.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("sample_market_data import", source)
        self.assertNotIn("class SampleMarketDataProvider", source)

    def test_one_to_two_types_stay_data_only(self) -> None:
        module = Path("server/firemoney_server/domain/one_to_two_types.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "shared.contracts",
            "server.firemoney_server.application",
            "server.firemoney_server.infrastructure",
            "client.desktop",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_market_data_uses_domain_types_without_policy_import(self) -> None:
        source = Path("server/firemoney_server/infrastructure/market_data.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("server.firemoney_server.domain.one_to_two_types import", source)
        self.assertNotIn("server.firemoney_server.domain.one_to_two import", source)

    def test_client_render_helpers_keep_server_and_infrastructure_out(self) -> None:
        module = Path("client/desktop/firemoney_client/render_helpers.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "server.firemoney_server",
            "client.desktop.firemoney_client.renderer",
            "client.desktop.firemoney_client.preview",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_board_shadow_review_service_keeps_client_and_main_chain_out(self) -> None:
        module = Path("server/firemoney_server/application/board_shadow_review_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_k92_emotion_liquidity_service_keeps_infrastructure_out(self) -> None:
        module = Path(
            "server/firemoney_server/application/k92_emotion_liquidity_service.py"
        )
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_k92_emotion_liquidity_backtest_service_keeps_runtime_infrastructure_out(self) -> None:
        module = Path(
            "server/firemoney_server/application/k92_emotion_liquidity_backtest_service.py"
        )
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_paper_backtest_service_keeps_runtime_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/paper_backtest_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_missed_opportunity_service_stays_read_only_and_client_free(self) -> None:
        module = Path("server/firemoney_server/application/missed_opportunity_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure.feishu_notifier",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)
        self.assertNotIn("paper_store.save", source)
        self.assertNotIn("notification_store.append", source)
        self.assertNotIn("scheduler_run_store.append", source)
        self.assertNotIn("feishu", source.lower())

    def test_execution_quality_service_keeps_runtime_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/execution_quality_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_historical_replay_service_keeps_client_and_main_chain_out(self) -> None:
        module = Path("server/firemoney_server/application/historical_replay_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_board_shadow_execution_service_keeps_client_and_main_chain_out(self) -> None:
        module = Path("server/firemoney_server/application/board_shadow_execution_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_paper_instruction_builder_keeps_client_storage_and_notifications_out(self) -> None:
        module = Path("server/firemoney_server/application/paper_instruction_builder.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
            "server.firemoney_server.application.notification_orchestrator",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_beta_readiness_service_keeps_client_storage_and_main_chain_out(self) -> None:
        module = Path("server/firemoney_server/application/beta_readiness_service.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_notification_rich_text_keeps_client_and_infrastructure_out(self) -> None:
        module = Path("server/firemoney_server/application/notification_rich_text.py")
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden), imported)

    def test_core_trading_decisions_do_not_import_llm_sdks(self) -> None:
        modules = (
            Path("server/firemoney_server/application/strategy_decision_service.py"),
            Path("server/firemoney_server/application/paper_decision_service.py"),
            Path("server/firemoney_server/application/paper_entry_policy.py"),
            Path("server/firemoney_server/application/paper_exit_policy.py"),
            Path("server/firemoney_server/application/watch_phase_service.py"),
        )
        forbidden_imports = (
            "openai",
            "anthropic",
            "dashscope",
            "zhipuai",
            "moonshot",
            "ollama",
            "langchain",
        )
        for module in modules:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            for imported in imports:
                self.assertFalse(
                    imported.split(".")[0] in forbidden_imports,
                    f"{module} must keep LLM calls outside core trading decisions: {imported}",
                )

    def test_ai_factor_research_gate_stays_shadow_and_sdk_free(self) -> None:
        module = Path("server/firemoney_server/application/ai_factor_research_gate.py")
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        forbidden_prefixes = (
            "client.desktop",
            "server.firemoney_server.infrastructure",
            "server.firemoney_server.application.main_chain",
        )
        forbidden_roots = (
            "openai",
            "anthropic",
            "dashscope",
            "zhipuai",
            "moonshot",
            "ollama",
            "langchain",
        )
        for imported in imports:
            self.assertFalse(imported.startswith(forbidden_prefixes), imported)
            self.assertFalse(imported.split(".")[0] in forbidden_roots, imported)


if __name__ == "__main__":
    unittest.main()
