"""
Обработчик создания платежей
"""

import logging
import datetime
import uuid
import aiosqlite
import traceback
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from yookassa import Payment

from ...utils import UIEmojis, safe_edit_or_reply, safe_edit_or_reply_universal
from ...navigation import NavStates, NavigationBuilder
from ...db import get_pending_payment, add_payment, PAYMENTS_DB_PATH

logger = logging.getLogger(__name__)

# Глобальный словарь для хранения сообщений о продлении
extension_messages = {}

def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'nav_system': getattr(bot_module, 'nav_system', None),
            'notify_admin': getattr(bot_module, 'notify_admin', None),
            'extension_messages': getattr(bot_module, 'extension_messages', {}),
            'admin_ids': getattr(bot_module, 'ADMIN_IDS', []),
        }
    except (ImportError, AttributeError):
        return {
            'nav_system': None,
            'notify_admin': None,
            'extension_messages': {},
            'admin_ids': [],
        }

async def handle_payment(update, context, price, period):
    """Обработчик создания платежа"""
    logger.info(f"handle_payment вызвана: price={price}, period={period}")
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    notify_admin = globals_dict['notify_admin']
    extension_messages = globals_dict['extension_messages']
    admin_ids = globals_dict['admin_ids']
    
    # Проверяем, что price и period не None
    if price is None or period is None:
        logger.error(f"❌ ОШИБКА: price={price}, period={period} - не могут быть None")
        await safe_edit_or_reply(update.message, "❌ Ошибка: не выбран тариф. Попробуйте снова.")
        return
    
    user = update.effective_user if hasattr(update, 'effective_user') else update.from_user
    user_id = str(user.id)
    logger.info(f"handle_payment: user_id={user_id}")
    
    # Получаем правильный объект сообщения
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    logger.info(f"handle_payment: message={message}, message_id={getattr(message, 'message_id', 'None')}")
    
    # Проверяем доступность серверов ПЕРЕД созданием платежа (только для новых покупок, не для продления)
    # Подписка включает все доступные серверы автоматически
    if not period.startswith('extend_'):
        try:
            from ...bot import new_client_manager, SERVERS_BY_LOCATION
            
            # Проверяем доступность серверов (проверяем все серверы, подписка включает все доступные)
            all_health = new_client_manager.check_all_servers_health(force_check=False)
            available_servers = 0
            
            # Проверяем все локации - подписка включает все доступные серверы
            for location, servers in SERVERS_BY_LOCATION.items():
                for server in servers:
                    if server.get("host") and server.get("login") and server.get("password"):
                        if all_health.get(server["name"], False):
                            available_servers += 1
            
            if available_servers == 0:
                logger.warning(f"Нет доступных серверов для создания подписки. user_id={user_id}")
                error_message = (
                    f"{UIEmojis.ERROR} <b>Серверы временно недоступны</b>\n\n"
                    f"Все серверы временно недоступны.\n\n"
                    f"Пожалуйста, попробуйте позже."
                )
                keyboard = InlineKeyboardMarkup([
                    [NavigationBuilder.create_back_button()]
                ])
                await safe_edit_or_reply_universal(message, error_message, reply_markup=keyboard, parse_mode="HTML", menu_type='buy_menu')
                return
        except Exception as e:
            logger.error(f"Ошибка проверки доступности серверов: {e}")
            # Продолжаем, но логируем ошибку
    
    # Добавляем PAYMENT в стек навигации (если еще не добавлено)
    # Это нужно для правильной работы кнопки "назад"
    from ...navigation import nav_manager
    current_stack = nav_manager.get_stack(context)
    if NavStates.PAYMENT not in current_stack:
        nav_manager.push_state(context, NavStates.PAYMENT)
    
    try:
        # Проверка на существующий pending-платёж по user_id и period
        payment_info = await get_pending_payment(user_id, period)
        logger.info(f"Проверка существующих платежей: user_id={user_id}, period={period}, found={payment_info is not None}")
        
        # Проверяем pending платежи пользователя и отменяем только неоплаченные
        logger.info(f"HANDLE_PAYMENT: Подключаемся к базе данных по пути: {PAYMENTS_DB_PATH}")
        async with aiosqlite.connect(PAYMENTS_DB_PATH) as db:
            # Проверяем существование таблицы payments
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'") as cursor:
                table_exists = await cursor.fetchone()
                logger.info(f"HANDLE_PAYMENT: Таблица payments существует: {table_exists is not None}")
                if not table_exists:
                    logger.error("HANDLE_PAYMENT: Таблица payments не найдена! Создаем её...")
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS payments (
                            user_id TEXT,
                            payment_id TEXT PRIMARY KEY,
                            status TEXT,
                            created_at INTEGER,
                            meta TEXT,
                            activated INTEGER DEFAULT 0
                        )
                    ''')
                    await db.commit()
                    logger.info("HANDLE_PAYMENT: Таблица payments создана")
            
            # Получаем все pending платежи пользователя
            async with db.execute('''
                SELECT payment_id, status FROM payments WHERE user_id = ? AND status = ?
            ''', (user_id, 'pending')) as cursor:
                pending_payments = await cursor.fetchall()
                logger.info(f"Найдено {len(pending_payments)} pending платежей для user_id={user_id}")
            
            # Просто помечаем все pending платежи как отмененные в БД
            # YooKassa автоматически отменит их через 15 минут
            canceled_count = len(pending_payments)
            if canceled_count > 0:
                logger.info(f"Помечаем {canceled_count} pending платежей как отмененные (YooKassa отменит их автоматически через 15 минут)")
            
            # Обновляем статус в БД для отмененных платежей
            if canceled_count > 0:
                await db.execute('UPDATE payments SET status = ? WHERE user_id = ? AND status = ?', ('canceled', user_id, 'pending'))
                await db.commit()
                logger.info(f"Отменено {canceled_count} pending платежей для user_id={user_id}")
        
        # 2. Создаём новый платёж
        now = int(datetime.datetime.now().timestamp())
        subscription_id = str(uuid.uuid4())
        unique_email = f'{user_id}_{subscription_id}'
        
        # Обычная покупка за деньги (1 подписка = 1 устройство)
        try:
            devices = 1
            payment = Payment.create({
                "amount": {"value": price, "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": f"https://t.me/{user.id}"},
                "capture": True,
                "description": f"VPN {period} для {user_id}",
                "metadata": {
                    "user_id": user_id, 
                    "type": period,
                    "device_limit": devices,
                    "message_id": message.message_id if message else None,
                    "unique_email": unique_email,
                    "price": price,
                },
                "receipt": {
                    "customer": {"email": f"{user_id}@vpn-x3.ru"},
                    "items": [{
                        "description": f"VPN {period} для {user_id}",
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1
                    }]
                }
            })
            payment_id = payment.id
        except Exception as e:
            logger.exception(f"Ошибка создания платежа для user_id={user_id}")
            # Уведомляем админа о критической ошибке создания платежа
            if notify_admin:
                await notify_admin(context.bot, admin_ids, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать платеж:\nПользователь: {user_id}\nПериод: {period}\nЦена: {price}\nОшибка: {str(e)}")
            await safe_edit_or_reply(message, 'Ошибка при создании платежа. Попробуйте позже.')
            return
        
        # Показываем ссылку на оплату
        try:
            # Определяем переменные для текста
            if period.startswith('extend_') or period.startswith('extend_sub_'):
                # Для продления убираем префиксы extend_ или extend_sub_
                actual_period = period.replace('extend_', '').replace('extend_sub_', '')
                period_text = "1 месяц" if actual_period == "month" else "3 месяца"
            else:
                # Для обычной покупки
                period_text = "1 месяц" if period == "month" else "3 месяца"
            payment_url = payment.confirmation.confirmation_url
            
            # message_id уже сохранен в мета-данных платежа в БД
            logger.info(f"Создан платеж {payment.id} с message_id {message.message_id}")
            
            # Для продления сохраняем информацию о сообщении для последующего редактирования
            if period.startswith('extend_') or period.startswith('extend_sub_'):
                extension_messages[payment.id] = (message.chat_id, message.message_id)
                logger.info(f"Сохранена информация о сообщении продления: payment_id={payment.id}, chat_id={message.chat_id}, message_id={message.message_id}")
            
            # Редактируем сообщение с меню выбора периода на информацию об оплате
            try:
                # Получаем текст сообщения об оплате
                payment_text = (
                    f"<b>Оплата подписки на {period_text}</b>\n\n"
                    f"Сумма: <b>{price}₽</b>\n"
                    f"Период: <b>{period_text}</b>\n\n"
                    f"<a href='{payment_url}'>Перейти к оплате</a>\n\n"
                    f"{UIEmojis.WARNING} <i>Ссылка действительна 15 минут</i>\n\n"
                    f"После оплаты подписка будет активирована автоматически и включит все доступные серверы."
                )
                
                # Создаем кнопку "Назад"
                keyboard = InlineKeyboardMarkup([
                    [NavigationBuilder.create_back_button()]
                ])
                
                await safe_edit_or_reply_universal(message, payment_text, reply_markup=keyboard, parse_mode="HTML", menu_type='payment')
                logger.info(f"Отредактировано сообщение с меню выбора периода на информацию об оплате: message_id={message.message_id}")
            except Exception as e:
                logger.error(f"Не удалось отредактировать сообщение с меню выбора периода: {e}")
                # Если не удалось отредактировать, удаляем и отправляем новое
                try:
                    await message.delete()
                    logger.info(f"Удалено сообщение с меню выбора периода: message_id={message.message_id}")
                except Exception as delete_error:
                    logger.error(f"Не удалось удалить сообщение с меню выбора периода: {delete_error}")
            
            # Подготавливаем метаданные платежа
            payment_meta = {"price": price, "type": period, "unique_email": unique_email, "message_id": message.message_id}
            
            # Добавляем информацию о продлении подписки, если это продление
            if period.startswith('extend_sub_') and context.user_data.get('extension_subscription_id'):
                payment_meta['extension_subscription_id'] = context.user_data['extension_subscription_id']
                logger.info(f"Добавлена информация о продлении подписки в метаданные: {context.user_data['extension_subscription_id']}")
            
            await add_payment(user_id, payment.id, 'pending', now, payment_meta)
        except Exception as e:
            logger.exception(f"Ошибка отправки сообщения об оплате для user_id={user_id}")
            await safe_edit_or_reply(message, 'Ошибка при отправке информации об оплате.')
    except Exception as e:
        logger.exception(f"Ошибка в handle_payment для user_id={user_id}")
        await safe_edit_or_reply(message, 'Произошла внутренняя ошибка. Администратор уже уведомлён.')
        if notify_admin:
            await notify_admin(context.bot, admin_ids, f"Ошибка в handle_payment для user_id={user_id}: {e}\n{traceback.format_exc()}")

