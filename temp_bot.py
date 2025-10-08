# Webhook для получения уведомлений от YooKassa
def create_webhook_app(bot_app):
    """Создает Flask приложение для обработки webhook'ов от YooKassa"""
    app = Flask(__name__)
    
    @app.route('/webhook/yookassa', methods=['POST'])
    def yookassa_webhook():
        try:
            # Получаем данные от YooKassa
            data = request.get_json()
            logger.info(f"🔔 WEBHOOK: Получен webhook от YooKassa")
            logger.info(f"🔔 WEBHOOK: Данные: {data}")
            
            # Логируем заголовки для отладки
            logger.info(f"🔔 WEBHOOK: Заголовки: {dict(request.headers)}")
            
            if not data or 'object' not in data:
                logger.error("Неверный формат webhook от YooKassa")
                return jsonify({'status': 'error'}), 400
            
            payment_data = data['object']
            payment_id = payment_data.get('id')
            status = payment_data.get('status')
            
            if not payment_id or not status:
                logger.error("Отсутствуют обязательные поля в webhook")
                return jsonify({'status': 'error'}), 400
            
            logger.info(f"🔔 WEBHOOK: Обработка webhook: payment_id={payment_id}, status={status}")
            
            # Логируем все возможные статусы
            if status == 'succeeded':
                logger.info(f"🔔 WEBHOOK: ✅ Платеж успешен - активируем ключ")
            elif status == 'canceled':
                logger.info(f"🔔 WEBHOOK: ❌ Платеж отменен - показываем ошибку")
            elif status == 'refunded':
                logger.info(f"🔔 WEBHOOK: 💰 Платеж возвращен - показываем ошибку")
            else:
                logger.info(f"🔔 WEBHOOK: ⚠️ Неизвестный статус: {status}")
            
            # Периодическая очистка данных (каждый 100-й webhook)
            import random
            if random.randint(1, 100) == 1:
                # Запускаем очистку в отдельном потоке
                def cleanup_data():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        async def cleanup():
                            try:
                                # Очищаем просроченные pending платежи
                                expired_count = await cleanup_expired_pending_payments(minutes_old=20)
                                if expired_count > 0:
                                    logger.info(f"🧹 WEBHOOK: Удалено {expired_count} просроченных pending платежей")
                                
                                # Очищаем старые записи
                                old_count = await cleanup_old_payments(days_old=7)
                                if old_count > 0:
                                    logger.info(f"🧹 WEBHOOK: Удалено {old_count} старых записей платежей")
                            except Exception as e:
                                logger.error(f"Ошибка очистки данных в webhook: {e}")
                        
                        loop.run_until_complete(cleanup())
                    finally:
                        loop.close()
                
                cleanup_thread = threading.Thread(target=cleanup_data, daemon=True)
                cleanup_thread.start()
            
            # Запускаем обработку платежа в отдельном потоке
            def process_payment():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(process_payment_webhook(bot_app, payment_id, status))
                finally:
                    loop.close()
            
            thread = threading.Thread(target=process_payment)
            thread.start()
            
            return jsonify({'status': 'ok'})
            
        except Exception as e:
            logger.error(f"Ошибка в webhook: {e}")
            return jsonify({'status': 'error'}), 500
    
    return app


async def process_payment_webhook(bot_app, payment_id, status):
    """Обрабатывает платеж из webhook'а"""
    try:
        # Получаем информацию о платеже из базы данных
        payment_info = await get_payment_by_id(payment_id)
        if not payment_info:
            logger.warning(f"Платеж {payment_id} не найден в базе данных")
            return
        
        user_id = payment_info['user_id']
        meta = payment_info['meta'] if isinstance(payment_info['meta'], dict) else json.loads(payment_info['meta'])
        
        logger.info(f"Обработка webhook платежа: payment_id={payment_id}, user_id={user_id}, status={status}")
        
        # Обрабатываем платеж аналогично auto_activate_keys
        if status == 'succeeded':
            # Успешная оплата - обрабатываем как в auto_activate_keys
            await process_successful_payment(bot_app, payment_id, user_id, meta)
        elif status in ['canceled', 'refunded']:
            # Отмененная/возвращенная оплата
            await process_canceled_payment(bot_app, payment_id, user_id, meta, status)
        elif status not in ['pending']:
            # Любой другой неуспешный статус
            await process_failed_payment(bot_app, payment_id, user_id, meta, status)
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook платежа {payment_id}: {e}")


async def process_successful_payment(bot_app, payment_id, user_id, meta):
    """Обрабатывает успешный платеж"""
    try:
        period = meta.get('type', 'month')
        message_id = payment_message_ids.get(payment_id)
        
        # Проверяем, это продление или новая покупка
        is_extension = period.startswith('extend_')
        if is_extension:
            # Обработка продления (код из auto_activate_keys)
            await process_extension_payment(bot_app, payment_id, user_id, meta, message_id)
        else:
            # Обработка новой покупки (код из auto_activate_keys)
            await process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id)
            
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_extension_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает продление ключа"""
    try:
        period = meta.get('type', 'month')
        actual_period = period.replace('extend_', '')  # убираем префикс extend_
        days = 90 if actual_period == '3month' else 30
        extension_email = meta.get('extension_key_email')
        
        logger.info(f"Обработка продления ключа: email={extension_email}, period={actual_period}, days={days}")
        
        if not extension_email:
            logger.error(f"Не найден email ключа для продления в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Ищем сервер с ключом для продления
        try:
            xui, server_name = server_manager.find_client_on_any_server(extension_email)
            if not xui or not server_name:
                logger.error(f"Ключ для продления не найден: {extension_email}")
                await update_payment_status(payment_id, 'failed')
                
                # Отправляем сообщение пользователю об ошибке продления
                if message_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить ключ!</b>\n\n"
                        f"<b>Ключ:</b> {extension_email}\n"
                        f"<b>Причина:</b> Ключ не найден на сервере\n\n"
                        f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                    )
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Попробовать снова", callback_data="mykey")],
                        [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
                    ])
                    
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                return
                            
                            # Продлеваем ключ
                            response = xui.extendClient(extension_email, days)
                            if response and response.status_code == 200:
                                await update_payment_status(payment_id, 'succeeded')
                                await update_payment_activation(payment_id, 1)
                                
                                # Проверяем реферальную связь и выдаем баллы
                                try:
                                    referrer_id = await get_pending_referral(user_id)
                                    if referrer_id:
                        # Выдаем 1 балл рефереру
                                        await add_points(
                                            referrer_id, 
                                            1, 
                                            f"Реферал: {user_id} продлил VPN",
                                            payment_id
                                        )
                                        
                                        # Отмечаем награду как выданную
                                        await mark_referral_reward_given(referrer_id, user_id, payment_id)
                                        
                                        # Уведомляем реферера
                                        try:
                                            points_days = await get_config('points_days_per_point', '14')
                            await bot_app.bot.send_message(
                                                chat_id=referrer_id,
                                                text=(
                                                    f"Поздравляем!\n\n"
                                                    "Ваш друг продлил VPN по вашей реферальной ссылке!\n"
                                                    f"Вы получили 1 балл!\n"
                                                    f"1 балл = {points_days} дней VPN бесплатно!\n\n"
                                                    "Используйте баллы для покупки или продления VPN!"
                                                )
                                            )
                                        except:
                                            pass
                                except Exception as e:
                    logger.error(f"Ошибка выдачи реферальных баллов при продлении: {e}")
                                
                                # Отправляем уведомление о продлении
                                try:
                                    # Получаем новое время истечения
                                    clients_response = xui.list()
                                    expiry_str = "—"
                                    if clients_response.get('success', False):
                                        for inbound in clients_response.get('obj', []):
                                            settings = json.loads(inbound.get('settings', '{}'))
                                            for client in settings.get('clients', []):
                                                if client.get('email') == extension_email:
                                                    expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                                    expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                                                    break
                                    
                                    # Очищаем старые уведомления об истечении для продленного ключа
                                    if notification_manager:
                                        await notification_manager.clear_key_notifications(user_id, extension_email)
                                        await notification_manager.record_key_extension(user_id, extension_email)
                                    
                                    extension_message = UIMessages.key_extended_message(
                                        email=extension_email,
                                        server_name=server_name,
                                        days=days,
                                        expiry_str=expiry_str,
                                        period=actual_period
                                    )
                                    
                    if message_id:
                                            keyboard = InlineKeyboardMarkup([
                                                [InlineKeyboardButton("Мои ключи", callback_data="mykey")],
                                                [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
                                            ])
                        
                        await safe_edit_message_with_photo(
                            bot_app.bot,
                            chat_id=int(user_id),
                                                message_id=message_id,
                                                text=extension_message,
                            reply_markup=keyboard,
                                                parse_mode="HTML",
                            menu_type='extend_key'
                                            )
                                            logger.info(f"Отредактировано сообщение о продлении ключа {extension_email} пользователю {user_id}")
                        
                        # Удаляем message_id из отслеживания
                        payment_message_ids.pop(payment_id, None)
                    else:
                                            # Fallback: отправляем новое сообщение
                        await safe_send_message_with_photo(
                            bot_app,
                            chat_id=int(user_id),
                                                    text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                                            )
                                            logger.info(f"Отправлено новое сообщение о продлении ключа {extension_email} пользователю {user_id}")
                                    
                                except Exception as e:
                                    logger.error(f"Ошибка отправки уведомления о продлении: {e}")
                            else:
                logger.error(f"Ошибка продления ключа {extension_email}: {response}")
                                await update_payment_status(payment_id, 'failed')
                                
                        except Exception as e:
                            logger.error(f"Ошибка при продлении ключа {extension_email}: {e}")
                            await update_payment_status(payment_id, 'failed')
                        
    except Exception as e:
        logger.error(f"Ошибка обработки продления ключа {payment_id}: {e}")


async def process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает новую покупку"""
    try:
        period = meta.get('type', 'month')
                    days = 90 if period == '3month' else 30
        unique_email = meta.get('unique_email')
        selected_location = meta.get('selected_location', 'auto')
        
        logger.info(f"Обработка новой покупки: period={period}, days={days}, email={unique_email}")
        
        if not unique_email:
            logger.error(f"Не найден unique_email в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
                    
                    # Создание ключа
                    try:
                        if selected_location == "auto":
                            # Для автовыбора выбираем лучшую локацию
                            xui, server_name = new_client_manager.get_best_location_server()
                        else:
                            xui, server_name = new_client_manager.get_server_by_user_choice(selected_location, "auto")
            
                        response = xui.addClient(day=days, tg_id=user_id, user_email=unique_email, timeout=15)
                        
                        if response.status_code == 200:
                            await update_payment_status(payment_id, 'succeeded')
                            await update_payment_activation(payment_id, 1)
                            
                            # Проверяем реферальную связь и выдаем баллы
                            try:
                                referrer_id = await get_pending_referral(user_id)
                                if referrer_id:
                        # Выдаем 1 балл рефереру
                                    await add_points(
                                        referrer_id, 
                                        1, 
                                        f"Реферал: {user_id} купил VPN",
                                        payment_id
                                    )
                                    
                                    # Отмечаем награду как выданную
                                    await mark_referral_reward_given(referrer_id, user_id, payment_id)
                                    
                                    # Уведомляем реферера
                                    try:
                                        points_days = await get_config('points_days_per_point', '14')
                            await bot_app.bot.send_message(
                                            chat_id=referrer_id,
                                            text=(
                                                f"Поздравляем!\n\n"
                                                "Ваш друг купил VPN по вашей реферальной ссылке!\n"
                                                f"Вы получили 1 балл!\n"
                                                f"1 балл = {points_days} дней VPN бесплатно!\n\n"
                                                "Используйте баллы для покупки или продления VPN!"
                                            )
                                        )
                                    except:
                                        pass
                            except Exception as e:
                    logger.error(f"Ошибка выдачи реферальных баллов при покупке: {e}")
                            
                # Отправка ключа пользователю
                            try:
                    # Получаем реальное время истечения из XUI API
                                clients_response = xui.list()
                    expiry_str = "—"
                    expiry_timestamp = 0
                    
                                if clients_response.get('success', False):
                                    clients = clients_response.get('obj', [])
                                    for inbound in clients:
                                        settings = json.loads(inbound.get('settings', '{}'))
                                        for client in settings.get('clients', []):
                                            if client.get('email') == unique_email:
                                                # Получаем точное время истечения из API
                                                expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                                expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                                                break
                                        else:
                                            continue
                                        break
                                else:
                                # Fallback: вычисляем время истечения
                                expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
                                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                                expiry_timestamp = int(expiry_time.timestamp())
                            
                            msg = format_vpn_key_message(
                                email=unique_email,
                                status='Активен',
                                server=server_name,
                                expiry=expiry_str,
                                key=xui.link(unique_email),
                                expiry_timestamp=expiry_timestamp
                            )
                            
                            keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
                            ])
                            
                    # Формируем полное сообщение о покупке
                            success_text = UIMessages.success_purchase_message(period, meta.get('price', '100'))
                            full_message = success_text + msg
                            
                            # Если есть сообщение с оплатой, редактируем его
                            if message_id:
                                try:
                            await safe_edit_message_with_photo(
                                bot_app.bot,
                                        chat_id=int(user_id),
                                        message_id=message_id,
                                        text=full_message,
                                        reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type='key_success'
                                    )
                                    logger.info(f"Отредактировано сообщение с оплатой {message_id} на информацию о ключе")
                                except Exception as edit_error:
                                    logger.error(f"Ошибка редактирования сообщения {message_id}: {edit_error}")
                            # Fallback: отправляем новое сообщение
                            await safe_send_message_with_photo(
                                bot_app.bot,
                                            chat_id=int(user_id),
                                            text=full_message,
                                            reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type='key_success'
                                        )
                                        logger.info(f"Отправлено новое сообщение с ключом для user_id={user_id}")
                            else:
                                # Если нет сообщения с оплатой, отправляем новое
                        await safe_send_message_with_photo(
                            bot_app.bot,
                                        chat_id=int(user_id),
                                        text=full_message,
                                        reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='key_success'
                                    )
                                    logger.info(f"Отправлено новое сообщение с ключом для user_id={user_id}")
                            
                            # Удаляем message_id из отслеживания
                            payment_message_ids.pop(payment_id, None)
                            
                    except Exception as e:
                    logger.error(f"Ошибка отправки ключа пользователю: {e}")
            else:
                logger.error(f"Ошибка создания ключа: {response}")
                await update_payment_status(payment_id, 'failed')
                
        except Exception as e:
            logger.error(f"Ошибка при создании ключа: {e}")
            await update_payment_status(payment_id, 'failed')
            
    except Exception as e:
        logger.error(f"Ошибка обработки новой покупки {payment_id}: {e}")


async def process_canceled_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает отмененный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
                    await update_payment_activation(payment_id, 0)
        
        # Отправляем сообщение пользователю об ошибке оплаты
        message_id = payment_message_ids.get(payment_id)
        if message_id:
            error_message = (
                f"{UIStyles.header('Ошибка оплаты')}\n\n"
                f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                f"<b>Причина:</b> Платеж был отменен или возвращен\n"
                f"<b>Статус:</b> {status}\n\n"
                f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Попробовать снова", callback_data="buy_menu")],
                [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
            ])
            
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='payment_failed'
            )
            logger.info(f"Отправлено сообщение об ошибке оплаты пользователю {user_id}")
            
            # Удаляем message_id из отслеживания
            payment_message_ids.pop(payment_id, None)
                    
        except Exception as e:
        logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {e}")


async def process_failed_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает неудачный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        # Определяем тип платежа для правильного сообщения
        period = meta.get('type', 'month')
        is_extension = period.startswith('extend_')
        
        message_id = payment_message_ids.get(payment_id)
        if message_id:
            if is_extension:
                # Ошибка продления
                extension_email = meta.get('extension_key_email', 'Неизвестно')
                error_message = (
                    f"{UIStyles.header('Ошибка продления')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Ключ:</b> {extension_email}\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Попробовать снова", callback_data="mykey")],
                    [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
                ])
                
                menu_type = 'extend_key'
            else:
                # Ошибка обычной покупки
                error_message = (
                    f"{UIStyles.header('Ошибка оплаты')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Попробовать снова", callback_data="buy_menu")],
                    [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
                ])
                
                menu_type = 'payment_failed'
            
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type
            )
            logger.info(f"Отправлено сообщение об ошибке пользователю {user_id}")
            
            # Удаляем message_id из отслеживания
            payment_message_ids.pop(payment_id, None)
            
    except Exception as e:
        logger.error(f"Ошибка обработки неудачного платежа {payment_id}: {e}")


async def auto_cleanup_expired_keys():
    """
    Автоматически удаляет просроченные ключи со всех серверов
    Удаляет ключи, которые истекли более 3 дней назад
    """
    logger.info("Запуск автоматической очистки просроченных ключей...")
    
    try:
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        # 3 дня после истечения = 3 * 24 * 60 * 60 * 1000 миллисекунд
        threshold_ms = now_ms - 3 * 24 * 60 * 60 * 1000
        total_deleted_count = 0
        
        # Очищаем все серверы
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                deleted_count = 0
                inbounds = xui.list()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients_to_delete = []
                    
                    # Собираем список клиентов для удаления
                    for client in settings.get("clients", []):
                        expiry = client.get('expiryTime', 0)
                        email = client.get('email', '')
                        
                        # Проверяем, что ключ просрочен более 3 дней
                        if expiry and expiry < threshold_ms:
                            # Удаляем только пользовательские ключи (с подчеркиванием)
                            if '_' in email:
                                clients_to_delete.append(client)
                    
                    # Удаляем найденных клиентов
                    for client in clients_to_delete:
                        try:
                            client_id = client.get('id')
                            inbound_id = inbound['id']
                            email = client.get('email', '')
                            
                            # Извлекаем user_id из email (формат: user_id_email@domain.com)
                            user_id = None
                            if '_' in email:
                                user_id = email.split('_')[0]
                            
                            # Формируем URL для удаления
                            url = f"{xui.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                            logger.info(f"Автоудаление просроченного ключа: inbound_id={inbound_id}, client_id={client_id}, email={email}")
                            
                            # Отправляем запрос на удаление
                            result = xui.ses.post(url)
                            if getattr(result, 'status_code', None) == 200:
                                deleted_count += 1
                                total_deleted_count += 1
                                
                                # Вычисляем, сколько дней назад истек ключ
                                expiry_date = datetime.datetime.fromtimestamp(client.get('expiryTime', 0) / 1000)
                                days_expired = (datetime.datetime.now() - expiry_date).days
                                
                                logger.info(f'Автоудален просроченный ключ: {email} с сервера {server["name"]} (истек {days_expired} дней назад)')
                                
                                # Очищаем связанные данные из кэшей
                                try:
                                    # Очищаем extension_keys_cache
                                    keys_to_remove = []
                                    for short_id, key_email in extension_keys_cache.items():
                                        if key_email == email:
                                            keys_to_remove.append(short_id)
                                    for short_id in keys_to_remove:
                                        extension_keys_cache.pop(short_id, None)
                                    
                                    if keys_to_remove:
                                        logger.info(f"Очищено {len(keys_to_remove)} записей из extension_keys_cache для удаленного ключа {email}")
                                    
                                    # Очищаем payment_message_ids (платежи для этого ключа)
                                    payments_to_remove = []
                                    for payment_id in list(payment_message_ids.keys()):
                                        # Проверяем, связан ли платеж с этим ключом
                                        try:
                                            from .keys_db import get_all_pending_payments
                                            pending_payments = await get_all_pending_payments()
                                            for payment in pending_payments:
                                                if payment['payment_id'] == payment_id:
                                                    meta = payment.get('meta', {})
                                                    if meta.get('key_email') == email:
                                                        payments_to_remove.append(payment_id)
                                                    break
                                        except:
                                            pass
                                    
                                    for payment_id in payments_to_remove:
                                        payment_message_ids.pop(payment_id, None)
                                        extension_messages.pop(payment_id, None)
                                    
                                    if payments_to_remove:
                                        logger.info(f"Очищено {len(payments_to_remove)} записей из payment_message_ids и extension_messages для удаленного ключа {email}")
                                    
                                    # Очищаем уведомления для удаленного ключа
                                    if user_id:
                                        try:
                                            # Используем глобальный notification_manager, инициализируемый в on_startup
                                            if notification_manager:
                                                await notification_manager.clear_key_notifications(user_id, email)
                                        except Exception as e:
                                            logger.error(f"Ошибка очистки уведомлений для удаленного ключа {email}: {e}")
                                        
                                except Exception as e:
                                    logger.error(f"Ошибка очистки кэшей при удалении ключа {email}: {e}")
                                
                                # Отправляем уведомление пользователю об удалении ключа
                                if user_id:
                                    try:
                                        if notification_manager:
                                            await notification_manager._send_deletion_notification(
                                                user_id=user_id,
                                                email=email,
                                                server_name=server["name"],
                                                days_expired=days_expired
                                            )
                                    except Exception as e:
                                        logger.error(f"Ошибка отправки уведомления об удалении пользователю {user_id}: {e}")
                            else:
                                logger.warning(f"Не удалось удалить ключ {email}: status_code={getattr(result, 'status_code', None)}")
                                
                        except Exception as e:
                            logger.error(f"Ошибка при автоудалении ключа {client.get('email', 'unknown')}: {e}")
                            continue
                
                if deleted_count > 0:
                    logger.info(f"Автоудалено {deleted_count} просроченных ключей с сервера {server['name']}")
                    
            except Exception as e:
                logger.error(f"Ошибка при автоочистке сервера {server['name']}: {e}")
                # Уведомляем админа о критической ошибке автоочистки
                await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при автоочистке сервера:\nСервер: {server['name']}\nОшибка: {str(e)}")
                continue
        
        logger.info(f"Автоочистка завершена. Всего удалено просроченных ключей: {total_deleted_count}")
        return total_deleted_count
        
    except Exception as e:
        logger.error(f"Критическая ошибка в auto_cleanup_expired_keys: {e}")
        # Уведомляем админа о критической ошибке автоочистки
        await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Критическая ошибка в auto_cleanup_expired_keys:\nОшибка: {str(e)}")
        return 0


# Старые функции уведомлений удалены - теперь используется NotificationManager


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
    
    # Уведомляем админа только о критических ошибках (не сетевых)
    try:
        error_message = f"🚨 Критическая ошибка в боте:\n\n{str(context.error)}"
        if update and hasattr(update, 'effective_user') and update.effective_user:
            error_message += f"\n\nПользователь: {update.effective_user.id}"
        
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

async def notify_server_issues(bot, server_name, issue_type, details=""):
    """Уведомляет админа о проблемах с серверами"""
    try:
        message = f"🚨 Проблема с сервером {server_name}\n\n"
        message += f"Тип проблемы: {issue_type}\n"
        message += f"Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        message += f"Статус: Требует внимания\n\n"
        
        if details:
            message += f"Детали: {details}\n\n"
        
        message += "Рекомендуемые действия:\n"
        message += "• Проверить доступность сервера\n"
        message += "• Уведомить клиентов о возможных проблемах\n"
        message += "• Проверить логи сервера"
        
        await notify_admin(bot, message)
        logger.warning(f"Отправлено уведомление о проблеме с сервером {server_name}: {issue_type}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о проблеме с сервером: {e}")

async def server_health_monitor(app):
    """Периодический мониторинг состояния серверов"""
    logger.info("Запуск мониторинга серверов")
    
    # Словарь для отслеживания предыдущего состояния серверов
    previous_server_status = {}
    
    while True:
        try:
            # Проверяем все серверы
            health_results = server_manager.check_all_servers_health()
            new_client_health = new_client_manager.check_all_servers_health()
            
            # Проверяем изменения в состоянии серверов
            current_time = datetime.datetime.now()
            
            for server_name, is_healthy in health_results.items():
                previous_status = previous_server_status.get(server_name, "unknown")
                current_status = "online" if is_healthy else "offline"
                
                # Если статус изменился, отправляем уведомление
                if previous_status != current_status:
                    if current_status == "offline":
                        health_status = server_manager.get_server_health_status()[server_name]
                        last_error = health_status.get("last_error", "Неизвестная ошибка")
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер недоступен",
                            f"Ошибка: {last_error}"
                        )
                    elif current_status == "online":
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер восстановлен",
                            "Сервер снова доступен"
                        )
                
                previous_server_status[server_name] = current_status
            
            # Проверяем серверы с длительными проблемами
            for server_name, is_healthy in health_results.items():
                if not is_healthy:
                    health_status = server_manager.get_server_health_status()[server_name]
                    consecutive_failures = health_status.get("consecutive_failures", 0)
                    last_check = health_status.get("last_check")
                    
                    # Если сервер недоступен более 15 минут (3 проверки по 5 минут)
                    if consecutive_failures >= 3 and last_check:
                        time_since_last_check = current_time - last_check
                        if time_since_last_check.total_seconds() > 900:  # 15 минут
                            await notify_server_issues(
                                app.bot, 
                                server_name, 
                                "Длительная недоступность",
                                f"Сервер недоступен более 15 минут. Неудачных попыток: {consecutive_failures}"
                            )
            
            # Логируем статус всех серверов
            logger.info(f"Статус серверов: {health_results}")
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге серверов: {e}")
        
        # Ждем 5 минут до следующей проверки
        await asyncio.sleep(300)

# Глобальный менеджер уведомлений
notification_manager = None

async def on_startup(app):
    global notification_manager
    
    logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")
    
    await init_all_db()  # Уже включает init_referral_db()
    
    # Инициализируем менеджер уведомлений
    logger.info("Инициализация менеджера уведомлений...")
    notification_manager = NotificationManager(app.bot, server_manager, ADMIN_IDS)
    await notification_manager.initialize()
    await notification_manager.start()
    logger.info("Менеджер уведомлений запущен")
    
    logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
    
    # Запускаем остальные задачи
    # auto_activate_keys больше не нужна - webhook'и обрабатывают платежи мгновенно
    asyncio.create_task(server_health_monitor(app))


# ==================== СТИЛЬ ИНТЕРФЕЙСА ====================

# Эмодзи для различных элементов интерфейса
class UIEmojis:
    
    # Навигация
    BACK = "←"
    NEXT = "→"
    PREV = "←"
    CLOSE = "✕"
    REFRESH = "↻"
    
    # Статусы
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    


class UIStyles:
    @staticmethod
    def header(text: str) -> str:
        """Основной заголовок"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def subheader(text: str) -> str:
        """Подзаголовок"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def description(text: str) -> str:
        """Описание"""
        return f"<i>{text}</i>"
    
    @staticmethod
    def highlight(text: str) -> str:
        """Выделенный текст"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def code_block(text: str) -> str:
        """Блок кода"""
        return f"<code>{text}</code>"
    
    @staticmethod
    def success_message(text: str) -> str:
        """Сообщение об успехе"""
        return f"{UIEmojis.SUCCESS} <b>{text}</b>"
    
    @staticmethod
    def error_message(text: str) -> str:
        """Сообщение об ошибке"""
        return f"{UIEmojis.ERROR} <b>{text}</b>"
    
    @staticmethod
    def warning_message(text: str) -> str:
        """Предупреждение"""
        return f"{UIEmojis.WARNING} <b>{text}</b>"
    
    @staticmethod
    def info_message(text: str) -> str:
        """Информационное сообщение"""
        return f"<i>{text}</i>"

# Шаблоны кнопок для единообразия
class UIButtons:
    @staticmethod
    def main_menu_buttons(is_admin=False):
        """Кнопки главного меню"""
        buttons = [
            [InlineKeyboardButton("Купить", callback_data="buy_menu")],
            [InlineKeyboardButton("Мои ключи", callback_data="mykey"), 
             InlineKeyboardButton("Инструкция", callback_data="instruction")],
            [InlineKeyboardButton("Рефералы", callback_data="referral"), 
             InlineKeyboardButton("Мои баллы", callback_data="points")],
            [InlineKeyboardButton("Наш канал", url="https://t.me/DarallaNews")],
        ]
        
        if is_admin:
            buttons.append([InlineKeyboardButton("Админ-меню", callback_data="admin_menu")])
        
        return buttons
    
    @staticmethod
    def back_button():
        """Кнопка назад"""
        return InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")
    
    @staticmethod
    def refresh_button(callback_data="refresh"):
        """Кнопка обновления"""
        return InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=callback_data)

# Шаблоны сообщений
class UIMessages:
    @staticmethod
    def welcome_message():
        """Приветственное сообщение"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}"
        )
    
    @staticmethod
    def buy_menu_message():
        """Сообщение меню покупки"""
        return (
            f"{UIStyles.header('Выберите период подписки')}\n\n"
            f"{UIStyles.description('Доступные тарифы:')}\n"
            f"• <b>1 месяц</b> — 100₽\n"
            f"• <b>3 месяца</b> — 250₽ <i>(выгода 50₽)</i>"
        )
    
    @staticmethod
    def instruction_menu_message():
        """Сообщение меню инструкций"""
        return (
            f"{UIStyles.header('Инструкции по настройке')}\n\n"
            f"{UIStyles.description('Выберите вашу платформу для получения подробной инструкции:')}"
        )
    
    @staticmethod
    def admin_menu_message():
        """Сообщение админ-меню"""
        return f"{UIStyles.header('Панель администратора')}"

    @staticmethod
    def broadcast_intro_message():
        return (
            f"{UIStyles.header('Создание рассылки')}\n\n"
            f"{UIStyles.description('Отправьте текст сообщения, которое нужно разослать всем пользователям.')}\n"
            f"{UIStyles.info_message('Поддерживается HTML. Предпросмотр будет показан перед отправкой.')}"
        )

    @staticmethod
    def broadcast_preview_message(text: str):
        return (
            f"{UIStyles.header('Предпросмотр рассылки')}\n\n"
            f"{text}"
        )
    
    @staticmethod
    def success_purchase_message(period, price):
        """Сообщение об успешной покупке"""
        period_text = "1 месяц" if period == "month" else "3 месяца"
        return (
            f"{UIStyles.success_message('Покупка прошла успешно!')}\n\n"
            f"<b>Подписка:</b> {period_text}\n"
            f"<b>Сумма:</b> {price}₽\n\n"
        )
    
    @staticmethod
    def key_expiring_message(email, server, time_remaining):
        """Сообщение об истекающем ключе"""
        return (
            f"{UIStyles.warning_message('Внимание! Ключ скоро истечет')}\n\n"
            f"<b>Ключ:</b> <code>{email}</code>\n"
            f"<b>Сервер:</b> {server}\n"
            f"<b>Осталось:</b> {time_remaining}\n\n"
            f"{UIStyles.description('Продлите ключ, чтобы не потерять доступ к VPN!')}"
        )
    
    @staticmethod
    def key_deleted_message(email, server, days_expired):
        """Сообщение об удаленном ключе"""
        return (
            f"{UIStyles.error_message('Ключ был удален')}\n\n"
            f"<b>Ключ:</b> <code>{email}</code>\n"
            f"<b>Сервер:</b> {server}\n"
            f"<b>Истек:</b> {days_expired} дней назад\n\n"
            f"{UIStyles.description('Ключ был автоматически удален из-за истечения срока действия.')}\n"
            f"{UIStyles.description('Купите новый ключ, чтобы продолжить пользоваться VPN.')}"
        )
    
    @staticmethod
    def no_keys_message():
        """Сообщение об отсутствии ключей"""
        return (
            f"{UIStyles.info_message('У вас пока нет активных ключей')}\n\n"
            f"{UIStyles.description('Купите подписку для начала использования VPN.')}"
        )
    
    @staticmethod
    def key_extended_message(email, server_name, days, expiry_str, period=None):
        """Сообщение о продлении ключа"""
        # Определяем текст периода
        if period:
            if period == '3month':
                period_text = "3 месяца"
            elif period == 'month':
                period_text = "1 месяц"
            else:
                period_text = f"{days} дней"
        else:
            period_text = f"{days} дней"
        
        return (
            f"{UIEmojis.SUCCESS} Ключ успешно продлен!\n\n"
            f"Ключ: `{email}`\n"
            f"Сервер: {server_name}\n"
            f"Продлен на: {period_text}\n"
            f"Новое время истечения: {expiry_str}"
        )
    
    
    @staticmethod
    def server_selection_message():
        """Сообщение выбора сервера"""
        return (
            f"{UIStyles.header('Выбор локации')}\n\n"
            f"{UIStyles.description('Выберите локацию для вашего VPN-ключа:')}\n"
            f"{UIStyles.info_message('Рекомендуется выбрать ближайший к вам сервер для лучшей скорости.')}"
        )
    
    @staticmethod
    def referral_menu_message(points, total_referrals, active_referrals, ref_link):
        """Сообщение реферального меню"""
        return (
            f"{UIStyles.header('Реферальная программа')}\n\n"
            f"<b>Ваши баллы:</b> {UIStyles.highlight(str(points))}\n\n"
            f"<b>Статистика рефералов:</b>\n"
            f"• Всего приглашено: {total_referrals}\n"
            f"• Активных: {active_referrals}\n\n"
            f"<b>Как заработать баллы:</b>\n"
            f"• Пригласите друга — получите 1 балл\n"
            f"• 1 балл = 14 дней VPN\n"
            f"• 1 балл = продление на 14 дней\n\n"
            f"{UIStyles.warning_message('Важно: Балл выдается только за привлечение новых клиентов!')}\n\n"
            f"<b>Ваша реферальная ссылка:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"<b>Как поделиться:</b>\n"
            f"{UIStyles.description('Отправьте ссылку друзьям или опубликуйте в социальных сетях')}"
        )
    
    @staticmethod
    def welcome_referral_new_user_message(days):
        """Приветственное сообщение для нового пользователя по реферальной ссылке"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Вы пришли по реферальной ссылке!')}\n\n"
            f"После покупки VPN ваш друг получит 1 балл!\n"
            f"1 балл = {days} дней VPN бесплатно!"
            
        )
    
    @staticmethod
    def welcome_referral_existing_user_message():
        """Приветственное сообщение для существующего пользователя по реферальной ссылке"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Вы пришли по реферальной ссылке')}\n\n"
            f"Но вы не новый пользователь.\n"
            f"Реферальная награда не будет выдана."
            
        )

# Глобальный словарь для хранения message_id платежей
# Ключ: payment_id, Значение: message_id
payment_message_ids = {}

# Глобальный словарь для хранения коротких идентификаторов ключей для продления
# Ключ: короткий_id, Значение: key_email
extension_keys_cache = {}

# Глобальный словарь для хранения сообщений продления
# Ключ: payment_id, Значение: (chat_id, message_id)
extension_messages = {}

# Импорт нового модуля уведомлений
try:
    from .notifications import NotificationManager
except ImportError:
    from .notifications import NotificationManager

import traceback

async def notify_admin(bot, text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=f"❗️[VPNBot ERROR]\n{text}")
        except telegram.error.Forbidden:
            logger.warning(f"Админ {admin_id} заблокировал бота")
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Админ {admin_id} заблокировал бота: {e}")
            else:
                logger.error(f'BadRequest ошибка отправки уведомления админу: {e}')
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления админу: {e}')


async def admin_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_errors':
            push_nav(context, 'admin_errors')
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        # Читаем ротационный файл логов приложения
        from .keys_db import DATA_DIR
        import os
        logs_path = os.path.join(DATA_DIR, 'logs', 'bot.log')
        logs = ''
        if os.path.exists(logs_path):
            with open(logs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = ''.join(lines[-200:])  # последние ~200 строк
        else:
            logs = 'Файл логов не найден. Он будет создан автоматически при работе бота.'

        # Ограничиваем длину логов для Telegram (максимум 4000 символов)
        if len(logs) > 3500:  # Оставляем место для HTML тегов
            logs = logs[-3500:]

        # Экранируем HTML и выводим как код
        escaped = html.escape(logs)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_errors_refresh")],
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для логов, ограничиваем длину для caption
        max_length = 800  # Telegram caption limit is 1024, but we use 800 to be safe
        if len(escaped) > max_length:
            escaped = escaped[:max_length] + "\n\n... (логи обрезаны)"
        
        logs_text = f"<b>Последние логи:</b>\n\n<pre><code>{escaped}</code></pre>"
        await safe_edit_or_reply_universal(message_obj, logs_text, reply_markup=keyboard, parse_mode='HTML', menu_type='admin_errors')
            
    except Exception as e:
        logger.exception("Ошибка в admin_errors")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для ошибки логов
        error_text = f'{UIEmojis.ERROR} Ошибка при чтении логов: {str(e)}'
        await safe_edit_or_reply_universal(message_obj, error_text, reply_markup=keyboard, menu_type='admin_errors')

async def admin_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дашборд уведомлений для админа"""
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_notifications':
            push_nav(context, 'admin_notifications')
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        if notification_manager is None:
            await safe_edit_or_reply(update.callback_query.message, 
                                   f"{UIEmojis.ERROR} Менеджер уведомлений не инициализирован")
            return
        
        # Получаем дашборд
        dashboard_text = await notification_manager.get_notification_dashboard()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_notifications_refresh")],
            [UIButtons.back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для уведомлений
        await safe_edit_or_reply_universal(message_obj, dashboard_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_notifications')
        
    except Exception as e:
        logger.error(f"Ошибка в admin_notifications: {e}")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для ошибки уведомлений
        error_text = f"{UIEmojis.ERROR} Ошибка загрузки дашборда: {e}"
        await safe_edit_or_reply_universal(message_obj, error_text, reply_markup=keyboard, menu_type='admin_notifications')



async def admin_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_check_servers':
            push_nav(context, 'admin_check_servers')
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        # Проверяем здоровье всех серверов
        health_results = server_manager.check_all_servers_health()
        health_status = server_manager.get_server_health_status()
        
        message = "🔍 Детальная проверка серверов:\n\n"
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_info = health_status.get(server_name, {})
            
            if is_healthy:
                # Получаем дополнительную информацию о сервере
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн\n"
                    message += f"   Всего клиентов: {total_clients}\n"
                    message += f"   Активных клиентов: {active_clients}\n"
                    message += f"   Истекших клиентов: {expired_clients}\n"
                    message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
                except Exception as e:
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн (ошибка получения деталей: {str(e)[:50]}...)\n"
            else:
                message += f"{UIEmojis.ERROR} {server_name}: Офлайн\n"
                message += f"   Ошибка: {status_info.get('last_error', 'Неизвестно')}\n"
                message += f"   {UIEmojis.REFRESH} Неудачных попыток: {status_info.get('consecutive_failures', 0)}\n"
                message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
            
            message += "\n"
        
        # Добавляем общую статистику
        total_servers = len(server_manager.servers)
        online_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
        offline_servers = total_servers - online_servers
        
        # Подсчитываем общее количество клиентов
        total_clients_all = 0
        active_clients_all = 0
        expired_clients_all = 0
        
        for server in server_manager.servers:
            if health_results.get(server["name"], False):
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_all += total_clients
                    active_clients_all += active_clients
                    expired_clients_all += expired_clients
                except:
                    pass
        
        message += f"Общая статистика:\n"
        message += f"   Всего серверов: {total_servers}\n"
        message += f"   Онлайн: {online_servers}\n"
        message += f"   Офлайн: {offline_servers}\n"
        message += f"   Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"Клиенты:\n"
        message += f"   Всего клиентов: {total_clients_all}\n"
        message += f"   Активных: {active_clients_all}\n"
        message += f"   Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_check_servers")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_check_servers')
    except Exception as e:
        logger.exception("Ошибка в admin_check_servers")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f'Ошибка при проверке серверов: {e}', reply_markup=keyboard, menu_type='admin_check_servers')


# Callback для продления ключей
async def extend_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # Извлекаем short_id из callback_data
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await query.answer("Ошибка: неверный формат данных")
        return
    
    short_id = parts[1]
    
    # Получаем email ключа из кэша
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        # Пытаемся найти ключ по short_id, созданному из уведомления
        # Проверяем все возможные форматы short_id
        import hashlib
        
        # Ищем ключ пользователя на серверах
        try:
            all_clients = []
            for server in server_manager.servers:
                try:
                    xui = server["x3"]
                    inbounds = xui.list()['obj']
                    for inbound in inbounds:
                        settings = json.loads(inbound['settings'])
                        clients = settings.get("clients", [])
                        for client in clients:
                            if client['email'].startswith(f"{user_id}_") or client['email'].startswith(f"trial_{user_id}_"):
                                all_clients.append(client)
                except Exception as e:
                    logger.error(f"Ошибка при поиске ключей на сервере {server['name']}: {e}")
                    continue
            
            # Ищем ключ, который соответствует short_id
            for client in all_clients:
                email = client['email']
                # Проверяем разные форматы short_id
                possible_short_ids = [
                    hashlib.md5(f"{user_id}:{email}".encode()).hexdigest()[:8],
                    hashlib.md5(f"extend:{email}".encode()).hexdigest()[:8]
                ]
                
                if short_id in possible_short_ids:
                    key_email = email
                    # Добавляем в кэш для будущих использований
                    extension_keys_cache[short_id] = email
                    logger.info(f"Найден ключ по short_id: {short_id} -> {email}")
                    break
            
            if not key_email:
                await query.answer("Ошибка: ключ не найден")
                logger.error(f"Не найден key_email для short_id: {short_id}")
                return
                
        except Exception as e:
            logger.error(f"Ошибка поиска ключа по short_id: {e}")
            await query.answer("Ошибка: ключ не найден")
            return
    
    await query.answer()
    
    logger.info(f"Запрос на продление ключа: user_id={user_id}, key_email={key_email}")
    
    # Проверяем, что ключ принадлежит пользователю
    if not (key_email.startswith(f"{user_id}_") or key_email.startswith(f"trial_{user_id}_")):
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: ключ не принадлежит вам.")
        return
    
    # Разрешаем продление любых ключей, включая старые trial
    
    # Проверяем, что ключ существует на серверах
    try:
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            await safe_edit_or_reply(query.message, "❌ Ключ не найден на серверах.")
            return
    except Exception as e:
        logger.error(f"Ошибка поиска ключа для продления: {e}")
        await safe_edit_or_reply(query.message, "❌ Ошибка при поиске ключа.")
        return
    
    # Создаем короткий идентификатор для ключа
    import hashlib
    short_id = hashlib.md5(f"{user_id}:{key_email}".encode()).hexdigest()[:8]
    extension_keys_cache[short_id] = key_email
    logger.info(f"Создан короткий ID для продления: {short_id} -> {key_email}")
    
    # Показываем меню выбора периода продления
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 месяц - 100₽", callback_data=f"ext_per:month:{short_id}")],
        [InlineKeyboardButton("3 месяца - 250₽", callback_data=f"ext_per:3month:{short_id}")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад к ключам", callback_data="mykey")]
    ])
    
    message_text = (
        f"{UIStyles.header('Продление ключа')}\n\n"
        f"<b>Ключ:</b> <code>{key_email}</code>\n"
        f"<b>Сервер:</b> {server_name}\n\n"
        f"{UIStyles.description('Выберите период продления:')}"
    )
    
    await safe_edit_or_reply_universal(query.message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')

# Callback для выбора периода продления
async def extend_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # Извлекаем период и short_id из callback_data: ext_per:month:short_id
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await query.answer("Ошибка: неверный формат данных")
        return
    
    period = parts[1]  # month или 3month
    short_id = parts[2]
    
    # Получаем email ключа из кэша
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        await query.answer("Ошибка: ключ не найден в кэше")
        logger.error(f"Не найден key_email для short_id: {short_id}")
        return
    
    await query.answer()
    
    logger.info(f"Выбран период продления: user_id={user_id}, period={period}, key_email={key_email}")
    
    # Определяем цену (такую же как при покупке)
    price = "100.00" if period == "month" else "250.00"  # в рублях
    
    # Создаем платеж для продления (используем существующую функцию handle_payment)
    try:
        # Сохраняем информацию о продлении в контексте
        context.user_data['extension_key_email'] = key_email
        context.user_data['extension_period'] = period
        
        # Вызываем функцию создания платежа
        await handle_payment(update, context, price, f"extend_{period}")
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа для продления: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад к ключам", callback_data="mykey")]
        ])
        await safe_edit_or_reply(query.message, "❌ Ошибка при создании платежа. Попробуйте позже.", reply_markup=keyboard)

# admin_delete_all удалена по требованию

async def admin_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущую конфигурацию баллов"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        config = await get_all_config()
        if not config:
            await safe_edit_or_reply(update.message, 'Конфигурация не найдена.')
            return
        
        message = "⚙️ Конфигурация баллов:\n\n"
        for key, data in config.items():
            if key.startswith('points_'):
                message += f"• {data['description']}: {data['value']}\n"
        
        message += "\n📝 Команды:\n"
        message += "• `/admin_set_days <дни>` - изменить количество дней за 1 балл\n"
        message += "• `/admin_set_days 14` - установить 14 дней за балл\n"
        message += "• `/admin_set_days 30` - установить 30 дней за балл\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, message, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Ошибка в admin_config")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} Ошибка: {e}')

async def admin_set_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает количество дней за 1 балл"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    if not context.args:
        await safe_edit_or_reply(update.message, 'Используйте: /admin_set_days <количество_дней>\nПример: /admin_set_days 14')
        return
    
    try:
        days = int(context.args[0])
        
        # Проверяем лимиты
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            await safe_edit_or_reply(update.message, f'Количество дней должно быть от {min_days} до {max_days}')
            return
        
        # Сохраняем новое значение
        success = await set_config('points_days_per_point', str(days), 'Количество дней VPN за 1 балл')
        
        if success:
            await safe_edit_or_reply(update.message, f'{UIEmojis.SUCCESS} Установлено: 1 балл = {days} дней VPN', parse_mode="Markdown")
        else:
            await safe_edit_or_reply(update.message, '❌ Ошибка при сохранении конфигурации')
            
    except ValueError:
        await safe_edit_or_reply(update.message, 'Количество дней должно быть числом')
    except Exception as e:
        logger.exception("Ошибка в admin_set_days")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} Ошибка: {e}')

# Состояние для ConversationHandler
WAITING_FOR_DAYS = 1

async def admin_set_days_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало интерактивного изменения дней за балл"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(query.message, 'Нет доступа.')
        return ConversationHandler.END
    
    # Получаем текущее значение
    current_days = await get_config('points_days_per_point', '14')
    min_days = await get_config('points_min_days', '1')
    max_days = await get_config('points_max_days', '365')
    
    message = (
        f"⚙️ <b>Настройка дней за балл</b>\n\n"
        f"Текущее значение: <b>1 балл = {current_days} дней VPN</b>\n\n"
        f"Введите новое количество дней (от {min_days} до {max_days}):"
    )
    
    # Создаем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
    ])
    
    # Сохраняем message_id для последующего редактирования
    context.user_data['config_message_id'] = query.message.message_id
    context.user_data['config_chat_id'] = query.message.chat_id
    
    await safe_edit_or_reply_universal(query.message, message, parse_mode="HTML", reply_markup=keyboard, menu_type='admin_menu')
    
    return WAITING_FOR_DAYS

async def admin_set_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода количества дней"""
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    async def edit_config_message(message, reply_markup=None):
        """Вспомогательная функция для редактирования сообщения настройки"""
        message_id = context.user_data.get('config_message_id')
        chat_id = context.user_data.get('config_chat_id')
        
        if message_id and chat_id:
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    menu_type='admin_menu'
                )
                return
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения настройки: {e}")
                # Fallback: отправляем новое сообщение
                await safe_send_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    menu_type='admin_menu'
                )
                return
        
        # Fallback: используем обычное редактирование
        await safe_edit_or_reply_universal(update.message, message, reply_markup=reply_markup, parse_mode="HTML", menu_type='admin_menu')
    
    try:
        # Удаляем сообщение пользователя
        await update.message.delete()
        
        days = int(update.message.text.strip())
        
        # Проверяем лимиты
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            message = (
                f"{UIEmojis.ERROR} <b>Ошибка</b>\n\n"
                f"Количество дней должно быть от {min_days} до {max_days}\n\n"
                f"Текущее значение: <b>1 балл = {await get_config('points_days_per_point', '14')} дней</b>\n\n"
                f"Введите новое количество дней:"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
            ])
            
            await safe_edit_or_reply_universal(update.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')
            
            return WAITING_FOR_DAYS
        
        # Сохраняем новое значение
        success = await set_config('points_days_per_point', str(days), 'Количество дней VPN за 1 балл')
        logger.info(f"ADMIN_SET_DAYS: Сохранение конфигурации points_days_per_point = {days}, success = {success}")
        
        # Проверяем, что значение действительно сохранилось
        saved_days = await get_config('points_days_per_point', '14')
        logger.info(f"ADMIN_SET_DAYS: Проверка сохраненного значения = {saved_days}")
        
        if success:
            message = (
                f"{UIEmojis.SUCCESS} <b>Настройка изменена!</b>\n\n"
                f"<b>1 балл = {days} дней VPN</b>\n\n"
                f"Введите другое значение для изменения или нажмите «Назад»:"
            )
        else:
            message = (
                f"{UIEmojis.ERROR} <b>Ошибка сохранения</b>\n\n"
                f"Попробуйте еще раз или нажмите «Назад»:"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="admin_set_days_cancel")]
        ])
        
        await edit_config_message(message, keyboard)
        
        return WAITING_FOR_DAYS
        
    except ValueError:
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        message = (
            f"{UIEmojis.ERROR} <b>Ошибка</b>\n\n"
            f"Введите число, например: 14, 30, 60\n\n"
            f"Текущее значение: <b>1 балл = {await get_config('points_days_per_point', '14')} дней</b>\n\n"
            f"Введите новое количество дней:"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
        ])
        
        await edit_config_message(message, keyboard)
        
        return WAITING_FOR_DAYS
        
    except Exception as e:
        logger.exception("Ошибка в admin_set_days_input")
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        await edit_config_message(f'{UIEmojis.ERROR} Ошибка: {e}')
        
        return ConversationHandler.END

async def admin_set_days_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена изменения конфига - возврат в админ меню"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем состояние изменения дней
    context.user_data.pop('config_message_id', None)
    context.user_data.pop('config_chat_id', None)
    
    # Возвращаемся в админ меню
    await admin_menu(update, context)
    
    return ConversationHandler.END

# Обработка callback-кнопок для start
async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Обработка callback: {query.data}")
    if query.data == "buy_menu":
        await buy_menu_handler(update, context)
    elif query.data.startswith("select_period_"):
        await select_period_callback(update, context)
    elif query.data.startswith("select_server_"):
        await select_server_callback(update, context)
    elif query.data == "mykey":
        await mykey(update, context)
    elif query.data.startswith("keys_page_"):
        logger.info(f"Переход на страницу ключей: {query.data}")
        await mykey(update, context)
    elif query.data == "instruction":
        await instruction(update, context)


# Обработчик для кнопки "Купить" в меню покупки
async def buy_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'buy_menu':
        push_nav(context, 'buy_menu')
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("buy_menu_handler: message is None")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 месяц — 100₽", callback_data="select_period_month")],
        [InlineKeyboardButton("3 месяца — 250₽", callback_data="select_period_3month")],
        [UIButtons.back_button()],
    ])
    
    # Используем единый стиль для сообщения меню покупки
    buy_menu_text = UIMessages.buy_menu_message()
    await safe_edit_or_reply_universal(message, buy_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='buy_menu')

# Новый обработчик выбора периода, который переводит к выбору сервера
async def select_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Сохраняем выбранный период
    if query.data == "select_period_month":
        context.user_data["pending_period"] = "month"
        context.user_data["pending_price"] = "100.00"
    elif query.data == "select_period_3month":
        context.user_data["pending_period"] = "3month"
        context.user_data["pending_price"] = "250.00"
    
    # Переходим к выбору сервера
    await server_selection_menu(update, context)

# Меню выбора сервера
async def server_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'server_selection':
        push_nav(context, 'server_selection')
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("server_selection_menu: message is None")
        return
    
    # Проверяем доступность всех серверов
    health_results = new_client_manager.check_all_servers_health()
    
    # Создаем кнопки для локаций с флагами и статусом
    location_buttons = []
    location_flags = {
        "Finland": "🇫🇮",
        "Latvia": "🇱🇻", 
        "Estonia": "🇪🇪"
    }
    
    # Формируем текст с информацией о локациях
    location_info_text = ""
    
    for location, servers in SERVERS_BY_LOCATION.items():
        if not servers:
            continue
            
        # Проверяем доступность серверов в локации
        available_servers = 0
        total_servers = 0
        
        for server in servers:
            if server["host"] and server["login"] and server["password"]:
                total_servers += 1
                if health_results.get(server['name'], False):
                    available_servers += 1
        
        if total_servers == 0:
            continue
            
        flag = location_flags.get(location)
        
        # Определяем статус локации
        if available_servers > 0:
            status_icon = UIEmojis.SUCCESS
            status_text = f"Доступно {available_servers}/{total_servers} серверов"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"select_server_{location.lower()}"
        else:
            status_icon = UIEmojis.ERROR
            status_text = "Недоступно"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"server_unavailable_{location.lower()}"
        
        location_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Добавляем информацию о локации в текст
        location_info_text += f"{flag} <b>{location}</b> - {status_text}\n"
    
    # Добавляем кнопку "Автовыбор" (только если есть доступные серверы)
    available_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
    if available_servers > 0:
        location_buttons.append([InlineKeyboardButton("🎯 Автовыбор", callback_data="select_server_auto")])
        location_info_text += "<b>🎯 Автовыбор</b> - Локация с наименьшей нагрузкой\n"
    
    location_buttons.append([InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="refresh_servers")])
    
    # Определяем текст периода и кнопку назад в зависимости от типа покупки
    pending_period = context.user_data.get("pending_period")
    if pending_period == "month":
        period_text = "1 месяц за 100₽"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "3month":
        period_text = "3 месяца за 250₽"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "points_month":
        period_text = "1 месяц за 1 балл"
        location_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="spend_points")])
    else:
        period_text = "Неизвестный период"
        location_buttons.append([UIButtons.back_button()])
    
    keyboard = InlineKeyboardMarkup(location_buttons)
    
    message_text = f"{UIStyles.subheader(f'Выбран период: {period_text}')}\n\n{UIMessages.server_selection_message()}\n\n{location_info_text}"
    
    await safe_edit_or_reply_universal(message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='server_selection')

# Обработчик выбора сервера
async def select_server_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Обработка обновления списка серверов
    if query.data == "refresh_servers":
        await server_selection_menu(update, context)
        return
    
    # Обработка недоступных локаций
    if query.data.startswith("server_unavailable_"):
        location_name = query.data.replace("server_unavailable_", "").title()
        await safe_edit_or_reply(
            query.message, 
            f"{UIEmojis.ERROR} Локация {location_name} временно недоступна\n\n"
            f"Пожалуйста, выберите другую локацию или попробуйте позже.\n\n"
            f"Для обновления статуса серверов нажмите кнопку \"{UIEmojis.REFRESH} Обновить\"",
            parse_mode="HTML"
        )
        return
    
    # Сохраняем выбранную локацию
    selected_location = None
    if query.data == "select_server_auto":
        selected_location = "auto"
    elif query.data == "select_server_finland":
        selected_location = "Finland"
    elif query.data == "select_server_latvia":
        selected_location = "Latvia"
    elif query.data == "select_server_estonia":
        selected_location = "Estonia"
    
    if not selected_location:
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Неверный выбор локации")
        return
    
    # Проверяем доступность выбранной локации
    if selected_location != "auto":
        # Проверяем, есть ли доступные серверы в локации
        available_servers = 0
        for server in SERVERS_BY_LOCATION.get(selected_location, []):
            if server["host"] and server["login"] and server["password"]:
                if new_client_manager.check_server_health(server["name"]):
                    available_servers += 1
        
        if available_servers == 0:
            await safe_edit_or_reply(
                query.message, 
                f"❌ Локация {selected_location} недоступна\n\n"
                f"Все серверы в этой локации временно недоступны. Пожалуйста, выберите другую локацию.",
                parse_mode="HTML"
            )
            return
    else:
        # Для автовыбора проверяем, есть ли доступные серверы в любой локации
        total_available = 0
        for location, servers in SERVERS_BY_LOCATION.items():
            for server in servers:
                if server["host"] and server["login"] and server["password"]:
                    if new_client_manager.check_server_health(server["name"]):
                        total_available += 1
        
        if total_available == 0:
            await safe_edit_or_reply(
                query.message, 
                "❌ Нет доступных серверов\n\n"
                "Все серверы временно недоступны. Попробуйте позже.",
                parse_mode="HTML"
            )
            return
    
    # Сохраняем выбранную локацию
    context.user_data["selected_location"] = selected_location
    
    # Получаем сохраненные данные
    period = context.user_data.get("pending_period")
    price = context.user_data.get("pending_price")
    
    # Запускаем процесс оплаты
    await handle_payment(update, context, price, period)



# === Навигационный стек и универсальный обработчик "Назад" ===
def push_nav(context, state, max_size=10):
    stack = context.user_data.setdefault('nav_stack', [])
    
    # Ограничиваем размер стека
    if len(stack) >= max_size:
        stack.pop(0)  # Удаляем самый старый элемент
    
    stack.append(state)
    logger.info(f"PUSH: {state} -> Stack: {stack}")

def pop_nav(context):
    stack = context.user_data.get('nav_stack', [])
    if stack:
        popped = stack.pop()
        logger.info(f"POP: {popped} -> Stack: {stack}")
        return stack[-1] if stack else None
    logger.info(f"POP: empty stack")
    return None


async def universal_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    logger.info(f"BACK: Current stack before pop: {context.user_data.get('nav_stack', [])}")
    prev_state = pop_nav(context)
    logger.info(f"BACK: Previous state: {prev_state}")
    
    logger.info(f"BACK: Navigating to {prev_state}")
    
    # Если стек пустой — возвращаемся в главное меню
    if prev_state is None:
        logger.info("BACK: prev_state is None, calling start()")
        await start(update, context)
    elif prev_state == 'main_menu':
        # Если возвращаемся в main_menu, редактируем существующее сообщение
        logger.info("BACK: prev_state == 'main_menu', calling edit_main_menu")
        await edit_main_menu(update, context)
    elif prev_state == 'instruction_menu':
        await instruction(update, context)
    elif prev_state == 'instruction_platform':
        # Возвращаемся к выбору платформы
        await instruction(update, context)

    elif prev_state == 'payment':
        # После активации ключа возвращаемся в главное меню
        await start(update, context)
    elif prev_state == 'mykeys_menu':
        await mykey(update, context)
    elif prev_state == 'admin_menu':
        await admin_menu(update, context)
    elif prev_state == 'admin_errors':
        await admin_menu(update, context)
    elif prev_state == 'admin_check_servers':
        await admin_menu(update, context)
    elif prev_state == 'admin_notifications':
        await admin_menu(update, context)
    elif prev_state == 'buy_menu':
        await buy_menu_handler(update, context)
    else:
        logger.warning(f"BACK: Unknown state {prev_state}, returning to main menu")
        await start(update, context)



async def force_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная проверка всех серверов"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'Нет доступа.')
        return
    
    try:
        await safe_edit_or_reply(update.message, '🔄 Принудительная проверка серверов...')
        
        # Проверяем все серверы
        health_results = server_manager.check_all_servers_health()
        new_client_health = new_client_manager.check_all_servers_health()
        
        # Формируем отчет
        message = "🔍 Результаты принудительной проверки:\n\n"
        
        # Основные серверы
        message += "Основные серверы:\n"
        total_clients_main = 0
        active_clients_main = 0
        expired_clients_main = 0
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
            
            if is_healthy:
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_main += total_clients
                    active_clients_main += active_clients
                    expired_clients_main += expired_clients
                    message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                except:
                    message += f"{status_icon} {server_name} (ошибка получения данных)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        message += "\nСерверы для новых клиентов:\n"
        total_clients_new = 0
        active_clients_new = 0
        expired_clients_new = 0
        
        for server in new_client_manager.servers:
            server_name = server["name"]
            is_healthy = new_client_health.get(server_name, False)
            status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
            
            if is_healthy:
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_new += total_clients
                    active_clients_new += active_clients
                    expired_clients_new += expired_clients
                    message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                except:
                    message += f"{status_icon} {server_name} (ошибка получения данных)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        # Статистика
        total_servers = len(health_results) + len(new_client_health)
        online_servers = sum(1 for is_healthy in list(health_results.values()) + list(new_client_health.values()) if is_healthy)
        total_clients_all = total_clients_main + total_clients_new
        active_clients_all = active_clients_main + active_clients_new
        expired_clients_all = expired_clients_main + expired_clients_new
        
        message += f"\nСтатистика серверов:\n"
        message += f"Всего серверов: {total_servers}\n"
        message += f"Онлайн: {online_servers}\n"
        message += f"Офлайн: {total_servers - online_servers}\n"
        message += f"Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"Статистика клиентов:\n"
        message += f"Всего клиентов: {total_clients_all}\n"
        message += f"Активных: {active_clients_all}\n"
        message += f"Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await safe_edit_or_reply(update.message, message, parse_mode="HTML")
        
    except Exception as e:
        logger.exception("Ошибка в force_check_servers")
        await safe_edit_or_reply(update.message, f'Ошибка при проверке серверов: {e}')

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЛЛАМИ И РЕФЕРАЛАМИ =====

async def points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает баллы пользователя"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    history = await get_points_history(user_id, 5)
    points_days = await get_config('points_days_per_point', '14')
    
    message = (
        f"*Ваши баллы*\n\n"
        f"Текущий баланс: *{mdv2(points_info['points'])} баллов*\n"
        f"Всего заработано: {mdv2(points_info['total_earned'])}\n"
        f"Всего потрачено: {mdv2(points_info['total_spent'])}\n\n"
        f"*1 балл \\= {mdv2(points_days)} дней VPN\\!*\n\n"
    )
    
    if history:
        message += "*Последние операции:*\n"
        for trans in history:
            icon = "\\+" if trans['type'] == 'earned' else "\\-"
            date_str = datetime.datetime.fromtimestamp(trans['created_at']).strftime('%d.%m %H:%M')
            message += f"{icon} {mdv2(trans['amount'])} \\- {mdv2(trans['description'])} \\({mdv2(date_str)}\\)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Потратить баллы", callback_data="spend_points")],
        [InlineKeyboardButton("Поделиться ссылкой", callback_data="referral")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
    ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"points_callback: failed to edit message: {e}")

async def spend_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню траты баллов"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '14')
    
    if points_info['points'] < 1:
        message = (
            f"{UIEmojis.ERROR} *Недостаточно баллов*\n\n"
            "У вас нет баллов для траты\\.\n"
            "Приглашайте друзей, чтобы заработать баллы\\!\n\n"
            f"1 реферал \\= {mdv2(points_days)} дней VPN"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Поделиться ссылкой", callback_data="referral")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="points")]
        ])
    else:
        message = (
            f"*Потратить баллы*\n\n"
            f"У вас есть: *{mdv2(points_info['points'])} баллов*\n\n"
            f"*Доступные покупки:*\n"
            f"• 1 балл \\= {mdv2(points_days)} дней VPN\n"
            f"• 1 балл \\= продление на {mdv2(points_days)} дней\n\n"
            f"Выберите действие:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Купить {mdv2(points_days)} дней за 1 балл", callback_data="buy_with_points")],
            [InlineKeyboardButton(f"Продлить ключ на {mdv2(points_days)} дней за 1 балл", callback_data="extend_with_points")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="points")]
        ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"spend_points_callback: failed to edit message: {e}")

async def buy_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка VPN за баллы - выбор сервера"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Недостаточно баллов!")
        return
    
    # Сохраняем информацию о покупке за баллы
    context.user_data["pending_period"] = "points_month"
    context.user_data["pending_price"] = "1 балл"
    
    # Переходим к выбору сервера
    await server_selection_menu(update, context)

async def extend_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продление ключа за баллы - выбор ключа"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="spend_points")]
        ])
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Недостаточно баллов!", reply_markup=keyboard, menu_type='extend_key')
        return
    
    # Ищем активные ключи пользователя
    try:
        all_clients = []
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(user_id):
                            client['server_name'] = server['name']
                            client['xui'] = xui
                            # Добавляем информацию о времени истечения
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            if expiry_timestamp > 0:
                                expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M')
                                client['expiry_str'] = expiry_str
                            else:
                                client['expiry_str'] = '—'
                            all_clients.append(client)
            except Exception as e:
                logger.error(f"Ошибка при получении клиентов с сервера {server['name']}: {e}")

        if not all_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="spend_points")]
            ])
            await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} У вас нет активных ключей для продления!", reply_markup=keyboard, menu_type='extend_key')
            return
        
        # Если только один ключ - продлеваем сразу
        if len(all_clients) == 1:
            client = all_clients[0]
            await extend_selected_key_with_points(update, context, client, user_id)
            return
        
        # Показываем список ключей для выбора
        keyboard_buttons = []
        for i, client in enumerate(all_clients, 1):
            email = client['email']
            server_name = client.get('server_name', 'Неизвестно')
            expiry_str = client.get('expiry_str', '—')
            
            # Создаем короткий ID для ключа
            import hashlib
            short_id = hashlib.md5(f"{user_id}:{email}:extend_points".encode()).hexdigest()[:8]
            extension_keys_cache[short_id] = {
                'email': email,
                'xui': client['xui'],
                'server_name': server_name,
                'user_id': user_id
            }
            
            button_text = f"Ключ #{i} ({server_name}) - {expiry_str}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"extend_points_key:{short_id}")])
        
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="spend_points")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        points_days = await get_config('points_days_per_point', '14')
        message = (
            f"{UIStyles.header('Продление ключа за баллы')}\n\n"
            f"<b>У вас есть:</b> {points_info['points']} баллов\n"
            f"<b>1 балл</b> = продление на {points_days} дней\n\n"
            f"{UIStyles.description('Выберите ключ для продления:')}"
        )
        
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type='extend_key')
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка ключей: {e}")
        await safe_edit_or_reply_universal(update.callback_query.message, "❌ Ошибка при получении списка ключей.", menu_type='extend_key')

async def extend_selected_key_with_points(update: Update, context: ContextTypes.DEFAULT_TYPE, client: dict, user_id: str):
    """Продлевает выбранный ключ за баллы"""
    try:
        xui = client['xui']
        email = client['email']
        server_name = client.get('server_name', 'Неизвестно')
        
        # Продлеваем ключ СНАЧАЛА
        points_days = int(await get_config('points_days_per_point', '14'))
        response = xui.extendClient(email, points_days)
        if response and response.status_code == 200:
            # Ключ продлен успешно - ТЕПЕРЬ списываем баллы
            success = await spend_points(user_id, 1, f"Продление ключа {email} за баллы", bot=context.bot)
            if not success:
                # Если не удалось списать баллы, откатываем продление
                try:
                    # Откатываем продление (уменьшаем на те же дни)
                    xui.extendClient(email, -points_days)
                    logger.warning(f"Rolled back extension for key {email} due to points spending failure")
                except Exception as e:
                    logger.error(f"Failed to rollback extension for key {email} after points failure: {e}")
                    # Уведомляем админа о критической ошибке
                    await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось откатить продление ключа после неудачного списания баллов:\nКлюч: {email}\nПользователь: {user_id}\nОшибка: {str(e)}")
                await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при списании баллов!", menu_type='extend_key')
                return
            # Очищаем старые уведомления об истечении для продленного ключа
            if notification_manager:
                await notification_manager.clear_key_notifications(user_id, email)
            
            # Получаем новое время истечения
            clients_response = xui.list()
            expiry_str = "—"
            if clients_response.get('success', False):
                for inbound in clients_response.get('obj', []):
                    settings = json.loads(inbound.get('settings', '{}'))
                    for client in settings.get('clients', []):
                        if client.get('email') == email:
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                            break
            
            message = UIMessages.key_extended_message(
                email=email,
                server_name=server_name,
                days=points_days,
                expiry_str=expiry_str,
                period=None  # Для продления за баллы период не указываем
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
            ])
            
            await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')
        else:
            # Ключ не продлен - баллы не списывались, просто сообщаем об ошибке
            await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при продлении ключа.", menu_type='extend_key')
            
    except Exception as e:
        logger.error(f"Ошибка продления выбранного ключа за баллы: {e}")
        # Баллы не списывались, просто сообщаем об ошибке
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при продлении.", menu_type='extend_key')

async def extend_points_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора ключа для продления за баллы"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    callback_data = update.callback_query.data
    
    # Извлекаем short_id из callback_data
    if not callback_data.startswith("extend_points_key:"):
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Неверный запрос!", menu_type='extend_key')
        return
    
    short_id = callback_data.split(":", 1)[1]
    
    # Получаем информацию о ключе из кэша
    if short_id not in extension_keys_cache:
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Ключ не найден или устарел!", menu_type='extend_key')
        return
    
    key_info = extension_keys_cache[short_id]
    
    # Проверяем, что ключ принадлежит пользователю
    if key_info['user_id'] != user_id:
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Доступ запрещен!", menu_type='extend_key')
        return
    
    # Создаем объект client для совместимости
    client = {
        'email': key_info['email'],
        'xui': key_info['xui'],
        'server_name': key_info['server_name']
    }
    
    # Продлеваем ключ
    await extend_selected_key_with_points(update, context, client, user_id)

async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает реферальную информацию"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    
    # Добавляем логирование для диагностики
    logger.info(f"REFERRAL_CALLBACK: user_id={user_id}")
    
    stats = await get_referral_stats(user_id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '30')
    
    # Логируем полученную статистику
    logger.info(f"REFERRAL_CALLBACK: stats={stats}, points={points_info}")
    
    # Генерируем реферальную ссылку
    referral_code = generate_referral_code(user_id)
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Используем единый стиль для реферального меню
    message = (
        f"{UIStyles.header('Реферальная программа')}\n\n"
        f"<b>Ваши баллы:</b> {UIStyles.highlight(str(points_info['points']))}\n\n"
        f"<b>Статистика рефералов:</b>\n"
        f"Всего приглашено: {stats['total_referrals']}\n"
        f"Успешных рефералов: {stats['successful_referrals']}\n"
        f"Ожидают покупки: {stats['pending_referrals']}\n\n"
        f"<b>Как заработать баллы:</b>\n"
        f"1. Поделитесь ссылкой с друзьями\n"
        f"2. Друг переходит по ссылке\n"
        f"3. Если друг НИКОГДА не пользовался ботом - он покупает и вы получаете 1 балл!\n"
        f"4. Если друг УЖЕ пользовался ботом - балл не выдается\n"
        f"5. 1 балл = {points_days} дней VPN бесплатно!\n\n"
        f"{UIStyles.warning_message('Важно: Балл выдается только за привлечение новых клиентов!')}\n\n"
        f"<b>Ваша реферальная ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"<b>Как поделиться:</b>\n"
        f"{UIStyles.description('• Нажмите на ссылку выше, чтобы скопировать')}\n"
        + UIStyles.description('• Или используйте кнопку "Поделиться в Telegram"')
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Поделиться в Telegram", url=f"https://t.me/share/url?url={referral_link}")],
        [UIButtons.back_button()]
    ])
    
    await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='referral_menu')

async def rename_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик переименования ключа"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    short_id = query.data.split(':')[1]
    
    try:
        # Ищем ключ по short_id
        key_email = None
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(f"{user_id}_") or client['email'].startswith(f"trial_{user_id}_"):
                            # Проверяем short_id
                            import hashlib
                            possible_short_ids = [
                                hashlib.md5(f"rename:{client['email']}".encode()).hexdigest()[:8]
                            ]
                            if short_id in possible_short_ids:
                                key_email = client['email']
                                break
                    if key_email:
                        break
                if key_email:
                    break
            except Exception as e:
                logger.error(f"Ошибка при поиске ключа на сервере {server['name']}: {e}")
                continue
        
        if not key_email:
            await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ключ не найден!")
            return
        
        # Сохраняем email ключа и message_id в контексте для последующего использования
        context.user_data['rename_key_email'] = key_email
        context.user_data['rename_message_id'] = query.message.message_id
        context.user_data['rename_chat_id'] = query.message.chat_id
        
        # Запрашиваем новое имя ключа
        message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"<b>Текущий ключ:</b> <code>{key_email}</code>\n\n"
            f"{UIStyles.description('Введите новое имя для ключа (максимум 50 символов):')}\n\n"
            f"{UIStyles.warning_message('Имя будет отображаться в списке ваших ключей')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        await safe_edit_or_reply_universal(query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='rename_key')
        
        # Устанавливаем состояние ожидания ввода имени
        context.user_data['waiting_for_key_name'] = True
        
    except Exception as e:
        logger.error(f"Ошибка в rename_key_callback: {e}")
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка при переименовании ключа!")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для переименования ключей"""
    if not await check_private_chat(update):
        return
    
    # Проверяем, ожидаем ли мы ввод имени ключа
    if not context.user_data.get('waiting_for_key_name', False):
        return
    
    user_id = str(update.message.from_user.id)
    new_name = update.message.text.strip()
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Получаем данные из контекста
    message_id = context.user_data.get('rename_message_id')
    chat_id = context.user_data.get('rename_chat_id')
    
    if not message_id or not chat_id:
        logger.error("Не найдены message_id или chat_id в контексте")
        return
    
    # Данные для редактирования сообщения получены из контекста
    
    # Валидация имени
    if len(new_name) > 50:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя ключа слишком длинное!\n\n"
            f"{UIStyles.description('Максимум 50 символов. Попробуйте еще раз.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            # Редактируем сообщение через бота
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='rename_key'
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    if not new_name:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя ключа не может быть пустым!\n\n"
            f"{UIStyles.description('Введите корректное имя для ключа.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            # Редактируем сообщение через бота
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='rename_key'
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    try:
        key_email = context.user_data.get('rename_key_email')
        if not key_email:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден в контексте!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
            return
        
        # Находим сервер с ключом
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден на серверах!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
            return
        
        # Обновляем имя ключа
        response = xui.updateClientName(key_email, new_name)
        
        if response and response.status_code == 200:
            # Очищаем состояние
            context.user_data.pop('waiting_for_key_name', None)
            context.user_data.pop('rename_key_email', None)
            context.user_data.pop('rename_message_id', None)
            context.user_data.pop('rename_chat_id', None)
            
            # Показываем успешное сообщение в том же окне
            success_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.SUCCESS} <b>Ключ успешно переименован!</b>\n\n"
                f"<b>Новое имя:</b> {new_name}\n"
                f"<b>Email:</b> <code>{key_email}</code>\n\n"
                f"{UIStyles.description('Имя будет отображаться в списке ваших ключей')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Мои ключи", callback_data="mykey")],
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=success_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
        else:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Не удалось обновить имя ключа на сервере!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при переименовании ключа: {e}")
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> {str(e)}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='extend_key'
            )
        except Exception as edit_e:
            logger.error(f"Ошибка редактирования сообщения: {edit_e}")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'Нет доступа.')
        return
    
    # Очищаем состояние всех ConversationHandler'ов при входе в админ меню
    context.user_data.pop('broadcast_text', None)
    context.user_data.pop('broadcast_msg_chat_id', None)
    context.user_data.pop('broadcast_msg_id', None)
    context.user_data.pop('broadcast_details', None)
    context.user_data.pop('config_message_id', None)
    context.user_data.pop('config_chat_id', None)
    
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'admin_menu':
        push_nav(context, 'admin_menu')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Логи", callback_data="admin_errors")],
        [InlineKeyboardButton("Проверка серверов", callback_data="admin_check_servers")],
        [InlineKeyboardButton("Уведомления", callback_data="admin_notifications")],
        [InlineKeyboardButton("Рассылка", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("Изменить дни за балл", callback_data="admin_set_days_start")],
        [UIButtons.back_button()],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("admin_menu: message is None")
        return
    
    # Используем единый стиль для админ-меню с фото
    admin_menu_text = UIMessages.admin_menu_message()
    await safe_edit_or_reply_universal(message, admin_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')


# ===== РАССЫЛКА ДЛЯ АДМИНА =====
BROADCAST_WAITING_TEXT = 1001
BROADCAST_CONFIRM = 1002

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.callback_query.message, 'Нет доступа.')
        return
    await update.callback_query.answer()
    # Сохраняем исходное сообщение для дальнейших редактирований
    context.user_data['broadcast_text'] = None
    context.user_data['broadcast_msg_chat_id'] = update.callback_query.message.chat_id
    context.user_data['broadcast_msg_id'] = update.callback_query.message.message_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="admin_broadcast_back")]])
    await safe_edit_or_reply_universal(update.callback_query.message, UIMessages.broadcast_intro_message(), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type='broadcast')
    return BROADCAST_WAITING_TEXT

async def admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    text = update.message.text
    context.user_data['broadcast_text'] = text
    # Удаляем сообщение админа с текстом
    try:
        await update.message.delete()
    except Exception:
        pass
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Отправить", callback_data="admin_broadcast_send")],
        [InlineKeyboardButton("← Назад", callback_data="admin_broadcast_back")]
    ])
    # Редактируем исходное сообщение на предпросмотр
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=UIMessages.broadcast_preview_message(text),
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения рассылки: {e}")
        # Fallback: отправляем новое сообщение
        await safe_send_message_with_photo(
            context.bot,
            chat_id=chat_id,
            text=UIMessages.broadcast_preview_message(text),
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    return BROADCAST_CONFIRM

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.callback_query.answer()
    text = context.user_data.get('broadcast_text')
    if not text:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=context.user_data.get('broadcast_msg_chat_id'),
            message_id=context.user_data.get('broadcast_msg_id'),
            text=f"{UIEmojis.ERROR} Текст рассылки пуст.",
            menu_type='broadcast'
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
            menu_type='broadcast'
        )
    except Exception:
        pass
    for i in range(0, total, batch):
        chunk = recipients[i:i+batch]
        for user_id in chunk:
            try:
                await context.bot.send_message(chat_id=int(user_id), text=text, parse_mode="HTML", disable_web_page_preview=True)
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
                    await context.bot.send_message(chat_id=int(user_id), text=text, parse_mode="HTML", disable_web_page_preview=True)
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
                menu_type='broadcast'
            )
        except Exception:
            pass

    # сохраняем детали в user_data для кнопок
    context.user_data['broadcast_details'] = details
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Экспорт CSV", callback_data="admin_broadcast_export")],
        [InlineKeyboardButton("← Назад", callback_data="admin_broadcast_back")]
    ])
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования финального сообщения рассылки: {e}")
        await safe_send_message_with_photo(
            context.bot,
            chat_id=chat_id,
            text=f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    return ConversationHandler.END

async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    
    # Очищаем состояние рассылки
    context.user_data.pop('broadcast_text', None)
    context.user_data.pop('broadcast_msg_chat_id', None)
    context.user_data.pop('broadcast_msg_id', None)
    context.user_data.pop('broadcast_details', None)
    
    await admin_menu(update, context)
    return ConversationHandler.END

async def admin_broadcast_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.callback_query.answer()
    import io, csv
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

# Регистрируем команды
if __name__ == '__main__':
    # Создаем HTTPXRequest с увеличенными таймаутами для стабильной работы
    http_request = HTTPXRequest(
        connection_pool_size=8,  # Размер пула соединений
        connect_timeout=30.0,    # Таймаут на установку соединения (увеличен с дефолтных 5)
        read_timeout=30.0,       # Таймаут на чтение ответа (увеличен с дефолтных 5)
        write_timeout=30.0,      # Таймаут на отправку данных
        pool_timeout=30.0        # Таймаут ожидания свободного соединения в пуле
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(http_request).post_init(on_startup).build()
    
    # Создаем Flask приложение для webhook'ов
    webhook_app = create_webhook_app(app)
    
    # Запускаем webhook сервер в отдельном потоке
    def run_webhook():
        webhook_app.run(host='0.0.0.0', port=5000, debug=False)
    
    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("Webhook сервер запущен на порту 5000")
    
    # Добавляем глобальную обработку ошибок
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('mykey', mykey))
    app.add_handler(CommandHandler('instruction', instruction))
   
    app.add_handler(CommandHandler('check_servers', force_check_servers))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^instr_"))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^back_instr$"))
    app.add_handler(CallbackQueryHandler(extend_key_callback, pattern="^ext_key:"))
    app.add_handler(CallbackQueryHandler(extend_period_callback, pattern="^ext_per:"))

    # ConversationHandler для интерактивной настройки дней за балл
    admin_set_days_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_set_days_start, pattern="^admin_set_days_start$")],
        states={
            WAITING_FOR_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_days_input),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin_set_days_cancel, pattern="^admin_set_days_cancel$")
        ],
        per_user=True,
        per_chat=True,
        per_message=False
    )
    app.add_handler(admin_set_days_conv)
    
    app.add_handler(CommandHandler('admin_errors', admin_errors))
    app.add_handler(CommandHandler('admin_check_servers', admin_check_servers))
    app.add_handler(CommandHandler('admin_notifications', admin_notifications))
    app.add_handler(CommandHandler('admin_config', admin_config))
    app.add_handler(CommandHandler('admin_set_days', admin_set_days))
    app.add_handler(CallbackQueryHandler(start_callback_handler, pattern="^(buy_menu|buy_month|buy_3month|select_period_.*|select_server_.*|mykey|instruction|keys_page_.*)$"))
    app.add_handler(CallbackQueryHandler(select_server_callback, pattern="^(select_server_.*|server_unavailable_.*|refresh_servers)$"))
    app.add_handler(CallbackQueryHandler(universal_back_callback, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(admin_menu, pattern="^admin_menu$"))
    # Добавляем обработчики для админ-меню
    app.add_handler(CallbackQueryHandler(admin_errors, pattern="^admin_errors$"))
    app.add_handler(CallbackQueryHandler(admin_errors, pattern="^admin_errors_refresh$"))
    app.add_handler(CallbackQueryHandler(admin_check_servers, pattern="^admin_check_servers$"))
    app.add_handler(CallbackQueryHandler(admin_notifications, pattern="^admin_notifications$"))
    app.add_handler(CallbackQueryHandler(admin_notifications, pattern="^admin_notifications_refresh$"))
    
    # Рассылка
    admin_broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$")],
        states={
            BROADCAST_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_input),
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_send, pattern="^admin_broadcast_send$"),
                CallbackQueryHandler(admin_broadcast_cancel, pattern="^back$")
            ]
        },
        fallbacks=[CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$")],
        per_user=True,
        per_chat=True,
        per_message=False
    )
    app.add_handler(admin_broadcast_conv)
    # Глобальный обработчик экспорта, чтобы работал и после завершения диалога
    app.add_handler(CallbackQueryHandler(admin_broadcast_export, pattern="^admin_broadcast_export$"))
    # Глобальный обработчик для кнопки рассылки (на случай если ConversationHandler заблокирован)
    app.add_handler(CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$"))
    # Глобальный обработчик для кнопки изменения дней (на случай если ConversationHandler заблокирован)
    app.add_handler(CallbackQueryHandler(admin_set_days_start, pattern="^admin_set_days_start$"))
    # Глобальный обработчик для кнопки назад в рассылке
    app.add_handler(CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$"))

    
    # Обработчики для реферальной системы
    app.add_handler(CallbackQueryHandler(points_callback, pattern="^points$"))
    app.add_handler(CallbackQueryHandler(spend_points_callback, pattern="^spend_points$"))
    app.add_handler(CallbackQueryHandler(buy_with_points_callback, pattern="^buy_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_with_points_callback, pattern="^extend_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_points_key_callback, pattern="^extend_points_key:"))
    app.add_handler(CallbackQueryHandler(referral_callback, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(rename_key_callback, pattern="^rename_key:"))
    
    # Обработчик текстовых сообщений для переименования ключей
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    app.run_polling()
