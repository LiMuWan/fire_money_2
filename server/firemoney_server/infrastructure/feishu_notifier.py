"""Feishu webhook notification adapter."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from urllib import request
from urllib.error import URLError

from shared.contracts import FeishuNotificationResult, NotificationStatus


class FeishuNotifier:
    """Sends text notifications through a Feishu custom bot webhook."""

    def __init__(
        self,
        enabled_env: str = "FEISHU_ENABLED",
        webhook_env: str = "FEISHU_WEBHOOK_URL",
        secret_env: str = "FEISHU_WEBHOOK_SECRET",
    ) -> None:
        self._enabled_env = enabled_env
        self._webhook_env = webhook_env
        self._secret_env = secret_env

    def notify(self, title: str, message: str) -> FeishuNotificationResult:
        enabled = os.environ.get(self._enabled_env, "").lower() == "true"
        webhook = os.environ.get(self._webhook_env, "")
        if not enabled:
            return FeishuNotificationResult(
                status=NotificationStatus.DISABLED,
                title=title,
                message=message,
                webhook_configured=bool(webhook),
            )
        if not webhook:
            return FeishuNotificationResult(
                status=NotificationStatus.PREPARED,
                title=title,
                message=message,
                webhook_configured=False,
                error="FEISHU_WEBHOOK_URL is not configured",
            )
        payload = self._payload(title, message)
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = request.Request(
                webhook,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=8) as response:
                if response.status >= 400:
                    raise URLError(f"HTTP {response.status}")
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

    def _payload(self, title: str, message: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "msg_type": "text",
            "content": {"text": f"{title}\n{message}"},
        }
        secret = os.environ.get(self._secret_env, "")
        if secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = self._sign(timestamp, secret)
        return payload

    def _sign(self, timestamp: str, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")
