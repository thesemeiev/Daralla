"""
Обработчики админ-команд бота
"""
from .admin_errors import admin_errors
from .admin_notifications import admin_notifications
from .admin_check_servers import admin_check_servers
from .admin_config import admin_config
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

__all__ = [
    'admin_errors', 'admin_notifications', 'admin_check_servers', 'admin_config',
    'admin_broadcast_start', 'admin_broadcast_input', 'admin_broadcast_send',
    'admin_broadcast_cancel', 'admin_broadcast_export',
    'admin_test_payment', 'test_confirm_payment_callback',
    'admin_sync', 'admin_check_subscription',
    'admin_search_user', 'admin_user_subscriptions', 'admin_user_payments',
    'admin_subscription_info', 'admin_extend_subscription', 'admin_cancel_subscription',
    'admin_change_device_limit', 'admin_change_device_limit_input', 'admin_change_device_limit_cancel',
    'ADMIN_SUB_CHANGE_LIMIT_WAITING'
]

