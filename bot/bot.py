"""
Точка входа бота. Порядок: конфиг → утилиты → сервисы → обработчики → запуск.
"""
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from yookassa import Configuration

# 1. Foundation: конфиг и пути
from . import config

config.validate_required()
config.ensure_dirs()
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY

if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
    print("ВНИМАНИЕ: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены!")

# 2. Логирование (config.ensure_dirs() уже создал LOGS_DIR)
app_log_path = str(config.APP_LOG_PATH)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = RotatingFileHandler(
    app_log_path,
    maxBytes=1_048_576,
    backupCount=3,
    encoding="utf-8",
    delay=True,
)
file_handler.setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[console_handler, file_handler],
)
logger = logging.getLogger(__name__)

# 3. Утилиты (пути к изображениям для меню)
from .utils import UIButtons, check_private_chat, set_image_paths

set_image_paths(config.IMAGE_PATHS)

# 4. Сервисы (подписки через Remnawave)
from .services import NotificationManager

# 4.1 Единый контекст приложения
from .context import AppContext

app_context = AppContext(
    notification_manager=None,
    admin_ids=config.ADMIN_IDS,
    telegram_app=None,
    config=config,
)

# Реэкспорт конфига для кода, читающего из bot.bot (WEBAPP_URL, ADMIN_IDS и т.д.)
TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
ADMIN_IDS = config.ADMIN_IDS
WEBHOOK_URL = config.WEBHOOK_URL
WEBAPP_URL = config.WEBAPP_URL
IMAGE_PATHS = config.IMAGE_PATHS
VPN_BRAND_NAME = config.VPN_BRAND_NAME
DATA_DIR = str(config.DATA_DIR)

# 5. Обработчики
from .handlers.commands import start
from .handlers.callbacks import link_telegram_confirm_callback
from .handlers.webhooks import create_webhook_app
from .handlers.utils import error_handler
from .core import on_startup

# Глобальный менеджер уведомлений (инициализируется в on_startup)
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
        if query.message:
            await query.message.reply_text(
                "Пожалуйста, откройте приложение для управления подписками и оплатой.",
                reply_markup=kb,
            )


async def open_mini_app_fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на текстовое сообщение в ЛС: предлагаем открыть приложение."""
    if not await check_private_chat(update):
        return
    if not update.message:
        return
    btn = UIButtons.create_webapp_button(text="Открыть в приложении")
    kb = InlineKeyboardMarkup([[btn]]) if btn else None
    await update.message.reply_text(
        "Пожалуйста, откройте приложение для управления подписками и оплатой.",
        reply_markup=kb,
    )


# --- Запуск (main) ---
if __name__ == "__main__":
    http_request = HTTPXRequest(
        connection_pool_size=8,  # Размер пула соединений
        connect_timeout=30.0,    # Таймаут на установку соединения (увеличен с дефолтных 5)
        read_timeout=30.0,       # Таймаут на чтение ответа (увеличен с дефолтных 5)
        write_timeout=30.0,      # Таймаут на отправку данных
        pool_timeout=30.0        # Таймаут ожидания свободного соединения в пуле
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(http_request).post_init(on_startup).build()
    setattr(sys.modules[__name__], "app", app)
    app_context.telegram_app = app

    # Создаем Flask приложение для webhook'ов (контекст передаётся в маршруты через app.config)
    webhook_app = create_webhook_app(app, app_context)
    
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
