"""
Обработчик команды /start
"""
import logging
import aiosqlite
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes

from ...utils import (
    UIStyles, UIButtons, UIMessages, get_site_urls,
    safe_edit_or_reply_universal, check_private_chat
)
from ...navigation import MenuTypes
from ...db import register_simple_user
from ...db.users_db import (
    get_or_create_subscriber,
    link_telegram_consume_state, get_user_by_id,
    link_telegram_to_account,
    get_user_by_telegram_id_v2, create_telegram_link, update_user_telegram_id,
    generate_user_id,
    reconcile_users_telegram_id_with_link,
)
from ...db.subscriptions_db import (
    get_all_active_subscriptions_by_user, create_subscription,
)
import time

logger = logging.getLogger(__name__)

def get_globals():
    """Получает сервисы из AppContext."""
    from ...app_context import get_ctx
    ctx = get_ctx()
    return {
        'server_manager': ctx.server_manager,
        'subscription_manager': ctx.subscription_manager,
        'WEBAPP_URL': ctx.webapp_url,
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not await check_private_chat(update):
        return
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return

    # Обработка привязки Telegram (веб-аккаунт): /start link_<state>
    args = context.args or []
    if args and args[0].startswith("link_"):
        state = args[0][5:]
        tg_user_id = str(update.effective_user.id)
        web_user_id = await link_telegram_consume_state(state)
        if not web_user_id:
            await message.reply_text("Ссылка недействительна или истекла. Зайдите на сайт и нажмите «Привязать Telegram» снова.")
            return
        existing_tg_user = await get_user_by_telegram_id_v2(tg_user_id, use_fallback=True)
        if existing_tg_user and not existing_tg_user.get("is_web"):
            # TG уже занят (TG-first пользователь) - предлагаем привязать его к текущему веб-аккаунту
            # Сохраняем web_user_id в контексте для callback handler
            context.user_data[f"link_web_user_id_{state}"] = web_user_id
            text = (
                "Этот Telegram уже привязан к другому аккаунту.\n\n"
                "Отвязать его и привязать к текущему веб-аккаунту?"
            )
            buttons = [
                [
                    InlineKeyboardButton("Да", callback_data=f"link_confirm_yes:{state}"),
                    InlineKeyboardButton("Нет", callback_data=f"link_confirm_no:{state}")
                ]
            ]
            keyboard = InlineKeyboardMarkup(buttons)
            await message.reply_text(text, reply_markup=keyboard)
            return
        web_user = await get_user_by_id(web_user_id)
        if not web_user:
            await message.reply_text("Ошибка: веб-аккаунт не найден.")
            return
        if web_user.get("telegram_id"):
            await message.reply_text("Аккаунт уже привязан к Telegram.")
            return

        # Единая привязка: связь TG ↔ веб-аккаунт; при перепривязке — merge и удаление старого аккаунта
        result = await link_telegram_to_account(tg_user_id, web_user_id)
        logger.info(
            f"Привязан Telegram {tg_user_id} к веб-аккаунту {web_user_id}"
            + (f" (объединён с бывшим аккаунтом {result['previous_user_id']})" if result.get("merged") else "")
        )
        text = (
            "Аккаунт привязан.\n\n"
            "Теперь вы можете:\n"
            "• Заходить в Mini App без пароля\n"
            "• Получать уведомления о подписках в этом чате"
        )
        buttons = []
        webapp_url, site_url = get_site_urls()
        if webapp_url:
            buttons.append([InlineKeyboardButton("Открыть Mini App", web_app=WebAppInfo(url=webapp_url))])
        if site_url:
            buttons.append([InlineKeyboardButton("Вернуться на сайт", url=site_url)])
        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        await message.reply_text(text, reply_markup=keyboard)
        return
    
    globals_dict = get_globals()
    server_manager = globals_dict.get('server_manager')
    
    telegram_id = str(update.effective_user.id)
    # TG-first: ищем по telegram_id; если нет — создаём аккаунт с сгенерированным user_id (не telegram_id)
    existing_user = await get_user_by_telegram_id_v2(telegram_id, use_fallback=True)
    if existing_user:
        user_id = existing_user["user_id"]
        was_known_user = True
    else:
        user_id = generate_user_id()
        was_known_user = False
        try:
            await register_simple_user(user_id)
            await create_telegram_link(telegram_id, user_id)
            await update_user_telegram_id(user_id, telegram_id)
        except aiosqlite.IntegrityError:
            logger.warning(
                "Гонка TG-first /start (IntegrityError), telegram_id=%s — сверка с telegram_links",
                telegram_id,
            )
            await reconcile_users_telegram_id_with_link(telegram_id)
            existing_user = await get_user_by_telegram_id_v2(telegram_id, use_fallback=True)
            if not existing_user:
                raise
            user_id = existing_user["user_id"]
            was_known_user = True

    # Теперь, когда все проверки выполнены и пользователь зарегистрирован
    trial_created = False
    try:
        
        # Если пользователь новый (не был в БД) - создаем пробную подписку на 5 дней
        if not was_known_user:
            try:
                # Проверяем, нет ли уже активных подписок (на всякий случай)
                existing_subs = await get_all_active_subscriptions_by_user(user_id)
                now = int(time.time())
                # Фильтруем только действительно активные (используем единую функцию)
                from ...db.subscriptions_db import is_subscription_active
                active_subs = [sub for sub in existing_subs if is_subscription_active(sub)]
                
                # Создаем пробную подписку только если у нового пользователя нет активных подписок
                if len(active_subs) == 0:
                    logger.info(f"Создание пробной подписки для нового пользователя: {user_id}")
                    subscriber_id = await get_or_create_subscriber(user_id)
                    
                    # Получаем менеджеры для создания подписки и клиентов
                    globals_dict = get_globals()
                    subscription_manager = globals_dict.get('subscription_manager')
                    server_manager = globals_dict.get('server_manager')
                    
                    if not subscription_manager:
                        logger.error("SubscriptionManager не доступен, пробная подписка не создана")
                        return

                    # Создаем пробную подписку на 5 дней
                    now = int(time.time())
                    expires_at = now + (5 * 24 * 60 * 60)
                    sub_dict, token = await subscription_manager.create_subscription_for_user(
                        user_id=user_id,
                        period='month',  # Обычная подписка (можно продлить)
                        device_limit=1,
                        price=0.0,
                        expires_at=expires_at,
                        name="Пробная подписка"
                    )
                    subscription_id = sub_dict['id']
                    subscription_group_id = sub_dict.get('group_id')
                    logger.info(f" Пробная подписка создана для пользователя {user_id}: subscription_id={subscription_id}, token={token}")
                    
                    # Устанавливаем trial_created сразу после создания подписки в БД
                    trial_created = True
                    
                    # Создаем клиентов только на серверах группы подписки (как при обычной покупке)
                    if subscription_manager and server_manager:
                        try:
                            # Генерируем уникальный email для клиента
                            import uuid
                            unique_email = f"{user_id}_{subscription_id}"
                            
                            # Серверы только из группы подписки
                            from ...db.servers_db import get_servers_config
                            servers_in_db = await get_servers_config(
                                group_id=subscription_group_id,
                                only_active=True
                            ) if subscription_group_id is not None else await get_servers_config(only_active=True)
                            all_configured_servers = [s["name"] for s in servers_in_db] if servers_in_db else []
                            # Fallback: если в БД пусто, берём из менеджера по группе
                            if not all_configured_servers and subscription_group_id is not None:
                                group_servers = server_manager.get_servers_by_group(subscription_group_id)
                                all_configured_servers = [s["name"] for s in group_servers if s.get("x3") is not None]
                            if not all_configured_servers:
                                for server in server_manager.servers:
                                    if server.get("x3") is not None:
                                        all_configured_servers.append(server["name"])
                            
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
                                                logger.info(f" Клиент создан на сервере {server_name} для пробной подписки")
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
    
    # Формируем приветственное сообщение (передаем информацию о том, новый ли пользователь)
    welcome_text = UIMessages.welcome_message(is_new_user=not was_known_user)
    
    # Если создана пробная подписка - добавляем информацию о ней
    if trial_created:
        trial_info = (
            f"\n\n{UIStyles.success_message('Вам выдана пробная подписка!')}\n"
            f"{UIStyles.description('Откройте мини-приложение, чтобы управлять подписками, продлевать и смотреть инструкции в пару нажатий.')}"
        )
        welcome_text += trial_info
    
    # Создаем кнопки главного меню используя единый стиль
    buttons = UIButtons.main_menu_buttons()
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Отправляем меню с фото
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)

