"""
Периодические задачи очистки данных
"""
import logging
import datetime
import json
import asyncio
from ..db import cleanup_expired_pending_payments, cleanup_old_payments, get_payment_by_id
from ..db.subscribers_db import get_all_active_subscriptions, update_subscription_status

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        else:
            # Если модуль еще не загружен, импортируем его
            bot_module = importlib.import_module('bot.bot')
        
        return {
            'extension_messages': getattr(bot_module, 'extension_messages', {}),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'sync_manager': getattr(bot_module, 'sync_manager', None),
            'notification_manager': getattr(bot_module, 'notification_manager', None),
            'notify_admin': getattr(bot_module, 'notify_admin', None),
            'app': getattr(bot_module, 'app', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'extension_messages': {},
            'server_manager': None,
            'new_client_manager': None,
            'subscription_manager': None,
            'sync_manager': None,
            'notification_manager': None,
            'notify_admin': None,
            'app': None,
        }


async def cleanup_old_payments_task():
    """Периодическая очистка старых платежей и данных"""
    while True:
        try:
            logger.info("🧹 Запуск периодической очистки данных")
            
            # Очищаем просроченные pending платежи
            expired_count = await cleanup_expired_pending_payments(minutes_old=20)
            if expired_count > 0:
                logger.info(f"🧹 Очистка: Удалено {expired_count} просроченных pending платежей")
            
            # Очищаем старые записи платежей
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


# Старая логика очистки ключей удалена - теперь работаем только с подписками
# Очистка истекших подписок выполняется через cleanup_expired_subscriptions() в cleanup_old_payments_task()


async def cleanup_expired_subscriptions():
    """Автоматически обновляет статус истекших подписок"""
    try:
        import time
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


async def sync_db_with_xui_task():
    """
    Периодическая задача синхронизации БД подписок с X-UI серверами.
    Запускается каждые 6 часов для предотвращения рассинхронизации.
    """
    logger.info("Запуск периодической синхронизации БД с X-UI")
    while True:
        try:
            # Ждем 6 часов перед первой синхронизацией (чтобы не нагружать при старте)
            await asyncio.sleep(6 * 60 * 60)
            
            # Получаем SyncManager из глобальных переменных
            globals_dict = get_globals()
            sync_manager = globals_dict.get('sync_manager')
            
            if not sync_manager:
                logger.warning("sync_manager не доступен, пропускаем синхронизацию")
                continue
            
            # Выполняем синхронизацию всех подписок
            stats = await sync_manager.sync_all_subscriptions()
            
            # Логируем результаты
            if stats['total_errors'] > 0:
                logger.warning(
                    f"Синхронизация завершена с ошибками: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"синхронизировано {stats['subscriptions_synced']}, "
                    f"ошибок {stats['total_errors']}"
                )
            else:
                logger.info(
                    f"Синхронизация успешно завершена: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"все синхронизированы"
                )
            
            # Ищем orphaned клиентов (клиенты на серверах без записи в БД)
            try:
                orphaned = await sync_manager.find_orphaned_clients()
                if orphaned:
                    logger.warning(
                        f"Найдено {len(orphaned)} orphaned клиентов на серверах "
                        f"(клиенты без записи в БД подписок)"
                    )
                    # Логируем первые 10 для примера
                    for orphan in orphaned[:10]:
                        logger.warning(
                            f"Orphaned клиент: {orphan['client_email']} на сервере {orphan['server_name']}"
                        )
            except Exception as e:
                logger.error(f"Ошибка поиска orphaned клиентов: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка в задаче синхронизации БД с X-UI: {e}")
            # В случае ошибки ждем 1 час перед повторной попыткой
            await asyncio.sleep(60 * 60)


async def sync_servers_with_config_task():
    """
    Периодическая задача синхронизации серверов в подписках с конфигурацией.
    Запускается каждый час для автоматического добавления/удаления серверов.
    """
    logger.info("Запуск периодической синхронизации серверов с конфигурацией")
    while True:
        try:
            # Ждем 1 час перед первой синхронизацией (чтобы не нагружать при старте)
            await asyncio.sleep(60 * 60)
            
            # Получаем SubscriptionManager из глобальных переменных
            globals_dict = get_globals()
            subscription_manager = globals_dict.get('subscription_manager')
            
            if not subscription_manager:
                logger.warning("subscription_manager не доступен, пропускаем синхронизацию")
                continue
            
            # Выполняем синхронизацию серверов с конфигурацией
            stats = await subscription_manager.sync_servers_with_config(auto_create_clients=True)
            
            # Логируем результаты
            if stats['errors']:
                logger.warning(
                    f"Синхронизация серверов завершена с ошибками: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"добавлено {stats['servers_added']} серверов, "
                    f"удалено {stats['servers_removed']} серверов, "
                    f"создано {stats['clients_created']} клиентов, "
                    f"ошибок {len(stats['errors'])}"
                )
            else:
                logger.info(
                    f"Синхронизация серверов успешно завершена: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"добавлено {stats['servers_added']} серверов, "
                    f"удалено {stats['servers_removed']} серверов, "
                    f"создано {stats['clients_created']} клиентов"
                )
            
        except Exception as e:
            logger.error(f"Ошибка в задаче синхронизации серверов с конфигурацией: {e}")
            # В случае ошибки ждем 30 минут перед повторной попыткой
            await asyncio.sleep(30 * 60)

