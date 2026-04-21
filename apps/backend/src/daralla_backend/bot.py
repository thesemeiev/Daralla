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
from .utils.logging_helpers import log_event

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

# WEBHOOK_URL — только для приёма webhook YooKassa (например https://daralla.ru/webhook/yookassa).
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# URL мини-приложения для кнопок «Открыть в приложении» (меню, уведомления, рассылка).
# Задаётся отдельно в .env как WEBAPP_URL (например https://daralla.ru/). Не выводится из WEBHOOK_URL.
_env_webapp = (os.getenv("WEBAPP_URL") or "").strip()
WEBAPP_URL = (_env_webapp.rstrip("/") + "/") if _env_webapp else None

# Пути к изображениям для меню: главное меню (/start), успех и ошибка (уведомления о платежах)
IMAGE_PATHS = {
    'main_menu': os.getenv("IMAGE_MAIN_MENU", "images/main_menu.jpg"),
    'payment_success': os.getenv("IMAGE_PAYMENT_SUCCESS", "images/payment_success.jpg"),
    'payment_failed': os.getenv("IMAGE_PAYMENT_FAILED", "images/payment_failed.jpg"),
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
    # Логируем предупреждение единообразно, без print в stdout.
    logging.getLogger(__name__).warning(
        "YOOKASSA credentials are missing: YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY"
    )

# Главное название бренда для VPN клиента
# Это название будет использоваться для всех серверов в подписке
VPN_BRAND_NAME = os.getenv("VPN_BRAND_NAME", "Daralla VPN").strip()

# Серверы добавляются через админ-панель, конфиг загружается из БД при старте (init_server_managers)

# Настраиваем файловый лог с ротацией в папке data/logs
logs_dir = os.path.join(DATA_DIR, 'logs')
os.makedirs(logs_dir, exist_ok=True)
app_log_path = os.path.join(logs_dir, 'bot.log')

console_handler = logging.StreamHandler()
_log_level_name = (os.getenv("DARALLA_LOG_LEVEL", "INFO") or "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
console_handler.setLevel(_log_level)

file_handler = RotatingFileHandler(
    app_log_path,
    maxBytes=1_048_576,
    backupCount=3,
    encoding='utf-8',
    delay=True
)
# Пишем в файл также INFO-сообщения, чтобы лучше видеть историю продакшена.
file_handler.setLevel(_log_level)

# Базовый формат логов с именем логгера — проще отлаживать и искать по модулям.
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)
log_event(
    logger,
    logging.INFO,
    "logging_initialized",
    level=logging.getLevelName(_log_level),
    log_file=app_log_path,
)

# Урезаем шум от httpx/httpcore до WARNING, чтобы логи не забивались
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# py3xui: иначе INFO на каждый login / get inbounds / client stats / update (тысячи строк при полной синхронизации)
logging.getLogger("py3xui").setLevel(logging.WARNING)

# === ИНИЦИАЛИЗАЦИЯ AppContext ===
from .app_context import AppContext, set_ctx, get_ctx

server_manager = MultiServerManager()
subscription_manager = SubscriptionManager(server_manager)
sync_manager = SyncManager(server_manager, subscription_manager)

_app_ctx = AppContext(
    server_manager=server_manager,
    subscription_manager=subscription_manager,
    sync_manager=sync_manager,
    admin_ids=ADMIN_IDS,
    webapp_url=WEBAPP_URL,
    vpn_brand_name=VPN_BRAND_NAME,
)
set_ctx(_app_ctx)

# Инициализация менеджеров серверов из БД (всегда используем экземпляр из контекста)
async def init_server_managers():
    try:
        from .services.server_provider import ServerProvider
        from .db.servers_db import check_and_run_initial_migration

        ctx = get_ctx()
        sm = ctx.server_manager
        if not sm:
            logger.error("Ошибка инициализации: server_manager в контексте отсутствует")
            return

        # Проверяем, есть ли серверы в БД
        has_servers = await check_and_run_initial_migration()

        if not has_servers:
            logger.warning("⚠️ В БД нет серверов. Серверы должны быть добавлены через админ-панель.")
            logger.warning("⚠️ Покупка VPN будет недоступна до добавления серверов.")
            sm.init_from_config({})
            return

        # Загружаем конфиг из БД и инициализируем тот же экземпляр, что используется в sync/роутах
        config = await ServerProvider.get_all_servers_by_group()
        sm.init_from_config(config)
        logger.info("Менеджер серверов успешно инициализирован из БД")
    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "init_server_managers_failed",
            error=str(e),
        )
        logger.debug("init_server_managers_failed_traceback", exc_info=True)

from .web.app_quart import create_quart_app



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
def run():
    """Точка входа: создание приложения, Quart/Hypercorn, обработчики и запуск polling."""
    global app
    # БД и X-UI до старта webhook: иначе Quart принимает запросы раньше post_init и server_manager пуст.
    # Не asyncio.run(): он закрывает event loop; в Python 3.10+ на MainThread после этого нет текущего loop,
    # и app.run_polling() (PTB) падает на asyncio.get_event_loop().
    import asyncio
    from .core.startup import ensure_db_and_servers_ready

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(ensure_db_and_servers_ready())

    # Создаем HTTPXRequest с увеличенными таймаутами для стабильной работы
    http_request = HTTPXRequest(
        connection_pool_size=8,  # Размер пула соединений
        connect_timeout=30.0,    # Таймаут на установку соединения (увеличен с дефолтных 5)
        read_timeout=30.0,       # Таймаут на чтение ответа (увеличен с дефолтных 5)
        write_timeout=30.0,      # Таймаут на отправку данных
        pool_timeout=30.0        # Таймаут ожидания свободного соединения в пуле
    )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(http_request).post_init(on_startup).build()

    # Quart + Hypercorn (ASGI) вместо Flask
    quart_app = create_quart_app(app)
    webhook_port = int(os.getenv("WEBHOOK_PORT", "5000"))

    def run_webhook():
        import asyncio
        from hypercorn.config import Config
        from hypercorn.asyncio import serve
        config = Config()
        config.bind = [f"0.0.0.0:{webhook_port}"]
        # shutdown_trigger prevents Hypercorn from installing signal handlers (which only work in main thread)
        shutdown_trigger = lambda: asyncio.Future()
        asyncio.run(serve(quart_app, config, shutdown_trigger=shutdown_trigger))

    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("Webhook сервер (Quart + Hypercorn) запущен на порту %s", webhook_port)

    # Добавляем глобальную обработку ошибок
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(link_telegram_confirm_callback, pattern="^link_confirm_"))

    # Текстовые сообщения в ЛС — предлагаем открыть приложение
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, open_mini_app_fallback_text))

    # Fallback для старых callback-кнопок (не перехватываем link_confirm_ — привязка Telegram).
    app.add_handler(CallbackQueryHandler(open_mini_app_fallback, pattern=r"^(?!link_confirm_).*$"))

    app.run_polling()


if __name__ == '__main__':
    run()
