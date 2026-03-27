"""
Сервис для работы с X-UI API через библиотеку py3xui (AsyncApi).
Сохраняет прежний публичный интерфейс класса X3 для совместимости с кодом проекта.
"""
import base64
import datetime
import json
import logging
import os
import uuid
from typing import List, Any, Optional
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


def _value_error_client_absent_on_panel(exc: ValueError) -> bool:
    """
    py3xui при get_by_email может кинуть ValueError, если клиента нет на этой ноде
    (текст от 3x-ui вроде «Inbound Not Found For Email» / «Error getting traffics»).
    Это не сбой сети — на панели просто нечего удалять.
    """
    msg = str(exc).lower()
    return (
        "not found for email" in msg
        or "inbound not found" in msg
        or ("error getting traffics" in msg and "not found" in msg)
    )


# Опциональный импорт py3xui — при отсутствии библиотеки будет понятная ошибка
try:
    from py3xui import AsyncApi
    from py3xui import Client as Py3xuiClient
    from py3xui import Inbound as Py3xuiInbound
    PY3XUI_AVAILABLE = True
except ImportError:
    PY3XUI_AVAILABLE = False
    AsyncApi = None
    Py3xuiClient = None
    Py3xuiInbound = None


def _client_to_api_dict(c: Any) -> dict:
    """Преобразует клиента py3xui (или dict) в формат 3x-ui API (camelCase)."""
    if hasattr(c, "model_dump"):
        d = c.model_dump()
    elif isinstance(c, dict):
        d = dict(c)
    else:
        d = {}
    key_map = {
        "expiry_time": "expiryTime",
        "limit_ip": "limitIp",
        "sub_id": "subId",
        "tg_id": "tgId",
        "total_gb": "totalGB",
    }
    out = {}
    for k, v in d.items():
        out[key_map.get(k, k)] = v
    return out


def _inbound_to_dict(inv: Any) -> dict:
    """Преобразует Inbound py3xui в элемент списка obj (формат ответа list())."""
    settings = getattr(inv, "settings", None)
    clients = []
    if settings is not None:
        raw_clients = getattr(settings, "clients", None) or []
        for c in raw_clients:
            clients.append(_client_to_api_dict(c))
    settings_str = json.dumps({"clients": clients})

    stream = getattr(inv, "stream_settings", None)
    if stream is not None and hasattr(stream, "model_dump"):
        stream_dict = stream.model_dump()
    elif isinstance(stream, dict):
        stream_dict = stream
    else:
        stream_dict = {}

    client_stats = getattr(inv, "client_stats", None) or []
    client_stats_list = []
    for s in client_stats:
        if hasattr(s, "model_dump"):
            client_stats_list.append(s.model_dump())
        elif isinstance(s, dict):
            client_stats_list.append(s)
        else:
            client_stats_list.append(_client_to_api_dict(s))

    return {
        "id": getattr(inv, "id", None),
        "protocol": getattr(inv, "protocol", "vless"),
        "port": getattr(inv, "port", 443),
        "settings": settings_str,
        "streamSettings": stream_dict,
        "clientStats": client_stats_list if client_stats_list else [],
        "enable": getattr(inv, "enable", True),
        "remark": getattr(inv, "remark", ""),
    }


class X3:
    """
    Обёртка над py3xui.AsyncApi с тем же публичным интерфейсом, что и прежний X3.
    Поддерживает vpn_host, subscription_port, subscription_url для link/subscription.
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
        if not PY3XUI_AVAILABLE:
            raise RuntimeError(
                "py3xui не установлен. Выполните: pip install py3xui>=0.5.5"
            )
        self.login = login
        self.password = password
        self.host = host.rstrip("/")
        self.vpn_host = vpn_host
        self.subscription_port = subscription_port if subscription_port is not None else 2096
        self.subscription_url = (subscription_url or "").strip() or None
        use_tls_verify = host.startswith("https://")
        self._api = AsyncApi(host, login, password, use_tls_verify=use_tls_verify)
        self._logged_in = False
        logger.debug("X3 (py3xui) создан для %s", host)

    async def _ensure_login(self) -> None:
        if not self._logged_in:
            await self._api.login()
            self._logged_in = True

    async def _ensure_connected(self) -> None:
        """Алиас для совместимости с прежним кодом."""
        await self._ensure_login()

    async def list(self, timeout: int = 15) -> dict:
        """Возвращает {success: True, obj: [inbound_dict, ...]} в формате 3x-ui API."""
        await self._ensure_login()
        inbounds = await self._api.inbound.get_list()
        obj = [_inbound_to_dict(inv) for inv in inbounds]
        return {"success": True, "obj": obj}

    async def list_quick(self, timeout: int = 10) -> dict:
        """Быстрая проверка доступности (для health check)."""
        return await self.list(timeout=timeout)

    async def client_exists(self, user_email: str) -> bool:
        """Проверяет наличие клиента по email. При ошибке «Inbound Not Found» считаем, что клиента нет."""
        await self._ensure_login()
        try:
            c = await self._api.client.get_by_email(user_email)
            return c is not None
        except Exception as e:
            # Панель возвращает "Inbound Not Found For Email" когда клиента ещё нет — не исключение, а норма
            msg = str(e).lower()
            if "not found" in msg or "inbound not found" in msg or "error getting traffics" in msg:
                logger.debug("Клиент %s не найден на панели (ожидаемо при создании): %s", user_email, e)
                return False
            raise

    async def get_client_expiry_time(self, user_email: str, timeout: int = 15) -> Optional[int]:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            return None
        expiry_ms = getattr(c, "expiry_time", None) or getattr(c, "expiryTime", 0)
        if not expiry_ms or expiry_ms <= 0:
            return None
        return int(expiry_ms) // 1000

    async def get_client_info(self, user_email: str, timeout: int = 15) -> Optional[dict]:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            return None
        inbound_id = getattr(c, "inbound_id", None)
        if inbound_id is None:
            inbounds = await self._api.inbound.get_list()
            for inv in inbounds:
                clients = getattr(getattr(inv, "settings", None), "clients", None) or []
                for cl in clients:
                    if getattr(cl, "email", None) == user_email:
                        inbound_id = getattr(inv, "id", None)
                        break
                if inbound_id is not None:
                    break
        protocol = "vless"
        if inbound_id is not None:
            try:
                inv = await self._api.inbound.get_by_id(int(inbound_id))
                if inv:
                    protocol = getattr(inv, "protocol", "vless") or "vless"
            except Exception:
                pass
        return {
            "client": _client_to_api_dict(c),
            "inbound_id": inbound_id,
            "protocol": protocol.lower(),
        }

    async def get_clients_by_tg_id(self, tg_id: str, timeout: int = 15) -> list:
        await self._ensure_login()
        data = await self.list(timeout=timeout)
        result = []
        for inbound in data.get("obj", []):
            try:
                settings = json.loads(inbound.get("settings", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            for client in settings.get("clients", []):
                if str(client.get("tgId", "")) == str(tg_id):
                    result.append({
                        "email": client.get("email"),
                        "client": client,
                        "inbound_id": inbound.get("id"),
                        "protocol": (inbound.get("protocol") or "vless").lower(),
                    })
        return result

    async def _find_inbound_id_for_client(self, user_email: str) -> Optional[int]:
        await self._ensure_login()
        inbounds = await self._api.inbound.get_list()
        for inv in inbounds:
            clients = getattr(getattr(inv, "settings", None), "clients", None) or []
            for c in clients:
                if getattr(c, "email", None) == user_email:
                    return getattr(inv, "id", None)
        return None

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
    ) -> Any:
        await self._ensure_login()
        inbounds = await self._api.inbound.get_list()
        if not inbounds:
            raise Exception("Список inbounds пуст")
        first = inbounds[0]
        if inbound_id is None:
            inbound_id = getattr(first, "id", None) or 1
        protocol = "vless"
        for inv in inbounds:
            if getattr(inv, "id", None) == inbound_id:
                protocol = (getattr(inv, "protocol", "vless") or "vless").lower()
                break

        if hours is not None:
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (hours * 3600000)
        else:
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (86400000 * day)
        limit_ip_value = limit_ip if limit_ip is not None else 1
        client_uuid = str(uuid.uuid4())

        if protocol == "trojan":
            new_client = Py3xuiClient(
                id=client_uuid,
                email=str(user_email),
                enable=True,
                password=client_uuid,
                limit_ip=limit_ip_value,
                expiry_time=x_time,
                tg_id=str(tg_id),
                sub_id=key_name or "",
            )
        else:
            kwargs = {
                "id": client_uuid,
                "email": str(user_email),
                "enable": True,
                "limit_ip": limit_ip_value,
                "expiry_time": x_time,
                "tg_id": str(tg_id),
                "sub_id": key_name or "",
            }
            if flow and str(flow).strip():
                kwargs["flow"] = str(flow).strip()
            new_client = Py3xuiClient(**kwargs)
        await self._api.client.add(int(inbound_id), [new_client])
        # Успех сигнализируется отсутствием исключения
        return True

    @staticmethod
    def _ensure_client_id_for_update(c: Any) -> Any:
        """Панель 3x-ui для VLESS ожидает в теле update поле id = UUID. get_by_email возвращает id как число — подставляем uuid."""
        uuid_val = getattr(c, "uuid", None)
        if uuid_val and isinstance(getattr(c, "id", None), int):
            c.id = uuid_val
        return c

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def extendClient(
        self,
        user_email: str,
        extend_days: int,
        timeout: int = 15,
        flow: Optional[str] = None,
    ) -> Optional[Any]:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            raise Exception(f"Клиент с email {user_email} не найден")
        current_ms = getattr(c, "expiry_time", 0) or 0
        if current_ms == 0:
            current_ms = int(datetime.datetime.now().timestamp() * 1000)
        new_ms = current_ms + (extend_days * 86400000)
        c.expiry_time = new_ms
        if flow is not None and str(flow).strip():
            c.flow = str(flow).strip()
        self._ensure_client_id_for_update(c)
        await self._api.client.update(c.id, c)
        # Успех сигнализируется отсутствием исключения
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def setClientExpiry(
        self,
        user_email: str,
        expiry_timestamp: int,
        timeout: int = 15,
        flow: Optional[str] = None,
    ) -> Optional[Any]:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            # Клиент не найден — считаем, что нечего обновлять
            return False
        c.expiry_time = expiry_timestamp * 1000
        if flow is not None:
            c.flow = (flow.strip() if isinstance(flow, str) else str(flow)).strip() or ""
        self._ensure_client_id_for_update(c)
        await self._api.client.update(c.id, c)
        # True — время истечения обновлено
        return True

    async def updateClientLimitIp(
        self,
        user_email: str,
        limit_ip: int,
        timeout: int = 15,
        flow: Optional[str] = None,
    ) -> Optional[Any]:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            # Клиент не найден — limitIp обновлять нечему
            return False
        c.limit_ip = limit_ip
        if flow is not None:
            c.flow = (flow.strip() if isinstance(flow, str) else str(flow)).strip() or ""
        self._ensure_client_id_for_update(c)
        await self._api.client.update(c.id, c)
        return True

    async def updateClientName(
        self,
        user_email: str,
        new_name: str,
        timeout: int = 15,
    ) -> Any:
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            raise Exception(f"Клиент с email {user_email} не найден")
        c.sub_id = new_name
        self._ensure_client_id_for_update(c)
        await self._api.client.update(c.id, c)
        # Успех — отсутствие исключения
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def deleteClient(self, user_email: str, timeout: int = 15) -> bool:
        await self._ensure_login()
        try:
            c = await self._api.client.get_by_email(user_email)
        except ValueError as e:
            if _value_error_client_absent_on_panel(e):
                logger.debug(
                    "Клиент %s на этой панели не найден (нет inbound/email): %s — удаление не требуется",
                    user_email,
                    e,
                )
                return False
            raise
        if c is None:
            logger.warning("Клиент с email=%s не найден для удаления", user_email)
            # False — клиента по этому email нет на панели
            return False
        inbound_id = getattr(c, "inbound_id", None)
        if inbound_id is None:
            inbound_id = await self._find_inbound_id_for_client(user_email)
        if inbound_id is None:
            logger.warning("Не удалось определить inbound_id для клиента %s", user_email)
            return False
        # Панель 3x-ui при delete ожидает client id в том же формате, что и при update (UUID для VLESS)
        self._ensure_client_id_for_update(c)
        await self._api.client.delete(int(inbound_id), c.id)
        logger.info("Клиент удалён: %s (inbound_id=%s)", user_email, inbound_id)
        # True — один клиент с таким email был удалён
        return True

    async def get_online_clients_ids(self, timeout: int = 15) -> tuple:
        """Возвращает (set of email/ids, success)."""
        await self._ensure_login()
        try:
            emails = await self._api.client.online()
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
            online_emails, api_ok = await self.get_online_clients_ids(timeout=timeout)
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
                    for client in settings.get("clients", []):
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
        data = await self.list(timeout=timeout)
        if not data.get("success") or not data.get("obj"):
            return None
        for inbound in data["obj"]:
            stats = inbound.get("clientStats", [])
            if isinstance(stats, list):
                for s in stats:
                    if s.get("email") == user_email:
                        up = s.get("up", 0) or s.get("upload", 0)
                        down = s.get("down", 0) or s.get("download", 0)
                        total = s.get("total", 0)
                        return {"upload": up, "download": down, "total": total}
            elif isinstance(stats, dict):
                s = stats.get(user_email)
                if s:
                    return {
                        "upload": s.get("up", 0) or s.get("upload", 0),
                        "download": s.get("down", 0) or s.get("download", 0),
                        "total": s.get("total", 0),
                    }
        return None

    async def get_client_count(self, timeout: int = 15) -> int:
        data = await self.list(timeout=timeout)
        n = 0
        for inv in data.get("obj", []):
            try:
                settings = json.loads(inv.get("settings", "{}"))
                n += len(settings.get("clients", []))
            except (json.JSONDecodeError, TypeError):
                pass
        return n

    async def get_clients_status_count(self, timeout: int = 15) -> tuple:
        """Возвращает (total, active, expired)."""
        data = await self.list(timeout=timeout)
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        total = 0
        active = 0
        expired = 0
        for inv in data.get("obj", []):
            try:
                settings = json.loads(inv.get("settings", "{}"))
                for c in settings.get("clients", []):
                    total += 1
                    exp = c.get("expiryTime", 0) or 0
                    if exp == 0 or now_ms < exp:
                        active += 1
                    else:
                        expired += 1
            except (json.JSONDecodeError, TypeError):
                pass
        return total, active, expired

    async def sync_flow_for_all_clients(self, flow_value: str, timeout: int = 15) -> tuple:
        await self._ensure_login()
        updated = 0
        errors = []
        inbounds = await self._api.inbound.get_list()
        flow_val = (flow_value or "").strip() or None
        for inv in inbounds:
            protocol = (getattr(inv, "protocol", None) or "vless").lower()
            if protocol == "trojan":
                continue
            inv_id = getattr(inv, "id", None)
            settings = getattr(inv, "settings", None)
            clients = getattr(settings, "clients", None) or []
            for c in clients:
                try:
                    if flow_val:
                        c.flow = flow_val
                    else:
                        if hasattr(c, "flow"):
                            c.flow = ""
                    self._ensure_client_id_for_update(c)
                    await self._api.client.update(c.id, c)
                    updated += 1
                except Exception as e:
                    errors.append(f"{getattr(c, 'email', '?')}: {e}")
        return updated, errors

    async def link(self, user_id: str, server_name: Optional[str] = None) -> str:
        """Генерирует VLESS или TROJAN ссылку для клиента."""
        await self._ensure_login()
        data = await self.list()
        for inbounds in data.get("obj", []):
            try:
                settings = json.loads(inbounds.get("settings", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            stream = inbounds.get("streamSettings") or {}
            if isinstance(stream, str):
                try:
                    stream = json.loads(stream)
                except (json.JSONDecodeError, TypeError):
                    stream = {}
            client = next((c for c in settings.get("clients", []) if c.get("email") == user_id), None)
            if not client:
                continue
            protocol = (inbounds.get("protocol") or "vless").lower()
            if self.vpn_host:
                host_part = self.vpn_host.split("//")[-1] if "//" in self.vpn_host else self.vpn_host
                host = host_part.split(":")[0] if ":" in host_part else host_part
            else:
                host_part = self.host.split("//")[-1]
                host = host_part.split(":")[0] if ":" in host_part else host_part
            port = inbounds.get("port", 443)
            network = stream.get("network", "tcp")
            security = stream.get("security", "reality")
            xhttp_settings = stream.get("xhttpSettings", {}) or {}
            reality = stream.get("realitySettings", {}) or {}
            if isinstance(reality, dict) and "settings" in reality:
                reality = reality.get("settings", reality) or reality
            path = xhttp_settings.get("path", "/")
            xhttp_host = xhttp_settings.get("host", "")
            mode = xhttp_settings.get("mode", "auto")
            pbk = reality.get("publicKey", "")
            fingerprint = reality.get("fingerprint", "chrome")
            spx = reality.get("spiderX", "/") or "/"
            if network == "xhttp" and xhttp_host:
                sni = xhttp_host
            else:
                sni = reality.get("serverName") or (reality.get("target", "") or "").split(":")[0] or "google.com"
            short_ids = reality.get("shortIds", [""])
            sid = short_ids[0] if isinstance(short_ids, list) and short_ids else (short_ids if isinstance(short_ids, str) else "")
            tag = quote(server_name, safe="") if server_name else f"{os.getenv('VPN_BRAND_NAME', 'Daralla')}-{user_id}"
            if protocol == "trojan":
                password = client.get("password") or client.get("id", "")
                params = [("type", network), ("security", security), ("pbk", pbk), ("fp", fingerprint), ("sni", sni), ("sid", sid), ("spx", quote(spx))]
                query = "&".join(f"{k}={v}" for k, v in params if v)
                return f"trojan://{quote(password)}@{host}:{port}?{query}#{tag}"
            params = [("type", network)]
            client_flow = (client.get("flow") or "").strip() or None
            if client_flow:
                params.append(("flow", quote(client_flow, safe="")))
            if network == "xhttp":
                params.append(("encryption", "none"))
                if path:
                    params.append(("path", quote(path)))
                if xhttp_host:
                    params.append(("host", xhttp_host))
                if mode:
                    params.append(("mode", mode))
            params.extend([("security", security), ("pbk", pbk), ("fp", fingerprint), ("sni", sni), ("sid", sid), ("spx", quote(spx))])
            query = "&".join(f"{k}={v}" for k, v in params)
            return f"vless://{client.get('id', '')}@{host}:{port}?{query}#{tag}"
        return "Клиент не найден."

    async def get_subscription_link(self, user_email: str) -> str:
        await self._ensure_login()
        data = await self.list()
        if not data.get("success"):
            return ""
        for inv in data.get("obj", []):
            try:
                settings = json.loads(inv.get("settings", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            for client in settings.get("clients", []):
                if client.get("email") == user_email:
                    sub_id = client.get("subId", "")
                    if sub_id:
                        host_part = self.host.split("//")[-1]
                        if "/panel" in host_part:
                            host_part = host_part.split("/panel")[0]
                        return f"{self.host.split('//')[0]}//{host_part}/sub/{sub_id}"
                    return ""
        return ""

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
                # Убираем порт панели (59580), чтобы подставить только subscription_port (2096)
                if ":" in host_part:
                    host_only = host_part.rsplit(":", 1)[0]
                else:
                    host_only = host_part
                host_for_sub = (self.vpn_host or host_only).strip()
                if host_for_sub and ":" in host_for_sub:
                    host_for_sub = host_for_sub.rsplit(":", 1)[0]
                base_url = f"{scheme}://{host_for_sub}:{self.subscription_port}"
            client = await self._api.client.get_by_email(user_email)
            if not client:
                logger.debug("get_subscription_links: клиент не найден email=%s", user_email)
                return []
            # sub_id с панели; при создании через API панель может не сохранить subId (3x-ui #3237)
            sub_id = getattr(client, "sub_id", None) or getattr(client, "subId", None)
            if not sub_id and hasattr(client, "model_dump"):
                d = (client.model_dump() or {})
                sub_id = d.get("sub_id") or d.get("subId")
            if not sub_id and subscription_token:
                sub_id = subscription_token
                logger.debug("get_subscription_links: используем subscription_token как sub_id для email=%s", user_email)
            if not sub_id:
                logger.debug("get_subscription_links: sub_id пустой у клиента email=%s", user_email)
                return []
            sub_url = f"{base_url.rstrip('/')}/sub/{sub_id}"
            try:
                async with httpx.AsyncClient(verify=False, timeout=15.0) as hc:
                    r = await hc.get(sub_url)
                    if r.status_code != 200:
                        logger.debug(
                            "Subscription endpoint вернул не 200: url=%s status=%s body_len=%s",
                            sub_url, r.status_code, len(r.text or ""),
                        )
                        return []
                    text = r.text
            except Exception as e:
                logger.warning("Ошибка запроса subscription URL %s: %s", sub_url, e)
                return []
            # Некоторые панели отдают подписку в base64 (одна строка)
            raw = (text or "").strip()
            if raw and "vless://" not in raw and "vmess://" not in raw and "trojan://" not in raw:
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
                if "vless://" in line or "vmess://" in line or "trojan://" in line:
                    if flow_override and "vless://" in line and "flow=" not in line:
                        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
                        try:
                            parsed = urlparse(line)
                            qs = parse_qs(parsed.query)
                            qs["flow"] = [flow_override]
                            new_query = urlencode(qs, doseq=True)
                            line = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
                        except Exception:
                            pass
                    if server_name and "#" in line:
                        pre, _, frag = line.partition("#")
                        line = f"{pre}#{quote(server_name, safe='')}"
                    links.append(line)
            if not links and raw:
                logger.debug(
                    "Subscription endpoint вернул тело без vless/vmess/trojan: url=%s body_len=%s",
                    sub_url, len(raw),
                )
            return links
        except Exception as e:
            logger.error("Ошибка get_subscription_links для %s: %s", user_email, e)
            return []
