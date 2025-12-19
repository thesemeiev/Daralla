"""
Менеджер синхронизации данных между БД и серверами X-UI
"""
import asyncio
import logging
import time
from typing import List, Dict, Any

from ..db.subscribers_db import (
    get_all_active_subscriptions,
    get_subscription_servers,
    update_subscription_status,
    remove_subscription_server
)
from .subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)

class SyncManager:
    """Менеджер для поддержания консистентности данных"""
    
    def __init__(self, server_manager, subscription_manager: SubscriptionManager):
        self.server_manager = server_manager
        self.subscription_manager = subscription_manager
        self.is_running = False

    async def run_sync(self):
        """Запуск полной синхронизации"""
        logger.info("🌀 Запуск полной синхронизации серверов...")
        
        # 1. Очистка старых подписок (истекли более 3 дней назад)
        await self.cleanup_expired_subscriptions(days_limit=3)
        
        # 2. Синхронизация активных подписок с конфигурацией серверов
        await self.subscription_manager.sync_servers_with_config(auto_create_clients=True)
        
        # 3. Проверка консистентности времени и наличия клиентов
        await self.sync_all_clients_states()
        
        logger.info("✅ Синхронизация завершена")

    async def cleanup_expired_subscriptions(self, days_limit: int = 3):
        """Удаляет подписки, которые истекли более N дней назад"""
        now = int(time.time())
        cutoff = now - (days_limit * 24 * 60 * 60)
        
        # Получаем все подписки
        async with self.server_manager as _: # Просто для логов, если нужно
            # Нам нужны все подписки из БД, у которых expires_at < cutoff
            from ..db.subscribers_db import get_all_active_subscriptions_by_user
            # Но проще получить вообще все и отфильтровать
            all_subs = await get_all_active_subscriptions()
            
            for sub in all_subs:
                if sub['expires_at'] < cutoff:
                    sub_id = sub['id']
                    logger.info(f"🗑 Удаление просроченной подписки {sub_id} (истекла {days_limit}+ дня назад)")
                    
                    # 1. Удаляем клиентов со всех серверов
                    servers = await get_subscription_servers(sub_id)
                    for s_info in servers:
                        server_name = s_info['server_name']
                        client_email = s_info['client_email']
                        
                        try:
                            xui, _ = self.server_manager.get_server_by_name(server_name)
                            if xui:
                                xui.deleteClient(client_email)
                                logger.debug(f"Удален клиент {client_email} с сервера {server_name}")
                        except Exception as e:
                            logger.error(f"Ошибка удаления клиента {client_email} с {server_name}: {e}")
                    
                    # 2. Удаляем из БД (статус canceled или полное удаление)
                    # По вашей просьбе — удаляем совсем
                    await update_subscription_status(sub_id, 'deleted')
                    # В реальной БД лучше просто скрыть, но мы удаляем связи
                    for s_info in servers:
                        await remove_subscription_server(sub_id, s_info['server_name'])
                    
                    logger.info(f"Подписка {sub_id} полностью удалена")

    async def sync_all_clients_states(self):
        """Проверяет каждый клиент на каждом сервере и синхронизирует время"""
        active_subs = await get_all_active_subscriptions()
        now = int(time.time())
        
        for sub in active_subs:
            sub_id = sub['id']
            expires_at = sub['expires_at']
            user_id = sub['user_id']
            token = sub['subscription_token']
            
            # Если подписка истекла, но еще не удалена (меньше 3 дней), 
            # мы её не трогаем, X-UI сам её заблокирует
            if expires_at < now:
                continue
                
            servers = await get_subscription_servers(sub_id)
            for s_info in servers:
                server_name = s_info['server_name']
                client_email = s_info['client_email']
                
                # Используем ensure_client_on_server, который мы уже доработали.
                # Он проверит существование И синхронизирует время (expiryTime).
                await self.subscription_manager.ensure_client_on_server(
                    subscription_id=sub_id,
                    server_name=server_name,
                    client_email=client_email,
                    user_id=user_id,
                    expires_at=expires_at,
                    token=token
                )
