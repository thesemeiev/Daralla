"""
Константы и типы состояний навигации бота
"""

class NavStates:
    """Состояния навигационного стека"""
    MAIN_MENU = 'main_menu'
    INSTRUCTION_MENU = 'instruction_menu'
    INSTRUCTION_PLATFORM = 'instruction_platform'
    BUY_MENU = 'buy_menu'
    PAYMENT = 'payment'
    SUBSCRIPTIONS_MENU = 'subs_menu'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST = 'broadcast'
    ADMIN_SEARCH_USER = 'admin_search_user'
    ADMIN_USER_INFO = 'admin_user_info'
    ADMIN_USER_SUBSCRIPTIONS = 'admin_user_subscriptions'
    ADMIN_USER_PAYMENTS = 'admin_user_payments'
    ADMIN_SUBSCRIPTION_INFO = 'admin_subscription_info'
    ADMIN_SUB_CHANGE_LIMIT = 'admin_sub_change_limit'
    ADMIN_CONFIG = 'admin_config'
    ADMIN_SYNC = 'admin_sync'
    ADMIN_CHECK_SUBSCRIPTION = 'admin_check_subscription'

class MenuTypes:
    """Типы меню для изображений"""
    MAIN_MENU = 'main_menu'
    INSTRUCTION_MENU = 'instruction_menu'
    INSTRUCTION_PLATFORM = 'instruction_platform'
    INSTRUCTION_ANDROID = 'instruction_android'
    INSTRUCTION_IOS = 'instruction_ios'
    INSTRUCTION_WINDOWS = 'instruction_windows'
    INSTRUCTION_MACOS = 'instruction_macos'
    INSTRUCTION_LINUX = 'instruction_linux'
    INSTRUCTION_TV = 'instruction_tv'
    INSTRUCTION_FAQ = 'instruction_faq'
    BUY_MENU = 'buy_menu'
    PAYMENT = 'payment'
    PAYMENT_SUCCESS = 'payment_success'
    PAYMENT_FAILED = 'payment_failed'
    SUBSCRIPTIONS_MENU = 'subs_menu'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST = 'broadcast'
    ADMIN_SEARCH_USER = 'admin_search_user'
    ADMIN_USER_INFO = 'admin_user_info'
    ADMIN_USER_SUBSCRIPTIONS = 'admin_user_subscriptions'
    ADMIN_USER_PAYMENTS = 'admin_user_payments'
    ADMIN_SUBSCRIPTION_INFO = 'admin_subscription_info'
    ADMIN_CONFIG = 'admin_config'
    ADMIN_SYNC = 'admin_sync'
    ADMIN_CHECK_SUBSCRIPTION = 'admin_check_subscription'

class CallbackData:
    """Константы callback_data"""
    BACK = 'back'
    MAIN_MENU = 'main_menu'
    INSTRUCTION = 'instruction'
    BUY_VPN = 'buy_vpn'
    MY_SUBSCRIPTIONS = 'my_subs'
    SUBSCRIPTIONS_MENU = 'subs_menu'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST_START = 'admin_broadcast_start'
    ADMIN_BROADCAST_BACK = 'admin_broadcast_back'
    # Инструкции
    INSTR_ANDROID = 'instr_android'
    INSTR_IOS = 'instr_ios'
    INSTR_WINDOWS = 'instr_windows'
    INSTR_MACOS = 'instr_macos'
    INSTR_LINUX = 'instr_linux'
    INSTR_TV = 'instr_tv'
    INSTR_FAQ = 'instr_faq'
    
    # Покупка
    SELECT_PERIOD_MONTH = 'select_period_month'
    SELECT_PERIOD_3MONTH = 'select_period_3month'
    
    # Подписки (паттерны для динамических callback_data)
    VIEW_SUB = 'view_sub:'  # Используется как f"view_sub:{id}"
    RENAME_SUB = 'rename_sub:'  # Используется как f"rename_sub:{id}"
    EXTEND_SUB = 'extend_sub:'  # Используется как f"extend_sub:{id}"
    EXT_SUB_PER = 'ext_sub_per:'  # Используется как f"ext_sub_per:{period}:{id}"
    SUBS_PAGE = 'subs_page_'  # Используется как f"subs_page_{page}"
    BUY_MENU = 'buy_menu'  # Для покупки новой подписки
    
    # Админ
    ADMIN_ERRORS_REFRESH = 'admin_errors_refresh'
    ADMIN_NOTIFICATIONS_REFRESH = 'admin_notifications_refresh'
    ADMIN_BROADCAST_SEND = 'admin_broadcast_send'
    ADMIN_BROADCAST_EXPORT = 'admin_broadcast_export'
    ADMIN_SEARCH_USER = 'admin_search_user'
    ADMIN_USER_SUBS = 'admin_user_subs:'  # f"admin_user_subs:{user_id}"
    ADMIN_USER_PAYMENTS = 'admin_user_payments:'  # f"admin_user_payments:{user_id}"
    ADMIN_USER_MESSAGE = 'admin_user_message:'  # f"admin_user_message:{user_id}"
    ADMIN_SUB_INFO = 'admin_sub_info:'  # f"admin_sub_info:{sub_id}"
    ADMIN_SUB_EXTEND = 'admin_sub_extend:'  # f"admin_sub_extend:{sub_id}:{days}"
    ADMIN_SUB_CANCEL = 'admin_sub_cancel:'  # f"admin_sub_cancel:{sub_id}"
    ADMIN_SUB_CHANGE_LIMIT = 'admin_sub_change_limit:'  # f"admin_sub_change_limit:{sub_id}"
    ADMIN_TEST_PAYMENT = 'admin_test_payment'  # Тестовое подтверждение платежей
    ADMIN_CONFIG = 'admin_config'  # Конфигурация
    ADMIN_SYNC = 'admin_sync'  # Синхронизация
    ADMIN_CHECK_SUBSCRIPTION = 'admin_check_subscription'  # Проверка подписки по токену

# Маппинг callback_data на состояния
CALLBACK_TO_STATE = {
    CallbackData.MAIN_MENU: NavStates.MAIN_MENU,
    CallbackData.INSTRUCTION: NavStates.INSTRUCTION_MENU,
    CallbackData.BUY_VPN: NavStates.BUY_MENU,
    CallbackData.MY_SUBSCRIPTIONS: NavStates.SUBSCRIPTIONS_MENU,
    CallbackData.SUBSCRIPTIONS_MENU: NavStates.SUBSCRIPTIONS_MENU,
    CallbackData.ADMIN_MENU: NavStates.ADMIN_MENU,
    CallbackData.ADMIN_ERRORS: NavStates.ADMIN_ERRORS,
    CallbackData.ADMIN_NOTIFICATIONS: NavStates.ADMIN_NOTIFICATIONS,
    CallbackData.ADMIN_CHECK_SERVERS: NavStates.ADMIN_CHECK_SERVERS,
    CallbackData.ADMIN_BROADCAST_START: NavStates.ADMIN_BROADCAST,
    CallbackData.ADMIN_SEARCH_USER: NavStates.ADMIN_SEARCH_USER,
    CallbackData.ADMIN_TEST_PAYMENT: NavStates.ADMIN_MENU,  # Обрабатывается через команду
    CallbackData.ADMIN_CONFIG: NavStates.ADMIN_CONFIG,
    CallbackData.ADMIN_SYNC: NavStates.ADMIN_SYNC,
    CallbackData.ADMIN_CHECK_SUBSCRIPTION: NavStates.ADMIN_CHECK_SUBSCRIPTION,
}

# Маппинг состояний на функции-обработчики
STATE_TO_HANDLER = {
    NavStates.MAIN_MENU: 'edit_main_menu',
    NavStates.INSTRUCTION_MENU: 'instruction',
    NavStates.INSTRUCTION_PLATFORM: 'instruction',
    NavStates.BUY_MENU: 'buy_menu_handler',
    NavStates.PAYMENT: 'mykey',
    NavStates.SUBSCRIPTIONS_MENU: 'mykey',
    NavStates.ADMIN_MENU: 'admin_menu',
    NavStates.ADMIN_ERRORS: 'admin_menu',
    NavStates.ADMIN_NOTIFICATIONS: 'admin_menu',
    NavStates.ADMIN_CHECK_SERVERS: 'admin_menu',
    NavStates.ADMIN_BROADCAST: 'admin_menu',
    NavStates.ADMIN_SEARCH_USER: 'admin_search_user',
    NavStates.ADMIN_USER_INFO: 'admin_user_info',
    NavStates.ADMIN_USER_SUBSCRIPTIONS: 'admin_user_subscriptions',
    NavStates.ADMIN_USER_PAYMENTS: 'admin_user_payments',
    NavStates.ADMIN_SUBSCRIPTION_INFO: 'admin_subscription_info',
    NavStates.ADMIN_SUB_CHANGE_LIMIT: 'admin_sub_change_limit',
    NavStates.ADMIN_CONFIG: 'admin_config',
    NavStates.ADMIN_SYNC: 'admin_sync',
    NavStates.ADMIN_CHECK_SUBSCRIPTION: 'admin_check_subscription',
}
