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
from typing import Optional, Tuple, List

from ..db.subscribers_db import (
    get_or_create_subscriber,
    create_subscription,
    add_subscription_server,
    get_all_active_subscriptions_by_user,
    get_subscription_servers,
    remove_subscription_server,
    get_all_active_subscriptions,
    get_subscriptions_to_sync,
    update_subscription_name,
)
from .server_manager import MultiServerManager

logger = logging.getLogger(__name__)

_PROTOCOL_PREFIXES = ('vless://', 'trojan://', 'vmess://', 'ss://', 'socks://')


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
    except Exception:
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

        # 1. Если group_id не указан, выбираем наименее загруженную группу
        if group_id is None:
            from ..db.subscribers_db import get_least_loaded_group_id
            group_id = await get_least_loaded_group_id()
            logger.info(f"Автоматически выбрана группа серверов: {group_id}")

        # 2. Получаем/создаём подписчика
        subscriber_id = await get_or_create_subscriber(user_id)

        # 3. Считаем срок действия, если не передан
        if expires_at is None:
            days = 90 if period == "3month" else 30
            now = int(datetime.datetime.now().timestamp())
            expires_at = now + days * 24 * 60 * 60

        # 4. Если имя не указано, генерируем автоматически
        if not name:
            existing_subs = await get_all_active_subscriptions_by_user(user_id)
            subscription_number = len(existing_subs) + 1
            name = f"Подписка {subscription_number}"

        # 5. Создаём запись подписки
        subscription_id, token = await create_subscription(
            subscriber_id=subscriber_id,
            period=period,
            device_limit=device_limit,
            price=price,
            expires_at=expires_at,
            name=name,
            group_id=group_id
        )

        # 6. Получаем созданную подписку
        from ..db.subscribers_db import get_subscription_by_id_only
        sub_dict = await get_subscription_by_id_only(subscription_id)
        
        logger.info(
            "Подписка создана: subscription_id=%s, token=%s, user_id=%s, group_id=%s",
            subscription_id,
            token,
            user_id,
            group_id,
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
    ) -> Tuple[bool, bool]:
        """
        Гарантирует наличие клиента на сервере.
        
        Если клиента нет - создает его.
        Если клиент есть - проверяет и синхронизирует время истечения и limitIp.
        
        Args:
            subscription_id: ID подписки
            server_name: Имя сервера
            client_email: Email клиента
            user_id: ID пользователя Telegram
            expires_at: Время истечения подписки (timestamp)
            token: Токен подписки
            device_limit: Лимит устройств/IP (если None, получается из подписки)
        
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
            
            xui, resolved_name = self.server_manager.get_server_by_name(server_name)
            if xui is None:
                logger.error(f"Сервер {server_name} недоступен")
                return False, False
            
            # Flow из конфига сервера — передаём при любом обновлении клиента, чтобы не слетал в X-UI
            server_config = self.server_manager.get_server_config(server_name)
            client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
            
            # Проверяем существование клиента
            if xui.client_exists(client_email):
                logger.info(f"Клиент {client_email} уже существует на сервере {server_name}")
                
                # Проверяем и синхронизируем время истечения
                # ВАЖНО: БД - источник истины. Мы синхронизируем серверы С БД, но НЕ изменяем БД на основе данных с сервера
                try:
                    server_expiry = xui.get_client_expiry_time(client_email)
                    current_time = int(time.time())
                    
                    # Допустимая разница в секундах (5 минут) - чтобы не синхронизировать из-за небольших расхождений
                    tolerance = 5 * 60
                    
                    if server_expiry:
                        # Проверяем разницу между временем на сервере и в БД
                        time_diff = abs(server_expiry - expires_at)
                        
                        if time_diff > tolerance:
                            # Время отличается значительно - синхронизируем сервер с БД
                            # БД - источник истины, поэтому мы всегда приводим сервер к значению БД
                            if server_expiry < expires_at:
                                # Время на сервере меньше, чем в БД - продлеваем на сервере до значения БД
                                days_to_add = (expires_at - server_expiry) // (24 * 60 * 60)
                                if days_to_add > 0:
                                    logger.info(
                                        f"Синхронизация времени истечения на сервере {server_name}: "
                                        f"добавляем {days_to_add} дней (сервер: {server_expiry}, БД: {expires_at})"
                                    )
                                    response = xui.extendClient(client_email, days_to_add, flow=client_flow)
                                    if response and response.status_code == 200:
                                        try:
                                            response_json = response.json()
                                            if response_json.get('success', False):
                                                logger.info(f"Время истечения синхронизировано на сервере {server_name} (продлено до значения БД)")
                                            else:
                                                logger.warning(f"Не удалось синхронизировать время на сервере {server_name}")
                                        except (json.JSONDecodeError, ValueError):
                                            logger.warning(f"Ответ от {server_name} не является валидным JSON при синхронизации")
                            else:
                                # Время на сервере больше, чем в БД - устанавливаем точное время из БД
                                # Это может произойти если админ вручную продлил ключ на сервере
                                # Но БД остается источником истины, поэтому уменьшаем время на сервере до значения БД
                                logger.info(
                                    f"Синхронизация времени истечения на сервере {server_name}: "
                                    f"устанавливаем точное время из БД (сервер: {server_expiry}, БД: {expires_at})"
                                )
                                try:
                                    response = xui.setClientExpiry(client_email, expires_at, flow=client_flow)
                                    if response and response.status_code == 200:
                                        try:
                                            response_json = response.json()
                                            if response_json.get('success', False):
                                                logger.info(f"Время истечения синхронизировано на сервере {server_name} (установлено значение из БД)")
                                            else:
                                                logger.warning(f"Не удалось установить точное время на сервере {server_name}")
                                        except (json.JSONDecodeError, ValueError):
                                            logger.warning(f"Ответ от {server_name} не является валидным JSON при установке времени")
                                except Exception as set_expiry_e:
                                    logger.error(f"Ошибка установки точного времени на сервере {server_name}: {set_expiry_e}")
                        else:
                            # Время совпадает (в пределах допуска) - синхронизация не требуется
                            logger.debug(
                                f"Время истечения на сервере {server_name} совпадает с БД "
                                f"(разница: {time_diff} сек, допуск: {tolerance} сек)"
                            )
                except Exception as sync_e:
                    logger.warning(f"Ошибка синхронизации времени на сервере {server_name}: {sync_e}")
                
                # Проверяем и синхронизируем limitIp
                try:
                    client_info = xui.get_client_info(client_email)
                    if client_info:
                        # Получаем текущий limitIp (если не установлен, получаем None, а не 0)
                        # Это важно, чтобы правильно определить, нужно ли устанавливать limitIp
                        current_limit_ip = client_info['client'].get('limitIp')
                        # Если limitIp отсутствует (None), равен 0, или отличается от device_limit - синхронизируем
                        if current_limit_ip is None or current_limit_ip == 0 or current_limit_ip != device_limit:
                            current_limit_display = current_limit_ip if current_limit_ip is not None else "не установлен"
                            logger.info(
                                f"Синхронизация limitIp на сервере {server_name} для клиента {client_email}: "
                                f"{current_limit_display} -> {device_limit}"
                            )
                            try:
                                xui.updateClientLimitIp(client_email, device_limit, flow=client_flow)
                                logger.info(f"limitIp успешно синхронизирован на сервере {server_name} для клиента {client_email}")
                            except Exception as update_e:
                                logger.error(f"Ошибка обновления limitIp на сервере {server_name} для клиента {client_email}: {update_e}")
                        else:
                            logger.debug(f"limitIp для клиента {client_email} на сервере {server_name} уже равен {device_limit}, синхронизация не требуется")
                    else:
                        logger.warning(f"Не удалось получить информацию о клиенте {client_email} на сервере {server_name} для синхронизации limitIp")
                except Exception as limit_sync_e:
                    logger.warning(f"Ошибка синхронизации limitIp на сервере {server_name} для клиента {client_email}: {limit_sync_e}")
                
                return True, False  # Клиент существует, не создавали
            else:
                # Клиент не найден - создаем его
                logger.info(f"Клиент {client_email} не найден на сервере {server_name}, создаем...")
                current_time = int(time.time())
                days_remaining = max(1, (expires_at - current_time) // (24 * 60 * 60))
                server_config = self.server_manager.get_server_config(server_name)
                logger.info(f"Создание клиента {client_email} на сервере {server_name} с limitIp={device_limit}")
                client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
                response = xui.addClient(
                    day=days_remaining,
                    tg_id=user_id,
                    user_email=client_email,
                    timeout=15,
                    key_name=token,
                    limit_ip=device_limit,
                    flow=client_flow
                )
                
                if response and response.status_code == 200:
                    try:
                        response_json = response.json()
                        if response_json.get('success', False):
                            logger.info(f"Клиент {client_email} успешно создан на сервере {server_name}")
                            
                            # ВАЖНО: Устанавливаем точное время истечения из БД
                            # addClient использует округление до дней, что может давать неточное время
                            # Поэтому после создания устанавливаем точное время из expires_at
                            try:
                                logger.info(f"Установка точного времени истечения для клиента {client_email} на сервере {server_name}: {expires_at}")
                                expiry_response = xui.setClientExpiry(client_email, expires_at, flow=client_flow)
                                if expiry_response and expiry_response.status_code == 200:
                                    try:
                                        expiry_json = expiry_response.json()
                                        if expiry_json.get('success', False):
                                            logger.info(f"Точное время истечения установлено для клиента {client_email} на сервере {server_name}")
                                        else:
                                            logger.warning(f"Не удалось установить точное время истечения для клиента {client_email} на сервере {server_name}")
                                    except (json.JSONDecodeError, ValueError):
                                        logger.warning(f"Ответ при установке времени истечения не является валидным JSON для клиента {client_email} на сервере {server_name}")
                                else:
                                    logger.warning(f"Ошибка установки точного времени истечения для клиента {client_email} на сервере {server_name}: HTTP {expiry_response.status_code if expiry_response else 'None'}")
                            except Exception as set_expiry_e:
                                logger.warning(f"Ошибка установки точного времени истечения для клиента {client_email} на сервере {server_name}: {set_expiry_e}")
                                # Не критично - клиент создан, время будет синхронизировано при следующей синхронизации
                            
                            return True, True  # Клиент создан
                        else:
                            error_msg = response_json.get('msg', 'Unknown error')
                            if 'duplicate email' in error_msg.lower() or 'duplicate' in error_msg.lower():
                                logger.info(f"Клиент {client_email} уже существует на сервере {server_name} (создан между проверкой и созданием)")
                                return True, False  # Клиент существует, не создавали
                            else:
                                logger.error(f"Ошибка создания клиента на сервере {server_name}: {error_msg}")
                                return False, False
                    except (json.JSONDecodeError, ValueError):
                        # Если ответ не JSON, но статус 200, считаем успехом
                        logger.info(f"Клиент {client_email} создан на сервере {server_name} (статус 200, не JSON)")
                        
                        # Все равно пытаемся установить точное время истечения
                        try:
                            logger.info(f"Установка точного времени истечения для клиента {client_email} на сервере {server_name}: {expires_at}")
                            expiry_response = xui.setClientExpiry(client_email, expires_at, flow=client_flow)
                            if expiry_response and expiry_response.status_code == 200:
                                logger.info(f"Точное время истечения установлено для клиента {client_email} на сервере {server_name}")
                        except Exception as set_expiry_e:
                            logger.warning(f"Ошибка установки точного времени истечения для клиента {client_email} на сервере {server_name}: {set_expiry_e}")
                        
                        return True, True
                else:
                    logger.error(f"Ошибка создания клиента на сервере {server_name}: HTTP {response.status_code if response else 'None'}")
                    return False, False
                    
        except Exception as e:
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
        links: List[str] = []
        seen_links = set()  # Для дедупликации ссылок (без tag)

        for s in servers:
            server_name = s["server_name"]
            client_email = s["client_email"]

            try:
                xui, resolved_name = self.server_manager.get_server_by_name(server_name)
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
                    xui_links = xui.get_subscription_links(client_email, server_name=display_name, flow_override=client_flow)
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
                        vless_link = xui.link(client_email, server_name=display_name)
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
                except Exception as link_e:
                    logger.error(
                        "Ошибка получения ссылок для server=%s, email=%s: %s",
                        resolved_name,
                        client_email,
                        link_e,
                    )
            except Exception as e:
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
        
        Принцип: БД - источник истины. Гарантирует, что все подписки имеют клиентов
        на серверах ИХ ГРУППЫ из конфигурации.
        """
        logger.info("Начало синхронизации подписок с серверами (БД → Серверы)")
        
        # Получаем все подписки, которые нужно синхронизировать
        all_subscriptions = await get_subscriptions_to_sync()
        
        # Получаем все серверы из конфигурации (БД)
        from ..db.subscribers_db import get_servers_config
        all_configured_servers = await get_servers_config(only_active=True)
        
        # Группируем серверы по group_id для быстрого поиска
        servers_by_group = {}
        for s in all_configured_servers:
            g_id = s["group_id"]
            if g_id not in servers_by_group:
                servers_by_group[g_id] = []
            servers_by_group[g_id].append(s["name"])
        
        stats = {
            "subscriptions_checked": len(all_subscriptions),
            "servers_added": 0,
            "servers_removed": 0,
            "clients_created": 0,
            "clients_restored": 0,
            "errors": [],
        }
        
        for sub in all_subscriptions:
            subscription_id = sub["id"]
            user_id = sub["user_id"]
            token = sub["subscription_token"]
            expires_at = sub["expires_at"]
            device_limit = sub.get("device_limit", 1)
            group_id = sub.get("group_id")
            
            # Если у подписки нет group_id, пропускаем
            if group_id is None:
                logger.warning(f"Подписка {subscription_id} не имеет group_id, пропускаем")
                continue
                
            # Получаем список серверов для группы этой подписки
            group_servers = set(servers_by_group.get(group_id, []))
            
            try:
                # Получаем список серверов, привязанных к этой подписке в БД
                current_servers = await get_subscription_servers(subscription_id)
                current_server_names = {s["server_name"] for s in current_servers}
                
                # Определяем email клиента
                client_email = None
                if current_servers:
                    client_email = current_servers[0]["client_email"]
                else:
                    client_email = f"{user_id}_{subscription_id}"
                
                # Шаг 1: Последовательно добавляем связи в БД (без гонок)
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
                            logger.info(f"Добавлена связь подписки {subscription_id} с сервером {server_name} в БД")
                        except Exception as e:
                            stats["errors"].append(f"Подписка {subscription_id}, server {server_name}: {e}")

                # Шаг 2: Параллельно гарантируем наличие клиента на сервере (Semaphore + gather)
                if auto_create_clients and group_servers:
                    sem = asyncio.Semaphore(15)

                    async def do_ensure(server_name):
                        async with sem:
                            return server_name, await self.ensure_client_on_server(
                                subscription_id=subscription_id,
                                server_name=server_name,
                                client_email=client_email,
                                user_id=user_id,
                                expires_at=expires_at,
                                token=token,
                                device_limit=device_limit,
                            )

                    ensure_results = await asyncio.gather(
                        *[do_ensure(server_name) for server_name in group_servers],
                        return_exceptions=True,
                    )
                    for res in ensure_results:
                        if isinstance(res, Exception):
                            stats["errors"].append(f"Подписка {subscription_id}: {res}")
                        else:
                            server_name, (client_exists, client_created) = res
                            if client_created:
                                stats["clients_created"] += 1
                            elif client_exists:
                                stats["clients_restored"] += 1
                
                # Удаляем связи с серверами, которых нет в ГРУППЕ или в конфиге
                servers_to_remove = current_server_names - group_servers
                for server_name in servers_to_remove:
                    try:
                        await remove_subscription_server(subscription_id, server_name)
                        stats["servers_removed"] += 1
                        logger.info(f"Удалена связь подписки {subscription_id} с сервером {server_name} (не в группе или удален)")
                        
                        # Также удаляем клиента с сервера, если он там есть
                        xui, _ = self.server_manager.get_server_by_name(server_name)
                        if xui:
                            xui.deleteClient(client_email)
                    except Exception as e:
                        logger.error(f"Ошибка удаления сервера {server_name} для подписки {subscription_id}: {e}")
            except Exception as e:
                stats["errors"].append(f"Подписка {subscription_id}: {e}")
        
        logger.info(
            f"Синхронизация завершена: "
            f"проверено {stats['subscriptions_checked']} подписок, "
            f"добавлено {stats['servers_added']} серверов, "
            f"удалено {stats['servers_removed']} серверов, "
            f"создано {stats['clients_created']} клиентов, "
            f"восстановлено {stats['clients_restored']} клиентов, "
            f"ошибок {len(stats['errors'])}"
        )
        
        return stats

