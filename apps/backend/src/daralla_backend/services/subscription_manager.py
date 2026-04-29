"""
Сервис для управления подписками (новая модель подписок и устройств).
Пока используется только слой работы с БД и подготовка к мультисерверности.
"""

import asyncio
import datetime
import json
import logging
import os
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
from .xui_helpers import panel_snapshot_matches_desired
from .subscription_helpers import (
    clients_by_email_from_xui_list_response,
    panel_entry_from_snapshot,
    normalize_subscription_link,
)

logger = logging.getLogger(__name__)


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
        # Точечные lock'и на пару (server_name, client_email) для serialize ensure.
        self._ensure_locks_guard = asyncio.Lock()
        self._ensure_locks: Dict[Tuple[str, str], asyncio.Lock] = {}

    async def _get_ensure_lock(self, server_name: str, client_email: str) -> asyncio.Lock:
        key = (str(server_name), str(client_email))
        async with self._ensure_locks_guard:
            lock = self._ensure_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._ensure_locks[key] = lock
            return lock

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
        dict при on_panel True: expiry_sec, limit_ip, flow, protocol (для reconcile без лишних запросов).
        
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
            protocol_aware_enabled = os.getenv("DARALLA_PROTOCOL_AWARE_SYNC", "1").strip() != "0"
            target_protocol = (
                (server_config.get("client_protocol") or server_config.get("protocol") or "").strip().lower()
                if server_config
                else ""
            ) or None
            target_inbound_id = None
            if server_config:
                raw_inbound_id = server_config.get("client_inbound_id")
                if raw_inbound_id is not None and str(raw_inbound_id).strip():
                    try:
                        target_inbound_id = int(raw_inbound_id)
                    except (TypeError, ValueError):
                        target_inbound_id = None
            if not protocol_aware_enabled:
                target_protocol = None
                target_inbound_id = None
            
            if panel_entry is not None:
                on_panel = bool(panel_entry.get("on_panel"))
            else:
                on_panel = await xui.client_exists(client_email)

            if on_panel:
                if panel_entry is not None and panel_snapshot_matches_desired(
                    panel_entry, expires_at, device_limit, client_flow
                ):
                    logger.debug(
                        "Клиент %s на сервере %s — snapshot совпадает, reconcile не нужен",
                        client_email, server_name,
                    )
                    return True, False

                if panel_entry is not None:
                    logger.debug("Клиент %s на сервере %s (снимок list, требует reconcile)", client_email, server_name)
                else:
                    logger.info(
                        "Клиент %s уже существует на сервере %s",
                        client_email,
                        server_name,
                    )
                try:
                    ok, did_update = await xui.reconcile_client(
                        client_email,
                        expiry_sec=expires_at,
                        limit_ip=device_limit,
                        flow_from_config=client_flow,
                        target_protocol=target_protocol,
                        target_inbound_id=target_inbound_id,
                    )
                    if not ok:
                        logger.warning(
                            "reconcile_client: клиент %s на %s не найден на панели после проверки наличия",
                            client_email,
                            server_name,
                        )
                        return False, False
                    elif did_update:
                        logger.info(
                            "Синхронизирован клиент %s на %s (expiry, limitIp, flow по БД/конфигу)",
                            client_email,
                            server_name,
                        )
                except Exception as rec_e:
                    root = rec_e
                    # tenacity RetryError hides underlying exception in last_attempt
                    last_attempt = getattr(rec_e, "last_attempt", None)
                    if last_attempt is not None:
                        try:
                            root = last_attempt.exception() or rec_e
                        except Exception:
                            root = rec_e
                    logger.warning(
                        "Ошибка reconcile_client на сервере %s для %s: %s (root=%r)",
                        server_name,
                        client_email,
                        rec_e,
                        root,
                    )
                    return False, False

                return True, False
            else:
                ensure_lock = await self._get_ensure_lock(server_name, client_email)
                async with ensure_lock:
                    # Под lock перепроверяем факт наличия на панели:
                    # другой параллельный ensure мог уже создать клиента.
                    exists_now = await xui.client_exists(client_email)
                    if exists_now:
                        ok, did_update = await xui.reconcile_client(
                            client_email,
                            expiry_sec=expires_at,
                            limit_ip=device_limit,
                            flow_from_config=client_flow,
                            target_protocol=target_protocol,
                            target_inbound_id=target_inbound_id,
                        )
                        if not ok:
                            return False, False
                        if did_update:
                            logger.info(
                                "Синхронизирован клиент %s на %s (expiry, limitIp, flow по БД/конфигу)",
                                client_email,
                                server_name,
                            )
                        return True, False

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
                        flow=client_flow,
                        target_protocol=target_protocol,
                        inbound_id=target_inbound_id,
                    )
                    created_ok = bool(created.get("ok")) if isinstance(created, dict) else bool(created)
                    if not created_ok and isinstance(created, dict):
                        reason = created.get("reason", "unknown")
                        logger.warning(
                            "Создание клиента пропущено/неуспешно: server=%s email=%s protocol=%s inbound_id=%s reason=%s detail=%s",
                            server_name,
                            client_email,
                            target_protocol or "auto",
                            target_inbound_id,
                            reason,
                            created.get("detail"),
                        )
                        return False, False

                    if created_ok:
                        logger.info(f"Клиент {client_email} успешно создан на сервере {server_name}")

                        # ВАЖНО: Устанавливаем точное время истечения из БД
                        # addClient использует округление до дней, что может давать неточное время
                        # Поэтому после создания устанавливаем точное время из expires_at
                        try:
                            logger.info(
                                f"Установка точного времени истечения и flow для клиента {client_email} "
                                f"на сервере {server_name}: {expires_at}"
                            )
                            ok_rec = False
                            # Под нагрузкой панель может не сразу отдавать свежего клиента в list/get_by_email.
                            # Не считаем это фатальной ошибкой создания: addClient уже успешен.
                            max_attempts = 4
                            for attempt in range(max_attempts):
                                ok_rec, _ = await xui.reconcile_client(
                                    client_email,
                                    expiry_sec=expires_at,
                                    limit_ip=device_limit,
                                    flow_from_config=client_flow,
                                    target_protocol=target_protocol,
                                    target_inbound_id=target_inbound_id,
                                )
                                if ok_rec:
                                    break
                                await asyncio.sleep(min(1.2, 0.3 * (attempt + 1)))

                            if ok_rec:
                                logger.info(
                                    f"Точное время и flow синхронизированы для клиента {client_email} "
                                    f"на сервере {server_name}"
                                )
                            else:
                                logger.warning(
                                    f"Не удалось синхронизировать клиента {client_email} "
                                    f"на сервере {server_name} сразу после создания "
                                    f"({max_attempts} попыток). Клиент создан, параметры будут догнаны "
                                    f"следующим sync/reconcile."
                                )
                                return True, True
                        except Exception as set_expiry_e:
                            details = str(set_expiry_e)
                            last_attempt = getattr(set_expiry_e, "last_attempt", None)
                            if last_attempt is not None and callable(getattr(last_attempt, "exception", None)):
                                try:
                                    cause = last_attempt.exception()
                                except Exception:
                                    cause = None
                                if cause is not None:
                                    details = f"{details}; root_cause={cause!r}"
                            logger.warning(
                                f"Ошибка синхронизации после создания клиента {client_email} "
                                f"на сервере {server_name}: {details}. "
                                f"Клиент создан, параметры будут догнаны позднее."
                            )
                            return True, True

                        return True, True  # Клиент создан

                    logger.error(f"Не удалось создать клиента на сервере {server_name}: неизвестная ошибка")
                    return False, False
                    
        except Exception as e:
            logger.error(f"Ошибка ensure_client_on_server для {server_name}: {e}")
            return False, False

    async def build_links_for_subscription(
        self, subscription_id: int
    ) -> List[str]:
        """
        Собирает набор ссылок подписки для всех серверов подписки.

        Возвращает уникальные ссылки любых поддерживаемых панелью протоколов
        (например, vless/vmess/trojan/hysteria2/tuic).
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
                            plain = normalize_subscription_link(link)
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
                            plain = normalize_subscription_link(vless_link)
                            link_without_tag = plain.split('#')[0] if '#' in plain else plain
                            if link_without_tag not in seen_links:
                                seen_links.add(link_without_tag)
                                links.append(plain)
                                logger.debug(
                                    "Ссылка сгенерирована вручную: server=%s, email=%s",
                                    resolved_name,
                                    client_email,
                                )
                            else:
                                logger.debug(f"Пропуск дубликата ссылки (ручная генерация) для {server_name}: {plain[:100]}...")
                        else:
                            logger.warning(
                                "Не удалось сгенерировать ссылку для server=%s, email=%s",
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

        logger.info(f"Сгенерировано {len(links)} уникальных ссылок для подписки {subscription_id}")
        return links

    async def build_vless_links_for_subscription(self, subscription_id: int) -> List[str]:
        """Backward-compatible alias for old call sites."""
        return await self.build_links_for_subscription(subscription_id)

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
            "ensure_skipped_unsupported": 0,
            "ensure_failed_protocol": 0,
            "clients_deleted_strict": 0,
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
                    except Exception as e:
                        logger.error(
                            f"Ошибка удаления сервера {server_name} для подписки {subscription_id}: {e}"
                        )
            except Exception as e:
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
                    return {
                        "pairs": [(t, Exception(f"Сервер {server_name} не в конфиге")) for t in tasks],
                        "strict_deleted": 0,
                        "strict_errors": [],
                    }
                xui, _ = found
                if xui is None:
                    return {
                        "pairs": [(t, Exception(f"Сервер {server_name} недоступен")) for t in tasks],
                        "strict_deleted": 0,
                        "strict_errors": [],
                    }
                email_map = None
                try:
                    data = await xui.list()
                    email_map = clients_by_email_from_xui_list_response(data)
                except Exception as e:
                    logger.warning(
                        "list() для сервера %s не удался, ensure по API на клиента: %s",
                        server_name,
                        e,
                    )
                try:
                    per_server_concurrency = int(os.getenv("XUI_SYNC_SERVER_CONCURRENCY", "2"))
                except ValueError:
                    per_server_concurrency = 2
                per_server_concurrency = max(1, min(per_server_concurrency, 15))
                sem = asyncio.Semaphore(per_server_concurrency)

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
                        except Exception as e:
                            return (t, e)

                pairs = await asyncio.gather(*[one(t) for t in tasks])

                # Если панель под нагрузкой и часть ensure не прошла, делаем мягкий догон:
                # повторяем только неуспешные задачи с меньшей параллельностью и без snapshot.
                retry_candidates: List[dict] = []
                for t, outcome in pairs:
                    if isinstance(outcome, Exception):
                        retry_candidates.append(t)
                        continue
                    client_exists, _ = outcome
                    if not client_exists:
                        retry_candidates.append(t)

                if retry_candidates:
                    logger.warning(
                        "Сервер %s: первичный ensure неуспешен для %s клиентов, запускаем догон",
                        server_name,
                        len(retry_candidates),
                    )
                    retry_sem = asyncio.Semaphore(max(1, min(3, per_server_concurrency)))

                    async def one_retry(t: dict):
                        async with retry_sem:
                            try:
                                r = await self.ensure_client_on_server(
                                    subscription_id=t["subscription_id"],
                                    server_name=server_name,
                                    client_email=t["client_email"],
                                    user_id=t["user_id"],
                                    expires_at=t["expires_at"],
                                    token=t["token"],
                                    device_limit=t["device_limit"],
                                    panel_entry=None,
                                )
                                return (t, r)
                            except Exception as e:
                                return (t, e)

                    retry_pairs = await asyncio.gather(*[one_retry(t) for t in retry_candidates])
                    retry_by_key = {
                        (rp[0]["subscription_id"], rp[0]["client_email"]): rp for rp in retry_pairs
                    }
                    merged_pairs = []
                    for t, outcome in pairs:
                        k = (t["subscription_id"], t["client_email"])
                        merged_pairs.append(retry_by_key.get(k, (t, outcome)))
                    pairs = merged_pairs

                # Жёсткий режим: сервер должен содержать только клиентов, назначенных группе
                # (email из ensure_tasks для этого server_name). Все лишние email удаляем.
                strict_deleted = 0
                strict_errors: List[str] = []
                expected_emails = {
                    str(t["client_email"]).strip()
                    for t in tasks
                    if t.get("client_email") is not None and str(t.get("client_email")).strip()
                }
                try:
                    latest = await xui.list()
                    panel_emails: set = set()
                    for inbound in latest.get("obj") or []:
                        try:
                            settings = json.loads(inbound.get("settings") or "{}")
                        except (json.JSONDecodeError, TypeError):
                            continue
                        for c in settings.get("clients") or []:
                            em = c.get("email")
                            if em is None:
                                continue
                            em = str(em).strip()
                            if em:
                                panel_emails.add(em)

                    extras = sorted(panel_emails - expected_emails)
                    missing = sorted(expected_emails - panel_emails)
                    for email in extras:
                        # На панели могут быть дубликаты email в нескольких inbound — удаляем до полного исчезновения.
                        max_delete_attempts = 5
                        for attempt in range(max_delete_attempts):
                            try:
                                deleted = await xui.deleteClient(email)
                            except Exception as del_e:
                                strict_errors.append(
                                    f"{server_name}: delete extra {email} failed ({type(del_e).__name__}: {del_e})"
                                )
                                break
                            if not deleted:
                                break
                            strict_deleted += 1
                    if strict_deleted > 0:
                        logger.info(
                            "Строгий sync состава: сервер %s, удалено лишних клиентов: %s",
                            server_name,
                            strict_deleted,
                        )
                    if missing:
                        strict_errors.append(
                            f"{server_name}: missing {len(missing)} expected clients after ensure"
                        )
                except Exception as strict_e:
                    strict_errors.append(
                        f"{server_name}: strict composition sync failed ({type(strict_e).__name__}: {strict_e})"
                    )

                return {
                    "pairs": pairs,
                    "strict_deleted": strict_deleted,
                    "strict_errors": strict_errors,
                }

            batches = await asyncio.gather(
                *[process_server(sn, tl) for sn, tl in by_server.items()],
                return_exceptions=True,
            )

            for batch in batches:
                if isinstance(batch, Exception):
                    stats["errors"].append(str(batch))
                    continue
                stats["clients_deleted_strict"] += int(batch.get("strict_deleted", 0))
                for se in batch.get("strict_errors", []):
                    stats["errors"].append(se)

                for pair in batch.get("pairs", []):
                    t, outcome = pair
                    if isinstance(outcome, Exception):
                        stats["errors"].append(
                            f"Подписка {t['subscription_id']}, server {t['server_name']}: {outcome}"
                        )
                        msg = str(outcome).lower()
                        if "unsupported_protocol" in msg:
                            stats["ensure_skipped_unsupported"] += 1
                        if "protocol" in msg:
                            stats["ensure_failed_protocol"] += 1
                        continue
                    client_exists, client_created = outcome
                    if not client_exists:
                        stats["errors"].append(
                            f"Подписка {t['subscription_id']}, server {t['server_name']}: "
                            f"ensure_client_on_server вернул client_exists=False"
                        )
                        stats["ensure_failed_protocol"] += 1
                        continue
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
            f"пропущено unsupported {stats['ensure_skipped_unsupported']}, "
            f"ошибок протокола {stats['ensure_failed_protocol']}, "
            f"удалено лишних (strict) {stats['clients_deleted_strict']} клиентов, "
            f"серверов (ensure) {stats['total_servers_checked']}, "
            f"ошибок {len(stats['errors'])}"
        )

        return stats

