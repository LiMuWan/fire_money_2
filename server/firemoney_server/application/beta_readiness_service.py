"""Beta readiness gate orchestration for FireMoney."""

from __future__ import annotations

from collections.abc import Callable

from shared.contracts import (
    FeishuNotificationResult,
    NotificationStatus,
    OneToTwoBetaReadinessReport,
    OneToTwoDoctorCheck,
    OneToTwoDoctorReport,
)


class BetaReadinessService:
    """Runs beta-check gates without knowing scheduler or paper-ledger internals."""

    def __init__(
        self,
        *,
        build_doctor_report: Callable[[str, bool, float], OneToTwoDoctorReport],
        build_feishu_check: Callable[[str, bool], OneToTwoDoctorCheck],
        has_feishu_delivery_config: Callable[[], bool],
        send_feishu_test: Callable[[str, bool], FeishuNotificationResult],
    ) -> None:
        self._build_doctor_report = build_doctor_report
        self._build_feishu_check = build_feishu_check
        self._has_feishu_delivery_config = has_feishu_delivery_config
        self._send_feishu_test = send_feishu_test

    def build_report(
        self,
        *,
        requested_date: str,
        trade_date: str,
        is_trading_day: bool,
        market_data_timeout_seconds: float = 45.0,
    ) -> OneToTwoBetaReadinessReport:
        preflight_report = self._build_doctor_report(
            requested_date,
            False,
            market_data_timeout_seconds,
        )
        not_ready_preflight_checks = tuple(
            check
            for check in preflight_report.checks
            if check.status != "ready" and check.check_id != "feishu"
        )
        feishu_shape_check = self._build_feishu_check(trade_date, False)
        should_send_feishu = (
            is_trading_day
            and not not_ready_preflight_checks
            and feishu_shape_check.status == "ready"
        )
        feishu_test = (
            self._send_feishu_test(trade_date, True)
            if should_send_feishu
            else FeishuNotificationResult(
                status=NotificationStatus.PREPARED,
                title=f"FireMoney 链路测试 | 未发送 | {trade_date}",
                message="今日动作：飞书链路测试未发送，不触发模拟买入或卖出。",
                webhook_configured=self._has_feishu_delivery_config(),
                error=self._skip_reason(
                    is_trading_day,
                    not_ready_preflight_checks,
                    feishu_shape_check,
                ),
            )
        )
        doctor_report = self._build_doctor_report(
            requested_date,
            True,
            market_data_timeout_seconds,
        )
        status = "ready" if doctor_report.status == "ready" else "blocked"
        summary = (
            "模拟盘 Beta 预检通过，可以启动主线首板值守。"
            if status == "ready"
            else "模拟盘 Beta 预检未通过，先修复阻断项再启动值守。"
        )
        return OneToTwoBetaReadinessReport(
            report_id=f"one-to-two-beta-readiness-{trade_date}",
            trade_date=trade_date,
            status=status,
            summary=summary,
            feishu_test=feishu_test,
            doctor_report=doctor_report,
            next_action=(
                "运行 beta-start --loop --interval-seconds 60。"
                if status == "ready"
                else "按 doctor_report.checks 修复 blocked 项后重新运行 beta-check。"
            ),
        )

    @staticmethod
    def _skip_reason(
        is_trading_day: bool,
        not_ready_preflight_checks: tuple[OneToTwoDoctorCheck, ...],
        feishu_shape_check: OneToTwoDoctorCheck,
    ) -> str:
        if not is_trading_day:
            return "non-trading day"
        if not_ready_preflight_checks:
            return f"preflight not ready: {not_ready_preflight_checks[0].check_id}"
        if feishu_shape_check.status != "ready":
            return f"feishu not ready: {feishu_shape_check.detail}"
        return "preflight blocked"


__all__ = ["BetaReadinessService"]
