"""
Быстрый поиск пользователей через Inline Query
Использование: @YourBot 123456789
"""
import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

from ...db.subscribers_db import get_user_by_id, get_all_subscriptions_by_user
from ...utils import UIEmojis, UIStyles

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
        }


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline query для быстрого поиска пользователей"""
    query = update.inline_query.query.strip()
    
    logger.info(f"Inline query received: '{query}' from user {update.inline_query.from_user.id}")
    
    # Проверяем права доступа
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.inline_query.from_user.id not in ADMIN_IDS:
        # Для не-админов показываем пустой результат
        logger.warning(f"Non-admin user {update.inline_query.from_user.id} tried to use inline query")
        await update.inline_query.answer([])
        return
    
    # Если запрос пустой, показываем подсказку
    if not query:
        results = [
            InlineQueryResultArticle(
                id="help",
                title="🔍 Быстрый поиск пользователей",
                description="Введите Telegram ID пользователя",
                input_message_content=InputTextMessageContent(
                    message_text="🔍 <b>Быстрый поиск пользователей</b>\n\n"
                               "Использование: <code>@YourBot 123456789</code>\n\n"
                               "Введите ID пользователя для поиска."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=1)
        return
    
    # Проверяем, что запрос - это число (ID пользователя)
    if not query.isdigit():
        results = [
            InlineQueryResultArticle(
                id="error",
                title="❌ Ошибка",
                description="ID должен быть числом",
                input_message_content=InputTextMessageContent(
                    message_text="❌ <b>Ошибка</b>\n\nID должен быть числом.\n\nПример: <code>123456789</code>"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=1)
        return
    
    user_id = query
    
    try:
        # Ищем пользователя
        user = await get_user_by_id(user_id)
        
        if not user:
            # Пользователь не найден
            results = [
                InlineQueryResultArticle(
                    id=f"not_found_{user_id}",
                    title=f"❌ Пользователь не найден",
                    description=f"ID: {user_id}",
                    input_message_content=InputTextMessageContent(
                        message_text=f"❌ <b>Пользователь не найден</b>\n\n"
                                   f"Пользователь с ID <code>{user_id}</code> не найден в базе данных."
                    )
                )
            ]
            await update.inline_query.answer(results, cache_time=1)
            return
        
        # Получаем подписки пользователя
        subscriptions = await get_all_subscriptions_by_user(user_id)
        active_subs = [s for s in subscriptions if s.get('status') == 'active']
        expired_subs = [s for s in subscriptions if s.get('status') == 'expired']
        trial_subs = [s for s in subscriptions if s.get('status') == 'trial']
        
        # Формируем информацию о пользователе
        username = user.get('username', 'Не указан')
        first_name = user.get('first_name', 'Не указано')
        last_name = user.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() if last_name else first_name
        
        # Статистика подписок
        total_subs = len(subscriptions)
        active_count = len(active_subs)
        expired_count = len(expired_subs)
        trial_count = len(trial_subs)
        
        # Формируем текст сообщения
        message_text = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Имя:</b> {full_name}\n"
            f"<b>Username:</b> @{username if username != 'Не указан' else 'нет'}\n\n"
            f"📊 <b>Статистика подписок:</b>\n"
            f"• Всего: {total_subs}\n"
            f"• Активных: {active_count}\n"
            f"• Истекших: {expired_count}\n"
            f"• Пробных: {trial_count}\n\n"
        )
        
        # Добавляем информацию об активных подписках
        if active_subs:
            message_text += f"✅ <b>Активные подписки:</b>\n"
            for sub in active_subs[:5]:  # Показываем максимум 5
                sub_name = sub.get('name', 'Без названия')
                expires_at = sub.get('expires_at', 0)
                if expires_at:
                    from datetime import datetime
                    expiry_date = datetime.fromtimestamp(expires_at).strftime('%d.%m.%Y %H:%M')
                    message_text += f"• {sub_name} (до {expiry_date})\n"
                else:
                    message_text += f"• {sub_name}\n"
            if len(active_subs) > 5:
                message_text += f"... и еще {len(active_subs) - 5}\n"
            message_text += "\n"
        
        # Добавляем кнопку для детальной информации
        message_text += "💡 Используйте команду /admin_user для детальной информации"
        
        results = [
            InlineQueryResultArticle(
                id=f"user_{user_id}",
                title=f"👤 {full_name} (@{username if username != 'Не указан' else 'нет'})",
                description=f"ID: {user_id} | Подписок: {total_subs} (Активных: {active_count})",
                input_message_content=InputTextMessageContent(
                    message_text=message_text,
                    parse_mode="HTML"
                )
            )
        ]
        
        await update.inline_query.answer(results, cache_time=60)
        
    except Exception as e:
        logger.error(f"Ошибка в inline_query_handler: {e}", exc_info=True)
        results = [
            InlineQueryResultArticle(
                id="error",
                title="❌ Ошибка при поиске",
                description=str(e)[:50],
                input_message_content=InputTextMessageContent(
                    message_text=f"❌ <b>Ошибка при поиске</b>\n\n{str(e)}"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=1)

