"""
Тонкий HTTP-клиент к 3x-ui панели.

Заменяет py3xui: никакой Pydantic-валидации, только raw JSON.
Принимает и возвращает обычные `dict`/`list` — формат, в котором панель
реально отвечает (`/panel/api/inbounds/...`).

Эндпоинты:
    POST /login
    GET  /panel/api/inbounds/list
    GET  /panel/api/inbounds/get/{id}
    POST /panel/api/inbounds/addClient
    POST /panel/api/inbounds/updateClient/{clientId}
    POST /panel/api/inbounds/{id}/delClient/{clientId}
    POST /panel/api/inbounds/{id}/delClientByEmail/{email}
    POST /panel/api/inbounds/onlines

Для каждого протокола панель ожидает разный clientId в URL:
    vmess/vless        -> client.id (UUID)
    trojan/tuic        -> client.password
    shadowsocks        -> client.email
    hysteria/hysteria2 -> client.auth

Важно: Quart (Hypercorn) у нас запускается в отдельном потоке с собственным
asyncio event loop (`asyncio.run(serve(...))`), а бот и фоновые задачи — на
другом loop. Один httpx.AsyncClient нельзя шарить между loop'ами. Поэтому для
каждого event loop хранится свой `_LoopHttpState` (свой AsyncClient и Lock).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class XUiPanelError(Exception):
    """Ошибка от 3x-ui API (panel вернула success=False, либо HTTP/JSON был кривым)."""

    def __init__(self, message: str, *, status: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class _LoopHttpState:
    """Состояние HTTP-сессии для одного asyncio event loop."""

    __slots__ = ("client", "login_lock", "logged_in", "login_ts")

    def __init__(self) -> None:
        self.client: Optional[httpx.AsyncClient] = None
        self.login_lock: Optional[asyncio.Lock] = None
        self.logged_in: bool = False
        self.login_ts: float = 0.0


class XUiPanelClient:
    """
    Прямой HTTP-клиент панели 3x-ui.

    Использование:
        client = XUiPanelClient(host="https://panel:2053/secret_path", login="...", password="...")
        await client.list_inbounds()
        await client.aclose()
    """

    def __init__(
        self,
        *,
        host: str,
        login: str,
        password: str,
        verify_tls: Optional[bool] = None,
        max_retries: Optional[int] = None,
        session_ttl_sec: Optional[float] = None,
    ) -> None:
        self.login = login
        self.password = password
        self.host = host.rstrip("/")
        if verify_tls is None:
            verify_tls = self.host.startswith("https://")
        self._verify_tls = bool(verify_tls)
        timeout_total = max(5.0, _float_env("XUI_HTTP_TIMEOUT_TOTAL", 30.0))
        timeout_connect = max(3.0, _float_env("XUI_HTTP_TIMEOUT_CONNECT", 15.0))
        timeout_pool = max(2.0, _float_env("XUI_HTTP_TIMEOUT_POOL", 10.0))
        self._timeout = httpx.Timeout(timeout_total, connect=timeout_connect, pool=timeout_pool)
        # id(asyncio.AbstractEventLoop) -> состояние; обычно 2 живых loop (бот + webhook thread).
        self._http_by_loop: Dict[int, _LoopHttpState] = {}
        self._max_retries = self._coerce_retries(max_retries)
        self._session_ttl = float(
            session_ttl_sec
            if session_ttl_sec is not None
            else _float_env("XUI_SESSION_TTL_SEC", 1800.0)
        )

    def _loop_http_state(self) -> _LoopHttpState:
        loop = asyncio.get_running_loop()
        key = id(loop)
        st = self._http_by_loop.get(key)
        if st is None:
            st = _LoopHttpState()
            self._http_by_loop[key] = st
        return st

    async def _ensure_http_client(self, st: _LoopHttpState) -> None:
        if st.client is None:
            st.client = httpx.AsyncClient(verify=self._verify_tls, timeout=self._timeout)
            st.logged_in = False
            st.login_ts = 0.0
        if st.login_lock is None:
            st.login_lock = asyncio.Lock()

    @staticmethod
    def _coerce_retries(max_retries: Optional[int]) -> int:
        if max_retries is None:
            try:
                mr = int(os.getenv("XUI_PANEL_MAX_RETRIES", "5"))
            except ValueError:
                mr = 5
        else:
            mr = int(max_retries)
        return max(1, min(mr, 10))

    @staticmethod
    def _should_recreate_client_after_error(exc: BaseException) -> bool:
        if isinstance(exc, (RuntimeError, ValueError)):
            s = str(exc).lower()
            return "different event loop" in s or "bound to a different event loop" in s
        if isinstance(exc, httpx.HTTPError):
            s = str(exc).lower()
            if "client has been closed" in s:
                return True
            if "closed" in s and "client" in s:
                return True
        return False

    async def _recreate_http_client(self, st: _LoopHttpState) -> None:
        if st.client is not None:
            try:
                await st.client.aclose()
            except Exception:
                logger.debug("XUiPanelClient: aclose during recreate failed", exc_info=True)
        st.client = None
        st.login_lock = None
        st.logged_in = False
        st.login_ts = 0.0
        await self._ensure_http_client(st)

    # ---- low-level ---------------------------------------------------------

    def _url(self, path: str) -> str:
        """Собирает абсолютный URL: host + относительный path."""
        path = path.lstrip("/")
        return f"{self.host}/{path}"

    async def aclose(self) -> None:
        """Закрывает httpx-клиент только для текущего event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        key = id(loop)
        st = self._http_by_loop.pop(key, None)
        if st is None:
            return
        if st.client is not None:
            try:
                await st.client.aclose()
            except Exception:
                logger.debug("XUiPanelClient: aclose failed", exc_info=True)
        st.client = None
        st.login_lock = None
        st.logged_in = False

    async def __aenter__(self) -> "XUiPanelClient":
        return self

    async def __aexit__(self, _exc_type, exc, _tb) -> None:
        await self.aclose()

    async def _ensure_login(self) -> None:
        st = self._loop_http_state()
        await self._ensure_http_client(st)
        assert st.login_lock is not None
        now = time.monotonic()
        if st.logged_in and (now - st.login_ts) < self._session_ttl:
            return
        async with st.login_lock:
            now = time.monotonic()
            if st.logged_in and (now - st.login_ts) < self._session_ttl:
                return
            await self._do_login(st)

    async def _relogin(self) -> None:
        st = self._loop_http_state()
        await self._ensure_http_client(st)
        assert st.login_lock is not None
        async with st.login_lock:
            await self._do_login(st)

    async def _do_login(self, st: _LoopHttpState) -> None:
        assert st.client is not None
        url = self._url("login")
        logger.debug("XUiPanelClient: login at %s", _mask_host(self.host))
        resp = await st.client.post(
            url,
            data={"username": self.login, "password": self.password},
            headers={"Accept": "application/json"},
        )
        body = _safe_json(resp)
        if resp.status_code != 200 or (isinstance(body, dict) and not body.get("success", True)):
            msg = (body.get("msg") if isinstance(body, dict) else None) or "login failed"
            raise XUiPanelError(f"3x-ui login failed: {msg}", status=resp.status_code, body=body)
        st.logged_in = True
        st.login_ts = time.monotonic()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        retries: Optional[int] = None,
    ) -> Any:
        """
        Универсальная отправка с релогином при 401 и retry при сетевых ошибках/SQLite-lock.
        Возвращает распарсенный JSON-объект (`obj` поле или весь body, см. ниже).
        """
        st = self._loop_http_state()
        await self._ensure_login()
        assert st.client is not None
        attempts = self._max_retries if retries is None else max(1, int(retries))
        last_exc: Optional[Exception] = None
        url = self._url(path)
        for attempt in range(1, attempts + 1):
            try:
                resp = await st.client.request(
                    method.upper(),
                    url,
                    data=data,
                    json=json_body,
                    headers={"Accept": "application/json"},
                )
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                last_exc = exc
                if self._should_recreate_client_after_error(exc):
                    logger.debug(
                        "XUiPanelClient: %s %s transport/loop issue, recreating client: %s",
                        method,
                        path,
                        exc,
                    )
                    try:
                        await self._recreate_http_client(st)
                        await self._ensure_login()
                        assert st.client is not None
                    except Exception:
                        logger.debug("XUiPanelClient: recreate after error failed", exc_info=True)
                logger.debug(
                    "XUiPanelClient: %s %s network error (attempt %s/%s): %s",
                    method,
                    path,
                    attempt,
                    attempts,
                    exc,
                )
                await asyncio.sleep(min(0.5 * attempt, 4.0))
                continue

            # Сессия истекла — релогин и повтор
            if resp.status_code in (401, 403):
                logger.debug("XUiPanelClient: %s %s -> %s, relogin", method, path, resp.status_code)
                st.logged_in = False
                await self._relogin()
                continue

            body = _safe_json(resp)
            if resp.status_code >= 500:
                last_exc = XUiPanelError(
                    f"3x-ui server error {resp.status_code}",
                    status=resp.status_code,
                    body=body,
                )
                logger.debug("%s", last_exc)
                await asyncio.sleep(min(0.5 * attempt, 4.0))
                continue
            if resp.status_code >= 400:
                raise XUiPanelError(
                    f"3x-ui {method} {path} -> HTTP {resp.status_code}",
                    status=resp.status_code,
                    body=body,
                )

            # Успешный HTTP, дальше смотрим формат панели.
            if isinstance(body, dict) and "success" in body:
                if not body.get("success"):
                    msg = str(body.get("msg") or "panel returned success=false")
                    # SQLite locked -> retry
                    if "database is locked" in msg.lower() and attempt < attempts:
                        last_exc = XUiPanelError(msg, status=resp.status_code, body=body)
                        logger.debug(
                            "XUiPanelClient: %s %s sqlite locked, attempt %s/%s",
                            method,
                            path,
                            attempt,
                            attempts,
                        )
                        await asyncio.sleep(min(0.5 * attempt, 4.0))
                        continue
                    raise XUiPanelError(msg, status=resp.status_code, body=body)
                return body.get("obj") if "obj" in body else body
            return body
        if last_exc is not None:
            raise last_exc
        raise XUiPanelError(f"3x-ui {method} {path} exhausted retries without response")

    # ---- inbounds ----------------------------------------------------------

    async def list_inbounds(self) -> List[Dict[str, Any]]:
        """`GET /panel/api/inbounds/list` -> список инбаундов как dict."""
        result = await self._request("GET", "panel/api/inbounds/list")
        if not isinstance(result, list):
            return []
        return result

    async def get_inbound(self, inbound_id: int) -> Optional[Dict[str, Any]]:
        """`GET /panel/api/inbounds/get/{id}` -> один инбаунд как dict."""
        result = await self._request("GET", f"panel/api/inbounds/get/{int(inbound_id)}")
        if isinstance(result, dict):
            return result
        return None

    # ---- clients -----------------------------------------------------------

    async def add_client(self, inbound_id: int, client_payload: Dict[str, Any]) -> None:
        """`POST /panel/api/inbounds/addClient` для одного клиента."""
        body = {
            "id": int(inbound_id),
            "settings": json.dumps({"clients": [client_payload]}),
        }
        await self._request("POST", "panel/api/inbounds/addClient", data=body)

    async def update_client(
        self,
        client_url_id: str,
        inbound_id: int,
        client_payload: Dict[str, Any],
    ) -> None:
        """`POST /panel/api/inbounds/updateClient/{clientId}` с одним клиентом."""
        if not client_url_id:
            raise ValueError("update_client: client_url_id is empty")
        body = {
            "id": int(inbound_id),
            "settings": json.dumps({"clients": [client_payload]}),
        }
        endpoint = f"panel/api/inbounds/updateClient/{quote(str(client_url_id), safe='')}"
        await self._request("POST", endpoint, data=body)

    async def delete_client(self, inbound_id: int, client_url_id: str) -> None:
        """`POST /panel/api/inbounds/{id}/delClient/{clientId}`."""
        if not client_url_id:
            raise ValueError("delete_client: client_url_id is empty")
        endpoint = (
            f"panel/api/inbounds/{int(inbound_id)}"
            f"/delClient/{quote(str(client_url_id), safe='')}"
        )
        await self._request("POST", endpoint)

    async def delete_client_by_email(self, inbound_id: int, email: str) -> None:
        """`POST /panel/api/inbounds/{id}/delClientByEmail/{email}` — страховка для delete."""
        if not email:
            raise ValueError("delete_client_by_email: email is empty")
        endpoint = (
            f"panel/api/inbounds/{int(inbound_id)}"
            f"/delClientByEmail/{quote(str(email), safe='')}"
        )
        await self._request("POST", endpoint)

    async def online_emails(self) -> List[str]:
        """`POST /panel/api/inbounds/onlines` -> список email-ов онлайн-клиентов."""
        result = await self._request("POST", "panel/api/inbounds/onlines")
        if isinstance(result, list):
            return [str(x) for x in result if x is not None]
        return []

    async def get_client_traffics_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """`GET /panel/api/inbounds/getClientTraffics/{email}` -> dict со статистикой
        конкретного клиента (поля up, down, total, ...). None — если клиент не найден.
        """
        if not email:
            return None
        try:
            result = await self._request(
                "GET",
                f"panel/api/inbounds/getClientTraffics/{quote(str(email), safe='')}",
            )
        except XUiPanelError as exc:
            msg = str(exc).lower()
            if "not found" in msg or "no records" in msg:
                return None
            raise
        if isinstance(result, dict):
            return result
        return None


def _safe_json(resp: httpx.Response) -> Any:
    """Парсит JSON, но не падает, если тело пустое или текстовое (например HTML 502)."""
    text = resp.text or ""
    if not text.strip():
        return None
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        logger.debug("XUiPanelClient: non-JSON body (status=%s, len=%s)", resp.status_code, len(text))
        return text


def _mask_host(host: str) -> str:
    """Скрывает секретный путь панели в логах (`https://h:port/secret/`)."""
    try:
        parts = urlsplit(host)
        return urlunsplit((parts.scheme, parts.netloc, "/...", "", ""))
    except Exception:
        return host
