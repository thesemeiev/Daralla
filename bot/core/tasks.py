"""
Фоновые задачи бота
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

async def start_background_tasks(subscription_manager, notification_manager):
    """Запускает все фоновые задачи"""
    logger.info("🚀 Запуск цикла фоновых задач...")
    
    # 1. Задача проверки истекающих подписок для уведомлений (каждые 30 минут)
    asyncio.create_task(notifications_task_loop(notification_manager))
    
    # 2. Задача очистки старых платежей (каждый час)
    asyncio.create_task(payments_cleanup_loop())
    
    _ = subscription_manager

async def notifications_task_loop(notification_manager):
    """Цикл уведомлений"""
    while True:
        try:
            # Метод внутри сам проверяет, кому пора слать
            await notification_manager._check_expiring_subscriptions()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в цикле уведомлений: {e}")
            
        # Раз в 30 минут
        await asyncio.sleep(1800)

async def payments_cleanup_loop():
    """Очистка просроченных платежей (pending → expired) и старых записей (раз в сутки)"""
    from ..db import cleanup_expired_pending_payments, cleanup_old_payments
    iteration = 0
    while True:
        try:
            count = await cleanup_expired_pending_payments(minutes_old=60)
            if count > 0:
                logger.info(f"Очищено {count} просроченных платежей")
            # Раз в 24 часа удаляем старые не-pending платежи (старше 30 дней)
            iteration += 1
            if iteration >= 24:
                iteration = 0
                deleted = await cleanup_old_payments(days=30)
                if deleted > 0:
                    logger.info(f"Удалено {deleted} старых записей платежей (старше 30 дней)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в очистке платежей: {e}")
            
        # Раз в час
        await asyncio.sleep(3600)

