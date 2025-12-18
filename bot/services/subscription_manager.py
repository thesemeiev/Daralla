"""
Сервис для управления подписками (новая модель подписок и устройств).
Пока используется только слой работы с БД и подготовка к мультисерверности.
"""

import datetime
import json
import logging
from typing import Optional, Tuple, List

from ..db.subscribers_db import (
    get_or_create_subscriber,
    create_subscription,
    add_subscription_server,
    get_active_subscription_by_user,
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
                            try:
                                xui, resolved_name = self.server_manager.get_server_by_name(server_name)
                                if xui is None:
                                    logger.warning(
                                        f"Сервер {server_name} недоступен для подписки {subscription_id}"
                                    )
                                    continue
                                
                                # Проверяем, не существует ли уже клиент
                                if xui.client_exists(client_email):
                                    logger.info(
                                        f"Клиент {client_email} уже существует на сервере {server_name}"
                                    )
                                else:
                                    # Вычисляем срок действия подписки
                                    # Используем время из БД подписки как основной источник истины
                                    expires_at_from_db = sub["expires_at"]
                                    import time
                                    current_time = int(time.time())
                                    
                                    # Проверяем время истечения существующих клиентов на других серверах
                                    # Это гарантирует синхронизацию, если время было изменено вручную на сервере
                                    max_expires_at = expires_at_from_db
                                    
                                    if current_servers:
                                        logger.debug(
                                            f"Проверка времени истечения существующих клиентов для синхронизации"
                                        )
                                        for existing_server in current_servers:
                                            existing_server_name = existing_server["server_name"]
                                            try:
                                                existing_xui, _ = self.server_manager.get_server_by_name(existing_server_name)
                                                if existing_xui:
                                                    existing_expiry = existing_xui.get_client_expiry_time(client_email)
                                                    if existing_expiry and existing_expiry > max_expires_at:
                                                        max_expires_at = existing_expiry
                                                        logger.info(
                                                            f"Найдено более позднее время истечения на сервере {existing_server_name}: "
                                                            f"{existing_expiry} (из БД: {expires_at_from_db})"
                                                        )
                                            except Exception as e:
                                                logger.debug(
                                                    f"Не удалось проверить время истечения на сервере {existing_server_name}: {e}"
                                                )
                                    
                                    # Вычисляем количество дней до истечения
                                    days_remaining = max(1, (max_expires_at - current_time) // (24 * 60 * 60))
                                    
                                    logger.info(
                                        f"Создание клиента на сервере {server_name} с временем истечения: "
                                        f"{days_remaining} дней (expires_at={max_expires_at}, "
                                        f"из БД={expires_at_from_db})"
                                    )
                                    
                                    # Создаем клиента на новом сервере
                                    response = xui.addClient(
                                        day=days_remaining,
                                        tg_id=user_id,
                                        user_email=client_email,
                                        timeout=15,
                                        key_name=token  # Используем токен подписки как subId
                                    )
                                    
                                    if response.status_code == 200:
                                        try:
                                            response_json = response.json()
                                            if response_json.get('success', False):
                                                logger.info(
                                                    f"Клиент {client_email} создан на сервере {server_name} для подписки {subscription_id}"
                                                )
                                                stats["clients_created"] += 1
                                            else:
                                                error_msg = response_json.get('msg', 'Unknown error')
                                                if 'duplicate email' in error_msg.lower():
                                                    logger.info(
                                                        f"Клиент {client_email} уже существует на сервере {server_name}"
                                                    )
                                                else:
                                                    raise Exception(f"Ошибка создания клиента: {error_msg}")
                                        except (json.JSONDecodeError, ValueError):
                                            # Если ответ не JSON, но статус 200, считаем успехом
                                            logger.info(
                                                f"Клиент {client_email} создан на сервере {server_name} (статус 200)"
                                            )
                                            stats["clients_created"] += 1
                                    else:
                                        raise Exception(f"HTTP {response.status_code}")
                                
                            except Exception as create_e:
                                logger.error(
                                    f"Ошибка создания клиента на сервере {server_name} для подписки {subscription_id}: {create_e}"
                                )
                                stats["errors"].append(
                                    f"Подписка {subscription_id}, сервер {server_name}: {str(create_e)}"
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


