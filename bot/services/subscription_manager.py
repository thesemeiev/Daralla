"""
Сервис для управления подписками (новая модель подписок и устройств).
Пока используется только слой работы с БД и подготовка к мультисерверности.
"""

import asyncio
import base64
import datetime
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ..db.users_db import get_or_create_subscriber
from ..db.subscriptions_db import (
    create_subscription,
    add_subscription_server,
    get_all_active_subscriptions_by_user,
    get_subscription_by_id_only,
    get_subscription_servers,
    get_subscription_servers_for_subscription_ids,
    remove_subscription_server,
    get_all_active_subscriptions,
    get_subscriptions_to_sync,
    update_subscription_name,
)
from .server_manager import MultiServerManager

logger = logging.getLogger(__name__)

_PROTOCOL_PREFIXES = ('vless://', 'trojan://', 'vmess://', 'ss://', 'socks://')


def clients_by_email_from_xui_list_response(list_payload: dict) -> Dict[str, Dict[str, Any]]:
    """
    Снимок клиентов с панели из ответа xui.list() (поле obj).
    email -> {expiry_sec, limit_ip}; при дубликате email последний inbound в обходе перезаписывает.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for inbound in list_payload.get("obj") or []:
        try:
            settings = json.loads(inbound.get("settings") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for client in settings.get("clients") or []:
            email = client.get("email")
            if not email:
                continue
            email = str(email)
            expiry_ms = client.get("expiryTime") or 0
            if not expiry_ms or int(expiry_ms) <= 0:
                expiry_sec = None
            else:
                expiry_sec = int(expiry_ms) // 1000
            out[email] = {"expiry_sec": expiry_sec, "limit_ip": client.get("limitIp")}
    return out


def panel_entry_from_snapshot(email_map: Optional[Dict[str, Dict[str, Any]]], client_email: str) -> Optional[dict]:
    """None — нет снимка, ходим в API как раньше. Иначе запись для ensure_client_on_server."""
    if email_map is None:
        return None
    row = email_map.get(client_email)
    if row is None:
        return {"on_panel": False}
    return {
        "on_panel": True,
        "expiry_sec": row["expiry_sec"],
        "limit_ip": row.get("limit_ip"),
    }


def _normalize_subscription_link(link: str) -> str:
    """
    Если ссылка пришла в base64 (часто от X-UI) — декодирует и возвращает plain vless:// или trojan://.
    Иначе возвращает ссылку как есть.
    """
    if not link or not link.strip():
        return link
    s = link.strip()
    if s.startswith(_PROTOCOL_PREFIXES):
        return s
    try:
        raw = base64.b64decode(s)
        decoded = raw.decode('utf-8')
        if decoded.startswith(_PROTOCOL_PREFIXES):
            return decoded
    except (ValueError, TypeError):
        pass
    return s


class SubscriptionManager:
    """
    Высокоуровневый менеджер подписок.

    Отвечает за:
    - создание подписки для пользователя;
    - привязку подписки к серверам XUI (subscription_servers);
    - подготовку данных для мультисерверной подписки (список нод);
    - (в дальнейшем) продление и апгрейд количества устройств.
    """

    def __init__(self, server_manager: MultiServerManager):
        self.server_manager = server_manager

    async def create_subscription_for_user(
        self,
        user_id: str,
        period: str,
        device_limit: int,
        price: float,
        name: str | None = None,
        group_id: int | None = None,
        expires_at: int | None = None,
    ) -> Tuple[dict, str]:
        """
        Создаёт базовую подписку для пользователя в БД.
        
        Args:
            user_id: ID пользователя Telegram
            period: Период подписки (month, 3month)
            device_limit: Лимит устройств
            price: Цена подписки
            name: Имя подписки
            group_id: ID группы серверов (если None, выбирается автоматически)
            expires_at: Точное время истечения (если None, рассчитывается по периоду)
        """
        logger.info(
            "Создание подписки: user_id=%s, period=%s, device_limit=%s, price=%s, name=%s, group_id=%s",
            user_id,
            period,
            device_limit,
            price,
            name,
            group_id,
        )

        # 1. Получаем/создаём подписчика (group_id разрешается внутри create_subscription через resolve_group_id)
        subscriber_id = await get_or_create_subscriber(user_id)

        # 2. Считаем срок действия, если не передан
        if expires_at is None:
            days = 90 if period == "3month" else 30
            now = int(datetime.datetime.now().timestamp())
            expires_at = now + days * 24 * 60 * 60

        # 3. Если имя не указано, генерируем автоматически
        if not name:
            existing_subs = await get_all_active_subscriptions_by_user(user_id)
            subscription_number = len(existing_subs) + 1
            name = f"Подписка {subscription_number}"

        # 4. Создаём запись подписки
        subscription_id, token = await create_subscription(
            subscriber_id=subscriber_id,
            period=period,
            device_limit=device_limit,
            price=price,
            expires_at=expires_at,
            name=name,
            group_id=group_id
        )

        # 5. Получаем созданную подписку
        from ..db.subscriptions_db import get_subscription_by_id_only
        sub_dict = await get_subscription_by_id_only(subscription_id)
        
        logger.info(
            "Подписка создана: subscription_id=%s, token=%s, user_id=%s, group_id=%s",
            subscription_id,
            token,
            user_id,
            sub_dict.get("group_id"),
        )
        return sub_dict, token


    async def attach_server_to_subscription(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        client_id: Optional[str] = None,
    ) -> int:
        """
        Регистрирует связь подписки с конкретным сервером XUI.

        Используется после успешного создания клиента на сервере.
        """
        logger.info(
            "Привязка сервера к подписке: subscription_id=%s, server=%s, email=%s",
            subscription_id,
            server_name,
            client_email,
        )
        return await add_subscription_server(
            subscription_id=subscription_id,
            server_name=server_name,
            client_email=client_email,
            client_id=client_id,
        )

    async def ensure_client_on_server(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        user_id: str,
        expires_at: int,
        token: str,
        device_limit: int = None,
        panel_entry: Optional[dict] = None,
    ) -> Tuple[bool, bool]:
        """
        Гарантирует наличие клиента на сервере.
        
        Если клиента нет - создает его.
        Если клиент есть - проверяет и синхронизирует время истечения и limitIp.
        
        panel_entry: снимок с панели из одного list() на сервер. None — как раньше (client_exists + get_*).
        dict: {"on_panel": bool, "expiry_sec": int|None, "limit_ip": int|None} при on_panel True.
        
        Returns:
            Tuple[bool, bool]:
                - Первый bool: True если клиент существует/создан успешно
                - Второй bool: True если клиент был создан (False если уже существовал)
        """
        try:
            # Получаем device_limit из подписки, если не передан
            if device_limit is None:
                from ..db import get_subscription_by_id_only
                sub = await get_subscription_by_id_only(subscription_id)
                if sub:
                    device_limit = sub.get('device_limit', 1)
                    logger.debug(f"Получен device_limit={device_limit} для подписки {subscription_id}")
                else:
                    device_limit = 1  # Fallback
                    logger.warning(f"Не удалось найти подписку {subscription_id} для получения device_limit, используем 1")
            
            found = self.server_manager.find_server_by_name(server_name)
            if found is None:
                logger.error("Сервер %s не в конфиге бота", server_name)
                return False, False
            xui, resolved_name = found
            if xui is None:
                logger.error(f"Сервер {server_name} недоступен")
                return False, False
            
            # Flow из конфига сервера — передаём при любом обновлении клиента, чтобы не слетал в X-UI
            server_config = self.server_manager.get_server_config(server_name)
            client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
            
            if panel_entry is not None:
                on_panel = bool(panel_entry.get("on_panel"))
            else:
                on_panel = await xui.client_exists(client_email)

            if on_panel:
                if panel_entry is not None:
                    logger.debug("Клиент %s на сервере %s (снимок list)", client_email, server_name)
                    server_expiry = panel_entry.get("expiry_sec")
                else:
                    logger.info(f"Клиент {client_email} уже существует на сервере {server_name}")
                    server_expiry = await xui.get_client_expiry_time(client_email)

                # Проверяем и синхронизируем время истечения
                # ВАЖНО: БД - источник истины. Мы синхронизируем серверы С БД, но НЕ изменяем БД на основе данных с сервера
                try:
                    tolerance = 5 * 60

                    if server_expiry:
                        time_diff = abs(server_expiry - expires_at)

                        if time_diff > tolerance:
                            if server_expiry < expires_at:
                                days_to_add = (expires_at - server_expiry) // (24 * 60 * 60)
                                if days_to_add > 0:
                                    logger.info(
                                        f"Синхронизация времени истечения на сервере {server_name}: "
                                        f"добавляем {days_to_add} дней (сервер: {server_expiry}, БД: {expires_at})"
                                    )
                                    await xui.extendClient(client_email, days_to_add, flow=client_flow)
                                    logger.info(
                                        f"Время истечения синхронизировано на сервере {server_name} "
                                        f"(продлено до значения БД)"
                                    )
                            else:
                                logger.info(
                                    f"Синхронизация времени истечения на сервере {server_name}: "
                                    f"устанавливаем точное время из БД (сервер: {server_expiry}, БД: {expires_at})"
                                )
                                try:
                                    updated = await xui.setClientExpiry(client_email, expires_at, flow=client_flow)
                                    if updated:
                                        logger.info(
                                            f"Время истечения синхронизировано на сервере {server_name} "
                                            f"(установлено значение из БД)"
                                        )
                                    else:
                                        logger.warning(
                                            f"Не удалось установить точное время на сервере {server_name}: "
                                            f"клиент не найден"
                                        )
                                except (RuntimeError, ValueError, TypeError) as set_expiry_e:
                                    logger.error(
                                        f"Ошибка установки точного времени на сервере {server_name}: {set_expiry_e}"
                                    )
                        else:
                            logger.debug(
                                f"Время истечения на сервере {server_name} совпадает с БД "
                                f"(разница: {time_diff} сек, допуск: {tolerance} сек)"
                            )
                except (RuntimeError, ValueError, TypeError) as sync_e:
                    logger.warning(f"Ошибка синхронизации времени на сервере {server_name}: {sync_e}")

                try:
                    if panel_entry is not None:
                        current_limit_ip = panel_entry.get("limit_ip")
                    else:
                        client_info = await xui.get_client_info(client_email)
                        current_limit_ip = client_info["client"].get("limitIp") if client_info else None

                    if current_limit_ip is None or current_limit_ip == 0 or current_limit_ip != device_limit:
                        current_limit_display = current_limit_ip if current_limit_ip is not None else "не установлен"
                        logger.info(
                            f"Синхронизация limitIp на сервере {server_name} для клиента {client_email}: "
                            f"{current_limit_display} -> {device_limit}"
                        )
                        try:
                            await xui.updateClientLimitIp(client_email, device_limit, flow=client_flow)
                            logger.info(
                                f"limitIp успешно синхронизирован на сервере {server_name} для клиента {client_email}"
                            )
                        except (RuntimeError, ValueError, TypeError) as update_e:
                            logger.error(
                                f"Ошибка обновления limitIp на сервере {server_name} для клиента {client_email}: {update_e}"
                            )
                    else:
                        logger.debug(
                            f"limitIp для клиента {client_email} на сервере {server_name} уже равен {device_limit}, "
                            f"синхронизация не требуется"
                        )
                except (RuntimeError, ValueError, TypeError, KeyError) as limit_sync_e:
                    logger.warning(
                        f"Ошибка синхронизации limitIp на сервере {server_name} для клиента {client_email}: {limit_sync_e}"
                    )

                return True, False
            else:
                logger.info(f"Клиент {client_email} не найден на сервере {server_name}, создаем...")
                current_time = int(time.time())
                days_remaining = max(1, (expires_at - current_time) // (24 * 60 * 60))
                server_config = self.server_manager.get_server_config(server_name)
                logger.info(f"Создание клиента {client_email} на сервере {server_name} с limitIp={device_limit}")
                client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
                created = await xui.addClient(
                    day=days_remaining,
                    tg_id=user_id,
                    user_email=client_email,
                    timeout=15,
                    key_name=token,
                    limit_ip=device_limit,
                    flow=client_flow
                )
                
                if created:
                    logger.info(f"Клиент {client_email} успешно создан на сервере {server_name}")

                    # ВАЖНО: Устанавливаем точное время истечения из БД
                    # addClient использует округление до дней, что может давать неточное время
                    # Поэтому после создания устанавливаем точное время из expires_at
                    try:
                        logger.info(
                            f"Установка точного времени истечения для клиента {client_email} "
                            f"на сервере {server_name}: {expires_at}"
                        )
                        updated = await xui.setClientExpiry(client_email, expires_at, flow=client_flow)
                        if updated:
                            logger.info(
                                f"Точное время истечения установлено для клиента {client_email} "
                                f"на сервере {server_name}"
                            )
                        else:
                            logger.warning(
                                f"Не удалось установить точное время истечения для клиента {client_email} "
                                f"на сервере {server_name}: клиент не найден"
                            )
                    except (RuntimeError, ValueError, TypeError) as set_expiry_e:
                        logger.warning(
                            f"Ошибка установки точного времени истечения для клиента {client_email} "
                            f"на сервере {server_name}: {set_expiry_e}"
                        )
                        # Не критично - клиент создан, время будет синхронизировано при следующей синхронизации
                    
                    return True, True  # Клиент создан

                logger.error(f"Не удалось создать клиента на сервере {server_name}: неизвестная ошибка")
                return False, False
                    
        except (RuntimeError, ValueError, TypeError, KeyError) as e:
            logger.error(f"Ошибка ensure_client_on_server для {server_name}: {e}")
            return False, False

    async def build_vless_links_for_subscription(
        self, subscription_id: int
    ) -> List[str]:
        """
        Собирает набор VLESS-ссылок для подписки на основе subscription_servers и конфигурации серверов.
        
        Возвращает список VLESS ссылок для всех серверов, привязанных к подписке (без дубликатов).
        """
        servers = await get_subscription_servers(subscription_id)
        # Токен подписки: при создании клиента через API панель 3x-ui может не сохранить subId (issue #3237),
        # поэтому передаём token в get_subscription_links как fallback для URL /sub/{token}.
        sub_record = await get_subscription_by_id_only(subscription_id)
        subscription_token = (sub_record or {}).get("subscription_token") or None

        links: List[str] = []
        seen_links = set()  # Для дедупликации ссылок (без tag)

        for s in servers:
            server_name = s["server_name"]
            client_email = s["client_email"]

            try:
                found = self.server_manager.find_server_by_name(server_name)
                if found is None:
                    logger.warning(
                        "Сервер %s не в конфиге бота (удалён или переименован), пропуск для подписки %s",
                        server_name,
                        subscription_id,
                    )
                    continue
                xui, resolved_name = found
                if xui is None:
                    logger.warning(
                        "Сервер %s недоступен для подписки %s",
                        server_name,
                        subscription_id,
                    )
                    continue
                
                # Получаем display_name сервера из конфигурации (если есть)
                # Это будет название конкретного сервера (локация)
                server_config = self.server_manager.get_server_config(server_name)
                server_display_name = server_config.get("display_name") or resolved_name
                
                # Используем только название сервера в tag
                # VPN клиент будет группировать серверы по главному названию из subscription URL
                # Главное название задается через VPN_BRAND_NAME, но в tag используем только название сервера
                display_name = server_display_name
                logger.info(f"Формируем название для VPN клиента: '{display_name}' (server='{server_display_name}')")
                
                # Используем готовый subscription endpoint X-UI вместо ручной генерации.
                # Передаём client_flow: X-UI часто не добавляет flow в URL подписки — без него VPN-клиент не парсит flow.
                try:
                    client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
                    xui_links = await xui.get_subscription_links(
                        client_email,
                        server_name=display_name,
                        flow_override=client_flow,
                        subscription_token=subscription_token,
                    )
                    if xui_links:
                        # Дедупликация: добавляем только уникальные ссылки (по части без tag)
                        for link in xui_links:
                            plain = _normalize_subscription_link(link)
                            link_without_tag = plain.split('#')[0] if '#' in plain else plain
                            if link_without_tag not in seen_links:
                                seen_links.add(link_without_tag)
                                links.append(plain)
                            else:
                                logger.debug(f"Пропуск дубликата ссылки для {server_name}: {plain[:100]}...")
                        logger.debug(
                            "Обработано ссылок из X-UI subscription endpoint: server=%s, email=%s",
                            resolved_name,
                            client_email,
                        )
                    else:
                        # Fallback: если subscription endpoint не работает, используем ручную генерацию
                        logger.warning(
                            "Subscription endpoint не вернул ссылки, используем ручную генерацию: server=%s, email=%s",
                            resolved_name,
                            client_email,
                        )
                        vless_link = await xui.link(client_email, server_name=display_name)
                        if vless_link and vless_link != 'Клиент не найден.':
                            plain = _normalize_subscription_link(vless_link)
                            link_without_tag = plain.split('#')[0] if '#' in plain else plain
                            if link_without_tag not in seen_links:
                                seen_links.add(link_without_tag)
                                links.append(plain)
                                logger.debug(
                                    "VLESS ссылка сгенерирована вручную: server=%s, email=%s",
                                    resolved_name,
                                    client_email,
                                )
                            else:
                                logger.debug(f"Пропуск дубликата ссылки (ручная генерация) для {server_name}: {plain[:100]}...")
                        else:
                            logger.warning(
                                "Не удалось сгенерировать VLESS ссылку для server=%s, email=%s",
                                resolved_name,
                                client_email,
                            )
                except (RuntimeError, ValueError, TypeError, KeyError) as link_e:
                    logger.error(
                        "Ошибка получения ссылок для server=%s, email=%s: %s",
                        resolved_name,
                        client_email,
                        link_e,
                    )
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                logger.error(
                    "Не удалось получить сервер %s для подписки %s: %s",
                    server_name,
                    subscription_id,
                    e,
                )
                continue

        logger.info(f"Сгенерировано {len(links)} уникальных VLESS ссылок для подписки {subscription_id}")
        return links

    async def sync_servers_with_config(self, auto_create_clients: bool = True) -> dict:
        """
        Синхронизирует подписки с серверами (БД → Серверы).

        Принцип: БД — источник истины. Связь подписка–сервер снимается только если сервер
        больше не входит в группу (удалён, другая группа). Временно выключенные (is_active=0)
        остаются в subscription_servers — ссылки на них не отдаются, пока сервер не в рантайме.
        """
        logger.info("Начало синхронизации подписок с серверами (БД → Серверы)")

        # Получаем все подписки, которые нужно синхронизировать
        all_subscriptions = await get_subscriptions_to_sync()

        from ..db.servers_db import get_servers_config

        all_servers_rows = await get_servers_config(only_active=False)
        servers_by_group = {}
        servers_by_group_all = {}
        for s in all_servers_rows:
            g_id = s["group_id"]
            name = s["name"]
            servers_by_group_all.setdefault(g_id, []).append(name)
            if s.get("is_active", 1):
                servers_by_group.setdefault(g_id, []).append(name)
        
        stats = {
            "subscriptions_checked": len(all_subscriptions),
            "servers_added": 0,
            "servers_removed": 0,
            "clients_created": 0,
            "clients_restored": 0,
            "total_servers_checked": 0,
            "total_servers_synced": 0,
            "subscriptions_synced": 0,
            "errors": [],
        }

        # Фаза 1: только БД (связи подписка–сервер). Клиентов на панели X-UI при снятии связи не удаляем.
        for sub in all_subscriptions:
            subscription_id = sub["id"]
            user_id = sub["user_id"]
            token = sub["subscription_token"]
            expires_at = sub["expires_at"]
            device_limit = sub.get("device_limit", 1)
            group_id = sub.get("group_id")

            if group_id is None:
                logger.warning(f"Подписка {subscription_id} не имеет group_id, пропускаем")
                continue

            group_servers = set(servers_by_group.get(group_id, []))
            group_servers_all = set(servers_by_group_all.get(group_id, []))

            try:
                current_servers = await get_subscription_servers(subscription_id)
                current_server_names = {s["server_name"] for s in current_servers}

                if current_servers:
                    client_email = current_servers[0]["client_email"]
                else:
                    client_email = f"{user_id}_{subscription_id}"

                for server_name in group_servers:
                    if server_name not in current_server_names:
                        try:
                            await add_subscription_server(
                                subscription_id=subscription_id,
                                server_name=server_name,
                                client_email=client_email,
                                client_id=None,
                            )
                            stats["servers_added"] += 1
                            logger.info(
                                f"Добавлена связь подписки {subscription_id} с сервером {server_name} в БД"
                            )
                        except (RuntimeError, ValueError, TypeError) as e:
                            stats["errors"].append(f"Подписка {subscription_id}, server {server_name}: {e}")

                servers_to_remove = current_server_names - group_servers_all
                for server_name in servers_to_remove:
                    try:
                        await remove_subscription_server(subscription_id, server_name)
                        stats["servers_removed"] += 1
                        logger.info(
                            f"Удалена связь подписки {subscription_id} с сервером {server_name} "
                            f"(сервер удалён из группы или перенесён); панель X-UI не изменялась"
                        )
                    except (RuntimeError, ValueError, TypeError, KeyError) as e:
                        logger.error(
                            f"Ошибка удаления сервера {server_name} для подписки {subscription_id}: {e}"
                        )
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                stats["errors"].append(f"Подписка {subscription_id}: {e}")

        # Фаза 2: один list() на X-UI сервер, затем ensure с снимком (без лишних get_by_email).
        # auto_create_clients=False: как прежний шаг 2 sync_all — только активные подписки (без второго полного прохода).
        subs_for_ensure = all_subscriptions if auto_create_clients else await get_all_active_subscriptions()

        if subs_for_ensure:
            sync_sub_ids = [s["id"] for s in subs_for_ensure if s.get("group_id") is not None]
            servers_by_sub = await get_subscription_servers_for_subscription_ids(sync_sub_ids)

            ensure_tasks: List[dict] = []
            for sub in subs_for_ensure:
                subscription_id = sub["id"]
                user_id = sub["user_id"]
                token = sub["subscription_token"]
                expires_at = sub["expires_at"]
                device_limit = sub.get("device_limit", 1)
                group_id = sub.get("group_id")
                if group_id is None:
                    continue
                group_servers = set(servers_by_group.get(group_id, []))
                if not group_servers:
                    continue
                cur = servers_by_sub.get(subscription_id, [])
                client_email = cur[0]["client_email"] if cur else f"{user_id}_{subscription_id}"
                for server_name in group_servers:
                    ensure_tasks.append(
                        {
                            "subscription_id": subscription_id,
                            "server_name": server_name,
                            "client_email": client_email,
                            "user_id": user_id,
                            "expires_at": expires_at,
                            "token": token,
                            "device_limit": device_limit,
                        }
                    )

            stats["total_servers_checked"] = len(ensure_tasks)
            sub_total: Dict[int, int] = defaultdict(int)
            sub_ok: Dict[int, int] = defaultdict(int)
            for t in ensure_tasks:
                sub_total[t["subscription_id"]] += 1

            by_server: Dict[str, List[dict]] = defaultdict(list)
            for t in ensure_tasks:
                by_server[t["server_name"]].append(t)

            async def process_server(server_name: str, tasks: List[dict]):
                found = self.server_manager.find_server_by_name(server_name)
                if found is None:
                    return [(t, Exception(f"Сервер {server_name} не в конфиге")) for t in tasks]
                xui, _ = found
                if xui is None:
                    return [(t, Exception(f"Сервер {server_name} недоступен")) for t in tasks]
                email_map = None
                try:
                    data = await xui.list()
                    email_map = clients_by_email_from_xui_list_response(data)
                except (RuntimeError, ValueError, TypeError) as e:
                    logger.warning(
                        "list() для сервера %s не удался, ensure по API на клиента: %s",
                        server_name,
                        e,
                    )
                sem = asyncio.Semaphore(15)

                async def one(t: dict):
                    async with sem:
                        pe = panel_entry_from_snapshot(email_map, t["client_email"])
                        try:
                            r = await self.ensure_client_on_server(
                                subscription_id=t["subscription_id"],
                                server_name=server_name,
                                client_email=t["client_email"],
                                user_id=t["user_id"],
                                expires_at=t["expires_at"],
                                token=t["token"],
                                device_limit=t["device_limit"],
                                panel_entry=pe,
                            )
                            return (t, r)
                        except (RuntimeError, ValueError, TypeError, KeyError) as e:
                            return (t, e)

                return await asyncio.gather(*[one(t) for t in tasks])

            batches = await asyncio.gather(
                *[process_server(sn, tl) for sn, tl in by_server.items()],
                return_exceptions=True,
            )

            for batch in batches:
                if isinstance(batch, Exception):
                    stats["errors"].append(str(batch))
                    continue
                for pair in batch:
                    t, outcome = pair
                    if isinstance(outcome, Exception):
                        stats["errors"].append(
                            f"Подписка {t['subscription_id']}, server {t['server_name']}: {outcome}"
                        )
                        continue
                    client_exists, client_created = outcome
                    if client_created:
                        stats["clients_created"] += 1
                    elif client_exists:
                        stats["clients_restored"] += 1
                    if client_exists:
                        stats["total_servers_synced"] += 1
                        sub_ok[t["subscription_id"]] += 1

            for sid, total in sub_total.items():
                if total > 0 and sub_ok.get(sid, 0) == total:
                    stats["subscriptions_synced"] += 1

        logger.info(
            f"Синхронизация завершена: "
            f"проверено {stats['subscriptions_checked']} подписок, "
            f"добавлено {stats['servers_added']} серверов, "
            f"удалено {stats['servers_removed']} серверов, "
            f"создано {stats['clients_created']} клиентов, "
            f"восстановлено {stats['clients_restored']} клиентов, "
            f"серверов (ensure) {stats['total_servers_checked']}, "
            f"ошибок {len(stats['errors'])}"
        )

        return stats

