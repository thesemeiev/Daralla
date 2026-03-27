"""
Глобальный обработчик ошибок
"""
import logging
import telegram
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def get_globals():
    """Получает конфигурацию из AppContext."""
    try:
        from ...app_context import get_ctx
        ctx = get_ctx()
        return {'ADMIN_IDS': ctx.admin_ids}
    except RuntimeError:
        logger.warning("AppContext не инициализирован, ADMIN_IDS пустой")
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
        logger.warning(f"Временная сетевая ошибка (будет автоматически повторена): {error_type}: {str(error)}")
        return
    
    # Для остальных ошибок - полное логирование
    logger.error("Необработанная ошибка:", exc_info=context.error)
    
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
                logger.warning(f"Админ {admin_id} заблокировал бота (error_handler)")
            except telegram.error.BadRequest as e:
                if "Chat not found" in str(e):
                    logger.warning(f"Админ {admin_id} заблокировал бота (error_handler): {e}")
                else:
                    pass  # Другие BadRequest ошибки игнорируем в error_handler
            except:
                pass  # Если не удается отправить админу, продолжаем работу
    except:
        pass  # Не прерываем работу бота из-за ошибки в error_handler

