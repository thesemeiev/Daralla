"""
Централизованный модуль работы с БД (Единая база daralla.db)
"""
import logging
import os

logger = logging.getLogger(__name__)

# Пути к единой базе данных
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'daralla.db')

# Экспорт путей для совместимости (если где-то остались старые импорты)
PAYMENTS_DB_PATH = DB_PATH
USERS_DB_PATH = DB_PATH
NOTIFICATIONS_DB_PATH = DB_PATH
SUBSCRIBERS_DB_PATH = DB_PATH

# Импортируем все функции из подмодулей
from .payments_db import (
    init_payments_db, add_payment, get_payment_by_id, update_payment_status,
    update_payment_activation, get_all_pending_payments, get_pending_payment,
    cleanup_old_payments, cleanup_expired_pending_payments
)
from .users_db import (
    init_users_db, get_all_user_ids, register_simple_user, is_known_user,
    get_config, set_config, get_all_config
)
from .notifications_db import (
    init_notifications_db, record_notification_metrics, cleanup_old_notifications,
    get_notification_stats, get_daily_notification_stats, clear_user_notifications,
    get_notification_settings, set_notification_setting,
    is_subscription_notification_sent, mark_subscription_notification_sent,
    clear_subscription_notifications, record_subscription_notification_effectiveness
)
from .subscribers_db import (
    init_subscribers_db, get_or_create_subscriber, create_subscription,
    get_all_active_subscriptions, update_subscription_status, update_subscription_name,
    get_subscription_by_token, get_subscription_servers, add_subscription_server,
    remove_subscription_server, get_all_active_subscriptions_by_user,
    get_subscription_by_id, update_subscription_expiry
)

async def init_all_db():
    """Инициализирует все таблицы в единой базе данных"""
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Инициализация единой базы данных: {DB_PATH}")
    
    # Последовательно вызываем инициализацию каждой части
    # Все они теперь будут открывать один и тот же файл DB_PATH
    await init_users_db()
    await init_subscribers_db()
    await init_payments_db()
    await init_notifications_db()
    
    logger.info("Единая база данных daralla.db успешно инициализирована")

__all__ = [
    'init_all_db', 'DB_PATH', 'DATA_DIR',
    'add_payment', 'get_payment_by_id', 'update_payment_status', 'update_payment_activation',
    'get_all_pending_payments', 'get_pending_payment', 'cleanup_old_payments', 'cleanup_expired_pending_payments',
    'get_all_user_ids', 'register_simple_user', 'is_known_user', 'get_config', 'set_config', 'get_all_config',
    'record_notification_metrics', 'cleanup_old_notifications', 'get_notification_stats',
    'get_daily_notification_stats', 'clear_user_notifications', 'get_notification_settings',
    'set_notification_setting', 'is_subscription_notification_sent', 'mark_subscription_notification_sent',
    'clear_subscription_notifications', 'record_subscription_notification_effectiveness',
    'get_or_create_subscriber', 'create_subscription', 'get_all_active_subscriptions',
    'update_subscription_status', 'update_subscription_name', 'get_subscription_by_token',
    'get_subscription_servers', 'add_subscription_server', 'remove_subscription_server',
    'get_all_active_subscriptions_by_user', 'get_subscription_by_id', 'update_subscription_expiry'
]
