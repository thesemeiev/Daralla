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
    remove_subscription_server,
    sync_subscription_statuses
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
        
        Улучшенная логика:
        1. Получаем ВСЕ подписки (не только активные) для полной картины
        2. Разделяем клиентов по статусам подписок:
           - active: должны остаться на сервере
           - expired/canceled/deleted: могут быть удалены (если связь еще есть в БД)
        3. Для каждого сервера:
           - Получаем список всех клиентов через X-UI API
           - Для каждого клиента проверяем:
             * Если клиент в active - оставляем
             * Если клиент в expired/canceled/deleted - проверяем дату истечения
             * Если клиента нет в БД вообще - удаляем (сиротский)
        
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
        
        # Получаем все подписки (не только активные) для полной картины
        from ..db.subscribers_db import get_all_active_subscriptions, get_subscription_servers, DB_PATH
        import aiosqlite
        import time
        
        # Получаем активные подписки
        active_subs = await get_all_active_subscriptions()
        active_client_emails = set()
        active_client_details = {}  # email -> {subscription_id, server_name, expires_at}
        
        for sub in active_subs:
            servers = await get_subscription_servers(sub['id'])
            for s_info in servers:
                client_email = s_info['client_email']
                active_client_emails.add(client_email)
                active_client_details[client_email] = {
                    'subscription_id': sub['id'],
                    'server_name': s_info['server_name'],
                    'expires_at': sub.get('expires_at', 0),
                    'status': sub.get('status', 'active')
                }
        
        # Получаем неактивные подписки (expired, canceled, deleted) для контекста
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.*, ss.server_name, ss.client_email 
                FROM subscriptions s
                JOIN subscription_servers ss ON s.id = ss.subscription_id
                WHERE s.status IN ('expired', 'canceled', 'deleted')
            """) as cur:
                inactive_subs = await cur.fetchall()
        
        inactive_client_emails = set()
        inactive_client_details = {}  # email -> list of details (может быть несколько подписок с одним email)
        for row in inactive_subs:
            client_email = row['client_email']
            server_name_row = row['server_name']
            inactive_client_emails.add(client_email)
            
            # Если email уже есть, добавляем в список (может быть несколько подписок)
            if client_email not in inactive_client_details:
                inactive_client_details[client_email] = []
            
            inactive_client_details[client_email].append({
                'subscription_id': row['id'],
                'server_name': server_name_row,
                'expires_at': row['expires_at'],
                'status': row['status']
            })
        
        logger.info(f"Найдено {len(active_client_emails)} активных клиентов и {len(inactive_client_emails)} неактивных клиентов в БД")
        
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
                            
                            # Проверяем статус клиента
                            current_time = int(time.time())
                            
                            # Если клиент в активных подписках - оставляем
                            if client_email in active_client_emails:
                                detail = active_client_details.get(client_email, {})
                                logger.debug(f"Клиент {client_email} активен (подписка {detail.get('subscription_id', '?')}), пропускаем")
                                continue
                            
                            # Если клиент в неактивных подписках - проверяем детали
                            if client_email in inactive_client_emails:
                                # Получаем все подписки для этого email (может быть несколько)
                                details_list = inactive_client_details.get(client_email, [])
                                
                                # Ищем подписку, связанную с этим сервером
                                matching_detail = None
                                for detail in details_list:
                                    if detail.get('server_name') == server_name:
                                        matching_detail = detail
                                        break
                                
                                # Если не нашли связь с этим сервером, но email есть в неактивных - 
                                # это может быть другая подписка на другом сервере, пропускаем
                                if not matching_detail:
                                    logger.debug(f"Клиент {client_email} есть в неактивных подписках, но не связан с сервером {server_name}, пропускаем")
                                    continue
                                
                                subscription_id = matching_detail.get('subscription_id', '?')
                                status = matching_detail.get('status', 'unknown')
                                expires_at = matching_detail.get('expires_at', 0)
                                
                                # Если подписка canceled или deleted - удаляем клиента
                                if status in ['canceled', 'deleted']:
                                    reason = f"Подписка {subscription_id} имеет статус {status}"
                                    try:
                                        xui.deleteClient(client_email)
                                        stats['deleted_count'] += 1
                                        stats['details'].append({
                                            'server': server_name,
                                            'email': client_email,
                                            'subscription_id': subscription_id,
                                            'reason': reason,
                                            'status': status
                                        })
                                        logger.info(f"Удален клиент {client_email} с сервера {server_name}: {reason}")
                                    except Exception as e:
                                        error_msg = f"Ошибка удаления клиента {client_email} с {server_name}: {e}"
                                        logger.error(error_msg)
                                        stats['errors'].append(error_msg)
                                # Если подписка expired - проверяем дату (удаляем если истекла более 3 дней назад)
                                elif status == 'expired':
                                    days_since_expiry = (current_time - expires_at) // (24 * 60 * 60) if expires_at > 0 else 999
                                    if days_since_expiry >= 3:
                                        reason = f"Подписка {subscription_id} истекла {days_since_expiry} дней назад"
                                        try:
                                            xui.deleteClient(client_email)
                                            stats['deleted_count'] += 1
                                            stats['details'].append({
                                                'server': server_name,
                                                'email': client_email,
                                                'subscription_id': subscription_id,
                                                'reason': reason,
                                                'status': status,
                                                'days_since_expiry': days_since_expiry
                                            })
                                            logger.info(f"Удален клиент {client_email} с сервера {server_name}: {reason}")
                                        except Exception as e:
                                            error_msg = f"Ошибка удаления клиента {client_email} с {server_name}: {e}"
                                            logger.error(error_msg)
                                            stats['errors'].append(error_msg)
                                    else:
                                        logger.debug(f"Клиент {client_email} истек недавно ({days_since_expiry} дней), оставляем")
                                continue
                            
                            # Если клиента нет ни в активных, ни в неактивных - это сиротский клиент
                            # (связь в subscription_servers была удалена, но клиент остался на сервере)
                            reason = "Клиент не найден в БД (сиротский клиент)"
                            try:
                                xui.deleteClient(client_email)
                                stats['deleted_count'] += 1
                                stats['details'].append({
                                    'server': server_name,
                                    'email': client_email,
                                    'subscription_id': None,
                                    'reason': reason,
                                    'status': 'orphaned'
                                })
                                logger.info(f"Удален сиротский клиент {client_email} с сервера {server_name} (не найден в БД)")
                            except Exception as e:
                                error_msg = f"Ошибка удаления сиротского клиента {client_email} с {server_name}: {e}"
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
        if stats['details']:
            logger.debug(f"Детали удаления: {len(stats['details'])} записей")
        return stats
    
    async def diagnose_server_client_mismatch(self, server_name: str = None):
        """
        Диагностирует расхождения между БД и серверами X-UI.
        
        Проверяет:
        1. Клиенты на сервере, которых нет в БД (сиротские)
        2. Клиенты в БД, которых нет на сервере (потерянные)
        3. Клиенты с несоответствием статуса (активны в БД, но истекли на сервере)
        4. Клиенты с несоответствием времени истечения
        
        Args:
            server_name: Имя сервера для проверки (если None - проверяет все серверы)
        
        Returns:
            dict с результатами диагностики для каждого сервера
        """
        logger.info(f"🔍 Начало диагностики расхождений между БД и серверами" + (f" (сервер: {server_name})" if server_name else ""))
        
        import aiosqlite
        from ..db.subscribers_db import get_subscription_servers, DB_PATH
        
        results = {}
        servers_to_check = []
        
        if server_name:
            # Проверяем только указанный сервер
            for server in self.server_manager.servers:
                if server["name"] == server_name:
                    servers_to_check.append(server)
                    break
        else:
            # Проверяем все серверы
            servers_to_check = self.server_manager.servers
        
        # Получаем все связи из БД
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT ss.*, s.status, s.expires_at, u.user_id
                FROM subscription_servers ss
                JOIN subscriptions s ON ss.subscription_id = s.id
                JOIN users u ON s.subscriber_id = u.id
            """) as cur:
                db_connections = await cur.fetchall()
        
        # Группируем по серверам
        db_clients_by_server = {}
        for conn in db_connections:
            server = conn['server_name']
            if server not in db_clients_by_server:
                db_clients_by_server[server] = []
            db_clients_by_server[server].append({
                'email': conn['client_email'],
                'subscription_id': conn['subscription_id'],
                'status': conn['status'],
                'expires_at': conn['expires_at'],
                'user_id': conn['user_id']
            })
        
        # Проверяем каждый сервер
        for server in servers_to_check:
            server_name_check = server["name"]
            xui = server.get("x3")
            
            if not xui:
                results[server_name_check] = {
                    'status': 'unavailable',
                    'error': 'Сервер недоступен'
                }
                continue
            
            result = {
                'status': 'ok',
                'orphaned_clients': [],  # На сервере, но нет в БД
                'missing_clients': [],   # В БД, но нет на сервере
                'status_mismatches': [], # Несоответствие статуса
                'expiry_mismatches': []  # Несоответствие времени истечения
            }
            
            try:
                # Получаем клиентов с сервера
                response = xui.list()
                if 'obj' not in response:
                    result['status'] = 'error'
                    result['error'] = 'Неожиданный формат ответа XUI'
                    results[server_name_check] = result
                    continue
                
                server_clients = {}
                for inbound in response['obj']:
                    try:
                        settings = json.loads(inbound['settings'])
                        clients = settings.get("clients", [])
                        for client in clients:
                            client_email = client.get('email')
                            if not client_email:
                                continue
                            
                            # Получаем время истечения клиента
                            expiry_time = client.get('expiryTime', 0)
                            if expiry_time:
                                # X-UI возвращает время в миллисекундах
                                if expiry_time > 1000000000000:  # Это миллисекунды
                                    expiry_time = expiry_time // 1000
                            
                            server_clients[client_email] = {
                                'expiry_time': expiry_time,
                                'expired': expiry_time > 0 and expiry_time < int(time.time())
                            }
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Ошибка обработки inbound на сервере {server_name_check}: {e}")
                        continue
                
                # Получаем клиентов из БД для этого сервера
                db_clients = db_clients_by_server.get(server_name_check, [])
                db_client_emails = {c['email'] for c in db_clients}
                
                # 1. Сиротские клиенты (на сервере, но нет в БД)
                for email, info in server_clients.items():
                    if email not in db_client_emails:
                        result['orphaned_clients'].append({
                            'email': email,
                            'expiry_time': info['expiry_time'],
                            'expired': info['expired']
                        })
                
                # 2. Потерянные клиенты (в БД, но нет на сервере)
                for db_info in db_clients:
                    client_email = db_info['email']
                    if client_email not in server_clients:
                        result['missing_clients'].append({
                            'email': client_email,
                            'subscription_id': db_info['subscription_id'],
                            'status': db_info['status'],
                            'user_id': db_info['user_id']
                        })
                
                # 3. Проверяем несоответствия статуса и времени
                for db_info in db_clients:
                    client_email = db_info['email']
                    if client_email not in server_clients:
                        continue  # Уже обработано как потерянный
                    
                    server_info = server_clients[client_email]
                    server_expired = server_info['expired']
                    db_expires_at = db_info['expires_at']
                    current_time = int(time.time())
                    db_expired = db_expires_at < current_time
                    
                    # Несоответствие статуса
                    if db_info['status'] == 'active' and server_expired:
                        # Активен в БД, но истек на сервере
                        result['status_mismatches'].append({
                            'email': client_email,
                            'subscription_id': db_info['subscription_id'],
                            'db_status': db_info['status'],
                            'db_expires_at': db_expires_at,
                            'server_expiry_time': server_info['expiry_time'],
                            'user_id': db_info['user_id']
                        })
                    elif db_info['status'] in ['expired', 'canceled', 'deleted'] and not server_expired:
                        # Неактивен в БД, но еще активен на сервере
                        result['status_mismatches'].append({
                            'email': client_email,
                            'subscription_id': db_info['subscription_id'],
                            'db_status': db_info['status'],
                            'db_expires_at': db_expires_at,
                            'server_expiry_time': server_info['expiry_time'],
                            'user_id': db_info['user_id']
                        })
                    
                    # Несоответствие времени истечения (разница более 1 дня)
                    if db_expires_at > 0 and server_info['expiry_time'] > 0:
                        time_diff = abs(db_expires_at - server_info['expiry_time'])
                        if time_diff > 24 * 60 * 60:  # Более 1 дня разницы
                            result['expiry_mismatches'].append({
                                'email': client_email,
                                'subscription_id': db_info['subscription_id'],
                                'db_expires_at': db_expires_at,
                                'server_expiry_time': server_info['expiry_time'],
                                'time_diff_hours': round(time_diff / 3600, 1),
                                'user_id': db_info['user_id']
                            })
                
                # Формируем итоговый статус
                total_issues = (len(result['orphaned_clients']) + 
                              len(result['missing_clients']) + 
                              len(result['status_mismatches']) + 
                              len(result['expiry_mismatches']))
                
                if total_issues > 0:
                    result['status'] = 'issues_found'
                    result['total_issues'] = total_issues
                else:
                    result['status'] = 'ok'
                    result['message'] = 'Расхождений не обнаружено'
                
                results[server_name_check] = result
                
            except Exception as e:
                result['status'] = 'error'
                result['error'] = str(e)
                results[server_name_check] = result
                logger.error(f"Ошибка диагностики сервера {server_name_check}: {e}")
        
        logger.info(f"✅ Диагностика завершена для {len(results)} серверов")
        return results
