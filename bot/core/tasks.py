"""
Фоновые задачи бота (Remnawave-only: синхронизация X-UI и снимки нагрузки отключены).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def start_background_tasks(sync_manager, subscription_manager, notification_manager, server_manager=None):
    """Запускает фоновые задачи. sync_manager/subscription_manager не используются (Remnawave)."""
    logger.info("🚀 Запуск цикла фоновых задач...")

    # 1. Задача проверки истекающих подписок для уведомлений (каждые 30 минут)
    asyncio.create_task(notifications_task_loop(notification_manager))

    # 2. Задача очистки старых платежей (каждый час)
    asyncio.create_task(payments_cleanup_loop())


async def notifications_task_loop(notification_manager):
    """Цикл уведомлений об истекающих подписках."""
    while True:
        try:
            await notification_manager._check_expiring_subscriptions()
        except Exception as e:
            logger.error("Ошибка в цикле уведомлений: %s", e)
        await asyncio.sleep(1800)


async def payments_cleanup_loop():
    """Очистка просроченных платежей."""
    from ..db import cleanup_expired_pending_payments
    while True:
        try:
            count = await cleanup_expired_pending_payments(minutes_old=60)
            if count > 0:
                logger.info("Очищено %s просроченных платежей", count)
        except Exception as e:
            logger.error("Ошибка в очистке платежей: %s", e)
        await asyncio.sleep(3600)
