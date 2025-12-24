"""
Менеджер синхронизации данных между БД и серверами X-UI
"""
import asyncio
import json
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

    async def sync_all_subscriptions(self, auto_fix: bool = False):
        """
        Полная синхронизация подписок и клиентов.

        Используется /admin_sync. Возвращает статистику для вывода админу.

        auto_fix=True включает автоматическое создание клиентов на новых серверах
        (используется как флаг --fix).
        """
        logger.info("🌀 Запуск sync_all_subscriptions (auto_fix=%s)", auto_fix)

        stats = {
            "subscriptions_checked": 0,
            "subscriptions_synced": 0,
            "total_servers_checked": 0,
            "total_servers_synced": 0,
            "total_clients_created": 0,
            "total_errors": 0,
            "errors": [],
        }

        # Шаг 1. Синхронизируем список серверов в подписках с конфигом
        try:
            cfg_stats = await self.subscription_manager.sync_servers_with_config(
                auto_create_clients=auto_fix
            )
            if cfg_stats:
                stats["total_clients_created"] += cfg_stats.get("clients_created", 0)
                stats["errors"].extend(cfg_stats.get("errors", []))
        except Exception as e:
            logger.error("Ошибка sync_servers_with_config: %s", e)
            stats["errors"].append(f"sync_servers_with_config: {e}")

        # Шаг 2. Синхронизируем expiry и limitIp для каждого клиента
        active_subs = await get_all_active_subscriptions()
        stats["subscriptions_checked"] = len(active_subs)

        now = int(time.time())
        for sub in active_subs:
            sub_id = sub["id"]
            expires_at = sub["expires_at"]
            user_id = sub["user_id"]
            token = sub["subscription_token"]
            device_limit = sub.get("device_limit", 1)

            # Пропускаем истекшие (их почистит cleanup)
            if expires_at < now:
                continue

            servers = await get_subscription_servers(sub_id)
            stats["total_servers_checked"] += len(servers)

            synced_for_sub = 0
            for s_info in servers:
                server_name = s_info["server_name"]
                client_email = s_info["client_email"]
                try:
                    exists, created = await self.subscription_manager.ensure_client_on_server(
                        subscription_id=sub_id,
                        server_name=server_name,
                        client_email=client_email,
                        user_id=user_id,
                        expires_at=expires_at,
                        token=token,
                        device_limit=device_limit,
                    )

                    if exists:
                        synced_for_sub += 1
                        stats["total_servers_synced"] += 1
                    if created:
                        stats["total_clients_created"] += 1
                except Exception as e:
                    err_msg = f"sub {sub_id}, server {server_name}: {e}"
                    logger.error("Ошибка sync_all_subscriptions: %s", err_msg)
                    stats["errors"].append(err_msg)

            if servers and synced_for_sub == len(servers):
                stats["subscriptions_synced"] += 1

        # Шаг 3. Очистка сиротских клиентов (не связанных с активными подписками)
        try:
            orphaned_stats = await self.cleanup_orphaned_clients()
            stats["orphaned_clients_deleted"] = orphaned_stats.get("deleted_count", 0)
            if orphaned_stats.get("errors"):
                stats["errors"].extend(orphaned_stats["errors"])
        except Exception as e:
            logger.error("Ошибка cleanup_orphaned_clients: %s", e)
            stats["errors"].append(f"cleanup_orphaned_clients: {e}")

        stats["total_errors"] = len(stats["errors"])
        logger.info(
            "✅ sync_all_subscriptions завершена: subs=%s, synced=%s, servers=%s, orphaned=%s, errors=%s",
            stats["subscriptions_checked"],
            stats["subscriptions_synced"],
            stats["total_servers_synced"],
            stats.get("orphaned_clients_deleted", 0),
            stats["total_errors"],
        )
        return stats

    async def run_sync(self):
        """Запуск полной синхронизации"""
        logger.info("🌀 Запуск полной синхронизации серверов...")
        
        # 1. Очистка старых подписок (истекли более 3 дней назад)
        await self.cleanup_expired_subscriptions(days_limit=3)
        
        # 2. Синхронизация активных подписок с конфигурацией серверов
        await self.subscription_manager.sync_servers_with_config(auto_create_clients=True)
        
        # 3. Проверка консистентности времени и наличия клиентов
        await self.sync_all_clients_states()
        
        # 4. Очистка сиротских клиентов (не связанных с активными подписками)
        orphaned_stats = await self.cleanup_orphaned_clients()
        if orphaned_stats['deleted_count'] > 0:
            logger.info(f"🧹 Удалено {orphaned_stats['deleted_count']} сиротских клиентов")
        
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
    
    async def cleanup_orphaned_clients(self):
        """
        Удаляет клиентов на серверах, которые не связаны ни с одной активной подпиской.
        
        Логика:
        1. Получаем все активные подписки
        2. Собираем все client_email из subscription_servers
        3. Для каждого сервера:
           - Получаем список всех клиентов через X-UI API
           - Для каждого клиента проверяем, есть ли он в списке активных подписок
           - Если клиента нет в списке - удаляем его
        
        Returns:
            dict со статистикой: {'deleted_count': int, 'servers_checked': int, 'errors': list}
        """
        logger.info("🧹 Начало очистки сиротских клиентов")
        
        stats = {
            'deleted_count': 0,
            'servers_checked': 0,
            'errors': []
        }
        
        # Получаем все активные подписки и их клиентов
        active_subs = await get_all_active_subscriptions()
        active_client_emails = set()
        
        for sub in active_subs:
            servers = await get_subscription_servers(sub['id'])
            for s_info in servers:
                active_client_emails.add(s_info['client_email'])
        
        logger.info(f"Найдено {len(active_client_emails)} активных клиентов в БД")
        
        # Проверяем каждый сервер
        for server in self.server_manager.servers:
            server_name = server["name"]
            xui = server.get("x3")
            
            if not xui:
                logger.warning(f"Сервер {server_name} недоступен, пропускаем")
                continue
            
            stats['servers_checked'] += 1
            
            try:
                # Получаем всех клиентов на сервере
                response = xui.list()
                if 'obj' not in response:
                    logger.warning(f"Неожиданный формат ответа XUI для сервера {server_name}")
                    continue
                
                for inbound in response['obj']:
                    try:
                        settings = json.loads(inbound['settings'])
                        clients = settings.get("clients", [])
                        
                        for client in clients:
                            client_email = client.get('email')
                            if not client_email:
                                continue
                            
                            # Если клиент не в списке активных - удаляем
                            if client_email not in active_client_emails:
                                try:
                                    xui.deleteClient(client_email)
                                    stats['deleted_count'] += 1
                                    logger.info(f"Удален сиротский клиент {client_email} с сервера {server_name}")
                                except Exception as e:
                                    error_msg = f"Ошибка удаления клиента {client_email} с {server_name}: {e}"
                                    logger.error(error_msg)
                                    stats['errors'].append(error_msg)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга settings для inbound {inbound.get('id', 'unknown')} на сервере {server_name}: {e}")
                        continue
                    except Exception as e:
                        error_msg = f"Ошибка обработки inbound на сервере {server_name}: {e}"
                        logger.error(error_msg)
                        stats['errors'].append(error_msg)
            
            except Exception as e:
                error_msg = f"Ошибка проверки сервера {server_name}: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)
        
        logger.info(f"✅ Очистка завершена: удалено {stats['deleted_count']} сиротских клиентов с {stats['servers_checked']} серверов")
        return stats
