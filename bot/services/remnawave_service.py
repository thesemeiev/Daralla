"""
Runtime-сервис работы с RemnaWave.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from ..db.remnawave_db import get_binding_by_subscription, upsert_binding

logger = logging.getLogger(__name__)


class RemnaWaveService:
    def __init__(self) -> None:
        self.api_url = (os.getenv("REMNAWAVE_API_URL") or "").rstrip("/")
        self.api_key = (os.getenv("REMNAWAVE_API_KEY") or "").strip()
        self.link_template = (
            os.getenv("REMNAWAVE_SUBSCRIPTION_URL_TEMPLATE")
            or os.getenv("SUBSCRIPTION_URL", "").rstrip("/") + "/sub/{token}"
        )

    def log_runtime_readiness(self) -> None:
        api_ready = bool(self.api_url and self.api_key)
        template_ready = bool(self.link_template)
        logger.info(
            "RemnaWave runtime readiness: api_ready=%s api_url_set=%s api_key_set=%s link_template_set=%s",
            api_ready,
            bool(self.api_url),
            bool(self.api_key),
            template_ready,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_url:
            return {}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.api_url}{path}",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def ensure_active_access(
        self,
        *,
        subscription_id: int,
        user_id: str,
        token: str,
        expires_at: int,
        device_limit: int,
    ) -> bool:
        binding = await get_binding_by_subscription(subscription_id)
        panel_user_id = binding["panel_user_id"] if binding else f"local-{subscription_id}"
        subscription_url = None

        if self.api_url and self.api_key:
            payload = {
                "panel_user_id": panel_user_id,
                "local_user_id": user_id,
                "subscription_id": subscription_id,
                "subscription_token": token,
                "expires_at": expires_at,
                "device_limit": device_limit,
            }
            try:
                result = await self._post("/api/integration/subscription/ensure", payload)
                panel_user_id = str(result.get("panel_user_id") or panel_user_id)
                subscription_url = result.get("subscription_url")
            except Exception as exc:
                logger.error("RemnaWave ensure_access error: %s", exc)
                return False
        elif not self.link_template:
            logger.error("REMNAWAVE_* env is not configured")
            return False

        if not subscription_url and self.link_template:
            subscription_url = self.link_template.format(token=token)

        await upsert_binding(
            subscription_id=subscription_id,
            user_id=user_id,
            panel_user_id=panel_user_id,
            subscription_url=subscription_url,
            now_ts=int(time.time()),
        )
        return True

    async def suspend_access(self, *, subscription_id: int) -> bool:
        binding = await get_binding_by_subscription(subscription_id)
        if not binding:
            return True
        if self.api_url and self.api_key:
            try:
                await self._post(
                    "/api/integration/subscription/suspend",
                    {"panel_user_id": binding["panel_user_id"]},
                )
            except Exception as exc:
                logger.error("RemnaWave suspend_access error: %s", exc)
                return False
        return True

    async def get_subscription_link(self, *, subscription_id: int, token: str) -> str | None:
        binding = await get_binding_by_subscription(subscription_id)
        if self.api_url and self.api_key and binding:
            try:
                result = await self._post(
                    "/api/integration/subscription/link",
                    {"panel_user_id": binding["panel_user_id"]},
                )
                panel_link = result.get("subscription_url")
                if panel_link:
                    return panel_link
            except Exception as exc:
                logger.warning("RemnaWave get_subscription_link fallback: %s", exc)
        if binding and binding.get("subscription_url"):
            return binding["subscription_url"]
        if self.link_template:
            return self.link_template.format(token=token)
        return None

    async def get_usage(self, *, subscription_id: int) -> dict[str, int]:
        binding = await get_binding_by_subscription(subscription_id)
        if self.api_url and self.api_key and binding:
            try:
                result = await self._post(
                    "/api/integration/subscription/usage",
                    {"panel_user_id": binding["panel_user_id"]},
                )
                return {
                    "upload": int(result.get("upload") or 0),
                    "download": int(result.get("download") or 0),
                    "total": int(result.get("total") or 0),
                }
            except Exception as exc:
                logger.warning("RemnaWave get_usage fallback: %s", exc)
        return {"upload": 0, "download": 0, "total": 0}
