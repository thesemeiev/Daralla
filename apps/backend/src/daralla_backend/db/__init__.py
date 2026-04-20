"""
Централизованный модуль работы с БД (Единая база daralla.db)
"""
import logging
import os

logger = logging.getLogger(__name__)

# Пути к единой базе данных
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
# В тестах задайте DARALLA_TEST_DB (например :memory: или путь к временному файлу) до импорта daralla_backend.db
DB_PATH = os.environ.get('DARALLA_TEST_DB', os.path.join(DATA_DIR, 'daralla.db'))

# Импортируем все функции из подмодулей
from .migrations import run_migrations
from .config_db import init_config_db, get_config, set_config, get_all_config
from .payments_db import (
    init_payments_db, add_payment, get_payment_by_id, update_payment_status,
    update_payment_activation, get_all_pending_payments, get_pending_payment,
    cleanup_old_payments, cleanup_expired_pending_payments, get_payments_by_user,
    get_revenue_by_gateway, get_daily_revenue,
)
from .users_db import (
    init_users_db, get_all_user_ids, register_simple_user, is_known_user,
    TG_USER_ID_HEX_LEN, UsernameAlreadyExistsError, generate_user_id, generate_tg_user_id, get_or_create_subscriber,
    get_user_by_id, get_user_by_username, resolve_user_by_query,
    get_user_growth_data, get_user_server_usage, register_web_user,
    update_user_auth_token, get_user_by_auth_token, get_user_by_username_or_id,
    username_available, update_user_username, update_user_password,
    link_telegram_create_state, link_telegram_consume_state,
    get_user_by_telegram_id, get_user_by_telegram_id_v2,
    create_telegram_link, delete_telegram_link, get_telegram_link,
    is_known_telegram_id, mark_telegram_id_known, update_user_telegram_id,
    get_telegram_chat_id_for_notification, merge_user_into_target,
    link_telegram_to_account, reconcile_users_telegram_id_with_link,
    rename_user_id, delete_user_completely,
)
from .servers_db import (
    init_servers_db,
    ensure_servers_config_client_sort_order_column,
    get_servers_config,
    get_server_by_id,
    get_server_groups,
    get_least_loaded_group_id,
    get_default_group_id,
    resolve_group_id,
    check_and_run_initial_migration,
    save_server_load_snapshot,
    get_server_load_averages,
    cleanup_old_server_load_history,
    get_group_load_statistics,
    add_server_group,
    add_server_config,
    update_server_group,
    update_server_config,
    delete_server_config,
    SERVER_CONFIG_UPDATE_KEYS,
)
from .subscriptions_db import (
    init_subscriptions_db,
    create_subscription,
    get_all_active_subscriptions,
    get_subscriptions_to_sync,
    get_all_active_subscriptions_by_user,
    get_all_subscriptions_by_user,
    update_subscription_status,
    update_subscription_name,
    update_subscription_expiry,
    update_subscription_device_limit,
    update_subscription_price,
    is_subscription_active,
    sync_subscription_statuses,
    get_subscription_by_token,
    get_subscription_by_id,
    get_subscription_by_id_only,
    get_subscription_servers,
    get_subscription_servers_for_subscription_ids,
    add_subscription_server,
    remove_subscription_server,
    get_subscription_statistics,
    get_subscription_types_statistics,
    get_subscription_dynamics_data,
    get_subscription_conversion_data,
    get_conversion_data,
)
from .notifications_db import (
    init_notifications_db, record_notification_metrics, cleanup_old_notifications,
    get_notification_stats, get_daily_notification_stats,
    get_notification_settings, set_notification_setting,
    is_subscription_notification_sent, mark_subscription_notification_sent,
    clear_subscription_notifications, reset_no_sub_notifications,
    get_all_notification_rules, get_active_notification_rules,
    create_notification_rule, update_notification_rule, delete_notification_rule,
    get_notification_rule_by_id,
    get_notification_send_count, get_last_notification_send_time,
    render_structured_template,
)
async def init_all_db():
    """Инициализирует схему БД через систему миграций."""
    import aiosqlite

    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Инициализация базы данных: {DB_PATH}")

    applied = await run_migrations()
    if applied:
        logger.info("Применено %d миграций", applied)
    if await ensure_servers_config_client_sort_order_column():
        logger.info("Схема восстановлена: servers_config.client_sort_order")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA busy_timeout=15000")
            async with db.execute("PRAGMA journal_mode=WAL") as cur:
                row = await cur.fetchone()
            mode = (row[0] if row else None) or ""
            if str(mode).upper() == "WAL":
                logger.info("SQLite: journal_mode=WAL (лучше для конкурентного доступа)")
            else:
                logger.warning("SQLite: journal_mode=%s (ожидался WAL)", mode)
            await db.commit()
    except Exception as e:
        logger.warning("Не удалось применить PRAGMA WAL/busy_timeout: %s", e)
    logger.info("База данных daralla.db готова")

__all__ = [
    'init_all_db', 'run_migrations', 'DB_PATH', 'DATA_DIR',
    'init_config_db', 'init_users_db', 'init_servers_db', 'init_subscriptions_db',
    'add_payment', 'get_payment_by_id', 'update_payment_status', 'update_payment_activation',
    'get_all_pending_payments', 'get_pending_payment', 'cleanup_old_payments', 'cleanup_expired_pending_payments',
    'get_payments_by_user', 'get_revenue_by_gateway', 'get_daily_revenue',
    'get_all_user_ids', 'register_simple_user', 'is_known_user', 'get_config', 'set_config', 'get_all_config',
    'record_notification_metrics', 'cleanup_old_notifications', 'get_notification_stats',
    'get_daily_notification_stats', 'get_notification_settings',
    'set_notification_setting', 'is_subscription_notification_sent', 'mark_subscription_notification_sent',
    'clear_subscription_notifications',
    'get_all_notification_rules', 'get_active_notification_rules',
    'create_notification_rule', 'update_notification_rule', 'delete_notification_rule',
    'get_notification_rule_by_id',
    'get_notification_send_count', 'get_last_notification_send_time',
    'TG_USER_ID_HEX_LEN', 'generate_user_id', 'generate_tg_user_id', 'get_or_create_subscriber', 'get_user_by_id', 'get_user_by_username',
    'resolve_user_by_query', 'get_user_growth_data', 'get_user_server_usage', 'UsernameAlreadyExistsError', 'register_web_user',
    'update_user_auth_token', 'get_user_by_auth_token', 'get_user_by_username_or_id',
    'username_available', 'update_user_username', 'update_user_password',
    'link_telegram_create_state', 'link_telegram_consume_state',
    'get_user_by_telegram_id', 'get_user_by_telegram_id_v2',
    'create_telegram_link', 'delete_telegram_link', 'get_telegram_link',
    'is_known_telegram_id', 'mark_telegram_id_known', 'update_user_telegram_id',
    'get_telegram_chat_id_for_notification', 'merge_user_into_target', 'link_telegram_to_account',
    'reconcile_users_telegram_id_with_link',
    'rename_user_id', 'delete_user_completely',
    'create_subscription', 'get_all_active_subscriptions', 'get_subscriptions_to_sync',
    'get_all_active_subscriptions_by_user', 'get_all_subscriptions_by_user',
    'update_subscription_status', 'update_subscription_name', 'update_subscription_expiry',
    'update_subscription_device_limit', 'update_subscription_price',
    'is_subscription_active', 'sync_subscription_statuses',
    'get_subscription_by_token', 'get_subscription_by_id', 'get_subscription_by_id_only',
    'get_subscription_servers', 'get_subscription_servers_for_subscription_ids',
    'add_subscription_server', 'remove_subscription_server',
    'get_subscription_statistics', 'get_subscription_types_statistics',
    'get_subscription_dynamics_data', 'get_subscription_conversion_data',
    'get_conversion_data',
    'init_servers_db', 'get_servers_config', 'get_server_by_id', 'get_server_groups',
    'get_least_loaded_group_id', 'check_and_run_initial_migration',
    'save_server_load_snapshot', 'get_server_load_averages', 'cleanup_old_server_load_history',
    'get_group_load_statistics',
    'get_default_group_id', 'resolve_group_id',
    'add_server_group', 'add_server_config', 'update_server_group', 'update_server_config',
    'delete_server_config', 'SERVER_CONFIG_UPDATE_KEYS',
]
