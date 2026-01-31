import logging
import os
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import pathlib

# === ИМПОРТ УТИЛИТ ===
from .utils import UIButtons, check_private_chat, set_image_paths

# === ИМПОРТ СЕРВИСОВ ===
from .services import X3, MultiServerManager, NotificationManager, SubscriptionManager
from .services.sync_manager import SyncManager

# === ИМПОРТ ОБРАБОТЧИКОВ ===
from .handlers.commands import start
from .handlers.callbacks import link_telegram_confirm_callback


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

import threading
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from yookassa import Configuration

Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

from .db import DATA_DIR


YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Поддержка нескольких админов через переменную окружения
ADMIN_IDS_STR = os.getenv("ADMIN_ID", os.getenv("ADMIN_IDS", ""))
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()] if ADMIN_IDS_STR else []

# URL мини-приложения (формируется на основе WEBHOOK_URL, сайт в корне домена)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
if WEBHOOK_URL:
    # Убираем путь /webhook/yookassa; Mini App в корне, например https://daralla.ru/
    if "/webhook/" in WEBHOOK_URL:
        WEBAPP_URL = WEBHOOK_URL.split("/webhook/")[0] + "/"
    else:
        WEBAPP_URL = WEBHOOK_URL.rstrip("/") + "/"
else:
    WEBAPP_URL = None

# Пути к изображениям для меню: главное меню (/start), успех и ошибка (уведомления о платежах)
IMAGE_PATHS = {
    'main_menu': 'images/main_menu.jpg',
    'payment_success': 'images/payment_success.jpg',
    'payment_failed': 'images/payment_failed.jpg',
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

# Главное название бренда для VPN клиента
# Это название будет использоваться для всех серверов в подписке
VPN_BRAND_NAME = " Daralla VPN"  # Можно изменить на любое красивое название

# Серверы добавляются через админ-панель, конфиг загружается из БД при старте (init_server_managers)

# Настраиваем файловый лог с ротацией в папке data/logs
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
server_manager = MultiServerManager()
# Менеджер только для новых клиентов
new_client_manager = MultiServerManager()
# Менеджер подписок
subscription_manager = SubscriptionManager(new_client_manager)
# Менеджер синхронизации
sync_manager = SyncManager(new_client_manager, subscription_manager)

# Инициализация менеджеров серверов из БД
async def init_server_managers():
    try:
        from .services.server_provider import ServerProvider
        from .db.subscribers_db import check_and_run_initial_migration
        
        # Проверяем, есть ли серверы в БД
        has_servers = await check_and_run_initial_migration()
        
        if not has_servers:
            logger.warning("⚠️ В БД нет серверов. Серверы должны быть добавлены через админ-панель.")
            logger.warning("⚠️ Покупка VPN будет недоступна до добавления серверов.")
            # Инициализируем менеджеры с пустым конфигом
            server_manager.init_from_config({})
            new_client_manager.init_from_config({})
            return
        
        # Загружаем конфиг из БД
        config = await ServerProvider.get_all_servers_by_location()
        server_manager.init_from_config(config)
        new_client_manager.init_from_config(config)
        logger.info("Менеджеры серверов успешно инициализированы из БД")
    except Exception as e:
        logger.error(f"Ошибка инициализации менеджеров серверов: {e}")

from .handlers.webhooks import create_webhook_app



from .handlers.utils import error_handler

from .core import on_startup

# Глобальный менеджер уведомлений
notification_manager = None

# Глобальный объект приложения (будет инициализирован в main)
app = None



async def open_mini_app_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback для старых callback-кнопок: предлагаем открыть приложение."""
    query = update.callback_query
    if query:
        await query.answer()
        btn = UIButtons.create_webapp_button(text="Открыть в приложении")
        kb = InlineKeyboardMarkup([[btn]]) if btn else None
        await query.message.reply_text(
            "Пожалуйста, откройте приложение для управления подписками и оплатой.",
            reply_markup=kb,
        )


async def open_mini_app_fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на текстовое сообщение в ЛС: предлагаем открыть приложение."""
    if not await check_private_chat(update):
        return
    btn = UIButtons.create_webapp_button(text="Открыть в приложении")
    kb = InlineKeyboardMarkup([[btn]]) if btn else None
    await update.message.reply_text(
        "Пожалуйста, откройте приложение для управления подписками и оплатой.",
        reply_markup=kb,
    )


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
    
    # Сохраняем модуль как bot.bot для доступа из других модулей (get_globals, WEBAPP_URL и т.д.)
    if 'bot.bot' not in sys.modules or sys.modules['bot.bot'] is not sys.modules[__name__]:
        sys.modules['bot.bot'] = sys.modules[__name__]
    
    # Добавляем глобальную обработку ошибок
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(link_telegram_confirm_callback, pattern="^link_confirm_"))
    
    # Текстовые сообщения в ЛС — предлагаем открыть приложение
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, open_mini_app_fallback_text))
    
    # Fallback для старых callback-кнопок (не перехватываем link_confirm_ — привязка Telegram)
    app.add_handler(CallbackQueryHandler(open_mini_app_fallback, pattern=r"^(?!link_confirm_).*$"))
    
    app.run_polling()
