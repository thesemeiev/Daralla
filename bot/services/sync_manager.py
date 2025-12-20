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
        
        # Получаем список активных подписок для проверки
        all_subs = await get_all_active_subscriptions()
        
        for sub in all_subs:
            sub_id = sub['id']
            
            # ВАЖНО: Проверяем актуальные данные из БД перед удалением
            # Это защищает от race condition, если подписка была продлена между получением списка и удалением
            # Получаем актуальные данные подписки (без проверки user_id, так как это cleanup)
            actual_sub = await self._get_subscription_by_id(sub_id)
            
            if not actual_sub:
                # Подписка уже удалена, пропускаем
                continue
            
            # Проверяем актуальный статус и expires_at
            if actual_sub['status'] != 'active':
                # Подписка уже не активна, пропускаем
                continue
            
            if actual_sub['expires_at'] >= cutoff:
                # Подписка была продлена или еще не истекла, пропускаем
                continue
            
            # Подписка действительно истекла более N дней назад и все еще активна
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
    
    async def _get_subscription_by_id(self, sub_id: int):
        """Вспомогательная функция для получения подписки по ID без проверки user_id"""
        from ..db.subscribers_db import DB_PATH
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def sync_all_clients_states(self):
        """Проверяет каждый клиент на каждом сервере и синхронизирует время и limitIp"""
        active_subs = await get_all_active_subscriptions()
        now = int(time.time())
        
        for sub in active_subs:
            sub_id = sub['id']
            expires_at = sub['expires_at']
            user_id = sub['user_id']
            token = sub['subscription_token']
            device_limit = sub.get('device_limit', 1)  # Получаем device_limit из подписки
            
            # Если подписка истекла, но еще не удалена (меньше 3 дней), 
            # мы её не трогаем, X-UI сам её заблокирует
            if expires_at < now:
                continue
                
            servers = await get_subscription_servers(sub_id)
            for s_info in servers:
                server_name = s_info['server_name']
                client_email = s_info['client_email']
                
                # Используем ensure_client_on_server, который мы уже доработали.
                # Он проверит существование И синхронизирует время (expiryTime) и limitIp.
                await self.subscription_manager.ensure_client_on_server(
                    subscription_id=sub_id,
                    server_name=server_name,
                    client_email=client_email,
                    user_id=user_id,
                    expires_at=expires_at,
                    token=token,
                    device_limit=device_limit  # Передаем device_limit напрямую
                )
