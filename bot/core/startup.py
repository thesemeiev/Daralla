"""
Функции инициализации и мониторинга бота
"""
import logging
import asyncio

from ..db import init_all_db
from ..services import NotificationManager

logger = logging.getLogger(__name__)


async def notify_admin(bot, admin_ids, text):
    """Отправляет уведомление всем администраторам"""
    if not admin_ids:
        logger.warning("Список администраторов пуст")
        return
        
    for admin_id in admin_ids:
        try:
            async with asyncio.timeout(10):
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"[VPNBot ERROR]\n{text}",
                    disable_web_page_preview=True
                )
                logger.info(f"Успешно отправлено уведомление админу {admin_id}")
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления админу {admin_id}: {e}')


async def on_startup(app):
    """Инициализация бота при запуске"""
    try:
        import sys
        bot_module = sys.modules.get("bot.bot")
        if not bot_module:
            import importlib
            bot_module = importlib.import_module("bot.bot")

        ctx = getattr(bot_module, "app_context", None)
        # Store running loop in context so webhook handlers can schedule coroutines
        try:
            import asyncio as _asyncio
            if ctx is not None:
                ctx.main_loop = _asyncio.get_running_loop()
        except Exception:
            pass
        if ctx:
            admin_ids = ctx.admin_ids
        else:
            admin_ids = getattr(bot_module, "ADMIN_IDS", [])
        
        logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")
        
        # 1. Инициализация БД
        await init_all_db()

        # 1.0.0 Модуль событий: таблицы (если включён)
        try:
            from bot.events import EVENTS_MODULE_ENABLED
            if EVENTS_MODULE_ENABLED:
                from bot.events.db.schema import init_events_tables
                await init_events_tables()
        except ImportError:
            pass
        except Exception as e:
            logger.warning("Модуль событий: не удалось инициализировать таблицы: %s", e)

        # 2. Инициализация и запуск менеджера уведомлений
        notification_manager = NotificationManager(app.bot, admin_ids)
        await notification_manager.initialize()
        await notification_manager.start()
        setattr(bot_module, "notification_manager", notification_manager)
        if ctx:
            ctx.notification_manager = notification_manager
        
        logger.info("Менеджер уведомлений запущен")
        logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
        
        # 3. Запуск фоновых задач
        from .tasks import start_background_tasks
        await start_background_tasks(notification_manager)

    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        raise
