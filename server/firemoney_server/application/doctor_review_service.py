"""Runtime readiness checks for the FireMoney one-to-two loop."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from queue import Empty, Queue
from threading import Thread
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from server.firemoney_server.domain.one_to_two_types import OneToTwoMarketRow
from shared.contracts import (
    NotificationStatus,
    OneToTwoDoctorCheck,
    OneToTwoDoctorReport,
    PaperAccount,
    TradingDayContext,
)


class DoctorSettingsLike(Protocol):
    min_score: float
    max_execution_score: float
    initial_cash: float
    max_position_pct: float
    small_account_mode_enabled: bool
    small_account_min_lot_shares: int
    small_account_target_position_pct: float
    small_account_max_position_pct: float
    max_daily_trades: int
    min_confirm_open_pct: float
    max_confirm_open_pct: float
    morning_time: str
    end_of_day_time: str


class MarketDataProviderLike(Protocol):
    def load_one_to_two_rows(self, trade_date: str) -> tuple[OneToTwoMarketRow, ...]:
        """Load the daily one-to-two market rows for one trade date."""


class PathStoreLike(Protocol):
    path: Path


class PaperStoreLike(PathStoreLike, Protocol):
    def load(self) -> PaperAccount:
        """Load the local paper-trading account."""


class NotificationStoreLike(PathStoreLike, Protocol):
    def load(self) -> tuple[object, ...]:
        """Load local notification audit records."""


class SchedulerStateStoreLike(PathStoreLike, Protocol):
    def load(self) -> tuple[object, ...]:
        """Load local scheduler state."""


class SchedulerRunStoreLike(PathStoreLike, Protocol):
    def load(self, limit: int = 1) -> tuple[object, ...]:
        """Load recent scheduler run audits."""


class DoctorReviewService:
    """Builds local readiness checks without sending notifications or mutating state."""

    def __init__(
        self,
        *,
        settings: DoctorSettingsLike,
        market_data_provider: MarketDataProviderLike,
        paper_store: PaperStoreLike,
        notification_store: NotificationStoreLike,
        scheduler_state_store: SchedulerStateStoreLike,
        scheduler_run_store: SchedulerRunStoreLike,
    ) -> None:
        self._settings = settings
        self._market_data_provider = market_data_provider
        self._paper_store = paper_store
        self._notification_store = notification_store
        self._scheduler_state_store = scheduler_state_store
        self._scheduler_run_store = scheduler_run_store

    def build_report(
        self,
        *,
        trade_context: TradingDayContext,
        beta: bool = False,
        skip_market_data: bool = False,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoDoctorReport:
        checks = (
            self._doctor_strategy_check(),
            self._doctor_trading_day_check(trade_context, beta=beta),
            (
                self._doctor_market_data_plan_check(trade_context.trade_date)
                if skip_market_data
                else self._doctor_market_data_check(
                    trade_context.trade_date,
                    timeout_seconds=market_data_timeout_seconds,
                )
            ),
            self._doctor_paper_store_check(),
            self._doctor_notification_store_check(),
            self._doctor_scheduler_state_store_check(),
            self._doctor_feishu_check(trade_context.trade_date, beta=beta),
            self._doctor_scheduler_check(),
            self._doctor_scheduler_run_store_check(),
        )
        has_blocked = any(check.status == "blocked" for check in checks)
        has_warning = any(check.status == "warning" for check in checks)
        status = "blocked" if has_blocked else ("warning" if has_warning else "ready")
        summary = (
            "主线首板运行体检未通过，先修复阻断项再启动模拟盘。"
            if status == "blocked"
            else (
                "主线首板运行体检有可选项未就绪，核心模拟盘可以继续。"
                if status == "warning"
                else "主线首板运行体检通过，可以按早盘、盘中、尾盘主线运行。"
            )
        )
        return OneToTwoDoctorReport(
            report_id=f"one-to-two-doctor-{trade_context.trade_date}",
            trade_date=trade_context.trade_date,
            status=status,
            summary=summary,
            checks=checks,
            next_action=(
                "修复 blocked 检查项后再运行 morning/watch/schedule。"
                if status == "blocked"
                else "继续按 morning -> watch -> eod -> stability 验证主线首板。"
            ),
        )

    def build_feishu_check(
        self,
        *,
        trade_date: str,
        beta: bool = False,
    ) -> OneToTwoDoctorCheck:
        return self._doctor_feishu_check(trade_date, beta=beta)

    def has_feishu_delivery_config(self) -> bool:
        return self._has_feishu_delivery_config()

    def _doctor_strategy_check(self) -> OneToTwoDoctorCheck:
        settings = self._settings
        valid = (
            settings.min_score > 0
            and (
                settings.max_execution_score <= 0
                or settings.max_execution_score > settings.min_score
            )
            and settings.initial_cash > 0
            and 0 < settings.max_position_pct <= 1
            and settings.max_daily_trades >= 1
            and 0 <= settings.min_confirm_open_pct <= settings.max_confirm_open_pct < 0.095
        )
        return OneToTwoDoctorCheck(
            check_id="strategy_config",
            label="主线首板策略配置",
            status="ready" if valid else "blocked",
            detail=(
                f"min_score={settings.min_score:g}, "
                f"execution_score={settings.min_score:g}-"
                f"{settings.max_execution_score:g}, "
                f"initial_cash={settings.initial_cash:.2f}, "
                f"max_position_pct={settings.max_position_pct:.0%}, "
                f"small_account={'on' if settings.small_account_mode_enabled else 'off'}, "
                f"lot={settings.small_account_min_lot_shares}, "
                f"target={settings.small_account_target_position_pct:.0%}, "
                f"small_max={settings.small_account_max_position_pct:.0%}, "
                f"max_daily_trades={settings.max_daily_trades}, "
                f"confirm_open={self._format_pct(settings.min_confirm_open_pct)}-"
                f"{self._format_pct(settings.max_confirm_open_pct)}"
            ),
            next_action=(
                "配置有效，继续保持单一主线首板主线。"
                if valid
                else "修复 one_to_two_strategy JSON 后再运行策略。"
            ),
        )

    def _doctor_trading_day_check(
        self,
        trade_context: TradingDayContext,
        beta: bool = False,
    ) -> OneToTwoDoctorCheck:
        if trade_context.is_trading_day:
            return OneToTwoDoctorCheck(
                check_id="trading_day",
                label="交易日",
                status="ready",
                detail=f"{trade_context.requested_date} 是 A 股交易日。",
                next_action="可以按当日主线首板主线运行。",
            )
        return OneToTwoDoctorCheck(
            check_id="trading_day",
            label="交易日",
            status="blocked" if beta else "warning",
            detail=(
                f"{trade_context.requested_date} 非交易日，"
                f"当前只解析到上一交易日 {trade_context.trade_date}。"
            ),
            next_action=(
                "模拟盘 Beta 只在真实交易日启动；如需演示请指定交易日并使用 --sample-data。"
                if beta
                else "非交易日不会触发 schedule 实际交易任务，可指定交易日做本地演示。"
            ),
        )

    def _doctor_market_data_check(
        self,
        trade_date: str,
        timeout_seconds: float,
    ) -> OneToTwoDoctorCheck:
        if importlib.util.find_spec("akshare") is None and hasattr(
            self._market_data_provider,
            "__class__",
        ):
            provider_name = self._market_data_provider.__class__.__name__
            if provider_name == "AkshareMarketDataProvider":
                return OneToTwoDoctorCheck(
                    check_id="market_data",
                    label="行情源",
                    status="blocked",
                    detail="AkShare 未安装，真实行情入口不可用。",
                    next_action="运行 python -m pip install -r requirements.txt 后重新执行 doctor。",
                )
        try:
            rows = self._load_market_rows_for_doctor(
                trade_date,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="market_data",
                label="行情源",
                status="blocked",
                detail=f"无法读取 {trade_date} 主线首板行情：{exc}",
                next_action="检查 AkShare 网络、接口可用性，或改用 --sample-data 预览。",
            )
        return OneToTwoDoctorCheck(
            check_id="market_data",
            label="行情源",
            status="ready" if rows else "warning",
            detail=f"{trade_date} 已读取 {len(rows)} 条候选原始行。",
            next_action=(
                "行情源可用。"
                if rows
                else "数据可读但没有候选，盘前继续观察或换交易日验证。"
            ),
        )

    def _doctor_market_data_plan_check(self, trade_date: str) -> OneToTwoDoctorCheck:
        return OneToTwoDoctorCheck(
            check_id="market_data",
            label="行情源",
            status="ready",
            detail=(
                f"{trade_date} 计划模式未读取实时行情；"
                "真实行情门禁由 beta-check 和 beta-start 执行。"
            ),
            next_action="盘前运行 beta-check，确认 AkShare 可读且飞书 sent 后再启动 beta-start。",
        )

    def _doctor_paper_store_check(self) -> OneToTwoDoctorCheck:
        try:
            account = self._paper_store.load()
            self._ensure_parent_directory(self._paper_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="paper_store",
                label="模拟盘账本",
                status="blocked",
                detail=f"账本读取失败：{exc}",
                next_action="修复 .firemoney/paper_trades.json 权限或内容后再运行。",
            )
        return OneToTwoDoctorCheck(
            check_id="paper_store",
            label="模拟盘账本",
            status="ready",
            detail=(
                f"equity={account.equity:.2f}, "
                f"positions={len(account.positions)}, "
                f"closed_samples={len(account.closed_trades)}"
            ),
            next_action="账本可用，继续用事件驱动模拟盘记录样本。",
        )

    def _doctor_notification_store_check(self) -> OneToTwoDoctorCheck:
        try:
            records = self._notification_store.load()
            self._ensure_parent_directory(self._notification_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="notification_store",
                label="通知归档",
                status="blocked",
                detail=f"无法读取或准备 {self._notification_store.path}：{exc}",
                next_action="修复 .firemoney/notifications.json 权限或路径后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="notification_store",
            label="通知归档",
            status="ready",
            detail=f"通知归档可读写，recent_records={len(records)}。",
            next_action="值守后用 notifications 查看飞书触达记录。",
        )

    def _doctor_scheduler_state_store_check(self) -> OneToTwoDoctorCheck:
        try:
            completed = self._scheduler_state_store.load()
            self._ensure_parent_directory(self._scheduler_state_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="scheduler_state",
                label="调度状态",
                status="blocked",
                detail=f"无法读取或准备 {self._scheduler_state_store.path}：{exc}",
                next_action="修复 .firemoney/scheduler_state.json 权限或路径后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="scheduler_state",
            label="调度状态",
            status="ready",
            detail=f"调度状态可读写，completed_tasks={len(completed)}。",
            next_action="状态可用，schedule --loop 不会重复触发同日任务。",
        )

    def _doctor_feishu_check(
        self,
        trade_date: str,
        beta: bool = False,
    ) -> OneToTwoDoctorCheck:
        enabled = os.environ.get("FEISHU_ENABLED", "").lower() == "true"
        webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
        webhook_configured = bool(webhook)
        app_configured = self._has_feishu_app_config()
        app_partial = self._has_feishu_app_partial_config()
        if enabled and not webhook_configured and not app_configured:
            status = "blocked" if beta else "warning"
            detail = "FEISHU_ENABLED=true，但飞书 webhook 或应用机器人配置不完整。"
            next_action = (
                "模拟盘 Beta 必须配置 FEISHU_WEBHOOK_URL，或者 FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_RECEIVE_ID。"
                if beta
                else "配置飞书 webhook 或应用机器人，或运行时使用 --no-notify。"
            )
            if app_partial:
                detail = "飞书应用机器人环境变量已部分配置，但缺少必需项。"
        elif enabled and webhook_configured:
            valid_webhook = self._is_feishu_webhook(webhook)
            if not valid_webhook:
                status = "blocked" if beta else "warning"
                detail = "FEISHU_WEBHOOK_URL 不是有效的飞书群机器人 webhook。"
                next_action = "使用 https://open.feishu.cn/open-apis/bot/v2/hook/... 格式的群机器人地址。"
            elif beta and not self._has_sent_feishu_test(trade_date):
                status = "blocked"
                detail = "飞书通知已配置，但当前交易日还没有 feishu-test sent 记录。"
                next_action = "先运行 feishu-test 并确认返回 sent，再重新执行 doctor --beta。"
            else:
                status = "ready"
                detail = "飞书通知已启用，webhook 已配置。"
                next_action = (
                    "飞书联通已验证，可以进入 Beta 值守。"
                    if beta
                    else "盘前先用 feishu-test 验证消息能到群。"
                )
        elif enabled and app_configured:
            if beta and not self._has_sent_feishu_test(trade_date):
                status = "blocked"
                detail = "飞书应用机器人已配置，但当前交易日还没有 feishu-test sent 记录。"
                next_action = "先运行 feishu-test 并确认返回 sent，再重新执行 doctor --beta。"
            else:
                status = "ready"
                detail = "飞书应用机器人已配置，receive_id 已配置。"
                next_action = (
                    "飞书联通已验证，可以进入 Beta 值守。"
                    if beta
                    else "盘前先用 feishu-test 验证消息能到群。"
                )
        elif beta:
            status = "blocked"
            detail = "模拟盘 Beta 需要飞书值守，但 FEISHU_ENABLED 未开启。"
            next_action = "设置 FEISHU_ENABLED=true 和飞书 webhook 或应用机器人后重新执行 doctor --beta。"
        else:
            status = "warning"
            detail = "飞书通知未启用，策略仍会生成 prepared 通知结果。"
            next_action = "模拟盘 Beta 必须设置 FEISHU_ENABLED=true 和飞书通知凭据后再值守。"
        return OneToTwoDoctorCheck(
            check_id="feishu",
            label="飞书通知",
            status=status,
            detail=detail,
            next_action=next_action,
        )

    def _doctor_scheduler_check(self) -> OneToTwoDoctorCheck:
        return OneToTwoDoctorCheck(
            check_id="scheduler",
            label="本地调度",
            status="ready",
            detail=(
                f"早盘 {self._settings.morning_time}, "
                "盘中 scan/auction/open/risk, "
                f"尾盘 {self._settings.end_of_day_time}"
            ),
            next_action="可以手动运行 schedule，也可以用 --loop 常驻观察。",
        )

    def _doctor_scheduler_run_store_check(self) -> OneToTwoDoctorCheck:
        try:
            records = self._scheduler_run_store.load(limit=1)
            self._ensure_parent_directory(self._scheduler_run_store.path)
        except Exception as exc:
            return OneToTwoDoctorCheck(
                check_id="scheduler_runs",
                label="调度审计",
                status="blocked",
                detail=f"无法读取或准备 {self._scheduler_run_store.path}：{exc}",
                next_action="修复 .firemoney 目录权限后再启动 Beta 值守。",
            )
        return OneToTwoDoctorCheck(
            check_id="scheduler_runs",
            label="调度审计",
            status="ready",
            detail=f"审计记录可读写，recent_records={len(records)}。",
            next_action="值守后用 scheduler-runs 查看每次调度覆盖情况。",
        )

    def _load_market_rows_with_timeout(
        self,
        trade_date: str,
        timeout_seconds: float,
        timeout_label: str = "AkShare 行情读取",
    ) -> tuple[OneToTwoMarketRow, ...]:
        return self._load_market_rows_for_doctor(
            trade_date,
            timeout_seconds=timeout_seconds,
            timeout_label=timeout_label,
        )

    def _load_market_rows_for_doctor(
        self,
        trade_date: str,
        timeout_seconds: float,
        timeout_label: str = "AkShare 行情体检",
    ) -> tuple[OneToTwoMarketRow, ...]:
        if timeout_seconds <= 0:
            raise TimeoutError(f"{timeout_label}超过 {timeout_seconds:.0f} 秒未返回")
        result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

        def load_rows() -> None:
            try:
                rows = self._market_data_provider.load_one_to_two_rows(trade_date)
                result_queue.put(
                    (
                        "ready",
                        rows,
                    )
                )
            except Exception as exc:
                result_queue.put(("blocked", exc))

        worker = Thread(target=load_rows, daemon=True)
        worker.start()
        try:
            status, payload = result_queue.get(timeout=max(0.1, timeout_seconds))
        except Empty as exc:
            raise TimeoutError(
                f"{timeout_label}超过 {timeout_seconds:.0f} 秒未返回"
            ) from exc
        if status == "blocked":
            if isinstance(payload, Exception):
                raise payload
            raise RuntimeError(str(payload))
        return payload  # type: ignore[return-value]

    @staticmethod
    def _ensure_parent_directory(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.parent.is_dir():
            raise OSError(f"{path.parent} is not a directory")

    @staticmethod
    def _format_pct(value: float) -> str:
        text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
        return f"{text}%"

    def _is_feishu_webhook(self, value: str) -> bool:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme == "https"
            and parsed.netloc in {"open.feishu.cn", "open.larksuite.com"}
            and parsed.path.startswith("/open-apis/bot/v2/hook/")
            and len(parsed.path.rsplit("/", 1)[-1]) > 0
        )

    def _has_feishu_delivery_config(self) -> bool:
        return bool(os.environ.get("FEISHU_WEBHOOK_URL", "").strip()) or self._has_feishu_app_config()

    def _has_feishu_app_config(self) -> bool:
        return bool(
            os.environ.get("FEISHU_APP_ID", "").strip()
            and os.environ.get("FEISHU_APP_SECRET", "").strip()
            and (
                os.environ.get("FEISHU_RECEIVE_ID", "").strip()
                or os.environ.get("FEISHU_OPEN_CHAT_ID", "").strip()
            )
        )

    def _has_feishu_app_partial_config(self) -> bool:
        return any(
            os.environ.get(key, "").strip()
            for key in (
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "FEISHU_RECEIVE_ID",
                "FEISHU_OPEN_CHAT_ID",
            )
        )

    def _has_sent_feishu_test(self, trade_date: str) -> bool:
        return any(
            getattr(record, "workflow", "") == "feishu:test"
            and getattr(record, "trade_date", "") == trade_date
            and getattr(record, "status", NotificationStatus.PREPARED)
            == NotificationStatus.SENT
            for record in self._notification_store.load()
        )


__all__ = ["DoctorReviewService", "DoctorSettingsLike"]
