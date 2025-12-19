"""
Модули для работы с базами данных
"""
import logging

logger = logging.getLogger(__name__)

from .payments_db import (
    init_payments_db, add_payment, get_payment_by_id, update_payment_status,
    get_all_pending_payments, get_pending_payment, cleanup_old_payments,
    cleanup_expired_pending_payments, is_known_user, register_simple_user,
    get_all_user_ids, get_config, set_config, get_all_config, init_users_db,
    update_payment_activation, PAYMENTS_DB_PATH, USERS_DB_PATH, DATA_DIR
)
from .notifications_db import (
    init_notifications_db,
    record_notification_metrics,
    cleanup_old_notifications, get_notification_stats, get_daily_notification_stats,
    clear_user_notifications, get_notification_settings,
    set_notification_setting, NOTIFICATIONS_DB_PATH,
    is_subscription_notification_sent, mark_subscription_notification_sent,
    clear_subscription_notifications, record_subscription_notification_effectiveness
)
from .subscribers_db import init_subscribers_db

async def init_all_db():
    """Инициализирует все базы данных"""
    import os
    from .payments_db import DATA_DIR
    
    # Создаем папку data если её нет
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Создана/проверена папка для баз данных: {DATA_DIR}")
    
    logger.info("Инициализация баз данных...")
    logger.info(f"Путь к базе платежей: {PAYMENTS_DB_PATH}")
    logger.info(f"Путь к базе уведомлений: {NOTIFICATIONS_DB_PATH}")
    
    logger.info("Вызываем init_payments_db()...")
    await init_payments_db()
    logger.info("init_payments_db() завершена")
    logger.info("База данных платежей инициализирована")
    
    await init_notifications_db()  # Инициализируем базу данных уведомлений
    logger.info("База данных уведомлений инициализирована")
    
    await init_users_db()  # Инициализируем базу данных пользователей и конфигурации
    logger.info("База данных пользователей инициализирована")
    
    await init_subscribers_db()  # Инициализируем базу данных подписок
    logger.info("База данных подписок инициализирована")
    
    logger.info("Все базы данных успешно инициализированы")

__all__ = [
    'init_all_db', 'init_payments_db', 'add_payment', 'get_payment_by_id',
    'update_payment_status', 'update_payment_activation', 'get_all_pending_payments', 'get_pending_payment',
    'cleanup_old_payments', 'cleanup_expired_pending_payments', 'is_known_user',
    'register_simple_user', 'get_all_user_ids', 'get_config', 'set_config',
    'get_all_config', 'init_users_db', 'PAYMENTS_DB_PATH', 'USERS_DB_PATH', 'DATA_DIR',
    'init_notifications_db', 'record_notification_metrics',
    'cleanup_old_notifications', 'get_notification_stats', 'get_daily_notification_stats',
    'clear_user_notifications', 'get_notification_settings',
    'set_notification_setting', 'NOTIFICATIONS_DB_PATH',
    'is_subscription_notification_sent', 'mark_subscription_notification_sent',
    'clear_subscription_notifications', 'record_subscription_notification_effectiveness'
]

