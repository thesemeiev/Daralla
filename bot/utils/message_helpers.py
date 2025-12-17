"""
Утилиты для безопасной работы с сообщениями Telegram
"""
import os
import asyncio
import logging
import time
import telegram
from telegram import InputMediaPhoto
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# Глобальная переменная для путей к изображениям (будет установлена из bot.py)
IMAGE_PATHS = {}

# Глобальный словарь для отслеживания уже отвеченных callback query
# Используем dict для хранения timestamp, чтобы можно было очищать старые записи
_answered_queries = {}

async def safe_answer_callback_query(query, text=None, show_alert=False, cache_time=None):
    """
    Безопасный ответ на callback query с обработкой ошибок
    
    Args:
        query: CallbackQuery объект
        text: Текст ответа (опционально)
        show_alert: Показывать ли alert (опционально)
        cache_time: Время кэширования ответа (опционально)
    
    Returns:
        bool: True если ответ успешен, False если произошла ошибка
    """
    if query is None:
        logger.warning("safe_answer_callback_query: query is None")
        return False
    
    # Проверяем, не был ли уже отвечен этот callback query
    query_id = query.id
    current_time = time.time()
    
    # Очищаем старые записи (старше 60 секунд)
    if _answered_queries:
        old_queries = [qid for qid, ts in _answered_queries.items() if current_time - ts > 60]
        for qid in old_queries:
            _answered_queries.pop(qid, None)
    
    if query_id in _answered_queries:
        logger.info(f"DUPLICATE: Callback query {query_id} already answered at {_answered_queries[query_id]:.3f}, skipping duplicate answer. Data: {query.data}")
        return True
    
    try:
        await query.answer(text=text, show_alert=show_alert, cache_time=cache_time)
        # Помечаем query как отвеченный с текущим timestamp
        _answered_queries[query_id] = current_time
        logger.debug(f"Callback query {query_id} answered successfully. Data: {query.data}")
        return True
    except BadRequest as e:
        # Query is too old - это нормально, просто логируем
        if "too old" in str(e).lower() or "timeout expired" in str(e).lower() or "invalid" in str(e).lower():
            logger.debug(f"Callback query {query.id} is too old or invalid: {e}")
            # Помечаем как отвеченный, чтобы не пытаться снова
            _answered_queries[query_id] = current_time
        else:
            logger.warning(f"BadRequest при ответе на callback query {query.id}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Ошибка при ответе на callback query {query.id}: {e}")
        return False


async def safe_edit_or_reply(message, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    """Безопасное редактирование или отправка текстового сообщения"""
    if message is None:
        logger.error("safe_edit_or_reply: message is None")
        return
    
    # Дополнительное логирование для отладки
    logger.info(f"SAFE_EDIT_OR_REPLY: message={message}, text_length={len(text) if text else 0}, reply_markup={reply_markup is not None}")
    
    # Проверяем, есть ли у сообщения фото
    if message.photo:
        # Если сообщение содержит фото, используем edit_caption
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return
        except Exception as e:
            logger.warning(f"Failed to edit caption, falling back to reply: {e}")
            # Fallback: отправляем новое сообщение
            await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return
    
    # Максимальное количество попыток для сетевых ошибок
    max_retries = 3
    retry_delay = 2  # секунды
    
    for attempt in range(max_retries):
        try:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return  # Успешно отправлено
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_text'):
                # Пробуем отправить как новое сообщение с повторными попытками
                for reply_attempt in range(max_retries):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                        return  # Успешно отправлено
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"Сетевая ошибка при отправке сообщения (попытка {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"Не удалось отправить сообщение после {max_retries} попыток: {net_err}")
                            raise
            elif "can't parse entities" in str(e).lower() and hasattr(message, 'reply_text'):
                # Фолбэк: отправляем как обычный текст без форматирования
                await message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=disable_web_page_preview
                )
                return
            elif "Message is not modified" in str(e):
                # Игнорируем эту ошибку, так как сообщение уже содержит нужное содержимое
                return
            else:
                raise
        except telegram.error.NetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Сетевая ошибка при редактировании сообщения (попытка {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                logger.error(f"Не удалось отредактировать сообщение после {max_retries} попыток: {e}")
                # Последняя попытка - пробуем отправить как новое сообщение
                if hasattr(message, 'reply_text'):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                    except:
                        raise e  # Если и это не удалось, пробрасываем исходную ошибку
                else:
                    raise
        except Exception as e:
            if hasattr(message, 'reply_text'):
                await message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
            else:
                raise


async def safe_edit_or_reply_photo(message, photo_path, caption, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    """Безопасная отправка или редактирование сообщения с фото"""
    if message is None:
        logger.error("safe_edit_or_reply_photo: message is None")
        return
    
    # Проверяем существование файла
    if not os.path.exists(photo_path):
        logger.warning(f"Photo file not found: {photo_path}, falling back to text message")
        await safe_edit_or_reply(message, caption, reply_markup, parse_mode, disable_web_page_preview)
        return
    
    # Максимальное количество попыток для сетевых ошибок
    max_retries = 3
    retry_delay = 2  # секунды
    
    for attempt in range(max_retries):
        try:
            # Пытаемся отредактировать существующее сообщение
            with open(photo_path, 'rb') as photo_file:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_file,
                        caption=caption,
                        parse_mode=parse_mode
                    ),
                    reply_markup=reply_markup
                )
            return  # Успешно отправлено
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_photo'):
                # Пробуем отправить как новое сообщение с повторными попытками
                for reply_attempt in range(max_retries):
                    try:
                        with open(photo_path, 'rb') as photo_file:
                            await message.reply_photo(
                                photo=photo_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode=parse_mode
                            )
                        return  # Успешно отправлено
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"Сетевая ошибка при отправке фото (попытка {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"Не удалось отправить фото после {max_retries} попыток: {net_err}")
                            raise
            elif "can't parse entities" in str(e) and hasattr(message, 'reply_photo'):
                # Фолбэк: отправляем как обычный текст без форматирования
                with open(photo_path, 'rb') as photo_file:
                    await message.reply_photo(
                        photo=photo_file,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                return
            elif "Message is not modified" in str(e):
                # Сообщение не изменилось, это нормально
                return
            else:
                # Другие ошибки - пробуем отправить как новое сообщение
                if hasattr(message, 'reply_photo'):
                    try:
                        with open(photo_path, 'rb') as photo_file:
                            await message.reply_photo(
                                photo=photo_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode=parse_mode
                            )
                        return
                    except:
                        raise e  # Если и это не удалось, пробрасываем исходную ошибку
                else:
                    raise
        except Exception as e:
            if hasattr(message, 'reply_photo'):
                with open(photo_path, 'rb') as photo_file:
                    await message.reply_photo(
                        photo=photo_file,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
            else:
                raise


async def safe_edit_or_reply_universal(message, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None, menu_type=None):
    """Универсальная функция для отправки/редактирования сообщений с автоматическим выбором фото или текста"""
    if message is None:
        logger.error("safe_edit_or_reply_universal: message is None")
        return
    
    # Если указан тип меню и есть соответствующее изображение, используем фото
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            await safe_edit_or_reply_photo(message, photo_path, text, reply_markup, parse_mode, disable_web_page_preview)
            return
    
    # Иначе используем обычное текстовое сообщение
    await safe_edit_or_reply(message, text, reply_markup, parse_mode, disable_web_page_preview)


async def safe_send_message_with_photo(bot, chat_id, text, reply_markup=None, parse_mode=None, menu_type=None):
    """Безопасная отправка сообщения с фото через бота"""
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            try:
                with open(photo_path, 'rb') as photo_file:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                return
            except Exception as e:
                logger.warning(f"Failed to send photo for menu_type {menu_type}: {e}")
    
    # Fallback to text message
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )


async def safe_edit_message_with_photo(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None, menu_type=None):
    """Безопасное редактирование сообщения с фото через бота"""
    max_retries = 3
    retry_delay = 2
    media_edit_successful = False
    
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            for attempt in range(max_retries):
                try:
                    with open(photo_path, 'rb') as photo_file:
                        await bot.edit_message_media(
                            chat_id=chat_id,
                            message_id=message_id,
                            media=InputMediaPhoto(
                                media=photo_file,
                                caption=text,
                                parse_mode=parse_mode
                            ),
                            reply_markup=reply_markup
                        )
                    media_edit_successful = True
                    logger.info(f"Сообщение {message_id} успешно отредактировано как медиа")
                    return  # Успешно отредактировано, выходим (не пытаемся редактировать как текст)
                except telegram.error.BadRequest as e:
                    error_str = str(e).lower()
                    # Если сообщение не может быть отредактировано как медиа (например, оно не было медиа-сообщением)
                    if "can't be edited" in error_str or "message to edit not found" in error_str or "no text" in error_str:
                        logger.info(f"Message {message_id} cannot be edited as media, will try text edit instead: {e}")
                        break  # Переходим к текстовому редактированию
                    elif attempt < max_retries - 1:
                        logger.warning(f"BadRequest при редактировании медиа (попытка {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    else:
                        logger.error(f"Failed to edit message with photo after {max_retries} attempts: {e}")
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Failed to edit message with photo (attempt {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    else:
                        logger.error(f"Failed to edit message with photo after {max_retries} attempts: {e}")
                        break
    
    # Fallback to text message только если редактирование медиа не было успешным
    if not media_edit_successful:
        for attempt in range(max_retries):
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                logger.info(f"Сообщение {message_id} успешно отредактировано как текст")
                return
            except telegram.error.BadRequest as e:
                error_str = str(e).lower()
                if "no text" in error_str or "can't be edited" in error_str:
                    # Сообщение уже является медиа-сообщением, не можем редактировать как текст
                    # Это нормальная ситуация - сообщение уже отредактировано как медиа
                    logger.debug(f"Сообщение {message_id} уже является медиа-сообщением, пропускаем редактирование как текст: {e}")
                    return  # Не пробрасываем ошибку, просто выходим
                elif attempt < max_retries - 1:
                    logger.warning(f"Failed to edit message text (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to edit message text after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to edit message text (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to edit message text after {max_retries} attempts: {e}")
                    raise


def set_image_paths(image_paths: dict):
    """Устанавливает пути к изображениям (вызывается из bot.py)"""
    global IMAGE_PATHS
    IMAGE_PATHS = image_paths

