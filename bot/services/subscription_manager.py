"""
Сервис для управления подписками (новая модель подписок и устройств).
Пока используется только слой работы с БД и подготовка к мультисерверности.
"""

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
    update_subscription_name,
)
from .server_manager import MultiServerManager

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

    async def create_subscription_for_user(
        self,
        user_id: str,
        period: str,
        device_limit: int,
        price: float,
        name: str | None = None,
    ) -> Tuple[dict, str]:
        """
        Создаёт базовую подписку для пользователя в БД (без реального создания клиентов на XUI).

        Это первый шаг: мы фиксируем в БД сам факт подписки и её параметры.
        Создание клиентов на серверах XUI будем накручивать на следующем этапе.
        
        Args:
            user_id: ID пользователя Telegram
            period: Период подписки (month, 3month)
            device_limit: Лимит устройств
            price: Цена подписки
            name: Имя подписки (опционально, если не указано - генерируется автоматически)
        """
        logger.info(
            "Создание подписки: user_id=%s, period=%s, device_limit=%s, price=%s, name=%s",
            user_id,
            period,
            device_limit,
            price,
            name,
        )

        # 1. Получаем/создаём подписчика
        subscriber_id = await get_or_create_subscriber(user_id)

        # 2. Считаем срок действия
        days = 90 if period == "3month" else 30
        now = int(datetime.datetime.now().timestamp())
        expires_at = now + days * 24 * 60 * 60

        # 3. Если имя не указано, генерируем автоматически (Подписка 1, Подписка 2 и т.д.)
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
        )

        # 5. Получаем созданную подписку
        all_subs = await get_all_active_subscriptions_by_user(user_id)
        sub_dict = next((s for s in all_subs if s['id'] == subscription_id), None)
        
        if not sub_dict:
            # Fallback: получаем по токену
            from ..db.subscribers_db import get_subscription_by_token
            sub_dict = await get_subscription_by_token(token)
        
        logger.info(
            "Подписка создана: subscription_id=%s, token=%s, user_id=%s, name=%s",
            subscription_id,
            token,
            user_id,
            name,
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
                                    response = xui.extendClient(client_email, days_to_add)
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
                                    response = xui.setClientExpiry(client_email, expires_at)
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
                                xui.updateClientLimitIp(client_email, device_limit)
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
                
                logger.info(f"Создание клиента {client_email} на сервере {server_name} с limitIp={device_limit}")
                response = xui.addClient(
                    day=days_remaining,
                    tg_id=user_id,
                    user_email=client_email,
                    timeout=15,
                    key_name=token,
                    limit_ip=device_limit
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
                                expiry_response = xui.setClientExpiry(client_email, expires_at)
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
                            expiry_response = xui.setClientExpiry(client_email, expires_at)
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
        
        Возвращает список VLESS ссылок для всех серверов, привязанных к подписке.
        """
        servers = await get_subscription_servers(subscription_id)
        links: List[str] = []

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
                
                # Используем готовый subscription endpoint X-UI вместо ручной генерации
                # Это более надежно - X-UI сам правильно генерирует ссылки
                # Передаем красивое название для tag в ссылках (заменит домен ghosttunnel.space на Daralla)
                try:
                    xui_links = xui.get_subscription_links(client_email, server_name=display_name)
                    if xui_links:
                        links.extend(xui_links)
                        logger.debug(
                            "Получено %d ссылок из X-UI subscription endpoint: server=%s, email=%s",
                            len(xui_links),
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
                            links.append(vless_link)
                            logger.debug(
                                "VLESS ссылка сгенерирована вручную: server=%s, email=%s",
                                resolved_name,
                                client_email,
                            )
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

        return links

    async def sync_servers_with_config(self, auto_create_clients: bool = True) -> dict:
        """
        Синхронизирует серверы в подписках с текущей конфигурацией серверов.
        
        Логика:
        1. Для каждой активной подписки:
           - Получаем список серверов из конфигурации (SERVERS_BY_LOCATION)
           - Получаем список серверов, привязанных к подписке
           - Добавляем новые серверы (есть в конфигурации, но нет в подписке)
           - Удаляем старые серверы (есть в подписке, но нет в конфигурации)
        
        2. При добавлении нового сервера:
           - Если auto_create_clients=True, создаем клиента на новом сервере
           - Привязываем сервер к подписке в БД
        
        3. При удалении сервера:
           - Удаляем связь из БД (клиент на сервере остается, но не используется в подписке)
        
        Args:
            auto_create_clients: Если True, автоматически создает клиентов на новых серверах
        
        Returns:
            dict со статистикой синхронизации
        """
        logger.info("Начало синхронизации серверов в подписках с конфигурацией")
        
        # Получаем все активные подписки
        all_subscriptions = await get_all_active_subscriptions()
        
        # Получаем список всех серверов из конфигурации
        configured_servers = set()
        for location, servers in self.server_manager.servers_by_location.items():
            for server_config in servers:
                configured_servers.add(server_config["name"])
        
        logger.info(f"Найдено {len(all_subscriptions)} активных подписок")
        logger.info(f"В конфигурации {len(configured_servers)} серверов: {configured_servers}")
        
        stats = {
            "subscriptions_checked": len(all_subscriptions),
            "servers_added": 0,
            "servers_removed": 0,
            "clients_created": 0,
            "errors": [],
        }
        
        for sub in all_subscriptions:
            subscription_id = sub["id"]
            user_id = sub["user_id"]
            token = sub["subscription_token"]
            expires_at = sub["expires_at"]
            
            try:
                # Получаем список серверов, привязанных к этой подписке
                current_servers = await get_subscription_servers(subscription_id)
                current_server_names = {s["server_name"] for s in current_servers}
                
                # Находим серверы, которые нужно добавить (есть в конфигурации, но нет в подписке)
                servers_to_add = configured_servers - current_server_names
                
                # Находим серверы, которые нужно удалить (есть в подписке, но нет в конфигурации)
                servers_to_remove = current_server_names - configured_servers
                
                if servers_to_add or servers_to_remove:
                    logger.info(
                        f"Подписка {subscription_id} (user={user_id}): "
                        f"добавить {len(servers_to_add)} серверов, "
                        f"удалить {len(servers_to_remove)} серверов"
                    )
                
                # Добавляем новые серверы
                for server_name in servers_to_add:
                    try:
                        # Получаем email клиента из первого существующего сервера подписки
                        # (все серверы в подписке используют один email)
                        client_email = None
                        if current_servers:
                            client_email = current_servers[0]["client_email"]
                        else:
                            # Если это первая подписка без серверов, создаем новый email
                            # Формат: {user_id}_{uuid}
                            import uuid
                            client_email = f"{user_id}_{uuid.uuid4().hex[:8]}"
                        
                        if not client_email:
                            logger.warning(
                                f"Не удалось определить email для подписки {subscription_id}, пропускаем сервер {server_name}"
                            )
                            continue
                        
                        # Если auto_create_clients=True, создаем клиента на новом сервере
                        if auto_create_clients:
                            client_exists, client_created = await self.ensure_client_on_server(
                                subscription_id=subscription_id,
                                server_name=server_name,
                                client_email=client_email,
                                user_id=user_id,
                                expires_at=expires_at,
                                token=token,
                            )
                            
                            if client_created:
                                stats["clients_created"] += 1
                            
                            if not client_exists:
                                logger.error(
                                    f"Не удалось создать клиента на сервере {server_name} для подписки {subscription_id}"
                                )
                                stats["errors"].append(
                                    f"Подписка {subscription_id}, сервер {server_name}: не удалось создать клиента"
                                )
                                # Продолжаем - привязываем сервер даже если создание не удалось
                                # (клиент может быть создан вручную позже)
                        
                        # Привязываем сервер к подписке в БД
                        await add_subscription_server(
                            subscription_id=subscription_id,
                            server_name=server_name,
                            client_email=client_email,
                            client_id=None,
                        )
                        stats["servers_added"] += 1
                        logger.info(
                            f"Сервер {server_name} добавлен в подписку {subscription_id}"
                        )
                        
                    except Exception as e:
                        logger.error(
                            f"Ошибка добавления сервера {server_name} в подписку {subscription_id}: {e}"
                        )
                        stats["errors"].append(
                            f"Подписка {subscription_id}, сервер {server_name}: {str(e)}"
                        )
                
                # Удаляем старые серверы
                for server_name in servers_to_remove:
                    try:
                        removed = await remove_subscription_server(subscription_id, server_name)
                        if removed:
                            stats["servers_removed"] += 1
                            logger.info(
                                f"Сервер {server_name} удален из подписки {subscription_id} "
                                f"(больше нет в конфигурации)"
                            )
                        else:
                            logger.warning(
                                f"Сервер {server_name} не найден в подписке {subscription_id} при попытке удаления"
                            )
                    except Exception as e:
                        logger.error(
                            f"Ошибка удаления сервера {server_name} из подписки {subscription_id}: {e}"
                        )
                        stats["errors"].append(
                            f"Подписка {subscription_id}, удаление {server_name}: {str(e)}"
                        )
                
            except Exception as e:
                logger.error(
                    f"Ошибка синхронизации подписки {subscription_id}: {e}"
                )
                stats["errors"].append(f"Подписка {subscription_id}: {str(e)}")
        
        logger.info(
            f"Синхронизация завершена: "
            f"проверено {stats['subscriptions_checked']} подписок, "
            f"добавлено {stats['servers_added']} серверов, "
            f"удалено {stats['servers_removed']} серверов, "
            f"создано {stats['clients_created']} клиентов, "
            f"ошибок {len(stats['errors'])}"
        )
        
        return stats
