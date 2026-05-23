"""Feishu notification adapter."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable
from urllib import request
from urllib.error import URLError
from urllib.parse import quote

from server.firemoney_server.application.notification_rich_text import (
    feishu_message_card,
)
from shared.contracts import FeishuNotificationResult, NotificationStatus


class FeishuNotifier:
    """Sends text notifications through Feishu webhook or app bot APIs."""

    def __init__(
        self,
        enabled_env: str = "FEISHU_ENABLED",
        webhook_env: str = "FEISHU_WEBHOOK_URL",
        secret_env: str = "FEISHU_WEBHOOK_SECRET",
        app_id_env: str = "FEISHU_APP_ID",
        app_secret_env: str = "FEISHU_APP_SECRET",
        receive_id_env: str = "FEISHU_RECEIVE_ID",
        receive_id_type_env: str = "FEISHU_RECEIVE_ID_TYPE",
        api_base_url_env: str = "FEISHU_API_BASE_URL",
        retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        self._enabled_env = enabled_env
        self._webhook_env = webhook_env
        self._secret_env = secret_env
        self._app_id_env = app_id_env
        self._app_secret_env = app_secret_env
        self._receive_id_env = receive_id_env
        self._receive_id_type_env = receive_id_type_env
        self._api_base_url_env = api_base_url_env
        self._retry_attempts = max(1, retry_attempts)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._sleep_func = sleep_func or time.sleep

    def notify(self, title: str, message: str) -> FeishuNotificationResult:
        enabled = os.environ.get(self._enabled_env, "").lower() == "true"
        webhook = os.environ.get(self._webhook_env, "")
        app_configured = self._app_configured()
        if not enabled:
            return FeishuNotificationResult(
                status=NotificationStatus.DISABLED,
                title=title,
                message=message,
                webhook_configured=bool(webhook or app_configured),
            )
        if webhook:
            return self._notify_webhook(title, message, webhook)
        if app_configured:
            return self._notify_app(title, message)
        return FeishuNotificationResult(
            status=NotificationStatus.PREPARED,
            title=title,
            message=message,
            webhook_configured=False,
            error=(
                "FEISHU_WEBHOOK_URL or "
                "FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_RECEIVE_ID is not configured"
            ),
        )

    def _notify_webhook(
        self,
        title: str,
        message: str,
        webhook: str,
    ) -> FeishuNotificationResult:
        payload = self._webhook_payload(title, message, rich=True)
        try:
            self._post_json(webhook, payload)
        except Exception as exc:
            text_payload = self._webhook_payload(title, message, rich=False)
            try:
                self._post_json(webhook, text_payload)
            except Exception as text_exc:
                return FeishuNotificationResult(
                    status=NotificationStatus.FAILED,
                    title=title,
                    message=message,
                    webhook_configured=True,
                    error=f"{exc}; fallback text failed: {text_exc}",
                )
        return FeishuNotificationResult(
            status=NotificationStatus.SENT,
            title=title,
            message=message,
            webhook_configured=True,
        )

    def _notify_app(self, title: str, message: str) -> FeishuNotificationResult:
        try:
            token = self._tenant_access_token()
            receive_id_type = (
                os.environ.get(self._receive_id_type_env, "").strip() or "chat_id"
            )
            send_url = (
                f"{self._api_base_url()}/open-apis/im/v1/messages"
                f"?receive_id_type={quote(receive_id_type)}"
            )
            self._post_json(
                send_url,
                {
                    "receive_id": self._receive_id(),
                    "msg_type": "interactive",
                    "content": json.dumps(
                        feishu_message_card(title, message),
                        ensure_ascii=False,
                    ),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception as exc:
            return FeishuNotificationResult(
                status=NotificationStatus.FAILED,
                title=title,
                message=message,
                webhook_configured=True,
                error=str(exc),
            )
        return FeishuNotificationResult(
            status=NotificationStatus.SENT,
            title=title,
            message=message,
            webhook_configured=True,
        )

    def _webhook_payload(
        self,
        title: str,
        message: str,
        rich: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object]
        if rich:
            payload = {
                "msg_type": "interactive",
                "card": feishu_message_card(title, message),
            }
        else:
            payload = {
                "msg_type": "text",
                "content": {"text": f"{title}\n{message}"},
            }
        secret = os.environ.get(self._secret_env, "")
        if secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = self._sign(timestamp, secret)
        return payload

    def _tenant_access_token(self) -> str:
        payload = self._post_json(
            f"{self._api_base_url()}/open-apis/auth/v3/tenant_access_token/internal",
            {
                "app_id": os.environ.get(self._app_id_env, ""),
                "app_secret": os.environ.get(self._app_secret_env, ""),
            },
        )
        token = str(payload.get("tenant_access_token") or "")
        if not token:
            raise URLError("Feishu tenant_access_token is missing")
        return token

    def _post_json(
        self,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                return self._post_json_once(url, payload, headers=headers)
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_post_error(exc):
                    raise
                if attempt >= self._retry_attempts - 1:
                    raise
                if self._retry_delay_seconds:
                    self._sleep_func(self._retry_delay_seconds)
        if last_error:
            raise last_error
        raise URLError("Feishu post failed without response")

    def _post_json_once(
        self,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        req = request.Request(
            url,
            data=data,
            headers=request_headers,
            method="POST",
        )
        with request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status >= 400:
                raise URLError(f"HTTP {response.status}")
            response_error = self._response_error(body)
            if response_error:
                raise URLError(response_error)
            return json.loads(body) if body.strip() else {}

    def _is_retryable_post_error(self, exc: Exception) -> bool:
        if isinstance(exc, URLError):
            reason = getattr(exc, "reason", None)
            return isinstance(reason, (OSError, TimeoutError))
        return isinstance(exc, (OSError, TimeoutError))

    def _response_error(self, body: str) -> str | None:
        if not body.strip():
            return "empty Feishu response"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return "invalid Feishu response JSON"
        if not isinstance(payload, dict):
            return "invalid Feishu response JSON"
        return self._payload_error(payload)

    def _payload_error(self, payload: dict[str, object]) -> str | None:
        success_fields = (
            payload.get("StatusCode"),
            payload.get("code"),
            payload.get("errcode"),
        )
        if any(value in (0, "0") for value in success_fields):
            return None
        if not any(value is not None for value in success_fields):
            status_message = str(payload.get("StatusMessage", "")).lower()
            if status_message == "success":
                return None

        message = (
            payload.get("StatusMessage")
            or payload.get("msg")
            or payload.get("errmsg")
            or "unknown error"
        )
        code = next((value for value in success_fields if value is not None), "unknown")
        return f"Feishu response code {code}: {message}"

    def _app_configured(self) -> bool:
        return bool(
            os.environ.get(self._app_id_env, "").strip()
            and os.environ.get(self._app_secret_env, "").strip()
            and self._receive_id()
        )

    def _receive_id(self) -> str:
        return (
            os.environ.get(self._receive_id_env, "").strip()
            or os.environ.get("FEISHU_OPEN_CHAT_ID", "").strip()
        )

    def _api_base_url(self) -> str:
        return (
            os.environ.get(self._api_base_url_env, "").strip()
            or "https://open.feishu.cn"
        ).rstrip("/")

    def _sign(self, timestamp: str, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")
