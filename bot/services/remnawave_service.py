"""
Remnawave API client.

This module is intentionally isolated from the rest of the codebase:
- Domain code uses account_id / identities.
- This adapter translates our needs to Remnawave HTTP API.
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class RemnawaveError(RuntimeError):
    pass


@dataclass
class RemnawaveConfig:
    base_url: str
    admin_username: str
    admin_password: str
    api_token: Optional[str] = None  # если задан — используем его для API вместо login
    timeout_seconds: int = 20


def is_remnawave_configured() -> bool:
    """True если Remnawave настроен (используем его как источник подписок)."""
    try:
        load_remnawave_config()
        return True
    except Exception:
        return False


def load_remnawave_config() -> RemnawaveConfig:
    base_url = (os.getenv("REMNAWAVE_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise RemnawaveError("REMNAWAVE_BASE_URL is not set")
    admin_username = (os.getenv("REMNAWAVE_ADMIN_USERNAME") or "").strip()
    admin_password = (os.getenv("REMNAWAVE_ADMIN_PASSWORD") or "").strip()
    api_token = (os.getenv("REMNAWAVE_API_TOKEN") or "").strip() or None
    if not api_token and (not admin_username or not admin_password):
        raise RemnawaveError("REMNAWAVE_API_TOKEN or REMNAWAVE_ADMIN_USERNAME/REMNAWAVE_ADMIN_PASSWORD must be set")
    timeout = os.getenv("REMNAWAVE_TIMEOUT_SECONDS")
    try:
        timeout_seconds = int(timeout) if timeout else 20
    except ValueError:
        timeout_seconds = 20
    return RemnawaveConfig(
        base_url=base_url,
        admin_username=admin_username,
        admin_password=admin_password,
        api_token=api_token,
        timeout_seconds=timeout_seconds,
    )


class RemnawaveClient:
    """
    Minimal Remnawave client used by the bot.

    Auth strategy (per plan): Admin JWT via POST /api/auth/login.
    We re-login automatically on 401.
    """

    def __init__(self, cfg: RemnawaveConfig):
        self.cfg = cfg
        self._session = requests.Session()
        self._admin_jwt: Optional[str] = None
        self._last_login_at: float = 0.0

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        token = self.cfg.api_token or self._admin_jwt
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def login(self, force: bool = False) -> None:
        # Avoid hammering login in tight loops.
        if not force and self._admin_jwt and (time.time() - self._last_login_at) < 30:
            return
        url = f"{self.cfg.base_url}/api/auth/login"
        payload = {"username": self.cfg.admin_username, "password": self.cfg.admin_password}
        r = self._session.post(url, json=payload, timeout=self.cfg.timeout_seconds)
        if r.status_code >= 400:
            raise RemnawaveError(f"Remnawave login failed: HTTP {r.status_code}: {r.text[:300]}")
        data = _safe_json(r)
        # We don't know exact response shape. Common variants:
        # { token: '...' } / { accessToken: '...' } / { jwt: '...' } / { data: { token: '...' } } / { response: { accessToken: '...' } }
        resp = data.get("response") or data.get("data") or {}
        token = (
            data.get("token")
            or data.get("accessToken")
            or data.get("jwt")
            or resp.get("token")
            or resp.get("accessToken")
        )
        if not token or not isinstance(token, str):
            raise RemnawaveError("Remnawave login: cannot find token in response")
        self._admin_jwt = token
        self._last_login_at = time.time()

    def request(self, method: str, path: str, *, json: Any | None = None, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.cfg.base_url}{path}"
        if not self.cfg.api_token:
            self.login()
        r = self._session.request(
            method=method.upper(),
            url=url,
            headers=self._headers(),
            json=json,
            params=params,
            timeout=self.cfg.timeout_seconds,
        )
        if r.status_code == 401 and not self.cfg.api_token:
            # JWT expired/invalid, retry once after re-login.
            self.login(force=True)
            r = self._session.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                json=json,
                params=params,
                timeout=self.cfg.timeout_seconds,
            )
        if r.status_code >= 400:
            raise RemnawaveError(f"Remnawave request failed: {method} {path} HTTP {r.status_code}: {r.text[:300]}")
        return _safe_json(r)

    # ---- High-level methods (minimal) ----

    def get_user_by_telegram_id(self, telegram_id: str) -> dict[str, Any] | None:
        telegram_id = str(telegram_id)
        data = self.request("GET", f"/api/users/by-telegram-id/{telegram_id}")
        return _unwrap_optional_object(data)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        uname = (username or "").strip()
        if not uname:
            return None
        data = self.request("GET", f"/api/users/by-username/{uname}")
        return _unwrap_optional_object(data)

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Create user in Remnawave.
        Payload shape is Remnawave-specific; we pass it through.
        Returns unwrapped user object (supports response/obj/data wrappers).
        """
        data = self.request("POST", "/api/users", json=payload)
        unwrapped = _unwrap_optional_object(data)
        if unwrapped is not None:
            return unwrapped
        return data

    def patch_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", "/api/users", json=payload)

    def delete_user(self, user_uuid: str) -> None:
        """
        Удаляет пользователя в Remnawave (подписка аннулируется).
        При 404 (User not found) не бросает исключение — считаем успехом.
        """
        if not user_uuid:
            return
        path = f"/api/users/{user_uuid}"
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.cfg.base_url}{path}"
        if not self.cfg.api_token:
            self.login()
        r = self._session.delete(url, headers=self._headers(), timeout=self.cfg.timeout_seconds)
        if r.status_code == 401 and not self.cfg.api_token:
            self.login(force=True)
            r = self._session.delete(url, headers=self._headers(), timeout=self.cfg.timeout_seconds)
        if r.status_code == 404:
            logger.info("Remnawave user %s already deleted (404)", user_uuid)
            return
        if r.status_code >= 400:
            raise RemnawaveError(f"Remnawave DELETE {path} HTTP {r.status_code}: {r.text[:300]}")

    def get_sub_info(self, short_uuid: str) -> dict[str, Any]:
        return self.request("GET", f"/api/sub/{short_uuid}/info")

    def get_sub_raw(self, short_uuid: str) -> str:
        # Some endpoints return plain text (subscription) rather than JSON.
        if not short_uuid:
            raise RemnawaveError("shortUuid is required")
        url = f"{self.cfg.base_url}/api/sub/{short_uuid}"
        if not self.cfg.api_token:
            self.login()
        r = self._session.get(url, headers=self._headers(), timeout=self.cfg.timeout_seconds)
        if r.status_code == 401 and not self.cfg.api_token:
            self.login(force=True)
            r = self._session.get(url, headers=self._headers(), timeout=self.cfg.timeout_seconds)
        if r.status_code >= 400:
            raise RemnawaveError(f"Remnawave sub fetch failed: HTTP {r.status_code}: {r.text[:300]}")
        return r.text

    def update_user_expiry(
        self,
        user_uuid: str,
        expire_at_unix_ts: int,
        device_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Set user subscription expiry (and optionally device limit).
        expire_at_unix_ts: Unix timestamp in seconds.
        Remnawave expects expireAt as ISO 8601 string.
        """
        expire_at_iso = datetime.datetime.utcfromtimestamp(expire_at_unix_ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload: dict[str, Any] = {
            "uuid": user_uuid,
            "expireAt": expire_at_iso,
        }
        if device_limit is not None:
            payload["deviceLimit"] = device_limit
        return self.patch_user(payload)

    def extend_user_by_days(
        self,
        user_uuid: str,
        short_uuid: str,
        add_days: int,
        device_limit: Optional[int] = None,
    ) -> int:
        """
        Add days to current expiry. Returns new expiry Unix timestamp (seconds).
        If current expiry cannot be read, uses current time as base.
        """
        now_ts = int(time.time())
        base_ts = now_ts
        try:
            from .subscription_service import _parse_expiry_to_timestamp
            info = self.get_sub_info(short_uuid)
            obj = info.get("obj") or info.get("data") or info
            raw_exp = obj.get("expiresAt") or obj.get("expires_at") or obj.get("expiryTime") or 0
            exp_ts = _parse_expiry_to_timestamp(raw_exp)
            if exp_ts > 0:
                base_ts = max(exp_ts, now_ts)
        except Exception as e:
            logger.warning("Remnawave get_sub_info for extend failed, using now: %s", e)
        new_expiry = base_ts + add_days * 24 * 60 * 60
        self.update_user_expiry(user_uuid, new_expiry, device_limit=device_limit)
        return new_expiry


def _safe_json(r: requests.Response) -> dict[str, Any]:
    try:
        data = r.json()
    except Exception as e:
        raise RemnawaveError(f"Remnawave expected JSON, got non-JSON: {e}; body={r.text[:300]}")
    if not isinstance(data, dict):
        raise RemnawaveError("Remnawave expected JSON object response")
    return data


def _unwrap_optional_object(data: dict[str, Any]) -> dict[str, Any] | None:
    # Heuristics for APIs that wrap response:
    # { success: true, obj: {...} } / { data: {...} } / { response: {...} } / { user: {...} }
    if data.get("success") is False:
        return None
    for k in ("response", "obj", "data", "user"):
        v = data.get(k)
        if isinstance(v, dict):
            return v
        if v is None:
            # If explicitly null, treat as not found
            return None
    # Sometimes API returns object directly (not wrapped)
    if any(k in data for k in ("uuid", "id", "shortUuid", "username", "telegramId")):
        return data
    return None

