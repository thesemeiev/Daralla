"""
Константы и типы состояний навигации бота
"""

class NavStates:
    """Состояния навигационного стека"""
    MAIN_MENU = 'main_menu'
    INSTRUCTION_MENU = 'instruction_menu'
    INSTRUCTION_PLATFORM = 'instruction_platform'
    BUY_MENU = 'buy_menu'
    SERVER_SELECTION = 'server_selection'
    PAYMENT = 'payment'
    MYKEYS_MENU = 'mykeys_menu'
    POINTS_MENU = 'points_menu'
    REFERRAL_MENU = 'referral_menu'
    EXTEND_KEY = 'extend_key'
    RENAME_KEY = 'rename_key'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST = 'broadcast'
    ADMIN_SET_DAYS = 'admin_set_days'

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
    SERVER_SELECTION = 'server_selection'
    PAYMENT = 'payment'
    PAYMENT_SUCCESS = 'payment_success'
    PAYMENT_FAILED = 'payment_failed'
    PAYMENT_SUCCESS_KEY = 'payment_success_key'
    MYKEYS_MENU = 'mykeys_menu'
    POINTS_MENU = 'points_menu'
    REFERRAL_MENU = 'referral_menu'
    EXTEND_KEY = 'extend_key'
    RENAME_KEY = 'rename_key'
    KEY_SUCCESS = 'key_success'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST = 'broadcast'

class CallbackData:
    """Константы callback_data"""
    BACK = 'back'
    MAIN_MENU = 'main_menu'
    INSTRUCTION = 'instruction'
    BUY_VPN = 'buy_vpn'
    MY_KEYS = 'mykey'
    MYKEYS_MENU = 'mykeys_menu'
    POINTS = 'points'
    REFERRAL = 'referral'
    ADMIN_MENU = 'admin_menu'
    ADMIN_ERRORS = 'admin_errors'
    ADMIN_NOTIFICATIONS = 'admin_notifications'
    ADMIN_CHECK_SERVERS = 'admin_check_servers'
    ADMIN_BROADCAST_START = 'admin_broadcast_start'
    ADMIN_BROADCAST_BACK = 'admin_broadcast_back'
    ADMIN_SET_DAYS_START = 'admin_set_days_start'
    ADMIN_SET_DAYS_CANCEL = 'admin_set_days_cancel'
    
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
    SELECT_SERVER_AUTO = 'select_server_auto'
    SELECT_SERVER_FINLAND = 'select_server_finland'
    SELECT_SERVER_LATVIA = 'select_server_latvia'
    SELECT_SERVER_ESTONIA = 'select_server_estonia'
    REFRESH_SERVERS = 'refresh_servers'
    
    # Ключи
    EXTEND_KEY_WITH_POINTS = 'extend_key_with_points'
    RENAME_KEY = 'rename_key'
    DELETE_KEY = 'delete_key'
    
    # Баллы
    SPEND_POINTS = 'spend_points'
    EXTEND_WITH_POINTS = 'extend_with_points'
    
    # Админ
    ADMIN_ERRORS_REFRESH = 'admin_errors_refresh'
    ADMIN_NOTIFICATIONS_REFRESH = 'admin_notifications_refresh'
    ADMIN_BROADCAST_SEND = 'admin_broadcast_send'
    ADMIN_BROADCAST_EXPORT = 'admin_broadcast_export'

# Маппинг callback_data на состояния
CALLBACK_TO_STATE = {
    CallbackData.MAIN_MENU: NavStates.MAIN_MENU,
    CallbackData.INSTRUCTION: NavStates.INSTRUCTION_MENU,
    CallbackData.BUY_VPN: NavStates.BUY_MENU,
    CallbackData.MY_KEYS: NavStates.MYKEYS_MENU,
    CallbackData.MYKEYS_MENU: NavStates.MYKEYS_MENU,
    CallbackData.POINTS: NavStates.POINTS_MENU,
    CallbackData.REFERRAL: NavStates.REFERRAL_MENU,
    CallbackData.ADMIN_MENU: NavStates.ADMIN_MENU,
    CallbackData.ADMIN_ERRORS: NavStates.ADMIN_ERRORS,
    CallbackData.ADMIN_NOTIFICATIONS: NavStates.ADMIN_NOTIFICATIONS,
    CallbackData.ADMIN_CHECK_SERVERS: NavStates.ADMIN_CHECK_SERVERS,
    CallbackData.ADMIN_BROADCAST_START: NavStates.ADMIN_BROADCAST,
}

# Маппинг состояний на функции-обработчики
STATE_TO_HANDLER = {
    NavStates.MAIN_MENU: 'edit_main_menu',
    NavStates.INSTRUCTION_MENU: 'instruction',
    NavStates.INSTRUCTION_PLATFORM: 'instruction',
    NavStates.BUY_MENU: 'buy_menu_handler',
    NavStates.SERVER_SELECTION: 'buy_menu_handler',
    NavStates.PAYMENT: 'mykey',
    NavStates.MYKEYS_MENU: 'mykey',
    NavStates.POINTS_MENU: 'points_callback',
    NavStates.REFERRAL_MENU: 'referral_callback',
    NavStates.EXTEND_KEY: 'extend_key_callback',
    NavStates.RENAME_KEY: 'rename_key_callback',
    NavStates.ADMIN_MENU: 'admin_menu',
    NavStates.ADMIN_ERRORS: 'admin_menu',
    NavStates.ADMIN_NOTIFICATIONS: 'admin_menu',
    NavStates.ADMIN_CHECK_SERVERS: 'admin_menu',
    NavStates.ADMIN_BROADCAST: 'admin_menu',
    NavStates.ADMIN_SET_DAYS: 'admin_menu',
}
