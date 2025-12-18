"""
Сервис для управления подписками (новая модель подписок и устройств).
Пока используется только слой работы с БД и подготовка к мультисерверности.
"""

import datetime
import logging
from typing import Optional, Tuple, List

from ..db.subscribers_db import (
    get_or_create_subscriber,
    create_subscription,
    add_subscription_server,
    get_active_subscription_by_user,
    get_subscription_servers,
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
    ) -> Tuple[dict, str]:
        """
        Создаёт базовую подписку для пользователя в БД (без реального создания клиентов на XUI).

        Это первый шаг: мы фиксируем в БД сам факт подписки и её параметры.
        Создание клиентов на серверах XUI будем накручивать на следующем этапе.
        """
        logger.info(
            "Создание подписки: user_id=%s, period=%s, device_limit=%s, price=%s",
            user_id,
            period,
            device_limit,
            price,
        )

        # 1. Получаем/создаём подписчика
        subscriber_id = await get_or_create_subscriber(user_id)

        # 2. Считаем срок действия
        days = 90 if period == "3month" else 30
        now = int(datetime.datetime.now().timestamp())
        expires_at = now + days * 24 * 60 * 60

        # 3. Создаём запись подписки
        subscription_id, token = await create_subscription(
            subscriber_id=subscriber_id,
            period=period,
            device_limit=device_limit,
            price=price,
            expires_at=expires_at,
        )

        sub_dict = await get_active_subscription_by_user(user_id)
        logger.info(
            "Подписка создана: subscription_id=%s, token=%s, user_id=%s",
            subscription_id,
            token,
            user_id,
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
                
                # Формируем красивое название: главное название + название сервера
                # Получаем display_name сервера из конфигурации (если есть)
                server_config = self.server_manager.get_server_config(server_name)
                server_display_name = server_config.get("display_name") or resolved_name
                
                # Получаем главное название бренда из bot.py
                try:
                    import sys
                    if 'bot.bot' in sys.modules:
                        bot_module = sys.modules['bot.bot']
                        main_name = getattr(bot_module, 'VPN_BRAND_NAME', 'Daralla')
                    else:
                        main_name = 'Daralla'
                except:
                    main_name = 'Daralla'
                
                # Формируем итоговое название: "Главное название - Название сервера"
                display_name = f"{main_name} - {server_display_name}"
                logger.info(f"Формируем название для VPN клиента: '{display_name}' (main_name='{main_name}', server='{server_display_name}')")
                
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


