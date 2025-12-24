"""
Обработчик команды /start
"""
import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, UIButtons, UIMessages,
    safe_edit_or_reply_universal, check_private_chat
)
from ...db import register_simple_user, is_known_user
from ...db.subscribers_db import get_all_active_subscriptions_by_user, get_or_create_subscriber, create_subscription
from ...navigation import NavStates, MenuTypes
import time

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
# Это временное решение до полного рефакторинга
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
        }
    except (ImportError, AttributeError):
        # Fallback если модуль еще не загружен
        return {'ADMIN_IDS': []}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    new_client_manager = globals_dict['new_client_manager']
    
    user_id = str(update.effective_user.id)
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return
    
    # Теперь, когда все проверки выполнены, регистрируем пользователя
    trial_created = False
    try:
        # Проверяем, новый ли пользователь (есть ли он уже в БД)
        was_known_user = await is_known_user(user_id)
        
        # Регистрируем пользователя
        await register_simple_user(user_id)
        
        # Если пользователь новый (не был в БД) - создаем пробную подписку на 5 дней
        if not was_known_user:
            try:
                # Проверяем, нет ли уже активных подписок (на всякий случай)
                existing_subs = await get_all_active_subscriptions_by_user(user_id)
                if len(existing_subs) == 0:
                    logger.info(f"Создание пробной подписки для нового пользователя: {user_id}")
                    subscriber_id = await get_or_create_subscriber(user_id)
                    now = int(time.time())
                    expires_at = now + (5 * 24 * 60 * 60)  # 5 дней
                    
                    subscription_id, token = await create_subscription(
                        subscriber_id=subscriber_id,
                        period='month',  # Обычная подписка (можно продлить)
                        device_limit=1,
                        price=0.0,  # Бесплатно
                        expires_at=expires_at,
                        name="Пробная подписка"
                    )
                    logger.info(f"✅ Пробная подписка создана в БД для пользователя {user_id}: subscription_id={subscription_id}, token={token}")
                    
                    # Устанавливаем trial_created сразу после создания подписки в БД
                    trial_created = True
                    
                    # Создаем клиентов на всех серверах для пробной подписки
                    globals_dict = get_globals()
                    subscription_manager = globals_dict.get('subscription_manager')
                    new_client_manager = globals_dict.get('new_client_manager')
                    
                    if subscription_manager and new_client_manager:
                        try:
                            # Генерируем уникальный email для клиента
                            import uuid
                            unique_email = f"{user_id}_{subscription_id}"
                            
                            # Получаем все серверы из конфигурации
                            all_configured_servers = []
                            for server in new_client_manager.servers:
                                server_name = server["name"]
                                if server.get("x3") is not None:
                                    all_configured_servers.append(server_name)
                            
                            if all_configured_servers:
                                logger.info(f"Создание клиентов на {len(all_configured_servers)} серверах для пробной подписки {subscription_id}")
                                
                                # Привязываем все серверы к подписке в БД
                                for server_name in all_configured_servers:
                                    try:
                                        await subscription_manager.attach_server_to_subscription(
                                            subscription_id=subscription_id,
                                            server_name=server_name,
                                            client_email=unique_email,
                                            client_id=None,
                                        )
                                        logger.info(f"Сервер {server_name} привязан к пробной подписке {subscription_id}")
                                    except Exception as attach_e:
                                        if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                                            logger.info(f"Сервер {server_name} уже привязан к подписке {subscription_id}")
                                        else:
                                            logger.error(f"Ошибка привязки сервера {server_name}: {attach_e}")
                                
                                # Создаем клиентов на всех серверах
                                successful_servers = []
                                failed_servers = []
                                for server_name in all_configured_servers:
                                    try:
                                        client_exists, client_created = await subscription_manager.ensure_client_on_server(
                                            subscription_id=subscription_id,
                                            server_name=server_name,
                                            client_email=unique_email,
                                            user_id=user_id,
                                            expires_at=expires_at,
                                            token=token,
                                            device_limit=1
                                        )
                                        
                                        if client_exists:
                                            successful_servers.append(server_name)
                                            if client_created:
                                                logger.info(f"✅ Клиент создан на сервере {server_name} для пробной подписки")
                                            else:
                                                logger.info(f"Клиент уже существует на сервере {server_name}")
                                        else:
                                            failed_servers.append(server_name)
                                            logger.warning(f"Не удалось создать клиента на сервере {server_name} (будет создан при синхронизации)")
                                    except Exception as e:
                                        logger.error(f"Ошибка создания клиента на сервере {server_name}: {e}")
                                        failed_servers.append(server_name)
                                
                                logger.info(f"Пробная подписка: успешно создано на {len(successful_servers)} серверах, ошибок: {len(failed_servers)}")
                            else:
                                logger.warning(f"Нет серверов в конфигурации для создания пробной подписки, но подписка создана в БД")
                        except Exception as client_e:
                            logger.error(f"Ошибка создания клиентов для пробной подписки {subscription_id}: {client_e}", exc_info=True)
                            logger.info(f"Пробная подписка создана в БД, но клиенты будут созданы при синхронизации")
                    else:
                        logger.warning(f"SubscriptionManager или NewClientManager недоступен, клиенты не созданы, но подписка создана в БД")
                else:
                    logger.info(f"Пользователь {user_id} новый, но уже есть {len(existing_subs)} подписок, пробная не создается")
            except Exception as trial_e:
                logger.error(f"Ошибка создания пробной подписки для {user_id}: {trial_e}", exc_info=True)
    except Exception as e:
        logger.error(f"Register user failed: {e}", exc_info=True)
    
    # Формируем приветственное сообщение
    welcome_text = UIMessages.welcome_message()
    
    # Если создана пробная подписка - добавляем информацию о ней
    if trial_created:
        trial_info = (
            f"\n\n{UIStyles.success_message('🎁 Вам выдана пробная подписка на 5 дней!')}\n"
            f"{UIStyles.description('Вы можете протестировать VPN прямо сейчас. Перейдите в «Мои подписки» для получения ключей.')}"
        )
        welcome_text += trial_info
    
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Добавляем главное меню в навигационный стек при старте
    globals_dict = get_globals()
    nav_system = globals_dict.get('nav_system')
    if nav_system:
        from ...navigation import nav_manager
        nav_manager.clear_stack(context)
        nav_manager.push_state(context, NavStates.MAIN_MENU)
    
    # Отправляем меню с фото
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)


async def edit_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирует существующее сообщение на главное меню"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Используем единый стиль для приветственного сообщения
    welcome_text = UIMessages.welcome_message()
    
    # Если это callback_query, используем safe_edit_message_with_photo для редактирования
    if update.callback_query:
        from ...utils.message_helpers import safe_edit_message_with_photo
        from ...utils import safe_answer_callback_query
        
        # Отвечаем на callback query
        await safe_answer_callback_query(update.callback_query)
        
        message = update.callback_query.message
        if message:
            logger.info(f"EDIT_MAIN_MENU: Редактируем сообщение {message.message_id} через callback_query")
            try:
                # Используем safe_edit_message_with_photo для редактирования медиа-сообщения
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    text=welcome_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type=MenuTypes.MAIN_MENU
                )
                logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано через callback_query")
                return
            except Exception as e:
                logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования через callback_query: {e}")
                # Fallback: используем обычный метод
                try:
                    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)
                    logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано через fallback")
                    return
                except Exception as e2:
                    logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования через fallback: {e2}")
                    # Последний fallback: отправляем новое сообщение
                    await start(update, context)
                    return
    
    # Если это обычное сообщение (не callback_query)
    message = update.message if update.message else None
    if message is None:
        logger.error("edit_main_menu: message is None")
        return
    
    logger.info(f"EDIT_MAIN_MENU: Редактируем сообщение {message.message_id}")
    try:
        # Отправляем меню с фото
        await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)
        logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано")
    except Exception as e:
        logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования сообщения: {e}")
        # Если не удалось отредактировать, отправляем новое
        logger.info("EDIT_MAIN_MENU: Вызываем start() как fallback")
        await start(update, context)

