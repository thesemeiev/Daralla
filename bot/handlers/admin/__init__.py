"""
Обработчики админ-команд бота
"""
from .admin_errors import admin_errors
from .admin_notifications import admin_notifications
from .admin_check_servers import admin_check_servers
from .admin_config import (
    admin_config, admin_config_change_promo_start, admin_config_change_promo_input,
    admin_config_change_promo_cancel, ADMIN_CONFIG_PROMO_WAITING
)
from .admin_broadcast import (
    admin_broadcast_start, admin_broadcast_input, admin_broadcast_send,
    admin_broadcast_cancel, admin_broadcast_export
)
from .admin_test_payment import admin_test_payment, test_confirm_payment_callback
from .admin_sync import admin_sync
from .admin_check_subscription import admin_check_subscription
from .admin_user_management import admin_search_user, admin_user_subscriptions, admin_user_payments
from .admin_subscription_manage import (
    admin_subscription_info, admin_extend_subscription, admin_cancel_subscription,
    admin_change_device_limit, admin_change_device_limit_input, admin_change_device_limit_cancel,
    ADMIN_SUB_CHANGE_LIMIT_WAITING
)
from .admin_give_subscription import (
    admin_give_subscription, admin_give_subscription_input_user, admin_give_subscription_continue,
    admin_give_subscription_period, admin_give_subscription_cancel, GIVE_SUB_WAITING_USER_ID
)

__all__ = [
    'admin_errors', 'admin_notifications', 'admin_check_servers', 'admin_config',
    'admin_config_change_promo_start', 'admin_config_change_promo_input',
    'admin_config_change_promo_cancel', 'ADMIN_CONFIG_PROMO_WAITING',
    'admin_broadcast_start', 'admin_broadcast_input', 'admin_broadcast_send',
    'admin_broadcast_cancel', 'admin_broadcast_export',
    'admin_test_payment', 'test_confirm_payment_callback',
    'admin_sync', 'admin_check_subscription',
    'admin_search_user', 'admin_user_subscriptions', 'admin_user_payments',
    'admin_subscription_info', 'admin_extend_subscription', 'admin_cancel_subscription',
    'admin_change_device_limit', 'admin_change_device_limit_input', 'admin_change_device_limit_cancel',
    'ADMIN_SUB_CHANGE_LIMIT_WAITING',
    'admin_give_subscription', 'admin_give_subscription_input_user', 'admin_give_subscription_continue',
    'admin_give_subscription_period', 'admin_give_subscription_cancel', 'GIVE_SUB_WAITING_USER_ID'
]

