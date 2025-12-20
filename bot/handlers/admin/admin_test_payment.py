"""
Админ-команда для тестирования подтверждения платежей
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import UIEmojis, UIStyles, safe_edit_or_reply_universal
from ...navigation import NavigationBuilder, MenuTypes
from ...db import get_pending_payment, get_all_pending_payments, get_payment_by_id

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        elif '__main__' in sys.modules:
            # Если запущено через python -m bot.bot, модуль может быть в __main__
            bot_module = sys.modules['__main__']
        else:
            # Если модуль еще не загружен, импортируем его
            bot_module = importlib.import_module('bot.bot')
        
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'app': getattr(bot_module, 'app', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'ADMIN_IDS': [],
            'app': None,
        }


async def admin_test_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда для тестирования подтверждения платежа
    
    Использование:
    /admin_test_payment - показать список pending платежей
    /admin_test_payment <payment_id> - подтвердить конкретный платеж
    """
    user = update.effective_user
    user_id_int = user.id  # int для проверки доступа
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    app = globals_dict['app']
    
    # Проверяем, что пользователь - админ (ADMIN_IDS содержит int)
    if user_id_int not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    if not app:
        await update.message.reply_text("Приложение бота не доступно.")
        return
    
    # Проверяем, передан ли payment_id как аргумент
    if context.args and len(context.args) > 0:
        payment_id = context.args[0]
        try:
            # Подтверждаем платеж напрямую
            from ...handlers.webhooks.payment_processors import process_payment_webhook
            await process_payment_webhook(app, payment_id, 'succeeded')
            
            await update.message.reply_text(
                f"{UIEmojis.SUCCESS} <b>Платеж {payment_id} подтвержден!</b>\n\n"
                f"{UIStyles.description('Платеж обработан и подписка создана.')}",
                parse_mode="HTML"
            )
            logger.info(f"Админ {user_id_int} подтвердил платеж {payment_id} через команду")
            return
        except Exception as e:
            logger.error(f"Ошибка при подтверждении платежа {payment_id}: {e}")
            await update.message.reply_text(f"Ошибка: {e}")
            return
    
    # Получаем список pending платежей
    try:
        pending_payments = await get_all_pending_payments()
        
        if not pending_payments:
            message = (
                f"{UIStyles.header('Тестирование платежей')}\n\n"
                f"{UIEmojis.WARNING} Нет pending платежей для подтверждения.\n\n"
                f"{UIStyles.description('Создайте платеж через бота, затем используйте эту команду для подтверждения.')}"
            )
            await safe_edit_or_reply_universal(
                update.message,
                message,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
            return
        
        # Формируем список платежей
        message = f"{UIStyles.header('Pending платежи для тестирования')}\n\n"
        keyboard_buttons = []
        
        for payment in pending_payments[:10]:  # Показываем максимум 10 платежей
            payment_id = payment['payment_id']
            payment_user_id = payment['user_id']
            created_at = payment.get('created_at', 0)
            
            # Форматируем дату создания
            import datetime
            if created_at:
                created_date = datetime.datetime.fromtimestamp(created_at).strftime('%d.%m.%Y %H:%M')
            else:
                created_date = "—"
            
            # Получаем метаданные
            meta = payment.get('meta', {})
            if isinstance(meta, str):
                import json
                try:
                    meta = json.loads(meta)
                except:
                    meta = {}
            
            period = meta.get('type', 'unknown')
            price = meta.get('price', '0')
            
            message += (
                f"<b>Платеж:</b> <code>{payment_id[:20]}...</code>\n"
                f"<b>Пользователь:</b> {payment_user_id}\n"
                f"<b>Период:</b> {period}\n"
                f"<b>Цена:</b> {price}₽\n"
                f"<b>Создан:</b> {created_date}\n\n"
            )
            
            # Кнопка для подтверждения
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"✓ Подтвердить {payment_id[:8]}...",
                    callback_data=f"test_confirm_payment:{payment_id}"
                )
            ])
        
        if len(pending_payments) > 10:
            message += f"\n{UIEmojis.WARNING} Показаны первые 10 из {len(pending_payments)} платежей\n"
        
        keyboard_buttons.append([NavigationBuilder.create_back_button()])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await safe_edit_or_reply_universal(
            update.message,
            message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_MENU
        )
        
    except Exception as e:
        logger.error(f"Ошибка в admin_test_payment: {e}")
        await update.message.reply_text(f"Ошибка: {e}")


async def test_confirm_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения платежа для тестирования"""
    query = update.callback_query
    user = query.from_user
    user_id_int = user.id  # int для проверки доступа
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    app = globals_dict['app']
    
    # Проверяем, что пользователь - админ (ADMIN_IDS содержит int)
    if user_id_int not in ADMIN_IDS:
        await query.answer("У вас нет доступа к этой команде.", show_alert=True)
        return
    
    if not app:
        await query.answer("Приложение бота не доступно.", show_alert=True)
        return
    
    # Извлекаем payment_id из callback_data
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await query.answer("Ошибка: неверный формат данных.", show_alert=True)
        return
    
    payment_id = parts[1]
    
    try:
        # Получаем информацию о платеже
        payment_info = await get_payment_by_id(payment_id)
        if not payment_info:
            await query.answer("Платеж не найден.", show_alert=True)
            return
        
        # Импортируем функцию обработки платежа
        from ...handlers.webhooks.payment_processors import process_payment_webhook
        
        # Симулируем успешный платеж
        await query.answer("Подтверждаю платеж...", show_alert=False)
        
        # Вызываем обработчик успешного платежа
        await process_payment_webhook(app, payment_id, 'succeeded')
        
        # Уведомляем админа об успехе
        from ...navigation import NavigationBuilder
        message = (
            f"{UIStyles.header('Платеж подтвержден')}\n\n"
            f"{UIEmojis.SUCCESS} <b>Платеж успешно подтвержден!</b>\n\n"
            f"<b>Payment ID:</b> <code>{payment_id}</code>\n"
            f"<b>Пользователь:</b> {payment_info['user_id']}\n\n"
            f"{UIStyles.description('Платеж обработан и подписка создана.')}"
        )
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(
            query.message,
            message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_MENU
        )
        
        logger.info(f"Админ {user_id_int} подтвердил тестовый платеж {payment_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при подтверждении платежа {payment_id}: {e}")
        await query.answer(f"Ошибка: {e}", show_alert=True)

