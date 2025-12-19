"""
Периодические задачи очистки данных и синхронизации
"""
import logging
import asyncio
import time
from ..db import cleanup_expired_pending_payments, cleanup_old_payments
from ..db.subscribers_db import get_all_active_subscriptions, update_subscription_status

logger = logging.getLogger(__name__)


async def cleanup_old_payments_task():
    """Периодическая очистка старых платежей и данных"""
    while True:
        try:
            logger.info("🧹 Запуск периодической очистки данных")
            
            # Очищаем просроченные pending платежи (увеличили до 60 минут для надежности)
            expired_count = await cleanup_expired_pending_payments(minutes_old=60)
            if expired_count > 0:
                logger.info(f"🧹 Очистка: Удалено {expired_count} просроченных pending платежей")
            
            # Очищаем старые записи платежей (храним 7 дней)
            old_count = await cleanup_old_payments(days_old=7)
            if old_count > 0:
                logger.info(f"🧹 Очистка: Удалено {old_count} старых записей платежей")
            
            # Очищаем истекшие подписки
            expired_subscriptions_count = await cleanup_expired_subscriptions()
            if expired_subscriptions_count > 0:
                logger.info(f"🧹 Очистка: Обновлено {expired_subscriptions_count} истекших подписок")
            
            logger.info("🧹 Периодическая очистка завершена")
            
        except Exception as e:
            logger.error(f"Ошибка в периодической очистке: {e}")
        
        # Ждем 1 час до следующей очистки
        await asyncio.sleep(3600)


async def cleanup_expired_subscriptions():
    """Автоматически обновляет статус истекших подписок"""
    try:
        current_time = int(time.time())
        subscriptions = await get_all_active_subscriptions()
        expired_count = 0
        
        for sub in subscriptions:
            if sub['expires_at'] < current_time:
                # Подписка истекла, обновляем статус
                await update_subscription_status(sub['id'], 'expired')
                expired_count += 1
                logger.info(f"Подписка {sub['id']} для пользователя {sub['user_id']} помечена как истекшая")
        
        return expired_count
        
    except Exception as e:
        logger.error(f"Ошибка в cleanup_expired_subscriptions: {e}")
        return 0


async def sync_db_with_xui_task(sync_manager):
    """
    Периодическая задача синхронизации БД подписок с X-UI серверами.
    """
    if not sync_manager:
        logger.error("sync_db_with_xui_task: sync_manager не передан!")
        return

    logger.info("Запуск периодической синхронизации БД с X-UI")
    while True:
        try:
            # Небольшая пауза при старте, чтобы дать боту прогрузиться
            await asyncio.sleep(60)
            
            # Выполняем синхронизацию всех подписок
            stats = await sync_manager.sync_all_subscriptions(auto_fix=True)
            logger.info(f"Синхронизация с X-UI завершена: {stats['subscriptions_synced']} подписок успешно")
            
            # Ищем orphaned клиентов
            orphaned = await sync_manager.find_orphaned_clients()
            if orphaned:
                logger.warning(f"Найдено {len(orphaned)} orphaned клиентов на серверах")
            
        except Exception as e:
            logger.error(f"Ошибка в задаче синхронизации БД с X-UI: {e}")
        
        # Ждем 6 часов до следующей синхронизации
        await asyncio.sleep(6 * 60 * 60)


async def sync_servers_with_config_task(subscription_manager):
    """
    Периодическая задача синхронизации серверов в подписках с конфигурацией.
    """
    if not subscription_manager:
        logger.error("sync_servers_with_config_task: subscription_manager не передан!")
        return

    logger.info("Запуск периодической синхронизации серверов с конфигурацией")
    while True:
        try:
            # Пауза при старте
            await asyncio.sleep(30)
            
            # Выполняем синхронизацию серверов с конфигурацией
            stats = await subscription_manager.sync_servers_with_config(auto_create_clients=True)
            if stats['servers_added'] > 0:
                logger.info(f"Авто-синхронизация: добавлено {stats['servers_added']} серверов в существующие подписки")
            
        except Exception as e:
            logger.error(f"Ошибка в задаче синхронизации серверов с конфигурацией: {e}")
        
        # Ждем 1 час до следующей синхронизации
        await asyncio.sleep(3600)
