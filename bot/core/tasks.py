"""
Фоновые задачи бота
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

async def start_background_tasks(sync_manager, subscription_manager, notification_manager):
    """Запускает все фоновые задачи"""
    logger.info("🚀 Запуск цикла фоновых задач...")
    
    # 1. Задача синхронизации и очистки (каждые 6 часов)
    # Она удаляет подписки через 3 дня после истечения и правит время на серверах
    asyncio.create_task(sync_task_loop(sync_manager))
    
    # 2. Задача проверки истекающих подписок для уведомлений (каждые 30 минут)
    asyncio.create_task(notifications_task_loop(notification_manager))
    
    # 3. Задача очистки старых платежей (каждый час)
    asyncio.create_task(payments_cleanup_loop())

async def sync_task_loop(sync_manager):
    """Цикл синхронизации данных"""
    while True:
        try:
            await sync_manager.run_sync()
        except Exception as e:
            logger.error(f"Ошибка в цикле синхронизации: {e}")
        
        # Раз в 6 часов
        await asyncio.sleep(6 * 3600)

async def notifications_task_loop(notification_manager):
    """Цикл уведомлений"""
    while True:
        try:
            # Метод внутри сам проверяет, кому пора слать
            await notification_manager._check_expiring_subscriptions()
        except Exception as e:
            logger.error(f"Ошибка в цикле уведомлений: {e}")
            
        # Раз в 30 минут
        await asyncio.sleep(1800)

async def payments_cleanup_loop():
    """Очистка просроченных платежей"""
    from ..db import cleanup_expired_pending_payments
    while True:
        try:
            count = await cleanup_expired_pending_payments(minutes_old=60)
            if count > 0:
                logger.info(f"Очищено {count} просроченных платежей")
        except Exception as e:
            logger.error(f"Ошибка в очистке платежей: {e}")
            
        # Раз в час
        await asyncio.sleep(3600)
