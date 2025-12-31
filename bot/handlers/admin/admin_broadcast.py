"""
Обработчики рассылки для админа
"""
import logging
import asyncio
import io
import csv
import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from ...utils import (
    UIEmojis, safe_edit_or_reply_universal, safe_edit_message_with_photo,
    safe_send_message_with_photo, check_private_chat
)
from ...utils.ui import UIMessages
from ...navigation import NavStates, CallbackData, MenuTypes
from ...db import get_all_user_ids

logger = logging.getLogger(__name__)

# Константы для состояний рассылки
BROADCAST_WAITING_TEXT = 1001
BROADCAST_CONFIRM = 1002

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    import sys
    bot_module = sys.modules.get('bot.bot')
    if not bot_module:
        try:
            from ... import bot as bot_module
        except (ImportError, AttributeError):
            pass
    
    if bot_module:
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    return {
        'ADMIN_IDS': [],
        'nav_system': None,
    }


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало рассылки"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply_universal(update.callback_query.message, 'Нет доступа.', menu_type=MenuTypes.ADMIN_BROADCAST)
        return
    
    from ...utils import safe_answer_callback_query
    await safe_answer_callback_query(update.callback_query)
    
    # Очищаем старые данные рассылки при новом запуске
    context.user_data.pop('broadcast_text', None)
    context.user_data.pop('broadcast_media', None)
    context.user_data.pop('broadcast_details', None)
    
    # Сохраняем исходное сообщение для дальнейших редактирований
    context.user_data['broadcast_msg_chat_id'] = update.callback_query.message.chat_id
    context.user_data['broadcast_msg_id'] = update.callback_query.message.message_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.ADMIN_BROADCAST_BACK)]])
    await safe_edit_or_reply_universal(update.callback_query.message, UIMessages.broadcast_intro_message(), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type=MenuTypes.ADMIN_BROADCAST)
    return BROADCAST_WAITING_TEXT


async def admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод контента для рассылки (ТОЛЬКО ТЕКСТ)"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    message = update.message
    
    # Разрешаем только текстовую рассылку
    if not message.text:
        chat_id = context.user_data.get('broadcast_msg_chat_id')
        msg_id = context.user_data.get('broadcast_msg_id')
        warn_text = f"{UIEmojis.ERROR} Для рассылки теперь разрешён только <b>текст</b>. Отправьте текстовое сообщение."
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=warn_text,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_BROADCAST
            )
        except Exception:
            await safe_send_message_with_photo(
                context.bot,
                chat_id=chat_id,
                text=warn_text,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_BROADCAST
            )
        return BROADCAST_WAITING_TEXT
    
    # Сохраняем текст и очищаем любые старые медиа
    context.user_data['broadcast_text'] = message.text
    context.user_data.pop('broadcast_media', None)
    preview_text = UIMessages.broadcast_preview_message(message.text)

    # Удаляем сообщение админа
    try:
        await message.delete()
    except Exception:
        pass
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Отправить", callback_data=CallbackData.ADMIN_BROADCAST_SEND)],
        [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.ADMIN_BROADCAST_BACK)]
    ])
    
    # Редактируем исходное сообщение на предпросмотр
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=preview_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения рассылки: {e}")
        # Fallback: отправляем новое сообщение
        await safe_send_message_with_photo(
            context.bot,
            chat_id=chat_id,
            text=preview_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
    return BROADCAST_CONFIRM


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка рассылки"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    from ...utils import safe_answer_callback_query
    await safe_answer_callback_query(update.callback_query)
    
    # Проверяем, есть ли текст для рассылки (только текстовая рассылка)
    text = context.user_data.get('broadcast_text')
    
    if not text:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=context.user_data.get('broadcast_msg_chat_id'),
            message_id=context.user_data.get('broadcast_msg_id'),
            text=f"{UIEmojis.ERROR} Контент рассылки пуст.",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
        return ConversationHandler.END

    # Получаем список получателей и исключаем админов
    recipients = await get_all_user_ids()
    admin_set = set(str(a) for a in ADMIN_IDS)
    recipients = [uid for uid in recipients if str(uid) not in admin_set]
    total = len(recipients)
    sent = 0
    failed = 0
    # собираем подробную статистику
    details = []  # [{'user_id': str, 'status': 'ok'|'failed'}]
    batch = 40

    # Готовим исходное сообщение к показу прогресса
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"<b>Отправка рассылки</b>\n\nОтправлено: 0/{total}. Ошибок: 0.",
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
    except Exception:
        pass
    
    for i in range(0, total, batch):
        chunk = recipients[i:i+batch]
        for user_id in chunk:
            try:
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button()
                
                reply_markup = None
                if webapp_button:
                    reply_markup = InlineKeyboardMarkup([[webapp_button]])
                
                # Отправляем текстовое сообщение с кнопкой
                await context.bot.send_message(
                    chat_id=int(user_id), 
                    text=text, 
                    parse_mode="HTML", 
                    disable_web_page_preview=True,
                    reply_markup=reply_markup
                )
                
                sent += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'ok'})
                    
            except telegram.error.Forbidden:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            except telegram.error.BadRequest as e:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(int(getattr(e, 'retry_after', 1)))
                try:
                    # Повторная попытка отправки текста
                    await context.bot.send_message(
                        chat_id=int(user_id), 
                        text=text, 
                        parse_mode="HTML", 
                        disable_web_page_preview=True
                    )
                    sent += 1
                    if len(details) < 10000:
                        details.append({'user_id': str(user_id), 'status': 'ok'})
                except Exception:
                    failed += 1
                    if len(details) < 10000:
                        details.append({'user_id': str(user_id), 'status': 'failed'})
            except Exception:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            # лёгкая задержка между сообщениями
            await asyncio.sleep(0.05)
        # пауза между батчами
        await asyncio.sleep(1.0)
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=f"<b>Отправка рассылки</b>\n\nОтправлено: {sent}/{total}. Ошибок: {failed}.",
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_BROADCAST
            )
        except Exception:
            pass

    # сохраняем детали в user_data для кнопок
    context.user_data['broadcast_details'] = details
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Экспорт CSV", callback_data=CallbackData.ADMIN_BROADCAST_EXPORT)],
        [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.ADMIN_BROADCAST_BACK)]
    ])
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования финального сообщения рассылки: {e}")
        await safe_send_message_with_photo(
            context.bot,
            chat_id=chat_id,
            text=f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_BROADCAST
        )
    return ConversationHandler.END


async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
    from ...utils import safe_answer_callback_query
    await safe_answer_callback_query(update.callback_query)
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    
    # Очищаем состояние рассылки
    context.user_data.pop('broadcast_text', None)
    context.user_data.pop('broadcast_media', None)
    context.user_data.pop('broadcast_msg_chat_id', None)
    context.user_data.pop('broadcast_msg_id', None)
    context.user_data.pop('broadcast_details', None)
    
    # Переходим к админ меню через навигационную систему
    # navigate_to_state уже вызовет admin_menu через MenuHandlers, поэтому не нужно вызывать его напрямую
    if not nav_system:
        logger.error("admin_broadcast_cancel: nav_system is None (navigation system is required)")
        # В админке можно просто завершить без вывода меню, чтобы не ломать стек
        return ConversationHandler.END

    await nav_system.navigate_to_state(update, context, NavStates.ADMIN_MENU)
    return ConversationHandler.END


async def admin_broadcast_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт отчета рассылки"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    from ...utils import safe_answer_callback_query
    await safe_answer_callback_query(update.callback_query)
    details = context.user_data.get('broadcast_details') or []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "status"])
    for row in details:
        writer.writerow([row.get('user_id',''), row.get('status','')])
    output.seek(0)
    bio = io.BytesIO(output.read().encode('utf-8'))
    bio.name = 'broadcast_report.csv'
    await context.bot.send_document(chat_id=update.effective_user.id, document=bio, caption="Отчёт рассылки")

