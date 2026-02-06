"""
Централизованный модуль работы с БД (единый файл app.db).
"""
import logging
import os

from ..config import DATA_DIR as _DATA_DIR

logger = logging.getLogger(__name__)

# Путь к базе данных
DATA_DIR = str(_DATA_DIR)
DB_PATH = os.path.join(DATA_DIR, "app.db")
BASE_DIR = os.path.dirname(DATA_DIR)

# Экспорт путей для совместимости (если где-то остались старые импорты)
PAYMENTS_DB_PATH = DB_PATH
USERS_DB_PATH = DB_PATH
NOTIFICATIONS_DB_PATH = DB_PATH

# Импортируем все функции из подмодулей
from .payments_db import (
    init_payments_db, add_payment, get_payment_by_id, update_payment_status,
    update_payment_activation, update_payment_meta, get_all_pending_payments, get_pending_payment,
    cleanup_old_payments,     cleanup_expired_pending_payments, get_payments_by_account,
    delete_payments_by_account_id,
)
from .notifications_db import (
    init_notifications_db, record_notification_metrics, cleanup_old_notifications,
    get_notification_stats,
    get_notification_settings, set_notification_setting,
    is_subscription_notification_sent, mark_subscription_notification_sent,
)
from .accounts_db import (
    init_accounts_db,
    create_account,
    touch_account,
    get_account_id_by_identity,
    link_identity,
    get_or_create_account_for_telegram,
    get_or_create_account_for_username,
    set_remnawave_mapping,
    get_remnawave_mapping,
    get_telegram_id_for_account,
    get_username_for_account,
    replace_password_identity,
    delete_identity,
    set_account_password,
    get_account_password_hash,
    username_available,
    link_telegram_create_state,
    link_telegram_consume_state,
    set_account_auth_token,
    get_account_id_by_auth_token,
    get_telegram_chat_id_for_account,
    upsert_account_expiry_cache,
    get_accounts_expiring_soon,
    delete_account,
    get_all_account_ids,
)
from .server_config_db import (
    init_server_config_db,
    get_node_map_overrides,
    upsert_node_map_override,
)

async def init_all_db():
    """Инициализирует все таблицы в единой базе данных"""
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Инициализация единой базы данных: {DB_PATH}")
    
    # Последовательно вызываем инициализацию каждой части
    # Все они теперь будут открывать один и тот же файл DB_PATH
    await init_accounts_db()
    await init_server_config_db()
    await init_payments_db()
    await init_notifications_db()
    
    logger.info("База данных app.db инициализирована")

__all__ = [
    'init_all_db', 'DB_PATH', 'DATA_DIR',
    'init_accounts_db',
    'create_account', 'touch_account',
    'get_account_id_by_identity', 'link_identity',
    'get_or_create_account_for_telegram', 'get_or_create_account_for_username',
    'set_remnawave_mapping', 'get_remnawave_mapping',
    'get_telegram_id_for_account', 'get_username_for_account',
    'replace_password_identity', 'delete_identity',
    'set_account_password', 'get_account_password_hash', 'username_available',
    'link_telegram_create_state', 'link_telegram_consume_state',
    'set_account_auth_token', 'get_account_id_by_auth_token',
    'get_telegram_chat_id_for_account', 'upsert_account_expiry_cache', 'get_accounts_expiring_soon',
    'delete_account',
    'add_payment', 'get_payment_by_id', 'update_payment_status', 'update_payment_activation', 'update_payment_meta',
    'get_all_pending_payments', 'get_pending_payment', 'cleanup_old_payments', 'cleanup_expired_pending_payments',
    'get_payments_by_account', 'delete_payments_by_account_id',
    'get_all_account_ids',
    'record_notification_metrics', 'cleanup_old_notifications', 'get_notification_stats',
    'get_notification_settings',
    'set_notification_setting', 'is_subscription_notification_sent', 'mark_subscription_notification_sent',
    'init_server_config_db',
    'get_node_map_overrides', 'upsert_node_map_override',
]
