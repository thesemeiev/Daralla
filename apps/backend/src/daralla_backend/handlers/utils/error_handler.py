"""
Глобальный обработчик ошибок
"""
import logging
import telegram
from telegram.ext import ContextTypes

from ...utils.logging_helpers import log_event

logger = logging.getLogger(__name__)


def get_globals():
    """Получает конфигурацию из AppContext."""
    try:
        from ...app_context import get_ctx
        ctx = get_ctx()
        return {'ADMIN_IDS': ctx.admin_ids}
    except RuntimeError:
        log_event(logger, logging.WARNING, "app_context_not_initialized_for_error_handler")
        return {'ADMIN_IDS': []}


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальная обработка необработанных ошибок"""
    
    # Проверяем тип ошибки
    error = context.error
    error_type = type(error).__name__
    
    # Список временных ошибок, которые не требуют уведомления админа
    temporary_errors = [
        'NetworkError',
        'TimedOut',
        'RetryAfter',
        'Conflict'
    ]
    
    # Проверяем, является ли ошибка временной сетевой проблемой
    is_network_error = (
        error_type in temporary_errors or
        'httpx' in str(error).lower() or
        'ReadError' in str(error) or
        'ConnectError' in str(error) or
        'TimeoutError' in str(error)
    )
    
    if is_network_error:
        # Для сетевых ошибок только логируем, не спамим админов
        log_event(
            logger,
            logging.WARNING,
            "temporary_network_error",
            error_type=error_type,
            error=str(error),
        )
        return
    
    # Для остальных ошибок - полное логирование
    log_event(
        logger,
        logging.ERROR,
        "unhandled_bot_error",
        error_type=error_type,
        error=str(error),
    )
    logger.debug("unhandled_bot_error_traceback", exc_info=context.error)
    
    # Получаем глобальные переменные
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Уведомляем админа только о критических ошибках (не сетевых)
    try:
        error_message = "Daralla — необработанная ошибка\n\n"
        error_message += str(context.error)
        if update and hasattr(update, "effective_user") and update.effective_user:
            error_message += f"\n\nПользователь (Telegram ID): {update.effective_user.id}"
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=error_message[:4000])
            except telegram.error.Forbidden:
                log_event(
                    logger,
                    logging.WARNING,
                    "error_handler_admin_forbidden",
                    admin_id=admin_id,
                )
            except telegram.error.BadRequest as e:
                if "Chat not found" in str(e):
                    log_event(
                        logger,
                        logging.WARNING,
                        "error_handler_admin_chat_not_found",
                        admin_id=admin_id,
                        error=str(e),
                    )
                else:
                    log_event(
                        logger,
                        logging.WARNING,
                        "error_handler_admin_bad_request",
                        admin_id=admin_id,
                        error=str(e),
                    )
            except Exception as e:
                log_event(
                    logger,
                    logging.WARNING,
                    "error_handler_admin_notify_failed",
                    admin_id=admin_id,
                    error=str(e),
                )
    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "error_handler_failed",
            error=str(e),
        )
        logger.debug("error_handler_failed_traceback", exc_info=True)

