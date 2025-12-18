import logging
import html
from logging.handlers import RotatingFileHandler
import datetime
import json
import uuid
import os
import requests
import asyncio
from dotenv import load_dotenv
import pathlib
import telegram
from telegram.helpers import escape_markdown

# === НОВАЯ СИСТЕМА НАВИГАЦИИ ===
from .navigation import NavigationIntegration, NavigationSystem, NavStates, CallbackData, nav_manager, NavigationBuilder

# === ИМПОРТ УТИЛИТ ===
from .utils import (
    UIEmojis, UIStyles, UIButtons, UIMessages,
    safe_edit_or_reply, safe_edit_or_reply_photo, safe_edit_or_reply_universal,
    safe_send_message_with_photo, safe_edit_message_with_photo,
    check_private_chat, calculate_time_remaining, format_vpn_key_message,
    set_image_paths
)

# === ИМПОРТ СЕРВИСОВ ===
from .services import X3, MultiServerManager, NotificationManager, SubscriptionManager
from .services.sync_manager import SyncManager

# === ИМПОРТ ОБРАБОТЧИКОВ ===
from .handlers.commands import start, edit_main_menu, instruction, mykey
from .handlers.callbacks import (
    instruction_callback, extend_key_callback,
    select_period_callback, select_server_callback, start_callback_handler,
    extend_period_callback
)
from .handlers.callbacks.extend_subscription_callback import (
    extend_subscription_callback, extend_subscription_period_callback
)
from .handlers.payments import handle_payment

# Экспортируем handle_payment для доступа через get_globals()
handle_payment = handle_payment
from .handlers.admin import (
    admin_errors, admin_notifications, admin_check_servers, force_check_servers, admin_config,
    admin_broadcast_start, admin_broadcast_input, admin_broadcast_send,
    admin_broadcast_cancel, admin_broadcast_export,
    admin_test_payment, test_confirm_payment_callback,
    admin_sync, admin_check_subscription
)
from .handlers.admin.admin_broadcast import BROADCAST_WAITING_TEXT, BROADCAST_CONFIRM

# Глобальная навигационная система (будет инициализирована в main())
nav_system = None


# Определяем путь к файлу .env
current_dir = pathlib.Path(__file__).parent
project_root = current_dir.parent
env_path = project_root / '.env'

# Загружаем .env из корня проекта (если файл существует)
# В Docker переменные уже передаются через environment:, но загрузка из файла
# может быть полезна для локальной разработки
if env_path.exists():
    load_dotenv(env_path, override=False)  # override=False - не перезаписывать существующие переменные
else:
    # В Docker это нормально, так как переменные передаются через environment:
    pass
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from yookassa import Payment, Configuration
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# Импорт для webhook
from flask import Flask, request, jsonify
import threading
import hmac
import hashlib

from .db import (
    init_all_db, init_payments_db, add_payment, get_payment, get_payment_by_id, update_payment_status, 
    get_all_pending_payments, get_pending_payment, cleanup_old_payments, cleanup_expired_pending_payments,
    is_known_user, register_simple_user, get_all_user_ids, update_payment_activation,
    get_config, set_config, get_all_config, DB_PATH, DATA_DIR
)


from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_result


YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Поддержка нескольких админов через переменную окружения
ADMIN_IDS_STR = os.getenv("ADMIN_ID", os.getenv("ADMIN_IDS", ""))
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()] if ADMIN_IDS_STR else []

# Пути к изображениям для меню
IMAGE_PATHS = {
    'main_menu': 'images/main_menu.jpg',
    'instruction_menu': 'images/instruction_menu.jpg',
    'instruction_platform': 'images/instruction_platform.jpg',
    'buy_menu': 'images/buy_menu.jpg',
    'mykeys_menu': 'images/mykeys_menu.jpg',
    'server_selection': 'images/server_selection.jpg',
    'extend_key': 'images/extend_key.jpg',
    'admin_menu': 'images/admin_menu.jpg',
    'admin_errors': 'images/admin_errors.jpg',
    'admin_notifications': 'images/admin_notifications.jpg',
    'admin_check_servers': 'images/admin_check_servers.jpg',
    'broadcast': 'images/broadcast.jpg',
    'payment': 'images/payment.jpg',
    'payment_success': 'images/payment_success.jpg',
    'payment_failed': 'images/payment_failed.jpg',
    'instruction_android': 'images/instruction_android.jpg',
    'instruction_ios': 'images/instruction_ios.jpg',
    'instruction_windows': 'images/instruction_windows.jpg',
    'instruction_macos': 'images/instruction_macos.jpg',
    'instruction_linux': 'images/instruction_linux.jpg',
    'instruction_tv': 'images/instruction_tv.jpg',
    'instruction_faq': 'images/instruction_faq.jpg',
    'key_success': 'images/key_success.jpg',
    'payment_success_key': 'images/payment_success_key.jpg'
}

# Устанавливаем пути к изображениям в утилитах
set_image_paths(IMAGE_PATHS)

# Проверяем наличие обязательных переменных
if not TELEGRAM_TOKEN:
    raise ValueError(
        "TELEGRAM_TOKEN не найден в переменных окружения!\n"
        "В Docker: убедитесь, что файл .env существует в корне проекта и содержит TELEGRAM_TOKEN.\n"
        "Docker Compose автоматически загружает переменные из .env файла."
    )

if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    print("ВНИМАНИЕ: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены!")

# Конфигурация серверов по локациям
SERVERS_BY_LOCATION = {
 
    "Latvia": [
        {
            "name": "Latvia-1",
            "host": os.getenv("XUI_HOST_LATVIA_1"),
            "login": os.getenv("XUI_LOGIN_LATVIA_1"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_LATVIA_1")  # IP/домен VPN сервера (если отличается от панели)
        },

    ],
 
}

# Создаем плоский список всех серверов для обратной совместимости
SERVERS = []
for location_servers in SERVERS_BY_LOCATION.values():
    SERVERS.extend(location_servers)

# Сервера для новых клиентов (теперь по локациям)
NEW_CLIENT_SERVERS = SERVERS_BY_LOCATION

# Проверяем конфигурацию серверов
for i, server in enumerate(SERVERS):
    if not server["host"] or not server["login"] or not server["password"]:
        print(f"ВНИМАНИЕ: Сервер {server['name']} не настроен! Проверьте переменные XUI_HOST_{server['name'].upper().replace('-', '_')}, XUI_LOGIN_{server['name'].upper().replace('-', '_')}, XUI_PASSWORD_{server['name'].upper().replace('-', '_')}")

# Настраиваем файловый лог с ротацией в папке data/logs
try:
    from .db import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

logs_dir = os.path.join(DATA_DIR, 'logs')
os.makedirs(logs_dir, exist_ok=True)
app_log_path = os.path.join(logs_dir, 'bot.log')

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

file_handler = RotatingFileHandler(
    app_log_path,
    maxBytes=1_048_576,
    backupCount=3,
    encoding='utf-8',
    delay=True
)
file_handler.setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)

# Создаем глобальный экземпляр менеджера серверов
server_manager = MultiServerManager(SERVERS_BY_LOCATION)
# Менеджер только для новых клиентов
new_client_manager = MultiServerManager(SERVERS_BY_LOCATION)
# Менеджер подписок (использует менеджер новых клиентов для создания клиентов на серверах)
subscription_manager = SubscriptionManager(new_client_manager)
# Менеджер синхронизации БД с X-UI серверами
sync_manager = SyncManager(new_client_manager)

from .handlers.webhooks import create_webhook_app

from .core import cleanup_old_payments_task, expired_keys_cleanup_task, auto_cleanup_expired_keys

from .handlers.utils import error_handler

from .core import on_startup, notify_admin, notify_server_issues, server_health_monitor

# Глобальный менеджер уведомлений
notification_manager = None

# Глобальный объект приложения (будет инициализирован в main)
app = None

# Глобальный словарь для хранения коротких идентификаторов ключей для продления
# Ключ: короткий_id, Значение: key_email
extension_keys_cache = {}

# Глобальный словарь для хранения сообщений продления
# Ключ: payment_id, Значение: (chat_id, message_id)
extension_messages = {}

import traceback


from .handlers.messages import handle_text_message



# Регистрируем команды
if __name__ == '__main__':
    # Создаем HTTPXRequest с увеличенными таймаутами для стабильной работы
    http_request = HTTPXRequest(
        connection_pool_size=8,  # Размер пула соединений
        connect_timeout=30.0,    # Таймаут на установку соединения (увеличен с дефолтных 5)
        read_timeout=30.0,       # Таймаут на чтение ответа (увеличен с дефолтных 5)
        write_timeout=30.0,      # Таймаут на отправку данных
        pool_timeout=30.0        # Таймаут ожидания свободного соединения в пуле
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(http_request).post_init(on_startup).build()
    
    # Сохраняем app в глобальную переменную для доступа из других модулей
    import sys
    sys.modules[__name__].app = app
    
    # Создаем Flask приложение для webhook'ов
    webhook_app = create_webhook_app(app)
    
    # Запускаем webhook сервер в отдельном потоке
    def run_webhook():
        webhook_app.run(host='0.0.0.0', port=5000, debug=False)
    
    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("Webhook сервер запущен на порту 5000")
    
    # Настройка системы навигации (без дублирования)
    bot_handlers = {
        'edit_main_menu': edit_main_menu,
        'instruction': instruction,
        'instruction_callback': instruction_callback,
        'handle_payment': handle_payment,
        'mykey': mykey,
        'extend_key_callback': extend_key_callback,
        'admin_errors': admin_errors,
        'admin_notifications': admin_notifications,
        'admin_check_servers': admin_check_servers,
        'admin_broadcast_start': admin_broadcast_start,
    }
    
    # Создаем интеграцию навигации
    nav_integration = NavigationIntegration(bot_handlers)
    
    # Создаем глобальную навигационную систему (используем те же обработчики)
    nav_system = NavigationSystem(bot_handlers)
    # Сохраняем nav_system в глобальную переменную для доступа из других модулей
    # Когда модуль запускается через "python -m bot.bot", __name__ = '__main__'
    # Сохраняем в текущий модуль (будет '__main__' при запуске через -m)
    sys.modules[__name__].nav_system = nav_system
    # Также сохраняем в bot.bot для доступа через importlib.import_module('bot.bot')
    # Когда модуль запускается через "python -m bot.bot", текущий модуль доступен как '__main__'
    # но мы также можем сохранить ссылку на него под именем 'bot.bot'
    if 'bot.bot' not in sys.modules or sys.modules['bot.bot'] is not sys.modules[__name__]:
        # Сохраняем ссылку на текущий модуль под именем 'bot.bot'
        # Это также делает доступными все атрибуты модуля (app, nav_system и т.д.)
        sys.modules['bot.bot'] = sys.modules[__name__]
        logger.debug(f"Модуль сохранен: __name__={__name__}, также доступен как 'bot.bot' (app и nav_system доступны)")
    else:
        logger.debug(f"nav_system сохранен в {__name__} (уже доступен как 'bot.bot')")
    
    # Добавляем глобальную обработку ошибок
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('mykey', mykey))
    app.add_handler(CommandHandler('instruction', instruction))
   
    app.add_handler(CommandHandler('check_servers', force_check_servers))
    # Эти обработчики остаются, так как они не покрываются навигационной системой
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^instr_"))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^back_instr$"))
    app.add_handler(CallbackQueryHandler(extend_key_callback, pattern="^ext_key:"))
    app.add_handler(CallbackQueryHandler(extend_period_callback, pattern="^ext_per:"))
    app.add_handler(CallbackQueryHandler(extend_subscription_callback, pattern="^extend_sub:"))
    app.add_handler(CallbackQueryHandler(extend_subscription_period_callback, pattern="^ext_sub_per:"))
    app.add_handler(CallbackQueryHandler(select_period_callback, pattern="^select_period_"))

    app.add_handler(CommandHandler('admin_errors', admin_errors))
    app.add_handler(CommandHandler('admin_check_servers', admin_check_servers))
    app.add_handler(CommandHandler('admin_notifications', admin_notifications))
    app.add_handler(CommandHandler('admin_config', admin_config))
    app.add_handler(CommandHandler('admin_test_payment', admin_test_payment))
    app.add_handler(CommandHandler('admin_sync', admin_sync))
    app.add_handler(CommandHandler('admin_check_subscription', admin_check_subscription))
    app.add_handler(CallbackQueryHandler(test_confirm_payment_callback, pattern="^test_confirm_payment:"))

    # Обработчики callback-ов для главного меню и выбора сервера
    # ВАЖНО: "back", "instruction", "buy_vpn", "mykeys_menu" убраны из паттерна, так как они обрабатываются через NavigationIntegration
    # Оставляем только специфичные callback'и, которые не обрабатываются навигационной системой
    app.add_handler(CallbackQueryHandler(start_callback_handler, pattern="^(buy_menu|buy_month|buy_3month|mykey|keys_page_.*|admin_notifications_refresh|admin_errors_refresh)$"))
    app.add_handler(CallbackQueryHandler(select_server_callback, pattern="^(select_server_.*|server_unavailable_.*|refresh_servers)$"))
 
    
    # Рассылка
    admin_broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$")],
        states={
            BROADCAST_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_input),
                MessageHandler(filters.PHOTO, admin_broadcast_input),
                MessageHandler(filters.VIDEO, admin_broadcast_input),
                MessageHandler(filters.Document.ALL, admin_broadcast_input),
                MessageHandler(filters.AUDIO, admin_broadcast_input),
                MessageHandler(filters.VOICE, admin_broadcast_input),
                MessageHandler(filters.Sticker.ALL, admin_broadcast_input),
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_send, pattern="^admin_broadcast_send$"),
                CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$"),
        ],
        per_user=True,
        per_chat=True,
        per_message=False
    )
    app.add_handler(admin_broadcast_conv)
    # Глобальный обработчик экспорта, чтобы работал и после завершения диалога
    app.add_handler(CallbackQueryHandler(admin_broadcast_export, pattern="^admin_broadcast_export$"))
    # Глобальный обработчик для кнопки рассылки (на случай если ConversationHandler заблокирован)
    app.add_handler(CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$"))
    # Глобальный обработчик для кнопки назад в рассылке
    app.add_handler(CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$"))

    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # === НОВЫЕ ОБРАБОТЧИКИ НАВИГАЦИИ ===
    app.add_handlers(nav_integration.get_handlers())
    
    app.run_polling()
