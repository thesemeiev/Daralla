"""
Сервис работы с панелью 3x-ui через собственный HTTP-клиент (XUiPanelClient).

Раньше использовалась библиотека py3xui, но она добавляла Pydantic-валидацию
поверх ответов панели и ломалась на «грязных» инбаундах (например, hy2 без
обязательного `enable`). Сейчас весь IO идёт напрямую через panel REST API.
"""
import asyncio
import base64
import datetime
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from .xui_helpers import (
    clients_from_settings_payload,
    client_to_api_dict,
    flow_matches_desired,
    panel_client_settings_dict,
    panel_snapshot_matches_desired,
)
from .xui_panel_client import XUiPanelClient
from ..utils.logging_helpers import mask_secret

logger = logging.getLogger(__name__)
_URI_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_SUPPORTED_PROTOCOLS = {"vless", "vmess", "trojan", "hysteria2", "tuic"}
_PASSWORD_BASED_PROTOCOLS = {"trojan", "tuic", "hysteria2"}

# Backward-compatibility aliases for existing tests/imports.
_flow_matches_desired = flow_matches_desired
_panel_snapshot_matches_desired = panel_snapshot_matches_desired


class X3:
    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return 0
            try:
                return int(float(s))
            except (TypeError, ValueError):
                return 0
        return 0

    @classmethod
    def _extract_traffic_from_mapping(cls, payload: Any) -> Optional[dict]:
        if not isinstance(payload, dict):
            return None
        up = cls._to_int(payload.get("up", payload.get("upload", 0)))
        down = cls._to_int(payload.get("down", payload.get("download", 0)))
        # total в панели — лимит трафика; 0 часто значит «безлимит». Не подменять на up+down,
        # иначе в subscription-userinfo лимит становится равным использованию и клиенты рисуют 100%.
        raw_total = payload.get("total")
        if raw_total is None:
            raw_total = payload.get("Total")
        if raw_total is None:
            total = cls._to_int(payload.get("used", 0))
            if total <= 0 and (up > 0 or down > 0):
                total = up + down
        else:
            total = cls._to_int(raw_total)
        # Возвращаем структуру даже с нулями — это валидное состояние для нового клиента.
        return {"upload": up, "download": down, "total": total}

    @staticmethod
    def _client_get(c: Any, key: str, default: Any = None) -> Any:
        if isinstance(c, dict):
            return c.get(key, default)
        return getattr(c, key, default)

    @staticmethod
    def _client_set(c: Any, key: str, value: Any) -> None:
        if isinstance(c, dict):
            c[key] = value
        else:
            try:
                setattr(c, key, value)
            except Exception:
                # py3xui/pydantic модели части протоколов не принимают "чужие" поля
                # (например expiryTime/limitIp в snake_case-only моделях и наоборот).
                # Это не критичная ошибка: совместимое поле задаётся соседним вызовом.
                return

    @classmethod
    def _client_set_expiry_ms(cls, c: Any, expiry_ms: int) -> None:
        val = int(expiry_ms)
        # Keep both shapes for compatibility between py3xui models and dict snapshots.
        cls._client_set(c, "expiry_time", val)
        cls._client_set(c, "expiryTime", val)

    @classmethod
    def _client_set_limit_ip(cls, c: Any, limit_ip: int) -> None:
        val = int(limit_ip)
        cls._client_set(c, "limit_ip", val)
        cls._client_set(c, "limitIp", val)

    @classmethod
    def _normalize_protocol_name(cls, protocol: Optional[str], inv: Any = None) -> str:
        p = (protocol or "vless").strip().lower()
        if p in {"hy2", "hysteria2"}:
            return "hysteria2"
        if p == "hysteria":
            # В 3x-ui/Xray для Hysteria2 protocol часто приходит как "hysteria"
            # с version=2 в settings, а иногда без version в модели.
            # Для совместимости считаем hysteria как hysteria2.
            return "hysteria2"
        return p

    """X3 — бизнес-обёртка над `XUiPanelClient` (тонкий HTTP-клиент 3x-ui).

    Сохраняет публичный интерфейс прежнего X3 для совместимости со всем кодом проекта
    (server_manager, admin_servers_service, subscription_manager и т.д.).
    """

    def __init__(
        self,
        login: str,
        password: str,
        host: str,
        vpn_host: Optional[str] = None,
        subscription_port: int = 2096,
        subscription_url: Optional[str] = None,
    ):
        self.login = login
        self.password = password
        self.host = host.rstrip("/")
        self.vpn_host = vpn_host
        self.subscription_port = subscription_port if subscription_port is not None else 2096
        self.subscription_url = (subscription_url or "").strip() or None
        use_tls_verify = host.startswith("https://")
        try:
            mr = int(os.getenv("XUI_PANEL_MAX_RETRIES", "5"))
        except ValueError:
            mr = 5
        mr = max(1, min(mr, 10))
        self._session_ttl: float = float(os.getenv("XUI_SESSION_TTL_SEC", "1800"))
        self._panel = XUiPanelClient(
            host=host,
            login=login,
            password=password,
            verify_tls=use_tls_verify,
            max_retries=mr,
            session_ttl_sec=self._session_ttl,
        )
        logger.debug("X3 создан для %s", host)

    async def _ensure_login(self) -> None:
        """Совместимость со старым кодом: логин делегируется panel-клиенту."""
        await self._panel._ensure_login()

    async def _relogin(self) -> None:
        """Принудительный повторный логин (при 401/session expired)."""
        await self._panel._relogin()

    async def list(self, timeout: int = 15) -> dict:
        """Возвращает {success: True, obj: [inbound_dict, ...]} в формате 3x-ui API.

        Чтение идёт через собственный HTTP-клиент панели (XUiPanelClient),
        без Pydantic-валидации.
        """
        obj = await self._panel.list_inbounds()
        return {"success": True, "obj": obj or []}

    async def list_quick(self, timeout: int = 10) -> dict:
        """Быстрая проверка доступности (для health check)."""
        return await self.list(timeout=timeout)

    async def client_exists(self, user_email: str) -> bool:
        """Проверяет наличие клиента по email через снимок списка inbound."""
        try:
            data = await self.list()
        except Exception:
            logger.debug("client_exists list call failed", exc_info=True)
            return False
        target = str(user_email).strip()
        for inbound in data.get("obj", []):
            try:
                settings = json.loads(inbound.get("settings", "{}"))
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
            for client in clients_from_settings_payload(settings):
                if str(client.get("email", "")).strip() == target:
                    return True
        return False

    async def get_client_info(self, user_email: str, timeout: int = 15) -> Optional[dict]:
        snap = await self._load_panel_client_snapshot(user_email)
        if snap is None:
            return None
        inbound_id, protocol, panel_client = snap
        return {
            "client": client_to_api_dict(panel_client),
            "inbound_id": inbound_id,
            "protocol": protocol.lower(),
        }

    @staticmethod
    def _build_protocol_client_payload(
        *,
        protocol: str,
        user_email: str,
        tg_id: str,
        key_name: str,
        expiry_ms: int,
        limit_ip: int,
        flow: Optional[str],
    ) -> Dict[str, Any]:
        protocol_norm = X3._normalize_protocol_name(protocol, None)
        payload: Dict[str, Any] = {
            "email": str(user_email),
            "enable": True,
            "limitIp": int(limit_ip),
            "expiryTime": int(expiry_ms),
            "tgId": str(tg_id),
            "subId": key_name or "",
            "protocol": protocol_norm,
        }
        if protocol_norm == "hysteria2":
            # Canonical hy2 payload uses auth only.
            hy2_secret = str(uuid.uuid4()).replace("-", "")
            payload["auth"] = hy2_secret
        elif protocol_norm in _PASSWORD_BASED_PROTOCOLS:
            payload["password"] = str(uuid.uuid4())
        else:
            payload["id"] = str(uuid.uuid4())
        if protocol_norm == "vless":
            payload["flow"] = (str(flow).strip() if flow and str(flow).strip() else "")
        return payload

    @staticmethod
    def _extract_protocol(inv: Any) -> str:
        raw = X3._client_get(inv, "protocol", "vless")
        if not isinstance(raw, str):
            raw = "vless"
        raw = (raw or "vless").strip().lower()
        return X3._normalize_protocol_name(raw, inv)

    async def _resolve_target_inbound(
        self,
        *,
        inbounds: List[Any],
        target_protocol: Optional[str],
        inbound_id: Optional[int],
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        if inbound_id is not None:
            for inv in inbounds:
                if self._client_get(inv, "id", None) == inbound_id:
                    protocol = self._extract_protocol(inv)
                    if protocol not in _SUPPORTED_PROTOCOLS:
                        return None, None, f"unsupported protocol for inbound_id={inbound_id}: {protocol}"
                    return int(inbound_id), protocol, None
            return None, None, f"inbound_id={inbound_id} not found"

        preferred = (target_protocol or "").strip().lower()
        preferred = self._normalize_protocol_name(preferred, None) if preferred else preferred
        if preferred:
            if preferred not in _SUPPORTED_PROTOCOLS:
                return None, None, f"unsupported target_protocol={preferred}"
            for inv in inbounds:
                protocol = self._extract_protocol(inv)
                if protocol == preferred:
                    resolved_id = self._client_get(inv, "id", None)
                    if resolved_id is not None:
                        return int(resolved_id), protocol, None
            return None, None, f"no inbound with protocol={preferred}"

        for inv in inbounds:
            protocol = self._extract_protocol(inv)
            resolved_id = self._client_get(inv, "id", None)
            if resolved_id is not None and protocol in _SUPPORTED_PROTOCOLS:
                return int(resolved_id), protocol, None
        return None, None, "no supported inbound found"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def addClient(
        self,
        day: int,
        tg_id: str,
        user_email: str,
        timeout: int = 15,
        hours: Optional[int] = None,
        key_name: str = "",
        inbound_id: Optional[int] = None,
        limit_ip: Optional[int] = None,
        flow: Optional[str] = None,
        target_protocol: Optional[str] = None,
    ) -> Any:
        inbounds = await self._panel.list_inbounds()
        if not inbounds:
            return {"ok": False, "reason": "no_inbounds"}
        inbound_id_resolved, protocol, resolve_error = await self._resolve_target_inbound(
            inbounds=inbounds,
            target_protocol=target_protocol,
            inbound_id=inbound_id,
        )
        if inbound_id_resolved is None or protocol is None:
            return {"ok": False, "reason": "unsupported_protocol", "detail": resolve_error}

        if hours is not None:
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (hours * 3600000)
        else:
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (86400000 * day)
        limit_ip_value = limit_ip if limit_ip is not None else 1
        payload = self._build_protocol_client_payload(
            protocol=protocol,
            user_email=user_email,
            tg_id=tg_id,
            key_name=key_name,
            expiry_ms=x_time,
            limit_ip=limit_ip_value,
            flow=flow,
        )
        await self._post_inbound_add_clients(
            int(inbound_id_resolved), [payload], protocol_hint=protocol,
        )
        return {
            "ok": True,
            "protocol": protocol,
            "inbound_id": int(inbound_id_resolved),
        }

    @classmethod
    def _client_url_id_for_protocol(cls, protocol: str, c: Any) -> Optional[str]:
        """
        Возвращает идентификатор клиента, который 3x-ui ожидает в URL
        ручек /updateClient/:clientId и /:inboundId/delClient/:clientId.

        Источник правил — `web/service/inbound.go` 3x-ui:
            vmess/vless        -> client.id (UUID)
            trojan/tuic        -> client.password
            shadowsocks        -> client.email
            hysteria/hysteria2 -> client.auth
        """
        protocol_norm = cls._normalize_protocol_name((protocol or "").strip().lower(), None)

        def _get(key: str) -> str:
            return str(cls._client_get(c, key, "") or "").strip()

        if protocol_norm in ("vmess", "vless"):
            uuid_val = _get("uuid")
            id_val = _get("id")
            return id_val or uuid_val or None
        if protocol_norm in ("trojan", "tuic"):
            return _get("password") or None
        if protocol_norm == "shadowsocks":
            return _get("email") or None
        if protocol_norm == "hysteria2":
            return _get("auth") or None
        # Неизвестный протокол: используем стандартный путь VLESS-подобного UUID,
        # затем падает с понятной ошибкой выше по стеку.
        return _get("id") or _get("uuid") or None

    @staticmethod
    def _find_client_in_inbound_by_email(inv: Any, email: str) -> Optional[Any]:
        """Ищем клиента в inbound.settings (clients/users) по email — без перезаписи инбаунда.
        Используется как третий уровень резолва идентификатора клиента,
        когда get_by_email возвращает объект без нужных полей (auth/password/id).
        """
        settings = getattr(inv, "settings", None)
        groups: list[list[Any]]
        if isinstance(settings, dict):
            groups = [list(settings.get("clients") or []), list(settings.get("users") or [])]
        else:
            groups = [
                list(getattr(settings, "clients", None) or []),
                list(getattr(settings, "users", None) or []),
            ]
        email_norm = str(email or "").strip()
        if not email_norm:
            return None
        for group in groups:
            for cl in group:
                cl_email = str(X3._client_get(cl, "email", "") or "").strip()
                if cl_email == email_norm:
                    return cl
        return None

    async def _post_inbound_add_clients(
        self,
        inbound_id: int,
        clients: List[Any],
        *,
        protocol_hint: Optional[str] = None,
    ) -> None:
        """addClient через собственный HTTP-клиент панели.

        protocol_hint: если задан — используется для нормализации payload
        (без protocol_hint некоторые поля могут быть пропущены/добавлены не для того протокола).
        """
        if protocol_hint is None:
            try:
                inv = await self._panel.get_inbound(int(inbound_id))
                if inv is not None:
                    protocol_hint = self._extract_protocol(inv)
            except Exception:
                protocol_hint = None
        for c in clients:
            payload = panel_client_settings_dict(c, protocol_hint=protocol_hint)
            await self._panel.add_client(int(inbound_id), payload)

    async def _post_inbound_update_client(
        self,
        c: Any,
        inbound_id_override: Optional[int] = None,
        flow_override: Optional[str] = None,
        protocol_hint: Optional[str] = None,
    ) -> None:
        """updateClient через собственный HTTP-клиент панели — единый линейный путь.

        Идея: у каждого протокола в URL `updateClient/:clientId` идёт строго
        своё поле клиента (см. `_client_url_id_for_protocol`). Сначала пытаемся
        взять идентификатор из переданного `c`. Если не получилось — читаем
        inbound, находим клиента по email, копируем недостающие
        протокольные поля (auth/password/id/uuid) и пробуем снова.

        inbound_id_override: если задан — используется как inbound_id в URL
        (для случаев, когда у `c` нет `inbound_id`).
        """
        protocol_norm = (
            self._normalize_protocol_name((protocol_hint or "").strip().lower(), None)
            if protocol_hint
            else ""
        )
        inbound_id = (
            int(inbound_id_override)
            if inbound_id_override is not None
            else self._client_get(c, "inbound_id", None)
        )
        if inbound_id is None:
            raise ValueError("updateClient: у клиента нет inbound_id")
        if not protocol_norm:
            protocol_from_payload = str(self._client_get(c, "protocol", "") or "").strip().lower()
            if protocol_from_payload:
                protocol_norm = self._normalize_protocol_name(protocol_from_payload, None)

        email = self._client_get(c, "email", None)
        client_url_id: Optional[str] = (
            self._client_url_id_for_protocol(protocol_norm, c) if protocol_norm else None
        )

        # Если протокол неизвестен ИЛИ нет clientId для URL — читаем inbound и тянем
        # текущие данные клиента с панели.
        if (not protocol_norm) or (not client_url_id):
            try:
                inv = await self._panel.get_inbound(int(inbound_id))
            except Exception:
                inv = None
                logger.debug(
                    "updateClient: не удалось прочитать inbound (inbound_id=%s)",
                    inbound_id,
                    exc_info=True,
                )
            if inv is not None:
                if not protocol_norm:
                    protocol_norm = self._extract_protocol(inv)
                if email and not client_url_id:
                    panel_client = self._find_client_in_inbound_by_email(inv, str(email))
                    if panel_client is not None:
                        for key in ("auth", "password", "id", "uuid"):
                            val = panel_client.get(key)
                            if val is None or str(val).strip() == "":
                                continue
                            if not self._client_get(c, key, None):
                                self._client_set(c, key, val)
                        client_url_id = self._client_url_id_for_protocol(protocol_norm, c)

        if not client_url_id:
            raise ValueError(
                f"updateClient: empty client id for protocol={protocol_norm or 'unknown'} "
                f"email={email or '-'} inbound_id={inbound_id}"
            )

        body = panel_client_settings_dict(
            c,
            flow_override=flow_override,
            protocol_hint=protocol_norm,
        )
        await self._panel.update_client(str(client_url_id), int(inbound_id), body)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def reconcile_client(
        self,
        user_email: str,
        *,
        expiry_sec: int,
        limit_ip: int,
        flow_from_config: Optional[str],
        target_protocol: Optional[str] = None,
        target_inbound_id: Optional[int] = None,
    ) -> Tuple[bool, bool]:
        """
        Выставляет на панели целевые expiry, limit_ip и flow (как в конфиге сервера).

        Обходит все inbound и обновляет каждую запись clients[] с данным email — иначе при дубликате
        email в нескольких inbound get_by_email менял бы только одну строку.

        Если в снимке get_list() email не найден, fallback: один update через get_by_email.

        Пустой/отсутствующий client_flow в конфиге => в JSON уходит flow "" (сброс на панели).

        Returns: (success, did_update). did_update True после хотя бы одного успешного update.
        """
        await self._ensure_login()
        want_flow = (flow_from_config or "").strip()
        exp_ms = int(expiry_sec) * 1000
        li = int(limit_ip)
        needle = str(user_email).strip()

        data = await self.list()
        wanted_protocol = (target_protocol or "").strip().lower()
        work_items: List[Tuple[int, str, dict]] = []
        for inv in data.get("obj", []):
            inv_id = inv.get("id")
            if inv_id is None:
                continue
            inv_protocol = self._normalize_protocol_name((inv.get("protocol") or "vless").strip().lower(), None)
            if target_inbound_id is not None and int(inv_id) != int(target_inbound_id):
                continue
            if wanted_protocol and inv_protocol != wanted_protocol:
                continue
            try:
                settings = json.loads(inv.get("settings", "{}"))
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
            clients = clients_from_settings_payload(settings)
            for cl in clients:
                em = cl.get("email")
                if em is None:
                    continue
                if str(em).strip() == needle:
                    work_items.append((int(inv_id), inv_protocol, cl))

        if not work_items:
            # Клиент с этим email не существует ни в одном из подходящих inbound.
            return False, False

        for inbound_id, inbound_protocol, c in work_items:
            self._client_set_expiry_ms(c, exp_ms)
            self._client_set_limit_ip(c, li)
            self._client_set(c, "enable", True)
            if inbound_protocol == "vless":
                self._client_set(c, "flow", want_flow)
            await self._post_inbound_update_client(
                c,
                inbound_id_override=inbound_id,
                flow_override=want_flow if inbound_protocol == "vless" else None,
                protocol_hint=inbound_protocol,
            )
        return True, True

    async def _load_panel_client_snapshot(
        self,
        email: str,
        *,
        target_inbound_id: Optional[int] = None,
    ) -> Optional[Tuple[int, str, Dict[str, Any]]]:
        """Возвращает (inbound_id, protocol, client_dict) для клиента по email
        или None, если клиент не найден ни в одном inbound.

        Без py3xui: данные читаются через self._panel.list_inbounds() / get_inbound(),
        клиент находится по email в settings.clients/users.
        """
        target = str(email).strip()
        inbounds = await self._panel.list_inbounds()
        for inv in inbounds:
            inv_id = inv.get("id")
            if inv_id is None:
                continue
            if target_inbound_id is not None and int(inv_id) != int(target_inbound_id):
                continue
            try:
                settings = json.loads(inv.get("settings") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            clients = clients_from_settings_payload(settings)
            for cl in clients:
                if str(cl.get("email", "")).strip() == target:
                    protocol = self._normalize_protocol_name(
                        str(inv.get("protocol") or "vless").strip().lower(), None
                    )
                    return int(inv_id), protocol, cl
        return None

    async def updateClientName(
        self,
        user_email: str,
        new_name: str,
        timeout: int = 15,
    ) -> Any:
        snap = await self._load_panel_client_snapshot(user_email)
        if snap is None:
            raise Exception(f"Клиент с email {user_email} не найден")
        inbound_id, protocol, panel_client = snap
        c = dict(panel_client)
        c["subId"] = new_name
        await self._post_inbound_update_client(
            c, inbound_id_override=inbound_id, protocol_hint=protocol,
        )
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def deleteClient(self, user_email: str, timeout: int = 15) -> bool:
        snap = await self._load_panel_client_snapshot(user_email)
        if snap is None:
            logger.debug(
                "deleteClient: клиент %s не найден ни в одном inbound — удаление не требуется",
                user_email,
            )
            return False
        inbound_id, protocol_norm, panel_client = snap
        client_url_id = self._client_url_id_for_protocol(protocol_norm, panel_client)

        if client_url_id:
            try:
                await self._panel.delete_client(int(inbound_id), str(client_url_id))
                logger.info(
                    "Клиент удалён: %s (inbound_id=%s, protocol=%s)",
                    user_email, inbound_id, protocol_norm or "?",
                )
                return True
            except Exception as exc:
                logger.warning(
                    "delete_client failed for %s (inbound_id=%s, protocol=%s): %s; "
                    "trying delClientByEmail",
                    user_email, inbound_id, protocol_norm or "?", exc,
                )

        # Страховка: штатная клиентская ручка по email (не перезаписывает inbound).
        await self._panel.delete_client_by_email(int(inbound_id), str(user_email))
        logger.info(
            "Клиент удалён через delClientByEmail: %s (inbound_id=%s, protocol=%s)",
            user_email, inbound_id, protocol_norm or "?",
        )
        return True

    async def get_online_clients_ids(self, timeout: int = 15) -> tuple:
        """Возвращает (set of email/ids, success)."""
        try:
            emails = await self._panel.online_emails()
            return set(emails or []), True
        except Exception as e:
            logger.warning("Ошибка получения онлайн клиентов: %s", e)
            return set(), False

    async def get_online_clients_count(self, timeout: int = 15) -> tuple:
        """Возвращает (total_active, online_count, offline_count)."""
        try:
            data = await self.list(timeout=timeout)
            if not data or "obj" not in data:
                return 0, 0, 0
            inbounds = data["obj"]
            if not inbounds:
                return 0, 0, 0
            online_emails, _ = await self.get_online_clients_ids(timeout=timeout)
            current_ms = int(datetime.datetime.now().timestamp() * 1000)
            total_active = 0
            online_count = 0
            offline_count = 0
            for inbound in inbounds:
                try:
                    settings = json.loads(inbound.get("settings", "{}"))
                except (json.JSONDecodeError, TypeError):
                    continue
                try:
                    for client in clients_from_settings_payload(settings):
                        expiry_ms = client.get("expiryTime", 0) or 0
                        if expiry_ms == 0 or current_ms < expiry_ms:
                            total_active += 1
                            email = client.get("email")
                            is_online = bool(email and str(email) in online_emails)
                            if is_online:
                                online_count += 1
                            else:
                                offline_count += 1
                except Exception:
                    continue
            return total_active, online_count, offline_count
        except Exception as e:
            logger.error("Ошибка при подсчёте онлайн клиентов на %s: %s", self.host, e, exc_info=True)
            return 0, 0, 0

    async def get_client_traffic(self, user_email: str, timeout: int = 15) -> Optional[dict]:
        target_email = str(user_email).strip()
        data = await self.list(timeout=timeout)
        if not data.get("success") or not data.get("obj"):
            return None
        for inbound in data["obj"]:
            stats = inbound.get("clientStats", [])
            if isinstance(stats, list):
                for s in stats:
                    if str(s.get("email", "")).strip() == target_email:
                        mapped = self._extract_traffic_from_mapping(s)
                        if mapped is not None:
                            return mapped
            elif isinstance(stats, dict):
                s = stats.get(target_email)
                if s is None:
                    # Иногда ключи в panel-ответе содержат лишние пробелы.
                    for k, v in stats.items():
                        if str(k).strip() == target_email:
                            s = v
                            break
                if s:
                    mapped = self._extract_traffic_from_mapping(s)
                    if mapped is not None:
                        return mapped

        # Fallback: для Hysteria2 list().clientStats может быть пустым/неполным.
        # Запрашиваем статистику конкретного клиента через штатный endpoint панели.
        try:
            stats = await self._panel.get_client_traffics_by_email(target_email)
        except Exception:
            logger.debug(
                "get_client_traffic fallback getClientTraffics failed for %s",
                target_email,
                exc_info=True,
            )
            return None
        if stats is None:
            return None
        return self._extract_traffic_from_mapping(stats)

    async def sync_flow_for_all_clients(self, flow_value: str, timeout: int = 15) -> tuple:
        """
        Массово выставляет flow для всех клиентов по inbound (протокол задаётся панелью).

        Обновление по строке clients[] из снимка панели + явный inbound_id в теле запроса.
        Flow в JSON всегда задаётся через flow_override (целевое значение с сервера), без сравнения
        со снимком: иначе при одном inbound возможны ложные skip.

        Несколько inbound с одним email: каждая строка обновляется отдельно.

        Returns: (updated_count, skipped_unchanged_count, errors_list).
        """
        target = (flow_value or "").strip()
        inbounds = await self._panel.list_inbounds()
        sem = asyncio.Semaphore(4)
        work_items: List[Tuple[int, str, Dict[str, Any]]] = []
        for inv in inbounds:
            inv_id = inv.get("id")
            if inv_id is None:
                continue
            inv_protocol = self._normalize_protocol_name(
                str(inv.get("protocol") or "vless").strip().lower(), None
            )
            try:
                settings = json.loads(inv.get("settings") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            for c in clients_from_settings_payload(settings):
                if c.get("email"):
                    work_items.append((int(inv_id), inv_protocol, c))

        async def _one(
            inbound_id: int, inbound_protocol: str, c: Dict[str, Any],
        ) -> Tuple[str, Optional[str]]:
            email = str(c.get("email") or "")
            if not email:
                return "err", "?: нет email у записи клиента в inbound"
            async with sem:
                last_exc: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        await self._post_inbound_update_client(
                            dict(c),
                            inbound_id_override=int(inbound_id),
                            flow_override=target,
                            protocol_hint=inbound_protocol,
                        )
                        return "ok", None
                    except Exception as up_e:
                        last_exc = up_e
                        if attempt < 2:
                            await asyncio.sleep(0.4 * (attempt + 1))
                return "err", f"{email}: {last_exc}"

        if not work_items:
            return 0, 0, []
        results = await asyncio.gather(
            *[_one(iid, proto, cl) for iid, proto, cl in work_items]
        )
        updated = sum(1 for status, _ in results if status == "ok")
        skipped = sum(1 for status, _ in results if status == "skip")
        errors = [msg for status, msg in results if status == "err" and msg]
        return updated, skipped, errors

    async def get_subscription_links(
        self,
        user_email: str,
        server_name: Optional[str] = None,
        flow_override: Optional[str] = None,
        subscription_token: Optional[str] = None,
    ) -> List[str]:
        """
        Получает ссылки подписки с endpoint панели /sub/{sub_id}.
        subscription_token: токен подписки из БД; используется как fallback для sub_id,
        если панель не сохранила subId при создании клиента через API (баг 3x-ui #3237).
        """
        await self._ensure_login()
        try:
            data = await self.list()
            if not data.get("success"):
                return []
            base_url = self.subscription_url
            if not base_url and self.host:
                scheme = "https" if self.host.startswith("https") else "http"
                host_part = self.host.split("//")[-1].split("/panel")[0]
                if ":" in host_part:
                    host_only = host_part.rsplit(":", 1)[0]
                else:
                    host_only = host_part
                host_for_sub = (self.vpn_host or host_only).strip()
                if host_for_sub and ":" in host_for_sub:
                    host_for_sub = host_for_sub.rsplit(":", 1)[0]
                base_url = f"{scheme}://{host_for_sub}:{self.subscription_port}/sub"
            # On some panels/protocols (notably hysteria2) get_by_email may fail with
            # "Inbound Not Found For Email" even when client exists. Resolve sub_id from list snapshot.
            sub_id = None
            email_norm = str(user_email).strip()
            for inv in data.get("obj", []):
                try:
                    settings = json.loads(inv.get("settings", "{}"))
                except (json.JSONDecodeError, TypeError, AttributeError):
                    continue
                for client in clients_from_settings_payload(settings):
                    if str(client.get("email", "")).strip() != email_norm:
                        continue
                    sub_id = client.get("subId") or client.get("sub_id")
                    if sub_id:
                        break
                if sub_id:
                    break
            if not sub_id and subscription_token:
                sub_id = subscription_token
                logger.debug("get_subscription_links: используем subscription_token как sub_id для email=%s", user_email)
            if not sub_id:
                logger.debug("get_subscription_links: sub_id не найден в list() для email=%s", user_email)
                return []
            sub_url = f"{base_url.rstrip('/')}/{sub_id}"
            sub_url_log = f"{base_url.rstrip('/')}/{mask_secret(sub_id)}"
            try:
                async with httpx.AsyncClient(verify=False, timeout=15.0) as hc:
                    r = await hc.get(sub_url)
                    if r.status_code != 200:
                        logger.debug(
                            "Subscription endpoint вернул не 200: url=%s status=%s body_len=%s",
                            sub_url_log, r.status_code, len(r.text or ""),
                        )
                        return []
                    text = r.text
            except Exception as e:
                logger.warning("Ошибка запроса subscription URL %s: %s", sub_url_log, e)
                return []
            # Некоторые панели отдают подписку в base64 (одна строка).
            # Не ограничиваемся vless/vmess/trojan: в подписке могут быть hy2/tuic и другие схемы.
            raw = (text or "").strip()
            if raw and "://" not in raw:
                try:
                    decoded = base64.standard_b64decode(raw).decode("utf-8", errors="replace")
                    if decoded.strip():
                        raw = decoded.strip()
                except Exception:
                    pass
            links = []
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not _URI_SCHEME_RE.match(line):
                    continue
                if flow_override and line.startswith("vless://"):
                    try:
                        parsed = urlparse(line)
                        qs = parse_qs(parsed.query)
                        qs["flow"] = [flow_override]
                        new_query = urlencode(qs, doseq=True)
                        line = urlunparse(
                            (
                                parsed.scheme,
                                parsed.netloc,
                                parsed.path,
                                parsed.params,
                                new_query,
                                parsed.fragment,
                            )
                        )
                    except Exception:
                        pass
                if server_name and "#" in line:
                    pre = line.split("#", 1)[0]
                    line = f"{pre}#{quote(server_name, safe='')}"
                links.append(line)
            if not links and raw:
                logger.debug(
                    "Subscription endpoint вернул тело без URI-ссылок: url=%s body_len=%s",
                    sub_url_log, len(raw),
                )
            return links
        except Exception as e:
            logger.error("Ошибка get_subscription_links для %s: %s", user_email, e)
            return []
