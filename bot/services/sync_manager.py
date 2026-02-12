"""
Менеджер синхронизации данных между БД и серверами X-UI
"""
import asyncio
import json
import logging
import time
from typing import List, Dict, Any

from ..db.subscriptions_db import (
    get_all_active_subscriptions,
    get_subscriptions_to_sync,
    get_subscription_servers,
    update_subscription_status,
    remove_subscription_server,
    sync_subscription_statuses
)
from ..db.notifications_db import clear_subscription_notifications
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

        # Шаг 2. Синхронизируем expiry и limitIp для каждого клиента (параллельно с лимитом)
        active_subs = await get_all_active_subscriptions()
        stats["subscriptions_checked"] = len(active_subs)

        now = int(time.time())
        # Собираем все пары (подписка, сервер) для параллельной обработки
        items = []
        sub_server_count = {}
        for sub in active_subs:
            sub_id = sub["id"]
            expires_at = sub["expires_at"]
            user_id = sub["user_id"]
            token = sub["subscription_token"]
            device_limit = sub.get("device_limit", 1)

            if expires_at < now:
                continue

            servers = await get_subscription_servers(sub_id)
            stats["total_servers_checked"] += len(servers)
            sub_server_count[sub_id] = len(servers)

            for s_info in servers:
                items.append((
                    sub_id,
                    expires_at,
                    user_id,
                    token,
                    device_limit,
                    s_info["server_name"],
                    s_info["client_email"],
                ))

        sem = asyncio.Semaphore(15)

        async def do_one(sub_id, expires_at, user_id, token, device_limit, server_name, client_email):
            async with sem:
                return await self.subscription_manager.ensure_client_on_server(
                    subscription_id=sub_id,
                    server_name=server_name,
                    client_email=client_email,
                    user_id=user_id,
                    expires_at=expires_at,
                    token=token,
                    device_limit=device_limit,
                )

        if items:
            results = await asyncio.gather(
                *[do_one(*item) for item in items],
                return_exceptions=True,
            )
            sub_synced_count = {sid: 0 for sid in sub_server_count}
            for item, result in zip(items, results):
                sub_id, _, _, _, _, server_name, _ = item
                if isinstance(result, Exception):
                    err_msg = f"sub {sub_id}, server {server_name}: {result}"
                    logger.error("Ошибка sync_all_subscriptions: %s", err_msg)
                    stats["errors"].append(err_msg)
                else:
                    exists, created = result
                    if exists:
                        sub_synced_count[sub_id] = sub_synced_count.get(sub_id, 0) + 1
                        stats["total_servers_synced"] += 1
                    if created:
                        stats["total_clients_created"] += 1
            for sub_id, total in sub_server_count.items():
                if total > 0 and sub_synced_count.get(sub_id, 0) == total:
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
        """
        Запуск полной синхронизации БД с серверами X-UI.
        
        Принцип: БД - источник истины. Серверы синхронизируются с БД.
        
        Шаги синхронизации:
        1. Синхронизация статусов в БД (active ↔ expired на основе expires_at)
        2. Удаление старых подписок (истекли > 3 дней) и их клиентов с серверов
        3. Синхронизация БД → Серверы (гарантирует наличие клиентов для всех подписок)
        4. Очистка сиротских клиентов (удаляет клиентов на серверах, которых нет в БД)
        """
        logger.info("🌀 Запуск полной синхронизации БД с серверами X-UI...")
        logger.info("📋 Принцип: БД - источник истины, серверы синхронизируются с БД")
        
        # Шаг 1: Синхронизация статусов подписок в БД
        # Обновляет статусы active ↔ expired на основе expires_at
        logger.info("📊 Шаг 1: Синхронизация статусов подписок в БД...")
        await sync_subscription_statuses()
        logger.info("✅ Шаг 1 завершен: статусы подписок синхронизированы")
        
        # Шаг 2: Удаление старых подписок (истекли более 3 дней назад)
        # Удаляет подписки со статусом deleted и их клиентов с серверов
        logger.info("🗑️ Шаг 2: Удаление старых подписок (истекли > 3 дней)...")
        await self.cleanup_expired_subscriptions(days_limit=3)
        logger.info("✅ Шаг 2 завершен: старые подписки удалены")
        
        # Шаг 3: Синхронизация БД → Серверы
        # Для каждой подписки (active или expired, но не deleted):
        # - Гарантирует наличие клиентов на всех серверах из конфигурации
        # - Синхронизирует параметры (expires_at, device_limit)
        logger.info("🔄 Шаг 3: Синхронизация подписок с серверами (БД → Серверы)...")
        await self.subscription_manager.sync_servers_with_config(auto_create_clients=True)
        logger.info("✅ Шаг 3 завершен: подписки синхронизированы с серверами")
        
        # Шаг 4: Очистка сиротских клиентов (Серверы → БД)
        # Удаляет клиентов на серверах, которых нет в БД (в active или expired подписках)
        logger.info("🧹 Шаг 4: Очистка сиротских клиентов (Серверы → БД)...")
        orphaned_stats = await self.cleanup_orphaned_clients()
        if orphaned_stats['deleted_count'] > 0:
            logger.info(f"✅ Шаг 4 завершен: удалено {orphaned_stats['deleted_count']} сиротских клиентов")
        else:
            logger.info("✅ Шаг 4 завершен: сиротских клиентов не найдено")
        
        logger.info("✅ Полная синхронизация завершена успешно")

    async def cleanup_expired_subscriptions(self, days_limit: int = 3):
        """Удаляет подписки, которые истекли более N дней назад"""
        now = int(time.time())
        cutoff = now - (days_limit * 24 * 60 * 60)
        
        # ИСПРАВЛЕНИЕ: Получаем подписки со статусом 'active' или 'expired',
        # которые истекли более N дней назад (не только 'active')
        # Это важно, так как sync_subscription_statuses() на шаге 1 может уже изменить статус на 'expired'
        from ..db import DB_PATH
        import aiosqlite
        
        expired_subs = []
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.*, u.user_id 
                FROM subscriptions s 
                JOIN users u ON s.subscriber_id = u.id 
                WHERE s.status IN ('active', 'expired')
                AND s.expires_at < ?
                AND s.status != 'deleted'
            """, (cutoff,)) as cur:
                rows = await cur.fetchall()
                expired_subs = [dict(row) for row in rows]
        
        logger.info(f"Найдено {len(expired_subs)} просроченных подписок для удаления (истекли {days_limit}+ дня назад)")
        
        for sub in expired_subs:
            sub_id = sub['id']
            
            # ВАЖНО: Проверяем актуальные данные из БД перед удалением
            # Это защищает от race condition, если подписка была продлена между получением списка и удалением
            # Получаем актуальные данные подписки (без проверки user_id, так как это cleanup)
            actual_sub = await self._get_subscription_by_id(sub_id)
            
            if not actual_sub:
                # Подписка уже удалена, пропускаем
                continue
            
            # Проверяем актуальный статус и expires_at
            if actual_sub['status'] == 'deleted':
                # Подписка уже удалена, пропускаем
                continue
            
            if actual_sub['expires_at'] >= cutoff:
                # Подписка была продлена или еще не истекла, пропускаем
                continue
            
            # Подписка действительно истекла более N дней назад
            logger.info(f"🗑 Удаление просроченной подписки {sub_id} (истекла {days_limit}+ дня назад, статус: {actual_sub['status']})")
            
            # 1. Удаляем клиентов со всех серверов
            servers = await get_subscription_servers(sub_id)
            for s_info in servers:
                server_name = s_info['server_name']
                client_email = s_info['client_email']
                
                try:
                    xui, _ = self.server_manager.get_server_by_name(server_name)
                    if xui:
                        await xui.deleteClient(client_email)
                        logger.debug(f"Удален клиент {client_email} с сервера {server_name}")
                except Exception as e:
                    logger.error(f"Ошибка удаления клиента {client_email} с {server_name}: {e}")
            
            # 2. Удаляем из БД (полное удаление)
            # По вашей просьбе — удаляем совсем
            await update_subscription_status(sub_id, 'deleted')
            # В реальной БД лучше просто скрыть, но мы удаляем связи
            for s_info in servers:
                await remove_subscription_server(sub_id, s_info['server_name'])
            await clear_subscription_notifications(sub_id)
            
            logger.info(f"Подписка {sub_id} полностью удалена")
    
    async def _get_subscription_by_id(self, sub_id: int):
        """Вспомогательная функция для получения подписки по ID без проверки user_id"""
        from ..db import DB_PATH
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def cleanup_orphaned_clients(self):
        """
        Удаляет клиентов на серверах, которых нет в БД (сиротские клиенты).
        
        Логика (БД - источник истины):
        1. Получаем все подписки, которые должны быть синхронизированы (active и expired, но не deleted)
        2. Строим карту всех клиентов, которые ДОЛЖНЫ существовать на серверах
        3. Для каждого сервера:
           - Получаем список всех клиентов через X-UI API
           - Для каждого клиента проверяем:
             * Если клиент есть в БД (в active или expired подписке) - оставляем
             * Если клиента нет в БД - удаляем (сиротский)
        
        Returns:
            dict со статистикой: {'deleted_count': int, 'servers_checked': int, 'errors': list, 'details': list}
        """
        logger.info("🧹 Начало очистки сиротских клиентов")
        
        stats = {
            'deleted_count': 0,
            'servers_checked': 0,
            'errors': [],
            'details': []  # Детальная информация о каждом удалении
        }
        
        # Получаем все подписки, которые должны быть синхронизированы (active и expired, но не deleted)
        # Это те же подписки, что используются в sync_servers_with_config для консистентности
        subs_to_sync = await get_subscriptions_to_sync()
        
        # Строим карту всех клиентов, которые ДОЛЖНЫ существовать на серверах
        # Формат: {server_name: {client_email: subscription_id}}
        valid_clients_by_server = {}  # server_name -> set of client_emails
        
        for sub in subs_to_sync:
            servers = await get_subscription_servers(sub['id'])
            for s_info in servers:
                server_name = s_info['server_name']
                client_email = s_info['client_email']
                
                if server_name not in valid_clients_by_server:
                    valid_clients_by_server[server_name] = set()
                
                valid_clients_by_server[server_name].add(client_email)
        
        total_valid_clients = sum(len(clients) for clients in valid_clients_by_server.values())
        logger.info(f"В БД найдено {len(subs_to_sync)} подписок для синхронизации, {total_valid_clients} клиентов должны существовать на серверах")
        
        # Проверяем каждый сервер
        for server in self.server_manager.servers:
            server_name = server["name"]
            xui = server.get("x3")
            
            if not xui:
                logger.warning(f"Сервер {server_name} недоступен, пропускаем")
                continue
            
            stats['servers_checked'] += 1
            
            # Получаем список валидных клиентов для этого сервера из БД
            valid_clients_for_server = valid_clients_by_server.get(server_name, set())
            logger.debug(f"Сервер {server_name}: в БД должно быть {len(valid_clients_for_server)} клиентов")
            
            try:
                # Получаем всех клиентов на сервере
                response = await xui.list()
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
                            
                            # Проверяем, есть ли клиент в списке валидных для этого сервера
                            # Если клиент есть в БД (в active или expired подписке) - оставляем
                            if client_email in valid_clients_for_server:
                                logger.debug(f"Клиент {client_email} найден в БД для сервера {server_name}, оставляем")
                                continue
                            
                            # Клиента нет в БД - это сиротский клиент, удаляем.
                            # ВАЖНО: на панели могут быть дубликаты одного и того же email в разных inbound'ах.
                            # deleteClient(email) удаляет только ОДНОГО клиента, поэтому вызываем её несколько раз,
                            # пока она реально что-то удаляет (resp.status_code == 200), либо не вернет None.
                            reason = "Клиент не найден в БД (сиротский клиент - нет в active или expired подписках)"
                            
                            max_delete_attempts = 5
                            for attempt in range(max_delete_attempts):
                                try:
                                    resp = await xui.deleteClient(client_email)
                                except Exception as e:
                                    error_msg = (
                                        f"Ошибка удаления сиротского клиента {client_email} с {server_name} "
                                        f"(попытка {attempt + 1}/{max_delete_attempts}): {e}"
                                    )
                                    logger.error(error_msg)
                                    stats['errors'].append(error_msg)
                                    # При ошибке не продолжаем попытки, чтобы избежать бесконечных циклов
                                    break
                                
                                # deleteClient вернет None, если клиент (по этому email) больше не найден на панели
                                if resp is None:
                                    if attempt == 0:
                                        # Нечего удалять — клиент уже исчез или не найден
                                        logger.debug(
                                            f"Сиротский клиент {client_email} на сервере {server_name} "
                                            f"не найден при попытке удаления"
                                        )
                                    break
                                
                                status_code = getattr(resp, "status_code", None)
                                if status_code == 200:
                                    stats['deleted_count'] += 1
                                    stats['details'].append({
                                        'server': server_name,
                                        'email': client_email,
                                        'subscription_id': None,
                                        'reason': reason,
                                        'status': 'orphaned'
                                    })
                                    logger.info(
                                        f"Удален сиротский клиент {client_email} с сервера {server_name} "
                                        f"(попытка {attempt + 1}/{max_delete_attempts}): {reason}"
                                    )
                                    # Пытаемся удалить возможные дубликаты с тем же email на других inbound'ах
                                    continue
                                else:
                                    error_msg = (
                                        f"Неожиданный статус при удалении сиротского клиента {client_email} "
                                        f"с {server_name}: HTTP {status_code}"
                                    )
                                    logger.error(error_msg)
                                    stats['errors'].append(error_msg)
                                    # При некорректном статусе дальнейшие попытки по этому email бессмысленны
                                    break
                    
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
        
        logger.info(f" Очистка завершена: удалено {stats['deleted_count']} сиротских клиентов с {stats['servers_checked']} серверов")
        if stats['details']:
            logger.debug(f"Детали удаления: {len(stats['details'])} записей")
        return stats
