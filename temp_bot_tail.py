async def process_payment_webhook(bot_app, payment_id, status):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РїР»Р°С‚РµР¶ РёР· webhook'Р°"""
    try:
        # РџРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїР»Р°С‚РµР¶Рµ РёР· Р±Р°Р·С‹ РґР°РЅРЅС‹С…
        payment_info = await get_payment(payment_id)
        if not payment_info:
            logger.warning(f"РџР»Р°С‚РµР¶ {payment_id} РЅРµ РЅР°Р№РґРµРЅ РІ Р±Р°Р·Рµ РґР°РЅРЅС‹С…")
            return
        
        user_id = payment_info['user_id']
        meta = json.loads(payment_info['meta'])
        
        logger.info(f"РћР±СЂР°Р±РѕС‚РєР° webhook РїР»Р°С‚РµР¶Р°: payment_id={payment_id}, user_id={user_id}, status={status}")
        
        # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј РїР»Р°С‚РµР¶ Р°РЅР°Р»РѕРіРёС‡РЅРѕ auto_activate_keys
        if status == 'succeeded':
            # РЈСЃРїРµС€РЅР°СЏ РѕРїР»Р°С‚Р° - РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РєР°Рє РІ auto_activate_keys
            await process_successful_payment(bot_app, payment_id, user_id, meta)
        elif status in ['canceled', 'refunded']:
            # РћС‚РјРµРЅРµРЅРЅР°СЏ/РІРѕР·РІСЂР°С‰РµРЅРЅР°СЏ РѕРїР»Р°С‚Р°
            await process_canceled_payment(bot_app, payment_id, user_id, meta, status)
        elif status not in ['pending']:
            # Р›СЋР±РѕР№ РґСЂСѓРіРѕР№ РЅРµСѓСЃРїРµС€РЅС‹Р№ СЃС‚Р°С‚СѓСЃ
            await process_failed_payment(bot_app, payment_id, user_id, meta, status)
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё webhook РїР»Р°С‚РµР¶Р° {payment_id}: {e}")


async def process_successful_payment(bot_app, payment_id, user_id, meta):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ СѓСЃРїРµС€РЅС‹Р№ РїР»Р°С‚РµР¶"""
    try:
        period = meta.get('type', 'month')
        message_id = payment_message_ids.get(payment_id)
        
        # РџСЂРѕРІРµСЂСЏРµРј, СЌС‚Рѕ РїСЂРѕРґР»РµРЅРёРµ РёР»Рё РЅРѕРІР°СЏ РїРѕРєСѓРїРєР°
        is_extension = period.startswith('extend_')
        if is_extension:
            # РћР±СЂР°Р±РѕС‚РєР° РїСЂРѕРґР»РµРЅРёСЏ (РєРѕРґ РёР· auto_activate_keys)
            await process_extension_payment(bot_app, payment_id, user_id, meta, message_id)
        else:
            # РћР±СЂР°Р±РѕС‚РєР° РЅРѕРІРѕР№ РїРѕРєСѓРїРєРё (РєРѕРґ РёР· auto_activate_keys)
            await process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id)
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё СѓСЃРїРµС€РЅРѕРіРѕ РїР»Р°С‚РµР¶Р° {payment_id}: {e}")


async def process_extension_payment(bot_app, payment_id, user_id, meta, message_id):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РїСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р°"""
    try:
        period = meta.get('type', 'month')
        actual_period = period.replace('extend_', '')  # СѓР±РёСЂР°РµРј РїСЂРµС„РёРєСЃ extend_
        days = 90 if actual_period == '3month' else 30
        extension_email = meta.get('extension_key_email')
        
        logger.info(f"РћР±СЂР°Р±РѕС‚РєР° РїСЂРѕРґР»РµРЅРёСЏ РєР»СЋС‡Р°: email={extension_email}, period={actual_period}, days={days}")
        
        if not extension_email:
            logger.error(f"РќРµ РЅР°Р№РґРµРЅ email РєР»СЋС‡Р° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ РІ meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # РС‰РµРј СЃРµСЂРІРµСЂ СЃ РєР»СЋС‡РѕРј РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ
        try:
            xui, server_name = server_manager.find_client_on_any_server(extension_email)
            if not xui or not server_name:
                logger.error(f"РљР»СЋС‡ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ РЅРµ РЅР°Р№РґРµРЅ: {extension_email}")
                await update_payment_status(payment_id, 'failed')
                
                # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ РѕР± РѕС€РёР±РєРµ РїСЂРѕРґР»РµРЅРёСЏ
                if message_id:
                    error_message = (
                        f"{UIStyles.header('РћС€РёР±РєР° РїСЂРѕРґР»РµРЅРёСЏ')}\n\n"
                        f"{UIEmojis.ERROR} <b>РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕРґР»РёС‚СЊ РєР»СЋС‡!</b>\n\n"
                        f"<b>РљР»СЋС‡:</b> {extension_email}\n"
                        f"<b>РџСЂРёС‡РёРЅР°:</b> РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РЅР° СЃРµСЂРІРµСЂРµ\n\n"
                        f"{UIStyles.description('РџРѕРїСЂРѕР±СѓР№С‚Рµ РїСЂРѕРґР»РёС‚СЊ Р·Р°РЅРѕРІРѕ РёР»Рё РѕР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ')}"
                    )
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("РџРѕРїСЂРѕР±РѕРІР°С‚СЊ СЃРЅРѕРІР°", callback_data="mykey")],
                        [InlineKeyboardButton("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="main_menu")]
                    ])
                    
                    await safe_edit_message_with_photo(
                        bot_app,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                return
            
            # РџСЂРѕРґР»РµРІР°РµРј РєР»СЋС‡
            response = xui.extendClient(extension_email, days)
            if response and response.status_code == 200:
                await update_payment_status(payment_id, 'succeeded')
                await update_payment_activation(payment_id, 1)
                
                # РџСЂРѕРІРµСЂСЏРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃРІСЏР·СЊ Рё РІС‹РґР°РµРј Р±Р°Р»Р»С‹
                try:
                    referrer_id = await get_pending_referral(user_id)
                    if referrer_id:
                        # Р’С‹РґР°РµРј 1 Р±Р°Р»Р» СЂРµС„РµСЂРµСЂСѓ
                        await add_points(
                            referrer_id, 
                            1, 
                            f"Р РµС„РµСЂР°Р»: {user_id} РїСЂРѕРґР»РёР» VPN",
                            payment_id
                        )
                        
                        # РћС‚РјРµС‡Р°РµРј РЅР°РіСЂР°РґСѓ РєР°Рє РІС‹РґР°РЅРЅСѓСЋ
                        await mark_referral_reward_given(referrer_id, user_id, payment_id)
                        
                        # РЈРІРµРґРѕРјР»СЏРµРј СЂРµС„РµСЂРµСЂР°
                        try:
                            points_days = await get_config('points_days_per_point', '14')
                            await bot_app.send_message(
                                chat_id=referrer_id,
                                text=(
                                    f"РџРѕР·РґСЂР°РІР»СЏРµРј!\n\n"
                                    "Р’Р°С€ РґСЂСѓРі РїСЂРѕРґР»РёР» VPN РїРѕ РІР°С€РµР№ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ!\n"
                                    f"Р’С‹ РїРѕР»СѓС‡РёР»Рё 1 Р±Р°Р»Р»!\n"
                                    f"1 Р±Р°Р»Р» = {points_days} РґРЅРµР№ VPN Р±РµСЃРїР»Р°С‚РЅРѕ!\n\n"
                                    "РСЃРїРѕР»СЊР·СѓР№С‚Рµ Р±Р°Р»Р»С‹ РґР»СЏ РїРѕРєСѓРїРєРё РёР»Рё РїСЂРѕРґР»РµРЅРёСЏ VPN!"
                                )
                            )
                        except:
                            pass
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РІС‹РґР°С‡Рё СЂРµС„РµСЂР°Р»СЊРЅС‹С… Р±Р°Р»Р»РѕРІ РїСЂРё РїСЂРѕРґР»РµРЅРёРё: {e}")
                
                # РћС‚РїСЂР°РІР»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ Рѕ РїСЂРѕРґР»РµРЅРёРё
                try:
                    # РџРѕР»СѓС‡Р°РµРј РЅРѕРІРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ
                    clients_response = xui.list()
                    expiry_str = "вЂ”"
                    if clients_response.get('success', False):
                        for inbound in clients_response.get('obj', []):
                            settings = json.loads(inbound.get('settings', '{}'))
                            for client in settings.get('clients', []):
                                if client.get('email') == extension_email:
                                    expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                    expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else 'вЂ”'
                                    break
                    
                    # РћС‡РёС‰Р°РµРј СЃС‚Р°СЂС‹Рµ СѓРІРµРґРѕРјР»РµРЅРёСЏ РѕР± РёСЃС‚РµС‡РµРЅРёРё РґР»СЏ РїСЂРѕРґР»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р°
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
                            [InlineKeyboardButton("РњРѕРё РєР»СЋС‡Рё", callback_data="mykey")],
                            [InlineKeyboardButton("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="main_menu")]
                        ])
                        
                        await safe_edit_message_with_photo(
                            bot_app,
                            chat_id=int(user_id),
                            message_id=message_id,
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                        )
                        logger.info(f"РћС‚СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ Рѕ РїСЂРѕРґР»РµРЅРёРё РєР»СЋС‡Р° {extension_email} РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {user_id}")
                        
                        # РЈРґР°Р»СЏРµРј message_id РёР· РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ
                        payment_message_ids.pop(payment_id, None)
                    else:
                        # Fallback: РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
                        await safe_send_message_with_photo(
                            bot_app,
                            chat_id=int(user_id),
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                        )
                        logger.info(f"РћС‚РїСЂР°РІР»РµРЅРѕ РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ Рѕ РїСЂРѕРґР»РµРЅРёРё РєР»СЋС‡Р° {extension_email} РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {user_id}")
                        
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СѓРІРµРґРѕРјР»РµРЅРёСЏ Рѕ РїСЂРѕРґР»РµРЅРёРё: {e}")
            else:
                logger.error(f"РћС€РёР±РєР° РїСЂРѕРґР»РµРЅРёСЏ РєР»СЋС‡Р° {extension_email}: {response}")
                await update_payment_status(payment_id, 'failed')
                
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїСЂРѕРґР»РµРЅРёРё РєР»СЋС‡Р° {extension_email}: {e}")
            await update_payment_status(payment_id, 'failed')
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё РїСЂРѕРґР»РµРЅРёСЏ РєР»СЋС‡Р° {payment_id}: {e}")


async def process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РЅРѕРІСѓСЋ РїРѕРєСѓРїРєСѓ"""
    try:
        period = meta.get('type', 'month')
        days = 90 if period == '3month' else 30
        unique_email = meta.get('unique_email')
        selected_location = meta.get('selected_location', 'auto')
        
        logger.info(f"РћР±СЂР°Р±РѕС‚РєР° РЅРѕРІРѕР№ РїРѕРєСѓРїРєРё: period={period}, days={days}, email={unique_email}")
        
        if not unique_email:
            logger.error(f"РќРµ РЅР°Р№РґРµРЅ unique_email РІ meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # РЎРѕР·РґР°РЅРёРµ РєР»СЋС‡Р°
        try:
            if selected_location == "auto":
                # Р”Р»СЏ Р°РІС‚РѕРІС‹Р±РѕСЂР° РІС‹Р±РёСЂР°РµРј Р»СѓС‡С€СѓСЋ Р»РѕРєР°С†РёСЋ
                xui, server_name = new_client_manager.get_best_location_server()
            else:
                xui, server_name = new_client_manager.get_server_by_user_choice(selected_location, "auto")
            
            response = xui.addClient(day=days, tg_id=user_id, user_email=unique_email, timeout=15)
            
            if response.status_code == 200:
                await update_payment_status(payment_id, 'succeeded')
                await update_payment_activation(payment_id, 1)
                
                # РџСЂРѕРІРµСЂСЏРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃРІСЏР·СЊ Рё РІС‹РґР°РµРј Р±Р°Р»Р»С‹
                try:
                    referrer_id = await get_pending_referral(user_id)
                    if referrer_id:
                        # Р’С‹РґР°РµРј 1 Р±Р°Р»Р» СЂРµС„РµСЂРµСЂСѓ
                        await add_points(
                            referrer_id, 
                            1, 
                            f"Р РµС„РµСЂР°Р»: {user_id} РєСѓРїРёР» VPN",
                            payment_id
                        )
                        
                        # РћС‚РјРµС‡Р°РµРј РЅР°РіСЂР°РґСѓ РєР°Рє РІС‹РґР°РЅРЅСѓСЋ
                        await mark_referral_reward_given(referrer_id, user_id, payment_id)
                        
                        # РЈРІРµРґРѕРјР»СЏРµРј СЂРµС„РµСЂРµСЂР°
                        try:
                            points_days = await get_config('points_days_per_point', '14')
                            await bot_app.send_message(
                                chat_id=referrer_id,
                                text=(
                                    f"РџРѕР·РґСЂР°РІР»СЏРµРј!\n\n"
                                    "Р’Р°С€ РґСЂСѓРі РєСѓРїРёР» VPN РїРѕ РІР°С€РµР№ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ!\n"
                                    f"Р’С‹ РїРѕР»СѓС‡РёР»Рё 1 Р±Р°Р»Р»!\n"
                                    f"1 Р±Р°Р»Р» = {points_days} РґРЅРµР№ VPN Р±РµСЃРїР»Р°С‚РЅРѕ!\n\n"
                                    "РСЃРїРѕР»СЊР·СѓР№С‚Рµ Р±Р°Р»Р»С‹ РґР»СЏ РїРѕРєСѓРїРєРё РёР»Рё РїСЂРѕРґР»РµРЅРёСЏ VPN!"
                                )
                            )
                        except:
                            pass
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РІС‹РґР°С‡Рё СЂРµС„РµСЂР°Р»СЊРЅС‹С… Р±Р°Р»Р»РѕРІ РїСЂРё РїРѕРєСѓРїРєРµ: {e}")
                
                # РћС‚РїСЂР°РІРєР° РєР»СЋС‡Р° РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
                try:
                    # РџРѕР»СѓС‡Р°РµРј СЂРµР°Р»СЊРЅРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ РёР· XUI API
                    clients_response = xui.list()
                    expiry_str = "вЂ”"
                    expiry_timestamp = 0
                    
                    if clients_response.get('success', False):
                        clients = clients_response.get('obj', [])
                        for inbound in clients:
                            settings = json.loads(inbound.get('settings', '{}'))
                            for client in settings.get('clients', []):
                                if client.get('email') == unique_email:
                                    # РџРѕР»СѓС‡Р°РµРј С‚РѕС‡РЅРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ РёР· API
                                    expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                    expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else 'вЂ”'
                                    break
                            else:
                                continue
                            break
                    else:
                        # Fallback: РІС‹С‡РёСЃР»СЏРµРј РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ
                        expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
                        expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                        expiry_timestamp = int(expiry_time.timestamp())
                    
                    msg = format_vpn_key_message(
                        email=unique_email,
                        status='РђРєС‚РёРІРµРЅ',
                        server=server_name,
                        expiry=expiry_str,
                        key=xui.link(unique_email),
                        expiry_timestamp=expiry_timestamp
                    )
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
                    ])
                    
                    # Р¤РѕСЂРјРёСЂСѓРµРј РїРѕР»РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ Рѕ РїРѕРєСѓРїРєРµ
                    success_text = UIMessages.success_purchase_message(period, meta.get('price', '100'))
                    full_message = success_text + msg
                    
                    # Р•СЃР»Рё РµСЃС‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РѕРїР»Р°С‚РѕР№, СЂРµРґР°РєС‚РёСЂСѓРµРј РµРіРѕ
                    if message_id:
                        try:
                            await safe_edit_message_with_photo(
                                bot_app,
                                chat_id=int(user_id),
                                message_id=message_id,
                                text=full_message,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type='key_success'
                            )
                            logger.info(f"РћС‚СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РѕРїР»Р°С‚РѕР№ {message_id} РЅР° РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР»СЋС‡Рµ")
                        except Exception as edit_error:
                            logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ {message_id}: {edit_error}")
                            # Fallback: РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
                            await safe_send_message_with_photo(
                                bot_app,
                                chat_id=int(user_id),
                                text=full_message,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type='key_success'
                            )
                            logger.info(f"РћС‚РїСЂР°РІР»РµРЅРѕ РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РєР»СЋС‡РѕРј РґР»СЏ user_id={user_id}")
                    else:
                        # Р•СЃР»Рё РЅРµС‚ СЃРѕРѕР±С‰РµРЅРёСЏ СЃ РѕРїР»Р°С‚РѕР№, РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ
                        await safe_send_message_with_photo(
                            bot_app,
                            chat_id=int(user_id),
                            text=full_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='key_success'
                        )
                        logger.info(f"РћС‚РїСЂР°РІР»РµРЅРѕ РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РєР»СЋС‡РѕРј РґР»СЏ user_id={user_id}")
                    
                    # РЈРґР°Р»СЏРµРј message_id РёР· РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ
                    payment_message_ids.pop(payment_id, None)
                    
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё РєР»СЋС‡Р° РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ: {e}")
            else:
                logger.error(f"РћС€РёР±РєР° СЃРѕР·РґР°РЅРёСЏ РєР»СЋС‡Р°: {response}")
                await update_payment_status(payment_id, 'failed')
                
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РєР»СЋС‡Р°: {e}")
            await update_payment_status(payment_id, 'failed')
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё РЅРѕРІРѕР№ РїРѕРєСѓРїРєРё {payment_id}: {e}")


async def process_canceled_payment(bot_app, payment_id, user_id, meta, status):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РѕС‚РјРµРЅРµРЅРЅС‹Р№ РїР»Р°С‚РµР¶"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ РѕР± РѕС€РёР±РєРµ РѕРїР»Р°С‚С‹
        message_id = payment_message_ids.get(payment_id)
        if message_id:
            error_message = (
                f"{UIStyles.header('РћС€РёР±РєР° РѕРїР»Р°С‚С‹')}\n\n"
                f"{UIEmojis.ERROR} <b>РџР»Р°С‚РµР¶ РЅРµ РїСЂРѕС€РµР»!</b>\n\n"
                f"<b>РџСЂРёС‡РёРЅР°:</b> РџР»Р°С‚РµР¶ Р±С‹Р» РѕС‚РјРµРЅРµРЅ РёР»Рё РІРѕР·РІСЂР°С‰РµРЅ\n"
                f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status}\n\n"
                f"{UIStyles.description('РџРѕРїСЂРѕР±СѓР№С‚Рµ РѕРїР»Р°С‚РёС‚СЊ Р·Р°РЅРѕРІРѕ РёР»Рё РѕР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("РџРѕРїСЂРѕР±РѕРІР°С‚СЊ СЃРЅРѕРІР°", callback_data="buy_menu")],
                [InlineKeyboardButton("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="main_menu")]
            ])
            
            await safe_edit_message_with_photo(
                bot_app,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='payment_failed'
            )
            logger.info(f"РћС‚РїСЂР°РІР»РµРЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ РѕРїР»Р°С‚С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {user_id}")
            
            # РЈРґР°Р»СЏРµРј message_id РёР· РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ
            payment_message_ids.pop(payment_id, None)
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё РѕС‚РјРµРЅРµРЅРЅРѕРіРѕ РїР»Р°С‚РµР¶Р° {payment_id}: {e}")


async def process_failed_payment(bot_app, payment_id, user_id, meta, status):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РЅРµСѓРґР°С‡РЅС‹Р№ РїР»Р°С‚РµР¶"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        # РћРїСЂРµРґРµР»СЏРµРј С‚РёРї РїР»Р°С‚РµР¶Р° РґР»СЏ РїСЂР°РІРёР»СЊРЅРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
        period = meta.get('type', 'month')
        is_extension = period.startswith('extend_')
        
        message_id = payment_message_ids.get(payment_id)
        if message_id:
            if is_extension:
                # РћС€РёР±РєР° РїСЂРѕРґР»РµРЅРёСЏ
                extension_email = meta.get('extension_key_email', 'РќРµРёР·РІРµСЃС‚РЅРѕ')
                error_message = (
                    f"{UIStyles.header('РћС€РёР±РєР° РїСЂРѕРґР»РµРЅРёСЏ')}\n\n"
                    f"{UIEmojis.ERROR} <b>РџР»Р°С‚РµР¶ РЅРµ РїСЂРѕС€РµР»!</b>\n\n"
                    f"<b>РљР»СЋС‡:</b> {extension_email}\n"
                    f"<b>РџСЂРёС‡РёРЅР°:</b> РџР»Р°С‚РµР¶ Р±С‹Р» РѕС‚РєР»РѕРЅРµРЅ\n"
                    f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status}\n\n"
                    f"{UIStyles.description('РџРѕРїСЂРѕР±СѓР№С‚Рµ РїСЂРѕРґР»РёС‚СЊ Р·Р°РЅРѕРІРѕ РёР»Рё РѕР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("РџРѕРїСЂРѕР±РѕРІР°С‚СЊ СЃРЅРѕРІР°", callback_data="mykey")],
                    [InlineKeyboardButton("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="main_menu")]
                ])
                
                menu_type = 'extend_key'
            else:
                # РћС€РёР±РєР° РѕР±С‹С‡РЅРѕР№ РїРѕРєСѓРїРєРё
                error_message = (
                    f"{UIStyles.header('РћС€РёР±РєР° РѕРїР»Р°С‚С‹')}\n\n"
                    f"{UIEmojis.ERROR} <b>РџР»Р°С‚РµР¶ РЅРµ РїСЂРѕС€РµР»!</b>\n\n"
                    f"<b>РџСЂРёС‡РёРЅР°:</b> РџР»Р°С‚РµР¶ Р±С‹Р» РѕС‚РєР»РѕРЅРµРЅ\n"
                    f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status}\n\n"
                    f"{UIStyles.description('РџРѕРїСЂРѕР±СѓР№С‚Рµ РѕРїР»Р°С‚РёС‚СЊ Р·Р°РЅРѕРІРѕ РёР»Рё РѕР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("РџРѕРїСЂРѕР±РѕРІР°С‚СЊ СЃРЅРѕРІР°", callback_data="buy_menu")],
                    [InlineKeyboardButton("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="main_menu")]
                ])
                
                menu_type = 'payment_failed'
            
            await safe_edit_message_with_photo(
                bot_app,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type
            )
            logger.info(f"РћС‚РїСЂР°РІР»РµРЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {user_id}")
            
            # РЈРґР°Р»СЏРµРј message_id РёР· РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ
            payment_message_ids.pop(payment_id, None)
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё РЅРµСѓРґР°С‡РЅРѕРіРѕ РїР»Р°С‚РµР¶Р° {payment_id}: {e}")


async def auto_cleanup_expired_keys():
    """
    РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё СѓРґР°Р»СЏРµС‚ РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ РєР»СЋС‡Рё СЃРѕ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ
    РЈРґР°Р»СЏРµС‚ РєР»СЋС‡Рё, РєРѕС‚РѕСЂС‹Рµ РёСЃС‚РµРєР»Рё Р±РѕР»РµРµ 3 РґРЅРµР№ РЅР°Р·Р°Рґ
    """
    logger.info("Р—Р°РїСѓСЃРє Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРѕР№ РѕС‡РёСЃС‚РєРё РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹С… РєР»СЋС‡РµР№...")
    
    try:
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        # 3 РґРЅСЏ РїРѕСЃР»Рµ РёСЃС‚РµС‡РµРЅРёСЏ = 3 * 24 * 60 * 60 * 1000 РјРёР»Р»РёСЃРµРєСѓРЅРґ
        threshold_ms = now_ms - 3 * 24 * 60 * 60 * 1000
        total_deleted_count = 0
        
        # РћС‡РёС‰Р°РµРј РІСЃРµ СЃРµСЂРІРµСЂС‹
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                deleted_count = 0
                inbounds = xui.list()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients_to_delete = []
                    
                    # РЎРѕР±РёСЂР°РµРј СЃРїРёСЃРѕРє РєР»РёРµРЅС‚РѕРІ РґР»СЏ СѓРґР°Р»РµРЅРёСЏ
                    for client in settings.get("clients", []):
                        expiry = client.get('expiryTime', 0)
                        email = client.get('email', '')
                        
                        # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РєР»СЋС‡ РїСЂРѕСЃСЂРѕС‡РµРЅ Р±РѕР»РµРµ 3 РґРЅРµР№
                        if expiry and expiry < threshold_ms:
                            # РЈРґР°Р»СЏРµРј С‚РѕР»СЊРєРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРµ РєР»СЋС‡Рё (СЃ РїРѕРґС‡РµСЂРєРёРІР°РЅРёРµРј)
                            if '_' in email:
                                clients_to_delete.append(client)
                    
                    # РЈРґР°Р»СЏРµРј РЅР°Р№РґРµРЅРЅС‹С… РєР»РёРµРЅС‚РѕРІ
                    for client in clients_to_delete:
                        try:
                            client_id = client.get('id')
                            inbound_id = inbound['id']
                            email = client.get('email', '')
                            
                            # РР·РІР»РµРєР°РµРј user_id РёР· email (С„РѕСЂРјР°С‚: user_id_email@domain.com)
                            user_id = None
                            if '_' in email:
                                user_id = email.split('_')[0]
                            
                            # Р¤РѕСЂРјРёСЂСѓРµРј URL РґР»СЏ СѓРґР°Р»РµРЅРёСЏ
                            url = f"{xui.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                            logger.info(f"РђРІС‚РѕСѓРґР°Р»РµРЅРёРµ РїСЂРѕСЃСЂРѕС‡РµРЅРЅРѕРіРѕ РєР»СЋС‡Р°: inbound_id={inbound_id}, client_id={client_id}, email={email}")
                            
                            # РћС‚РїСЂР°РІР»СЏРµРј Р·Р°РїСЂРѕСЃ РЅР° СѓРґР°Р»РµРЅРёРµ
                            result = xui.ses.post(url)
                            if getattr(result, 'status_code', None) == 200:
                                deleted_count += 1
                                total_deleted_count += 1
                                
                                # Р’С‹С‡РёСЃР»СЏРµРј, СЃРєРѕР»СЊРєРѕ РґРЅРµР№ РЅР°Р·Р°Рґ РёСЃС‚РµРє РєР»СЋС‡
                                expiry_date = datetime.datetime.fromtimestamp(client.get('expiryTime', 0) / 1000)
                                days_expired = (datetime.datetime.now() - expiry_date).days
                                
                                logger.info(f'РђРІС‚РѕСѓРґР°Р»РµРЅ РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Р№ РєР»СЋС‡: {email} СЃ СЃРµСЂРІРµСЂР° {server["name"]} (РёСЃС‚РµРє {days_expired} РґРЅРµР№ РЅР°Р·Р°Рґ)')
                                
                                # РћС‡РёС‰Р°РµРј СЃРІСЏР·Р°РЅРЅС‹Рµ РґР°РЅРЅС‹Рµ РёР· РєСЌС€РµР№
                                try:
                                    # РћС‡РёС‰Р°РµРј extension_keys_cache
                                    keys_to_remove = []
                                    for short_id, key_email in extension_keys_cache.items():
                                        if key_email == email:
                                            keys_to_remove.append(short_id)
                                    for short_id in keys_to_remove:
                                        extension_keys_cache.pop(short_id, None)
                                    
                                    if keys_to_remove:
                                        logger.info(f"РћС‡РёС‰РµРЅРѕ {len(keys_to_remove)} Р·Р°РїРёСЃРµР№ РёР· extension_keys_cache РґР»СЏ СѓРґР°Р»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р° {email}")
                                    
                                    # РћС‡РёС‰Р°РµРј payment_message_ids (РїР»Р°С‚РµР¶Рё РґР»СЏ СЌС‚РѕРіРѕ РєР»СЋС‡Р°)
                                    payments_to_remove = []
                                    for payment_id in list(payment_message_ids.keys()):
                                        # РџСЂРѕРІРµСЂСЏРµРј, СЃРІСЏР·Р°РЅ Р»Рё РїР»Р°С‚РµР¶ СЃ СЌС‚РёРј РєР»СЋС‡РѕРј
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
                                        logger.info(f"РћС‡РёС‰РµРЅРѕ {len(payments_to_remove)} Р·Р°РїРёСЃРµР№ РёР· payment_message_ids Рё extension_messages РґР»СЏ СѓРґР°Р»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р° {email}")
                                    
                                    # РћС‡РёС‰Р°РµРј СѓРІРµРґРѕРјР»РµРЅРёСЏ РґР»СЏ СѓРґР°Р»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р°
                                    if user_id:
                                        try:
                                            # РСЃРїРѕР»СЊР·СѓРµРј РіР»РѕР±Р°Р»СЊРЅС‹Р№ notification_manager, РёРЅРёС†РёР°Р»РёР·РёСЂСѓРµРјС‹Р№ РІ on_startup
                                            if notification_manager:
                                                await notification_manager.clear_key_notifications(user_id, email)
                                        except Exception as e:
                                            logger.error(f"РћС€РёР±РєР° РѕС‡РёСЃС‚РєРё СѓРІРµРґРѕРјР»РµРЅРёР№ РґР»СЏ СѓРґР°Р»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р° {email}: {e}")
                                        
                                except Exception as e:
                                    logger.error(f"РћС€РёР±РєР° РѕС‡РёСЃС‚РєРё РєСЌС€РµР№ РїСЂРё СѓРґР°Р»РµРЅРёРё РєР»СЋС‡Р° {email}: {e}")
                                
                                # РћС‚РїСЂР°РІР»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ РѕР± СѓРґР°Р»РµРЅРёРё РєР»СЋС‡Р°
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
                                        logger.error(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СѓРІРµРґРѕРјР»РµРЅРёСЏ РѕР± СѓРґР°Р»РµРЅРёРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {user_id}: {e}")
                            else:
                                logger.warning(f"РќРµ СѓРґР°Р»РѕСЃСЊ СѓРґР°Р»РёС‚СЊ РєР»СЋС‡ {email}: status_code={getattr(result, 'status_code', None)}")
                                
                        except Exception as e:
                            logger.error(f"РћС€РёР±РєР° РїСЂРё Р°РІС‚РѕСѓРґР°Р»РµРЅРёРё РєР»СЋС‡Р° {client.get('email', 'unknown')}: {e}")
                            continue
                
                if deleted_count > 0:
                    logger.info(f"РђРІС‚РѕСѓРґР°Р»РµРЅРѕ {deleted_count} РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹С… РєР»СЋС‡РµР№ СЃ СЃРµСЂРІРµСЂР° {server['name']}")
                    
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё Р°РІС‚РѕРѕС‡РёСЃС‚РєРµ СЃРµСЂРІРµСЂР° {server['name']}: {e}")
                # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ Р°РІС‚РѕРѕС‡РёСЃС‚РєРё
                await notify_admin(app.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РћС€РёР±РєР° РїСЂРё Р°РІС‚РѕРѕС‡РёСЃС‚РєРµ СЃРµСЂРІРµСЂР°:\nРЎРµСЂРІРµСЂ: {server['name']}\nРћС€РёР±РєР°: {str(e)}")
                continue
        
        logger.info(f"РђРІС‚РѕРѕС‡РёСЃС‚РєР° Р·Р°РІРµСЂС€РµРЅР°. Р’СЃРµРіРѕ СѓРґР°Р»РµРЅРѕ РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹С… РєР»СЋС‡РµР№: {total_deleted_count}")
        return total_deleted_count
        
    except Exception as e:
        logger.error(f"РљСЂРёС‚РёС‡РµСЃРєР°СЏ РѕС€РёР±РєР° РІ auto_cleanup_expired_keys: {e}")
        # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ Р°РІС‚РѕРѕС‡РёСЃС‚РєРё
        await notify_admin(app.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РљСЂРёС‚РёС‡РµСЃРєР°СЏ РѕС€РёР±РєР° РІ auto_cleanup_expired_keys:\nРћС€РёР±РєР°: {str(e)}")
        return 0


# РЎС‚Р°СЂС‹Рµ С„СѓРЅРєС†РёРё СѓРІРµРґРѕРјР»РµРЅРёР№ СѓРґР°Р»РµРЅС‹ - С‚РµРїРµСЂСЊ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ NotificationManager


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Р“Р»РѕР±Р°Р»СЊРЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° РЅРµРѕР±СЂР°Р±РѕС‚Р°РЅРЅС‹С… РѕС€РёР±РѕРє"""
    
    # РџСЂРѕРІРµСЂСЏРµРј С‚РёРї РѕС€РёР±РєРё
    error = context.error
    error_type = type(error).__name__
    
    # РЎРїРёСЃРѕРє РІСЂРµРјРµРЅРЅС‹С… РѕС€РёР±РѕРє, РєРѕС‚РѕСЂС‹Рµ РЅРµ С‚СЂРµР±СѓСЋС‚ СѓРІРµРґРѕРјР»РµРЅРёСЏ Р°РґРјРёРЅР°
    temporary_errors = [
        'NetworkError',
        'TimedOut',
        'RetryAfter',
        'Conflict'
    ]
    
    # РџСЂРѕРІРµСЂСЏРµРј, СЏРІР»СЏРµС‚СЃСЏ Р»Рё РѕС€РёР±РєР° РІСЂРµРјРµРЅРЅРѕР№ СЃРµС‚РµРІРѕР№ РїСЂРѕР±Р»РµРјРѕР№
    is_network_error = (
        error_type in temporary_errors or
        'httpx' in str(error).lower() or
        'ReadError' in str(error) or
        'ConnectError' in str(error) or
        'TimeoutError' in str(error)
    )
    
    if is_network_error:
        # Р”Р»СЏ СЃРµС‚РµРІС‹С… РѕС€РёР±РѕРє С‚РѕР»СЊРєРѕ Р»РѕРіРёСЂСѓРµРј, РЅРµ СЃРїР°РјРёРј Р°РґРјРёРЅРѕРІ
        logger.warning(f"Р’СЂРµРјРµРЅРЅР°СЏ СЃРµС‚РµРІР°СЏ РѕС€РёР±РєР° (Р±СѓРґРµС‚ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РїРѕРІС‚РѕСЂРµРЅР°): {error_type}: {str(error)}")
        return
    
    # Р”Р»СЏ РѕСЃС‚Р°Р»СЊРЅС‹С… РѕС€РёР±РѕРє - РїРѕР»РЅРѕРµ Р»РѕРіРёСЂРѕРІР°РЅРёРµ
    logger.error("РќРµРѕР±СЂР°Р±РѕС‚Р°РЅРЅР°СЏ РѕС€РёР±РєР°:", exc_info=context.error)
    
    # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° С‚РѕР»СЊРєРѕ Рѕ РєСЂРёС‚РёС‡РµСЃРєРёС… РѕС€РёР±РєР°С… (РЅРµ СЃРµС‚РµРІС‹С…)
    try:
        error_message = f"рџљЁ РљСЂРёС‚РёС‡РµСЃРєР°СЏ РѕС€РёР±РєР° РІ Р±РѕС‚Рµ:\n\n{str(context.error)}"
        if update and hasattr(update, 'effective_user') and update.effective_user:
            error_message += f"\n\nРџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: {update.effective_user.id}"
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=error_message[:4000])
            except telegram.error.Forbidden:
                logger.warning(f"РђРґРјРёРЅ {admin_id} Р·Р°Р±Р»РѕРєРёСЂРѕРІР°Р» Р±РѕС‚Р° (error_handler)")
            except telegram.error.BadRequest as e:
                if "Chat not found" in str(e):
                    logger.warning(f"РђРґРјРёРЅ {admin_id} Р·Р°Р±Р»РѕРєРёСЂРѕРІР°Р» Р±РѕС‚Р° (error_handler): {e}")
                else:
                    pass  # Р”СЂСѓРіРёРµ BadRequest РѕС€РёР±РєРё РёРіРЅРѕСЂРёСЂСѓРµРј РІ error_handler
            except:
                pass  # Р•СЃР»Рё РЅРµ СѓРґР°РµС‚СЃСЏ РѕС‚РїСЂР°РІРёС‚СЊ Р°РґРјРёРЅСѓ, РїСЂРѕРґРѕР»Р¶Р°РµРј СЂР°Р±РѕС‚Сѓ
    except:
        pass  # РќРµ РїСЂРµСЂС‹РІР°РµРј СЂР°Р±РѕС‚Сѓ Р±РѕС‚Р° РёР·-Р·Р° РѕС€РёР±РєРё РІ error_handler

async def notify_server_issues(bot, server_name, issue_type, details=""):
    """РЈРІРµРґРѕРјР»СЏРµС‚ Р°РґРјРёРЅР° Рѕ РїСЂРѕР±Р»РµРјР°С… СЃ СЃРµСЂРІРµСЂР°РјРё"""
    try:
        message = f"рџљЁ РџСЂРѕР±Р»РµРјР° СЃ СЃРµСЂРІРµСЂРѕРј {server_name}\n\n"
        message += f"РўРёРї РїСЂРѕР±Р»РµРјС‹: {issue_type}\n"
        message += f"Р’СЂРµРјСЏ: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        message += f"РЎС‚Р°С‚СѓСЃ: РўСЂРµР±СѓРµС‚ РІРЅРёРјР°РЅРёСЏ\n\n"
        
        if details:
            message += f"Р”РµС‚Р°Р»Рё: {details}\n\n"
        
        message += "Р РµРєРѕРјРµРЅРґСѓРµРјС‹Рµ РґРµР№СЃС‚РІРёСЏ:\n"
        message += "вЂў РџСЂРѕРІРµСЂРёС‚СЊ РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ СЃРµСЂРІРµСЂР°\n"
        message += "вЂў РЈРІРµРґРѕРјРёС‚СЊ РєР»РёРµРЅС‚РѕРІ Рѕ РІРѕР·РјРѕР¶РЅС‹С… РїСЂРѕР±Р»РµРјР°С…\n"
        message += "вЂў РџСЂРѕРІРµСЂРёС‚СЊ Р»РѕРіРё СЃРµСЂРІРµСЂР°"
        
        await notify_admin(bot, message)
        logger.warning(f"РћС‚РїСЂР°РІР»РµРЅРѕ СѓРІРµРґРѕРјР»РµРЅРёРµ Рѕ РїСЂРѕР±Р»РµРјРµ СЃ СЃРµСЂРІРµСЂРѕРј {server_name}: {issue_type}")
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СѓРІРµРґРѕРјР»РµРЅРёСЏ Рѕ РїСЂРѕР±Р»РµРјРµ СЃ СЃРµСЂРІРµСЂРѕРј: {e}")

async def server_health_monitor(app):
    """РџРµСЂРёРѕРґРёС‡РµСЃРєРёР№ РјРѕРЅРёС‚РѕСЂРёРЅРі СЃРѕСЃС‚РѕСЏРЅРёСЏ СЃРµСЂРІРµСЂРѕРІ"""
    logger.info("Р—Р°РїСѓСЃРє РјРѕРЅРёС‚РѕСЂРёРЅРіР° СЃРµСЂРІРµСЂРѕРІ")
    
    # РЎР»РѕРІР°СЂСЊ РґР»СЏ РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ РїСЂРµРґС‹РґСѓС‰РµРіРѕ СЃРѕСЃС‚РѕСЏРЅРёСЏ СЃРµСЂРІРµСЂРѕРІ
    previous_server_status = {}
    
    while True:
        try:
            # РџСЂРѕРІРµСЂСЏРµРј РІСЃРµ СЃРµСЂРІРµСЂС‹
            health_results = server_manager.check_all_servers_health()
            new_client_health = new_client_manager.check_all_servers_health()
            
            # РџСЂРѕРІРµСЂСЏРµРј РёР·РјРµРЅРµРЅРёСЏ РІ СЃРѕСЃС‚РѕСЏРЅРёРё СЃРµСЂРІРµСЂРѕРІ
            current_time = datetime.datetime.now()
            
            for server_name, is_healthy in health_results.items():
                previous_status = previous_server_status.get(server_name, "unknown")
                current_status = "online" if is_healthy else "offline"
                
                # Р•СЃР»Рё СЃС‚Р°С‚СѓСЃ РёР·РјРµРЅРёР»СЃСЏ, РѕС‚РїСЂР°РІР»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ
                if previous_status != current_status:
                    if current_status == "offline":
                        health_status = server_manager.get_server_health_status()[server_name]
                        last_error = health_status.get("last_error", "РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР°")
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "РЎРµСЂРІРµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ",
                            f"РћС€РёР±РєР°: {last_error}"
                        )
                    elif current_status == "online":
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "РЎРµСЂРІРµСЂ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅ",
                            "РЎРµСЂРІРµСЂ СЃРЅРѕРІР° РґРѕСЃС‚СѓРїРµРЅ"
                        )
                
                previous_server_status[server_name] = current_status
            
            # РџСЂРѕРІРµСЂСЏРµРј СЃРµСЂРІРµСЂС‹ СЃ РґР»РёС‚РµР»СЊРЅС‹РјРё РїСЂРѕР±Р»РµРјР°РјРё
            for server_name, is_healthy in health_results.items():
                if not is_healthy:
                    health_status = server_manager.get_server_health_status()[server_name]
                    consecutive_failures = health_status.get("consecutive_failures", 0)
                    last_check = health_status.get("last_check")
                    
                    # Р•СЃР»Рё СЃРµСЂРІРµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ Р±РѕР»РµРµ 15 РјРёРЅСѓС‚ (3 РїСЂРѕРІРµСЂРєРё РїРѕ 5 РјРёРЅСѓС‚)
                    if consecutive_failures >= 3 and last_check:
                        time_since_last_check = current_time - last_check
                        if time_since_last_check.total_seconds() > 900:  # 15 РјРёРЅСѓС‚
                            await notify_server_issues(
                                app.bot, 
                                server_name, 
                                "Р”Р»РёС‚РµР»СЊРЅР°СЏ РЅРµРґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ",
                                f"РЎРµСЂРІРµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ Р±РѕР»РµРµ 15 РјРёРЅСѓС‚. РќРµСѓРґР°С‡РЅС‹С… РїРѕРїС‹С‚РѕРє: {consecutive_failures}"
                            )
            
            # Р›РѕРіРёСЂСѓРµРј СЃС‚Р°С‚СѓСЃ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ
            logger.info(f"РЎС‚Р°С‚СѓСЃ СЃРµСЂРІРµСЂРѕРІ: {health_results}")
            
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РІ РјРѕРЅРёС‚РѕСЂРёРЅРіРµ СЃРµСЂРІРµСЂРѕРІ: {e}")
        
        # Р–РґРµРј 5 РјРёРЅСѓС‚ РґРѕ СЃР»РµРґСѓСЋС‰РµР№ РїСЂРѕРІРµСЂРєРё
        await asyncio.sleep(300)

# Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ РјРµРЅРµРґР¶РµСЂ СѓРІРµРґРѕРјР»РµРЅРёР№
notification_manager = None

async def on_startup(app):
    global notification_manager
    
    logger.info("=== РќРђР§РђР›Рћ РРќРР¦РРђР›РР—РђР¦РР Р‘РћРўРђ ===")
    
    await init_all_db()  # РЈР¶Рµ РІРєР»СЋС‡Р°РµС‚ init_referral_db()
    
    # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј РјРµРЅРµРґР¶РµСЂ СѓРІРµРґРѕРјР»РµРЅРёР№
    logger.info("РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ РјРµРЅРµРґР¶РµСЂР° СѓРІРµРґРѕРјР»РµРЅРёР№...")
    notification_manager = NotificationManager(app.bot, server_manager, ADMIN_IDS)
    await notification_manager.initialize()
    await notification_manager.start()
    logger.info("РњРµРЅРµРґР¶РµСЂ СѓРІРµРґРѕРјР»РµРЅРёР№ Р·Р°РїСѓС‰РµРЅ")
    
    logger.info("=== РРќРР¦РРђР›РР—РђР¦РРЇ Р‘РћРўРђ Р—РђР’Р•Р РЁР•РќРђ ===")
    
    # Р—Р°РїСѓСЃРєР°РµРј РѕСЃС‚Р°Р»СЊРЅС‹Рµ Р·Р°РґР°С‡Рё
    # auto_activate_keys Р±РѕР»СЊС€Рµ РЅРµ РЅСѓР¶РЅР° - webhook'Рё РѕР±СЂР°Р±Р°С‚С‹РІР°СЋС‚ РїР»Р°С‚РµР¶Рё РјРіРЅРѕРІРµРЅРЅРѕ
    asyncio.create_task(server_health_monitor(app))


# ==================== РЎРўРР›Р¬ РРќРўР•Р Р¤Р•Р™РЎРђ ====================

# Р­РјРѕРґР·Рё РґР»СЏ СЂР°Р·Р»РёС‡РЅС‹С… СЌР»РµРјРµРЅС‚РѕРІ РёРЅС‚РµСЂС„РµР№СЃР°
class UIEmojis:
    
    # РќР°РІРёРіР°С†РёСЏ
    BACK = "в†ђ"
    NEXT = "в†’"
    PREV = "в†ђ"
    CLOSE = "вњ•"
    REFRESH = "в†»"
    
    # РЎС‚Р°С‚СѓСЃС‹
    SUCCESS = "вњ“"
    ERROR = "вњ—"
    WARNING = "вљ "
    


class UIStyles:
    @staticmethod
    def header(text: str) -> str:
        """РћСЃРЅРѕРІРЅРѕР№ Р·Р°РіРѕР»РѕРІРѕРє"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def subheader(text: str) -> str:
        """РџРѕРґР·Р°РіРѕР»РѕРІРѕРє"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def description(text: str) -> str:
        """РћРїРёСЃР°РЅРёРµ"""
        return f"<i>{text}</i>"
    
    @staticmethod
    def highlight(text: str) -> str:
        """Р’С‹РґРµР»РµРЅРЅС‹Р№ С‚РµРєСЃС‚"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def code_block(text: str) -> str:
        """Р‘Р»РѕРє РєРѕРґР°"""
        return f"<code>{text}</code>"
    
    @staticmethod
    def success_message(text: str) -> str:
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± СѓСЃРїРµС…Рµ"""
        return f"{UIEmojis.SUCCESS} <b>{text}</b>"
    
    @staticmethod
    def error_message(text: str) -> str:
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС€РёР±РєРµ"""
        return f"{UIEmojis.ERROR} <b>{text}</b>"
    
    @staticmethod
    def warning_message(text: str) -> str:
        """РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ"""
        return f"{UIEmojis.WARNING} <b>{text}</b>"
    
    @staticmethod
    def info_message(text: str) -> str:
        """РРЅС„РѕСЂРјР°С†РёРѕРЅРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ"""
        return f"<i>{text}</i>"

# РЁР°Р±Р»РѕРЅС‹ РєРЅРѕРїРѕРє РґР»СЏ РµРґРёРЅРѕРѕР±СЂР°Р·РёСЏ
class UIButtons:
    @staticmethod
    def main_menu_buttons(is_admin=False):
        """РљРЅРѕРїРєРё РіР»Р°РІРЅРѕРіРѕ РјРµРЅСЋ"""
        buttons = [
            [InlineKeyboardButton("РљСѓРїРёС‚СЊ", callback_data="buy_menu")],
            [InlineKeyboardButton("РњРѕРё РєР»СЋС‡Рё", callback_data="mykey"), 
             InlineKeyboardButton("РРЅСЃС‚СЂСѓРєС†РёСЏ", callback_data="instruction")],
            [InlineKeyboardButton("Р РµС„РµСЂР°Р»С‹", callback_data="referral"), 
             InlineKeyboardButton("РњРѕРё Р±Р°Р»Р»С‹", callback_data="points")],
            [InlineKeyboardButton("РќР°С€ РєР°РЅР°Р»", url="https://t.me/DarallaNews")],
        ]
        
        if is_admin:
            buttons.append([InlineKeyboardButton("РђРґРјРёРЅ-РјРµРЅСЋ", callback_data="admin_menu")])
        
        return buttons
    
    @staticmethod
    def back_button():
        """РљРЅРѕРїРєР° РЅР°Р·Р°Рґ"""
        return InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")
    
    @staticmethod
    def refresh_button(callback_data="refresh"):
        """РљРЅРѕРїРєР° РѕР±РЅРѕРІР»РµРЅРёСЏ"""
        return InlineKeyboardButton(f"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ", callback_data=callback_data)

# РЁР°Р±Р»РѕРЅС‹ СЃРѕРѕР±С‰РµРЅРёР№
class UIMessages:
    @staticmethod
    def welcome_message():
        """РџСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "РСЃРїРѕР»СЊР·СѓСЏ РґР°РЅРЅС‹Р№ СЃРµСЂРІРёСЃ, РІС‹ СЃРѕРіР»Р°С€Р°РµС‚РµСЃСЊ СЃ <a href=\"" + terms_url + "\">СѓСЃР»РѕРІРёСЏРјРё РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ</a> Рё РѕР±СЏР·СѓРµС‚РµСЃСЊ СЃРѕР±Р»СЋРґР°С‚СЊ Р·Р°РєРѕРЅРѕРґР°С‚РµР»СЊСЃС‚РІРѕ Р Р¤."
        return (
            f"{UIStyles.header('Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}"
        )
    
    @staticmethod
    def buy_menu_message():
        """РЎРѕРѕР±С‰РµРЅРёРµ РјРµРЅСЋ РїРѕРєСѓРїРєРё"""
        return (
            f"{UIStyles.header('Р’С‹Р±РµСЂРёС‚Рµ РїРµСЂРёРѕРґ РїРѕРґРїРёСЃРєРё')}\n\n"
            f"{UIStyles.description('Р”РѕСЃС‚СѓРїРЅС‹Рµ С‚Р°СЂРёС„С‹:')}\n"
            f"вЂў <b>1 РјРµСЃСЏС†</b> вЂ” 100в‚Ѕ\n"
            f"вЂў <b>3 РјРµСЃСЏС†Р°</b> вЂ” 250в‚Ѕ <i>(РІС‹РіРѕРґР° 50в‚Ѕ)</i>"
        )
    
    @staticmethod
    def instruction_menu_message():
        """РЎРѕРѕР±С‰РµРЅРёРµ РјРµРЅСЋ РёРЅСЃС‚СЂСѓРєС†РёР№"""
        return (
            f"{UIStyles.header('РРЅСЃС‚СЂСѓРєС†РёРё РїРѕ РЅР°СЃС‚СЂРѕР№РєРµ')}\n\n"
            f"{UIStyles.description('Р’С‹Р±РµСЂРёС‚Рµ РІР°С€Сѓ РїР»Р°С‚С„РѕСЂРјСѓ РґР»СЏ РїРѕР»СѓС‡РµРЅРёСЏ РїРѕРґСЂРѕР±РЅРѕР№ РёРЅСЃС‚СЂСѓРєС†РёРё:')}"
        )
    
    @staticmethod
    def admin_menu_message():
        """РЎРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅ-РјРµРЅСЋ"""
        return f"{UIStyles.header('РџР°РЅРµР»СЊ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂР°')}"

    @staticmethod
    def broadcast_intro_message():
        return (
            f"{UIStyles.header('РЎРѕР·РґР°РЅРёРµ СЂР°СЃСЃС‹Р»РєРё')}\n\n"
            f"{UIStyles.description('РћС‚РїСЂР°РІСЊС‚Рµ С‚РµРєСЃС‚ СЃРѕРѕР±С‰РµРЅРёСЏ, РєРѕС‚РѕСЂРѕРµ РЅСѓР¶РЅРѕ СЂР°Р·РѕСЃР»Р°С‚СЊ РІСЃРµРј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏРј.')}\n"
            f"{UIStyles.info_message('РџРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ HTML. РџСЂРµРґРїСЂРѕСЃРјРѕС‚СЂ Р±СѓРґРµС‚ РїРѕРєР°Р·Р°РЅ РїРµСЂРµРґ РѕС‚РїСЂР°РІРєРѕР№.')}"
        )

    @staticmethod
    def broadcast_preview_message(text: str):
        return (
            f"{UIStyles.header('РџСЂРµРґРїСЂРѕСЃРјРѕС‚СЂ СЂР°СЃСЃС‹Р»РєРё')}\n\n"
            f"{text}"
        )
    
    @staticmethod
    def success_purchase_message(period, price):
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± СѓСЃРїРµС€РЅРѕР№ РїРѕРєСѓРїРєРµ"""
        period_text = "1 РјРµСЃСЏС†" if period == "month" else "3 РјРµСЃСЏС†Р°"
        return (
            f"{UIStyles.success_message('РџРѕРєСѓРїРєР° РїСЂРѕС€Р»Р° СѓСЃРїРµС€РЅРѕ!')}\n\n"
            f"<b>РџРѕРґРїРёСЃРєР°:</b> {period_text}\n"
            f"<b>РЎСѓРјРјР°:</b> {price}в‚Ѕ\n\n"
        )
    
    @staticmethod
    def key_expiring_message(email, server, time_remaining):
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± РёСЃС‚РµРєР°СЋС‰РµРј РєР»СЋС‡Рµ"""
        return (
            f"{UIStyles.warning_message('Р’РЅРёРјР°РЅРёРµ! РљР»СЋС‡ СЃРєРѕСЂРѕ РёСЃС‚РµС‡РµС‚')}\n\n"
            f"<b>РљР»СЋС‡:</b> <code>{email}</code>\n"
            f"<b>РЎРµСЂРІРµСЂ:</b> {server}\n"
            f"<b>РћСЃС‚Р°Р»РѕСЃСЊ:</b> {time_remaining}\n\n"
            f"{UIStyles.description('РџСЂРѕРґР»РёС‚Рµ РєР»СЋС‡, С‡С‚РѕР±С‹ РЅРµ РїРѕС‚РµСЂСЏС‚СЊ РґРѕСЃС‚СѓРї Рє VPN!')}"
        )
    
    @staticmethod
    def key_deleted_message(email, server, days_expired):
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± СѓРґР°Р»РµРЅРЅРѕРј РєР»СЋС‡Рµ"""
        return (
            f"{UIStyles.error_message('РљР»СЋС‡ Р±С‹Р» СѓРґР°Р»РµРЅ')}\n\n"
            f"<b>РљР»СЋС‡:</b> <code>{email}</code>\n"
            f"<b>РЎРµСЂРІРµСЂ:</b> {server}\n"
            f"<b>РСЃС‚РµРє:</b> {days_expired} РґРЅРµР№ РЅР°Р·Р°Рґ\n\n"
            f"{UIStyles.description('РљР»СЋС‡ Р±С‹Р» Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё СѓРґР°Р»РµРЅ РёР·-Р·Р° РёСЃС‚РµС‡РµРЅРёСЏ СЃСЂРѕРєР° РґРµР№СЃС‚РІРёСЏ.')}\n"
            f"{UIStyles.description('РљСѓРїРёС‚Рµ РЅРѕРІС‹Р№ РєР»СЋС‡, С‡С‚РѕР±С‹ РїСЂРѕРґРѕР»Р¶РёС‚СЊ РїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ VPN.')}"
        )
    
    @staticmethod
    def no_keys_message():
        """РЎРѕРѕР±С‰РµРЅРёРµ РѕР± РѕС‚СЃСѓС‚СЃС‚РІРёРё РєР»СЋС‡РµР№"""
        return (
            f"{UIStyles.info_message('РЈ РІР°СЃ РїРѕРєР° РЅРµС‚ Р°РєС‚РёРІРЅС‹С… РєР»СЋС‡РµР№')}\n\n"
            f"{UIStyles.description('РљСѓРїРёС‚Рµ РїРѕРґРїРёСЃРєСѓ РґР»СЏ РЅР°С‡Р°Р»Р° РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ VPN.')}"
        )
    
    @staticmethod
    def key_extended_message(email, server_name, days, expiry_str, period=None):
        """РЎРѕРѕР±С‰РµРЅРёРµ Рѕ РїСЂРѕРґР»РµРЅРёРё РєР»СЋС‡Р°"""
        # РћРїСЂРµРґРµР»СЏРµРј С‚РµРєСЃС‚ РїРµСЂРёРѕРґР°
        if period:
            if period == '3month':
                period_text = "3 РјРµСЃСЏС†Р°"
            elif period == 'month':
                period_text = "1 РјРµСЃСЏС†"
            else:
                period_text = f"{days} РґРЅРµР№"
        else:
            period_text = f"{days} РґРЅРµР№"
        
        return (
            f"{UIEmojis.SUCCESS} РљР»СЋС‡ СѓСЃРїРµС€РЅРѕ РїСЂРѕРґР»РµРЅ!\n\n"
            f"РљР»СЋС‡: `{email}`\n"
            f"РЎРµСЂРІРµСЂ: {server_name}\n"
            f"РџСЂРѕРґР»РµРЅ РЅР°: {period_text}\n"
            f"РќРѕРІРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ: {expiry_str}"
        )
    
    
    @staticmethod
    def server_selection_message():
        """РЎРѕРѕР±С‰РµРЅРёРµ РІС‹Р±РѕСЂР° СЃРµСЂРІРµСЂР°"""
        return (
            f"{UIStyles.header('Р’С‹Р±РѕСЂ Р»РѕРєР°С†РёРё')}\n\n"
            f"{UIStyles.description('Р’С‹Р±РµСЂРёС‚Рµ Р»РѕРєР°С†РёСЋ РґР»СЏ РІР°С€РµРіРѕ VPN-РєР»СЋС‡Р°:')}\n"
            f"{UIStyles.info_message('Р РµРєРѕРјРµРЅРґСѓРµС‚СЃСЏ РІС‹Р±СЂР°С‚СЊ Р±Р»РёР¶Р°Р№С€РёР№ Рє РІР°Рј СЃРµСЂРІРµСЂ РґР»СЏ Р»СѓС‡С€РµР№ СЃРєРѕСЂРѕСЃС‚Рё.')}"
        )
    
    @staticmethod
    def referral_menu_message(points, total_referrals, active_referrals, ref_link):
        """РЎРѕРѕР±С‰РµРЅРёРµ СЂРµС„РµСЂР°Р»СЊРЅРѕРіРѕ РјРµРЅСЋ"""
        return (
            f"{UIStyles.header('Р РµС„РµСЂР°Р»СЊРЅР°СЏ РїСЂРѕРіСЂР°РјРјР°')}\n\n"
            f"<b>Р’Р°С€Рё Р±Р°Р»Р»С‹:</b> {UIStyles.highlight(str(points))}\n\n"
            f"<b>РЎС‚Р°С‚РёСЃС‚РёРєР° СЂРµС„РµСЂР°Р»РѕРІ:</b>\n"
            f"вЂў Р’СЃРµРіРѕ РїСЂРёРіР»Р°С€РµРЅРѕ: {total_referrals}\n"
            f"вЂў РђРєС‚РёРІРЅС‹С…: {active_referrals}\n\n"
            f"<b>РљР°Рє Р·Р°СЂР°Р±РѕС‚Р°С‚СЊ Р±Р°Р»Р»С‹:</b>\n"
            f"вЂў РџСЂРёРіР»Р°СЃРёС‚Рµ РґСЂСѓРіР° вЂ” РїРѕР»СѓС‡РёС‚Рµ 1 Р±Р°Р»Р»\n"
            f"вЂў 1 Р±Р°Р»Р» = 14 РґРЅРµР№ VPN\n"
            f"вЂў 1 Р±Р°Р»Р» = РїСЂРѕРґР»РµРЅРёРµ РЅР° 14 РґРЅРµР№\n\n"
            f"{UIStyles.warning_message('Р’Р°Р¶РЅРѕ: Р‘Р°Р»Р» РІС‹РґР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ Р·Р° РїСЂРёРІР»РµС‡РµРЅРёРµ РЅРѕРІС‹С… РєР»РёРµРЅС‚РѕРІ!')}\n\n"
            f"<b>Р’Р°С€Р° СЂРµС„РµСЂР°Р»СЊРЅР°СЏ СЃСЃС‹Р»РєР°:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"<b>РљР°Рє РїРѕРґРµР»РёС‚СЊСЃСЏ:</b>\n"
            f"{UIStyles.description('РћС‚РїСЂР°РІСЊС‚Рµ СЃСЃС‹Р»РєСѓ РґСЂСѓР·СЊСЏРј РёР»Рё РѕРїСѓР±Р»РёРєСѓР№С‚Рµ РІ СЃРѕС†РёР°Р»СЊРЅС‹С… СЃРµС‚СЏС…')}"
        )
    
    @staticmethod
    def welcome_referral_new_user_message(days):
        """РџСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РґР»СЏ РЅРѕРІРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїРѕ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "РСЃРїРѕР»СЊР·СѓСЏ РґР°РЅРЅС‹Р№ СЃРµСЂРІРёСЃ, РІС‹ СЃРѕРіР»Р°С€Р°РµС‚РµСЃСЊ СЃ <a href=\"" + terms_url + "\">СѓСЃР»РѕРІРёСЏРјРё РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ</a> Рё РѕР±СЏР·СѓРµС‚РµСЃСЊ СЃРѕР±Р»СЋРґР°С‚СЊ Р·Р°РєРѕРЅРѕРґР°С‚РµР»СЊСЃС‚РІРѕ Р Р¤."
        return (
            f"{UIStyles.header('Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Р’С‹ РїСЂРёС€Р»Рё РїРѕ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ!')}\n\n"
            f"РџРѕСЃР»Рµ РїРѕРєСѓРїРєРё VPN РІР°С€ РґСЂСѓРі РїРѕР»СѓС‡РёС‚ 1 Р±Р°Р»Р»!\n"
            f"1 Р±Р°Р»Р» = {days} РґРЅРµР№ VPN Р±РµСЃРїР»Р°С‚РЅРѕ!"
            
        )
    
    @staticmethod
    def welcome_referral_existing_user_message():
        """РџСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РґР»СЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїРѕ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "РСЃРїРѕР»СЊР·СѓСЏ РґР°РЅРЅС‹Р№ СЃРµСЂРІРёСЃ, РІС‹ СЃРѕРіР»Р°С€Р°РµС‚РµСЃСЊ СЃ <a href=\"" + terms_url + "\">СѓСЃР»РѕРІРёСЏРјРё РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ</a> Рё РѕР±СЏР·СѓРµС‚РµСЃСЊ СЃРѕР±Р»СЋРґР°С‚СЊ Р·Р°РєРѕРЅРѕРґР°С‚РµР»СЊСЃС‚РІРѕ Р Р¤."
        return (
            f"{UIStyles.header('Р”РѕР±СЂРѕ РїРѕР¶Р°Р»РѕРІР°С‚СЊ РІ Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Р’С‹ РїСЂРёС€Р»Рё РїРѕ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРµ')}\n\n"
            f"РќРѕ РІС‹ РЅРµ РЅРѕРІС‹Р№ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ.\n"
            f"Р РµС„РµСЂР°Р»СЊРЅР°СЏ РЅР°РіСЂР°РґР° РЅРµ Р±СѓРґРµС‚ РІС‹РґР°РЅР°."
            
        )

# Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ СЃР»РѕРІР°СЂСЊ РґР»СЏ С…СЂР°РЅРµРЅРёСЏ message_id РїР»Р°С‚РµР¶РµР№
# РљР»СЋС‡: payment_id, Р—РЅР°С‡РµРЅРёРµ: message_id
payment_message_ids = {}

# Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ СЃР»РѕРІР°СЂСЊ РґР»СЏ С…СЂР°РЅРµРЅРёСЏ РєРѕСЂРѕС‚РєРёС… РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂРѕРІ РєР»СЋС‡РµР№ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ
# РљР»СЋС‡: РєРѕСЂРѕС‚РєРёР№_id, Р—РЅР°С‡РµРЅРёРµ: key_email
extension_keys_cache = {}

# Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ СЃР»РѕРІР°СЂСЊ РґР»СЏ С…СЂР°РЅРµРЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№ РїСЂРѕРґР»РµРЅРёСЏ
# РљР»СЋС‡: payment_id, Р—РЅР°С‡РµРЅРёРµ: (chat_id, message_id)
extension_messages = {}

# РРјРїРѕСЂС‚ РЅРѕРІРѕРіРѕ РјРѕРґСѓР»СЏ СѓРІРµРґРѕРјР»РµРЅРёР№
try:
    from .notifications import NotificationManager
except ImportError:
    from .notifications import NotificationManager

import traceback

async def notify_admin(bot, text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=f"вќ—пёЏ[VPNBot ERROR]\n{text}")
        except telegram.error.Forbidden:
            logger.warning(f"РђРґРјРёРЅ {admin_id} Р·Р°Р±Р»РѕРєРёСЂРѕРІР°Р» Р±РѕС‚Р°")
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"РђРґРјРёРЅ {admin_id} Р·Р°Р±Р»РѕРєРёСЂРѕРІР°Р» Р±РѕС‚Р°: {e}")
            else:
                logger.error(f'BadRequest РѕС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СѓРІРµРґРѕРјР»РµРЅРёСЏ Р°РґРјРёРЅСѓ: {e}')
        except Exception as e:
            logger.error(f'РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ СѓРІРµРґРѕРјР»РµРЅРёСЏ Р°РґРјРёРЅСѓ: {e}')


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
        await safe_edit_or_reply(message_obj, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    try:
        # Р§РёС‚Р°РµРј СЂРѕС‚Р°С†РёРѕРЅРЅС‹Р№ С„Р°Р№Р» Р»РѕРіРѕРІ РїСЂРёР»РѕР¶РµРЅРёСЏ
        from .keys_db import DATA_DIR
        import os
        logs_path = os.path.join(DATA_DIR, 'logs', 'bot.log')
        logs = ''
        if os.path.exists(logs_path):
            with open(logs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = ''.join(lines[-200:])  # РїРѕСЃР»РµРґРЅРёРµ ~200 СЃС‚СЂРѕРє
        else:
            logs = 'Р¤Р°Р№Р» Р»РѕРіРѕРІ РЅРµ РЅР°Р№РґРµРЅ. РћРЅ Р±СѓРґРµС‚ СЃРѕР·РґР°РЅ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РїСЂРё СЂР°Р±РѕС‚Рµ Р±РѕС‚Р°.'

        # РћРіСЂР°РЅРёС‡РёРІР°РµРј РґР»РёРЅСѓ Р»РѕРіРѕРІ РґР»СЏ Telegram (РјР°РєСЃРёРјСѓРј 4000 СЃРёРјРІРѕР»РѕРІ)
        if len(logs) > 3500:  # РћСЃС‚Р°РІР»СЏРµРј РјРµСЃС‚Рѕ РґР»СЏ HTML С‚РµРіРѕРІ
            logs = logs[-3500:]

        # Р­РєСЂР°РЅРёСЂСѓРµРј HTML Рё РІС‹РІРѕРґРёРј РєР°Рє РєРѕРґ
        escaped = html.escape(logs)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ", callback_data="admin_errors_refresh")],
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # РСЃРїРѕР»СЊР·СѓРµРј С„РѕС‚Рѕ РґР»СЏ Р»РѕРіРѕРІ, РѕРіСЂР°РЅРёС‡РёРІР°РµРј РґР»РёРЅСѓ РґР»СЏ caption
        max_length = 800  # Telegram caption limit is 1024, but we use 800 to be safe
        if len(escaped) > max_length:
            escaped = escaped[:max_length] + "\n\n... (Р»РѕРіРё РѕР±СЂРµР·Р°РЅС‹)"
        
        logs_text = f"<b>РџРѕСЃР»РµРґРЅРёРµ Р»РѕРіРё:</b>\n\n<pre><code>{escaped}</code></pre>"
        await safe_edit_or_reply_universal(message_obj, logs_text, reply_markup=keyboard, parse_mode='HTML', menu_type='admin_errors')
            
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ admin_errors")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # РСЃРїРѕР»СЊР·СѓРµРј С„РѕС‚Рѕ РґР»СЏ РѕС€РёР±РєРё Р»РѕРіРѕРІ
        error_text = f'{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё С‡С‚РµРЅРёРё Р»РѕРіРѕРІ: {str(e)}'
        await safe_edit_or_reply_universal(message_obj, error_text, reply_markup=keyboard, menu_type='admin_errors')

async def admin_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Р”Р°С€Р±РѕСЂРґ СѓРІРµРґРѕРјР»РµРЅРёР№ РґР»СЏ Р°РґРјРёРЅР°"""
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_notifications':
            push_nav(context, 'admin_notifications')
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    try:
        if notification_manager is None:
            await safe_edit_or_reply(update.callback_query.message, 
                                   f"{UIEmojis.ERROR} РњРµРЅРµРґР¶РµСЂ СѓРІРµРґРѕРјР»РµРЅРёР№ РЅРµ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ")
            return
        
        # РџРѕР»СѓС‡Р°РµРј РґР°С€Р±РѕСЂРґ
        dashboard_text = await notification_manager.get_notification_dashboard()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ", callback_data="admin_notifications_refresh")],
            [UIButtons.back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # РСЃРїРѕР»СЊР·СѓРµРј С„РѕС‚Рѕ РґР»СЏ СѓРІРµРґРѕРјР»РµРЅРёР№
        await safe_edit_or_reply_universal(message_obj, dashboard_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_notifications')
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РІ admin_notifications: {e}")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # РСЃРїРѕР»СЊР·СѓРµРј С„РѕС‚Рѕ РґР»СЏ РѕС€РёР±РєРё СѓРІРµРґРѕРјР»РµРЅРёР№
        error_text = f"{UIEmojis.ERROR} РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё РґР°С€Р±РѕСЂРґР°: {e}"
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
        await safe_edit_or_reply(message_obj, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    try:
        # РџСЂРѕРІРµСЂСЏРµРј Р·РґРѕСЂРѕРІСЊРµ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ
        health_results = server_manager.check_all_servers_health()
        health_status = server_manager.get_server_health_status()
        
        message = "рџ”Ќ Р”РµС‚Р°Р»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° СЃРµСЂРІРµСЂРѕРІ:\n\n"
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_info = health_status.get(server_name, {})
            
            if is_healthy:
                # РџРѕР»СѓС‡Р°РµРј РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅСѓСЋ РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ СЃРµСЂРІРµСЂРµ
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    message += f"{UIEmojis.SUCCESS} {server_name}: РћРЅР»Р°Р№РЅ\n"
                    message += f"   Р’СЃРµРіРѕ РєР»РёРµРЅС‚РѕРІ: {total_clients}\n"
                    message += f"   РђРєС‚РёРІРЅС‹С… РєР»РёРµРЅС‚РѕРІ: {active_clients}\n"
                    message += f"   РСЃС‚РµРєС€РёС… РєР»РёРµРЅС‚РѕРІ: {expired_clients}\n"
                    message += f"   РџРѕСЃР»РµРґРЅСЏСЏ РїСЂРѕРІРµСЂРєР°: {status_info.get('last_check', 'РќРµРёР·РІРµСЃС‚РЅРѕ')}\n"
                except Exception as e:
                    message += f"{UIEmojis.SUCCESS} {server_name}: РћРЅР»Р°Р№РЅ (РѕС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РґРµС‚Р°Р»РµР№: {str(e)[:50]}...)\n"
            else:
                message += f"{UIEmojis.ERROR} {server_name}: РћС„Р»Р°Р№РЅ\n"
                message += f"   РћС€РёР±РєР°: {status_info.get('last_error', 'РќРµРёР·РІРµСЃС‚РЅРѕ')}\n"
                message += f"   {UIEmojis.REFRESH} РќРµСѓРґР°С‡РЅС‹С… РїРѕРїС‹С‚РѕРє: {status_info.get('consecutive_failures', 0)}\n"
                message += f"   РџРѕСЃР»РµРґРЅСЏСЏ РїСЂРѕРІРµСЂРєР°: {status_info.get('last_check', 'РќРµРёР·РІРµСЃС‚РЅРѕ')}\n"
            
            message += "\n"
        
        # Р”РѕР±Р°РІР»СЏРµРј РѕР±С‰СѓСЋ СЃС‚Р°С‚РёСЃС‚РёРєСѓ
        total_servers = len(server_manager.servers)
        online_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
        offline_servers = total_servers - online_servers
        
        # РџРѕРґСЃС‡РёС‚С‹РІР°РµРј РѕР±С‰РµРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РєР»РёРµРЅС‚РѕРІ
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
        
        message += f"РћР±С‰Р°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР°:\n"
        message += f"   Р’СЃРµРіРѕ СЃРµСЂРІРµСЂРѕРІ: {total_servers}\n"
        message += f"   РћРЅР»Р°Р№РЅ: {online_servers}\n"
        message += f"   РћС„Р»Р°Р№РЅ: {offline_servers}\n"
        message += f"   Р”РѕСЃС‚СѓРїРЅРѕСЃС‚СЊ: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"РљР»РёРµРЅС‚С‹:\n"
        message += f"   Р’СЃРµРіРѕ РєР»РёРµРЅС‚РѕРІ: {total_clients_all}\n"
        message += f"   РђРєС‚РёРІРЅС‹С…: {active_clients_all}\n"
        message += f"   РСЃС‚РµРєС€РёС…: {expired_clients_all}\n\n"
        message += f"Р’СЂРµРјСЏ РїСЂРѕРІРµСЂРєРё: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ", callback_data="admin_check_servers")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_check_servers')
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ admin_check_servers")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f'РћС€РёР±РєР° РїСЂРё РїСЂРѕРІРµСЂРєРµ СЃРµСЂРІРµСЂРѕРІ: {e}', reply_markup=keyboard, menu_type='admin_check_servers')


# Callback РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ РєР»СЋС‡РµР№
async def extend_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # РР·РІР»РµРєР°РµРј short_id РёР· callback_data
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await query.answer("РћС€РёР±РєР°: РЅРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РґР°РЅРЅС‹С…")
        return
    
    short_id = parts[1]
    
    # РџРѕР»СѓС‡Р°РµРј email РєР»СЋС‡Р° РёР· РєСЌС€Р°
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        # РџС‹С‚Р°РµРјСЃСЏ РЅР°Р№С‚Рё РєР»СЋС‡ РїРѕ short_id, СЃРѕР·РґР°РЅРЅРѕРјСѓ РёР· СѓРІРµРґРѕРјР»РµРЅРёСЏ
        # РџСЂРѕРІРµСЂСЏРµРј РІСЃРµ РІРѕР·РјРѕР¶РЅС‹Рµ С„РѕСЂРјР°С‚С‹ short_id
        import hashlib
        
        # РС‰РµРј РєР»СЋС‡ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РЅР° СЃРµСЂРІРµСЂР°С…
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
                    logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРёСЃРєРµ РєР»СЋС‡РµР№ РЅР° СЃРµСЂРІРµСЂРµ {server['name']}: {e}")
                    continue
            
            # РС‰РµРј РєР»СЋС‡, РєРѕС‚РѕСЂС‹Р№ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ short_id
            for client in all_clients:
                email = client['email']
                # РџСЂРѕРІРµСЂСЏРµРј СЂР°Р·РЅС‹Рµ С„РѕСЂРјР°С‚С‹ short_id
                possible_short_ids = [
                    hashlib.md5(f"{user_id}:{email}".encode()).hexdigest()[:8],
                    hashlib.md5(f"extend:{email}".encode()).hexdigest()[:8]
                ]
                
                if short_id in possible_short_ids:
                    key_email = email
                    # Р”РѕР±Р°РІР»СЏРµРј РІ РєСЌС€ РґР»СЏ Р±СѓРґСѓС‰РёС… РёСЃРїРѕР»СЊР·РѕРІР°РЅРёР№
                    extension_keys_cache[short_id] = email
                    logger.info(f"РќР°Р№РґРµРЅ РєР»СЋС‡ РїРѕ short_id: {short_id} -> {email}")
                    break
            
            if not key_email:
                await query.answer("РћС€РёР±РєР°: РєР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ")
                logger.error(f"РќРµ РЅР°Р№РґРµРЅ key_email РґР»СЏ short_id: {short_id}")
                return
                
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїРѕРёСЃРєР° РєР»СЋС‡Р° РїРѕ short_id: {e}")
            await query.answer("РћС€РёР±РєР°: РєР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ")
            return
    
    await query.answer()
    
    logger.info(f"Р—Р°РїСЂРѕСЃ РЅР° РїСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р°: user_id={user_id}, key_email={key_email}")
    
    # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РєР»СЋС‡ РїСЂРёРЅР°РґР»РµР¶РёС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
    if not (key_email.startswith(f"{user_id}_") or key_email.startswith(f"trial_{user_id}_")):
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} РћС€РёР±РєР°: РєР»СЋС‡ РЅРµ РїСЂРёРЅР°РґР»РµР¶РёС‚ РІР°Рј.")
        return
    
    # Р Р°Р·СЂРµС€Р°РµРј РїСЂРѕРґР»РµРЅРёРµ Р»СЋР±С‹С… РєР»СЋС‡РµР№, РІРєР»СЋС‡Р°СЏ СЃС‚Р°СЂС‹Рµ trial
    
    # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РєР»СЋС‡ СЃСѓС‰РµСЃС‚РІСѓРµС‚ РЅР° СЃРµСЂРІРµСЂР°С…
    try:
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            await safe_edit_or_reply(query.message, "вќЊ РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РЅР° СЃРµСЂРІРµСЂР°С….")
            return
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїРѕРёСЃРєР° РєР»СЋС‡Р° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ: {e}")
        await safe_edit_or_reply(query.message, "вќЊ РћС€РёР±РєР° РїСЂРё РїРѕРёСЃРєРµ РєР»СЋС‡Р°.")
        return
    
    # РЎРѕР·РґР°РµРј РєРѕСЂРѕС‚РєРёР№ РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂ РґР»СЏ РєР»СЋС‡Р°
    import hashlib
    short_id = hashlib.md5(f"{user_id}:{key_email}".encode()).hexdigest()[:8]
    extension_keys_cache[short_id] = key_email
    logger.info(f"РЎРѕР·РґР°РЅ РєРѕСЂРѕС‚РєРёР№ ID РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ: {short_id} -> {key_email}")
    
    # РџРѕРєР°Р·С‹РІР°РµРј РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР° РїСЂРѕРґР»РµРЅРёСЏ
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 РјРµСЃСЏС† - 100в‚Ѕ", callback_data=f"ext_per:month:{short_id}")],
        [InlineKeyboardButton("3 РјРµСЃСЏС†Р° - 250в‚Ѕ", callback_data=f"ext_per:3month:{short_id}")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ Рє РєР»СЋС‡Р°Рј", callback_data="mykey")]
    ])
    
    message_text = (
        f"{UIStyles.header('РџСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р°')}\n\n"
        f"<b>РљР»СЋС‡:</b> <code>{key_email}</code>\n"
        f"<b>РЎРµСЂРІРµСЂ:</b> {server_name}\n\n"
        f"{UIStyles.description('Р’С‹Р±РµСЂРёС‚Рµ РїРµСЂРёРѕРґ РїСЂРѕРґР»РµРЅРёСЏ:')}"
    )
    
    await safe_edit_or_reply_universal(query.message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')

# Callback РґР»СЏ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР° РїСЂРѕРґР»РµРЅРёСЏ
async def extend_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # РР·РІР»РµРєР°РµРј РїРµСЂРёРѕРґ Рё short_id РёР· callback_data: ext_per:month:short_id
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await query.answer("РћС€РёР±РєР°: РЅРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РґР°РЅРЅС‹С…")
        return
    
    period = parts[1]  # month РёР»Рё 3month
    short_id = parts[2]
    
    # РџРѕР»СѓС‡Р°РµРј email РєР»СЋС‡Р° РёР· РєСЌС€Р°
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        await query.answer("РћС€РёР±РєР°: РєР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РІ РєСЌС€Рµ")
        logger.error(f"РќРµ РЅР°Р№РґРµРЅ key_email РґР»СЏ short_id: {short_id}")
        return
    
    await query.answer()
    
    logger.info(f"Р’С‹Р±СЂР°РЅ РїРµСЂРёРѕРґ РїСЂРѕРґР»РµРЅРёСЏ: user_id={user_id}, period={period}, key_email={key_email}")
    
    # РћРїСЂРµРґРµР»СЏРµРј С†РµРЅСѓ (С‚Р°РєСѓСЋ Р¶Рµ РєР°Рє РїСЂРё РїРѕРєСѓРїРєРµ)
    price = "100.00" if period == "month" else "250.00"  # РІ СЂСѓР±Р»СЏС…
    
    # РЎРѕР·РґР°РµРј РїР»Р°С‚РµР¶ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ (РёСЃРїРѕР»СЊР·СѓРµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰СѓСЋ С„СѓРЅРєС†РёСЋ handle_payment)
    try:
        # РЎРѕС…СЂР°РЅСЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїСЂРѕРґР»РµРЅРёРё РІ РєРѕРЅС‚РµРєСЃС‚Рµ
        context.user_data['extension_key_email'] = key_email
        context.user_data['extension_period'] = period
        
        # Р’С‹Р·С‹РІР°РµРј С„СѓРЅРєС†РёСЋ СЃРѕР·РґР°РЅРёСЏ РїР»Р°С‚РµР¶Р°
        await handle_payment(update, context, price, f"extend_{period}")
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° СЃРѕР·РґР°РЅРёСЏ РїР»Р°С‚РµР¶Р° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ Рє РєР»СЋС‡Р°Рј", callback_data="mykey")]
        ])
        await safe_edit_or_reply(query.message, "вќЊ РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РїР»Р°С‚РµР¶Р°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.", reply_markup=keyboard)

# admin_delete_all СѓРґР°Р»РµРЅР° РїРѕ С‚СЂРµР±РѕРІР°РЅРёСЋ

async def admin_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєР°Р·С‹РІР°РµС‚ С‚РµРєСѓС‰СѓСЋ РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ Р±Р°Р»Р»РѕРІ"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    try:
        config = await get_all_config()
        if not config:
            await safe_edit_or_reply(update.message, 'РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ РЅРµ РЅР°Р№РґРµРЅР°.')
            return
        
        message = "вљ™пёЏ РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ Р±Р°Р»Р»РѕРІ:\n\n"
        for key, data in config.items():
            if key.startswith('points_'):
                message += f"вЂў {data['description']}: {data['value']}\n"
        
        message += "\nрџ“ќ РљРѕРјР°РЅРґС‹:\n"
        message += "вЂў `/admin_set_days <РґРЅРё>` - РёР·РјРµРЅРёС‚СЊ РєРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ Р·Р° 1 Р±Р°Р»Р»\n"
        message += "вЂў `/admin_set_days 14` - СѓСЃС‚Р°РЅРѕРІРёС‚СЊ 14 РґРЅРµР№ Р·Р° Р±Р°Р»Р»\n"
        message += "вЂў `/admin_set_days 30` - СѓСЃС‚Р°РЅРѕРІРёС‚СЊ 30 РґРЅРµР№ Р·Р° Р±Р°Р»Р»\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="back")]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, message, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ admin_config")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} РћС€РёР±РєР°: {e}')

async def admin_set_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РЈСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ Р·Р° 1 Р±Р°Р»Р»"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    if not context.args:
        await safe_edit_or_reply(update.message, 'РСЃРїРѕР»СЊР·СѓР№С‚Рµ: /admin_set_days <РєРѕР»РёС‡РµСЃС‚РІРѕ_РґРЅРµР№>\nРџСЂРёРјРµСЂ: /admin_set_days 14')
        return
    
    try:
        days = int(context.args[0])
        
        # РџСЂРѕРІРµСЂСЏРµРј Р»РёРјРёС‚С‹
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            await safe_edit_or_reply(update.message, f'РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РѕС‚ {min_days} РґРѕ {max_days}')
            return
        
        # РЎРѕС…СЂР°РЅСЏРµРј РЅРѕРІРѕРµ Р·РЅР°С‡РµРЅРёРµ
        success = await set_config('points_days_per_point', str(days), 'РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ VPN Р·Р° 1 Р±Р°Р»Р»')
        
        if success:
            await safe_edit_or_reply(update.message, f'{UIEmojis.SUCCESS} РЈСЃС‚Р°РЅРѕРІР»РµРЅРѕ: 1 Р±Р°Р»Р» = {days} РґРЅРµР№ VPN', parse_mode="Markdown")
        else:
            await safe_edit_or_reply(update.message, 'вќЊ РћС€РёР±РєР° РїСЂРё СЃРѕС…СЂР°РЅРµРЅРёРё РєРѕРЅС„РёРіСѓСЂР°С†РёРё')
            
    except ValueError:
        await safe_edit_or_reply(update.message, 'РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ С‡РёСЃР»РѕРј')
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ admin_set_days")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} РћС€РёР±РєР°: {e}')

# РЎРѕСЃС‚РѕСЏРЅРёРµ РґР»СЏ ConversationHandler
WAITING_FOR_DAYS = 1

async def admin_set_days_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РќР°С‡Р°Р»Рѕ РёРЅС‚РµСЂР°РєС‚РёРІРЅРѕРіРѕ РёР·РјРµРЅРµРЅРёСЏ РґРЅРµР№ Р·Р° Р±Р°Р»Р»"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(query.message, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return ConversationHandler.END
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ
    current_days = await get_config('points_days_per_point', '14')
    min_days = await get_config('points_min_days', '1')
    max_days = await get_config('points_max_days', '365')
    
    message = (
        f"вљ™пёЏ <b>РќР°СЃС‚СЂРѕР№РєР° РґРЅРµР№ Р·Р° Р±Р°Р»Р»</b>\n\n"
        f"РўРµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ: <b>1 Р±Р°Р»Р» = {current_days} РґРЅРµР№ VPN</b>\n\n"
        f"Р’РІРµРґРёС‚Рµ РЅРѕРІРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ (РѕС‚ {min_days} РґРѕ {max_days}):"
    )
    
    # РЎРѕР·РґР°РµРј РєР»Р°РІРёР°С‚СѓСЂСѓ СЃ РєРЅРѕРїРєРѕР№ РѕС‚РјРµРЅС‹
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.BACK} РћС‚РјРµРЅР°", callback_data="admin_set_days_cancel")]
    ])
    
    # РЎРѕС…СЂР°РЅСЏРµРј message_id РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµРіРѕ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ
    context.user_data['config_message_id'] = query.message.message_id
    context.user_data['config_chat_id'] = query.message.chat_id
    
    await safe_edit_or_reply_universal(query.message, message, parse_mode="HTML", reply_markup=keyboard, menu_type='admin_menu')
    
    return WAITING_FOR_DAYS

async def admin_set_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚РєР° РІРІРѕРґР° РєРѕР»РёС‡РµСЃС‚РІР° РґРЅРµР№"""
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    async def edit_config_message(message, reply_markup=None):
        """Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅР°СЏ С„СѓРЅРєС†РёСЏ РґР»СЏ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ РЅР°СЃС‚СЂРѕР№РєРё"""
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
                logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ РЅР°СЃС‚СЂРѕР№РєРё: {e}")
                # Fallback: РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
                await safe_send_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    menu_type='admin_menu'
                )
                return
        
        # Fallback: РёСЃРїРѕР»СЊР·СѓРµРј РѕР±С‹С‡РЅРѕРµ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ
        await safe_edit_or_reply_universal(update.message, message, reply_markup=reply_markup, parse_mode="HTML", menu_type='admin_menu')
    
    try:
        # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        await update.message.delete()
        
        days = int(update.message.text.strip())
        
        # РџСЂРѕРІРµСЂСЏРµРј Р»РёРјРёС‚С‹
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            message = (
                f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°</b>\n\n"
                f"РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РѕС‚ {min_days} РґРѕ {max_days}\n\n"
                f"РўРµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ: <b>1 Р±Р°Р»Р» = {await get_config('points_days_per_point', '14')} РґРЅРµР№</b>\n\n"
                f"Р’РІРµРґРёС‚Рµ РЅРѕРІРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№:"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} РћС‚РјРµРЅР°", callback_data="admin_set_days_cancel")]
            ])
            
            await safe_edit_or_reply_universal(update.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')
            
            return WAITING_FOR_DAYS
        
        # РЎРѕС…СЂР°РЅСЏРµРј РЅРѕРІРѕРµ Р·РЅР°С‡РµРЅРёРµ
        success = await set_config('points_days_per_point', str(days), 'РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ VPN Р·Р° 1 Р±Р°Р»Р»')
        logger.info(f"ADMIN_SET_DAYS: РЎРѕС…СЂР°РЅРµРЅРёРµ РєРѕРЅС„РёРіСѓСЂР°С†РёРё points_days_per_point = {days}, success = {success}")
        
        # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ Р·РЅР°С‡РµРЅРёРµ РґРµР№СЃС‚РІРёС‚РµР»СЊРЅРѕ СЃРѕС…СЂР°РЅРёР»РѕСЃСЊ
        saved_days = await get_config('points_days_per_point', '14')
        logger.info(f"ADMIN_SET_DAYS: РџСЂРѕРІРµСЂРєР° СЃРѕС…СЂР°РЅРµРЅРЅРѕРіРѕ Р·РЅР°С‡РµРЅРёСЏ = {saved_days}")
        
        if success:
            message = (
                f"{UIEmojis.SUCCESS} <b>РќР°СЃС‚СЂРѕР№РєР° РёР·РјРµРЅРµРЅР°!</b>\n\n"
                f"<b>1 Р±Р°Р»Р» = {days} РґРЅРµР№ VPN</b>\n\n"
                f"Р’РІРµРґРёС‚Рµ РґСЂСѓРіРѕРµ Р·РЅР°С‡РµРЅРёРµ РґР»СЏ РёР·РјРµРЅРµРЅРёСЏ РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РќР°Р·Р°РґВ»:"
            )
        else:
            message = (
                f"{UIEmojis.ERROR} <b>РћС€РёР±РєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ</b>\n\n"
                f"РџРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р· РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РќР°Р·Р°РґВ»:"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="admin_set_days_cancel")]
        ])
        
        await edit_config_message(message, keyboard)
        
        return WAITING_FOR_DAYS
        
    except ValueError:
        # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        try:
            await update.message.delete()
        except:
            pass
        
        message = (
            f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°</b>\n\n"
            f"Р’РІРµРґРёС‚Рµ С‡РёСЃР»Рѕ, РЅР°РїСЂРёРјРµСЂ: 14, 30, 60\n\n"
            f"РўРµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ: <b>1 Р±Р°Р»Р» = {await get_config('points_days_per_point', '14')} РґРЅРµР№</b>\n\n"
            f"Р’РІРµРґРёС‚Рµ РЅРѕРІРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№:"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} РћС‚РјРµРЅР°", callback_data="admin_set_days_cancel")]
        ])
        
        await edit_config_message(message, keyboard)
        
        return WAITING_FOR_DAYS
        
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ admin_set_days_input")
        
        # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        try:
            await update.message.delete()
        except:
            pass
        
        await edit_config_message(f'{UIEmojis.ERROR} РћС€РёР±РєР°: {e}')
        
        return ConversationHandler.END

async def admin_set_days_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћС‚РјРµРЅР° РёР·РјРµРЅРµРЅРёСЏ РєРѕРЅС„РёРіР° - РІРѕР·РІСЂР°С‚ РІ Р°РґРјРёРЅ РјРµРЅСЋ"""
    query = update.callback_query
    await query.answer()
    
    # РћС‡РёС‰Р°РµРј СЃРѕСЃС‚РѕСЏРЅРёРµ РёР·РјРµРЅРµРЅРёСЏ РґРЅРµР№
    context.user_data.pop('config_message_id', None)
    context.user_data.pop('config_chat_id', None)
    
    # Р’РѕР·РІСЂР°С‰Р°РµРјСЃСЏ РІ Р°РґРјРёРЅ РјРµРЅСЋ
    await admin_menu(update, context)
    
    return ConversationHandler.END

# РћР±СЂР°Р±РѕС‚РєР° callback-РєРЅРѕРїРѕРє РґР»СЏ start
async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"РћР±СЂР°Р±РѕС‚РєР° callback: {query.data}")
    if query.data == "buy_menu":
        await buy_menu_handler(update, context)
    elif query.data.startswith("select_period_"):
        await select_period_callback(update, context)
    elif query.data.startswith("select_server_"):
        await select_server_callback(update, context)
    elif query.data == "mykey":
        await mykey(update, context)
    elif query.data.startswith("keys_page_"):
        logger.info(f"РџРµСЂРµС…РѕРґ РЅР° СЃС‚СЂР°РЅРёС†Сѓ РєР»СЋС‡РµР№: {query.data}")
        await mykey(update, context)
    elif query.data == "instruction":
        await instruction(update, context)


# РћР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РєРЅРѕРїРєРё "РљСѓРїРёС‚СЊ" РІ РјРµРЅСЋ РїРѕРєСѓРїРєРё
async def buy_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'buy_menu':
        push_nav(context, 'buy_menu')
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("buy_menu_handler: message is None")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 РјРµСЃСЏС† вЂ” 100в‚Ѕ", callback_data="select_period_month")],
        [InlineKeyboardButton("3 РјРµСЃСЏС†Р° вЂ” 250в‚Ѕ", callback_data="select_period_3month")],
        [UIButtons.back_button()],
    ])
    
    # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ СЃРѕРѕР±С‰РµРЅРёСЏ РјРµРЅСЋ РїРѕРєСѓРїРєРё
    buy_menu_text = UIMessages.buy_menu_message()
    await safe_edit_or_reply_universal(message, buy_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='buy_menu')

# РќРѕРІС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР°, РєРѕС‚РѕСЂС‹Р№ РїРµСЂРµРІРѕРґРёС‚ Рє РІС‹Р±РѕСЂСѓ СЃРµСЂРІРµСЂР°
async def select_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # РЎРѕС…СЂР°РЅСЏРµРј РІС‹Р±СЂР°РЅРЅС‹Р№ РїРµСЂРёРѕРґ
    if query.data == "select_period_month":
        context.user_data["pending_period"] = "month"
        context.user_data["pending_price"] = "100.00"
    elif query.data == "select_period_3month":
        context.user_data["pending_period"] = "3month"
        context.user_data["pending_price"] = "250.00"
    
    # РџРµСЂРµС…РѕРґРёРј Рє РІС‹Р±РѕСЂСѓ СЃРµСЂРІРµСЂР°
    await server_selection_menu(update, context)

# РњРµРЅСЋ РІС‹Р±РѕСЂР° СЃРµСЂРІРµСЂР°
async def server_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'server_selection':
        push_nav(context, 'server_selection')
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("server_selection_menu: message is None")
        return
    
    # РџСЂРѕРІРµСЂСЏРµРј РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ
    health_results = new_client_manager.check_all_servers_health()
    
    # РЎРѕР·РґР°РµРј РєРЅРѕРїРєРё РґР»СЏ Р»РѕРєР°С†РёР№ СЃ С„Р»Р°РіР°РјРё Рё СЃС‚Р°С‚СѓСЃРѕРј
    location_buttons = []
    location_flags = {
        "Finland": "рџ‡«рџ‡®",
        "Latvia": "рџ‡±рџ‡»", 
        "Estonia": "рџ‡Єрџ‡Є"
    }
    
    # Р¤РѕСЂРјРёСЂСѓРµРј С‚РµРєСЃС‚ СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ Р»РѕРєР°С†РёСЏС…
    location_info_text = ""
    
    for location, servers in SERVERS_BY_LOCATION.items():
        if not servers:
            continue
            
        # РџСЂРѕРІРµСЂСЏРµРј РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ СЃРµСЂРІРµСЂРѕРІ РІ Р»РѕРєР°С†РёРё
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
        
        # РћРїСЂРµРґРµР»СЏРµРј СЃС‚Р°С‚СѓСЃ Р»РѕРєР°С†РёРё
        if available_servers > 0:
            status_icon = UIEmojis.SUCCESS
            status_text = f"Р”РѕСЃС‚СѓРїРЅРѕ {available_servers}/{total_servers} СЃРµСЂРІРµСЂРѕРІ"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"select_server_{location.lower()}"
        else:
            status_icon = UIEmojis.ERROR
            status_text = "РќРµРґРѕСЃС‚СѓРїРЅРѕ"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"server_unavailable_{location.lower()}"
        
        location_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Р”РѕР±Р°РІР»СЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ Р»РѕРєР°С†РёРё РІ С‚РµРєСЃС‚
        location_info_text += f"{flag} <b>{location}</b> - {status_text}\n"
    
    # Р”РѕР±Р°РІР»СЏРµРј РєРЅРѕРїРєСѓ "РђРІС‚РѕРІС‹Р±РѕСЂ" (С‚РѕР»СЊРєРѕ РµСЃР»Рё РµСЃС‚СЊ РґРѕСЃС‚СѓРїРЅС‹Рµ СЃРµСЂРІРµСЂС‹)
    available_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
    if available_servers > 0:
        location_buttons.append([InlineKeyboardButton("рџЋЇ РђРІС‚РѕРІС‹Р±РѕСЂ", callback_data="select_server_auto")])
        location_info_text += "<b>рџЋЇ РђРІС‚РѕРІС‹Р±РѕСЂ</b> - Р›РѕРєР°С†РёСЏ СЃ РЅР°РёРјРµРЅСЊС€РµР№ РЅР°РіСЂСѓР·РєРѕР№\n"
    
    location_buttons.append([InlineKeyboardButton(f"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ", callback_data="refresh_servers")])
    
    # РћРїСЂРµРґРµР»СЏРµРј С‚РµРєСЃС‚ РїРµСЂРёРѕРґР° Рё РєРЅРѕРїРєСѓ РЅР°Р·Р°Рґ РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ С‚РёРїР° РїРѕРєСѓРїРєРё
    pending_period = context.user_data.get("pending_period")
    if pending_period == "month":
        period_text = "1 РјРµСЃСЏС† Р·Р° 100в‚Ѕ"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "3month":
        period_text = "3 РјРµСЃСЏС†Р° Р·Р° 250в‚Ѕ"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "points_month":
        period_text = "1 РјРµСЃСЏС† Р·Р° 1 Р±Р°Р»Р»"
        location_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="spend_points")])
    else:
        period_text = "РќРµРёР·РІРµСЃС‚РЅС‹Р№ РїРµСЂРёРѕРґ"
        location_buttons.append([UIButtons.back_button()])
    
    keyboard = InlineKeyboardMarkup(location_buttons)
    
    message_text = f"{UIStyles.subheader(f'Р’С‹Р±СЂР°РЅ РїРµСЂРёРѕРґ: {period_text}')}\n\n{UIMessages.server_selection_message()}\n\n{location_info_text}"
    
    await safe_edit_or_reply_universal(message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='server_selection')

# РћР±СЂР°Р±РѕС‚С‡РёРє РІС‹Р±РѕСЂР° СЃРµСЂРІРµСЂР°
async def select_server_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # РћР±СЂР°Р±РѕС‚РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ СЃРїРёСЃРєР° СЃРµСЂРІРµСЂРѕРІ
    if query.data == "refresh_servers":
        await server_selection_menu(update, context)
        return
    
    # РћР±СЂР°Р±РѕС‚РєР° РЅРµРґРѕСЃС‚СѓРїРЅС‹С… Р»РѕРєР°С†РёР№
    if query.data.startswith("server_unavailable_"):
        location_name = query.data.replace("server_unavailable_", "").title()
        await safe_edit_or_reply(
            query.message, 
            f"{UIEmojis.ERROR} Р›РѕРєР°С†РёСЏ {location_name} РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅР°\n\n"
            f"РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РІС‹Р±РµСЂРёС‚Рµ РґСЂСѓРіСѓСЋ Р»РѕРєР°С†РёСЋ РёР»Рё РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.\n\n"
            f"Р”Р»СЏ РѕР±РЅРѕРІР»РµРЅРёСЏ СЃС‚Р°С‚СѓСЃР° СЃРµСЂРІРµСЂРѕРІ РЅР°Р¶РјРёС‚Рµ РєРЅРѕРїРєСѓ \"{UIEmojis.REFRESH} РћР±РЅРѕРІРёС‚СЊ\"",
            parse_mode="HTML"
        )
        return
    
    # РЎРѕС…СЂР°РЅСЏРµРј РІС‹Р±СЂР°РЅРЅСѓСЋ Р»РѕРєР°С†РёСЋ
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
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} РќРµРІРµСЂРЅС‹Р№ РІС‹Р±РѕСЂ Р»РѕРєР°С†РёРё")
        return
    
    # РџСЂРѕРІРµСЂСЏРµРј РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ РІС‹Р±СЂР°РЅРЅРѕР№ Р»РѕРєР°С†РёРё
    if selected_location != "auto":
        # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё РґРѕСЃС‚СѓРїРЅС‹Рµ СЃРµСЂРІРµСЂС‹ РІ Р»РѕРєР°С†РёРё
        available_servers = 0
        for server in SERVERS_BY_LOCATION.get(selected_location, []):
            if server["host"] and server["login"] and server["password"]:
                if new_client_manager.check_server_health(server["name"]):
                    available_servers += 1
        
        if available_servers == 0:
            await safe_edit_or_reply(
                query.message, 
                f"вќЊ Р›РѕРєР°С†РёСЏ {selected_location} РЅРµРґРѕСЃС‚СѓРїРЅР°\n\n"
                f"Р’СЃРµ СЃРµСЂРІРµСЂС‹ РІ СЌС‚РѕР№ Р»РѕРєР°С†РёРё РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅС‹. РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РІС‹Р±РµСЂРёС‚Рµ РґСЂСѓРіСѓСЋ Р»РѕРєР°С†РёСЋ.",
                parse_mode="HTML"
            )
            return
    else:
        # Р”Р»СЏ Р°РІС‚РѕРІС‹Р±РѕСЂР° РїСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё РґРѕСЃС‚СѓРїРЅС‹Рµ СЃРµСЂРІРµСЂС‹ РІ Р»СЋР±РѕР№ Р»РѕРєР°С†РёРё
        total_available = 0
        for location, servers in SERVERS_BY_LOCATION.items():
            for server in servers:
                if server["host"] and server["login"] and server["password"]:
                    if new_client_manager.check_server_health(server["name"]):
                        total_available += 1
        
        if total_available == 0:
            await safe_edit_or_reply(
                query.message, 
                "вќЊ РќРµС‚ РґРѕСЃС‚СѓРїРЅС‹С… СЃРµСЂРІРµСЂРѕРІ\n\n"
                "Р’СЃРµ СЃРµСЂРІРµСЂС‹ РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅС‹. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.",
                parse_mode="HTML"
            )
            return
    
    # РЎРѕС…СЂР°РЅСЏРµРј РІС‹Р±СЂР°РЅРЅСѓСЋ Р»РѕРєР°С†РёСЋ
    context.user_data["selected_location"] = selected_location
    
    # РџРѕР»СѓС‡Р°РµРј СЃРѕС…СЂР°РЅРµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
    period = context.user_data.get("pending_period")
    price = context.user_data.get("pending_price")
    
    # Р—Р°РїСѓСЃРєР°РµРј РїСЂРѕС†РµСЃСЃ РѕРїР»Р°С‚С‹
    await handle_payment(update, context, price, period)



# === РќР°РІРёРіР°С†РёРѕРЅРЅС‹Р№ СЃС‚РµРє Рё СѓРЅРёРІРµСЂСЃР°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє "РќР°Р·Р°Рґ" ===
def push_nav(context, state, max_size=10):
    stack = context.user_data.setdefault('nav_stack', [])
    
    # РћРіСЂР°РЅРёС‡РёРІР°РµРј СЂР°Р·РјРµСЂ СЃС‚РµРєР°
    if len(stack) >= max_size:
        stack.pop(0)  # РЈРґР°Р»СЏРµРј СЃР°РјС‹Р№ СЃС‚Р°СЂС‹Р№ СЌР»РµРјРµРЅС‚
    
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
    
    # Р•СЃР»Рё СЃС‚РµРє РїСѓСЃС‚РѕР№ вЂ” РІРѕР·РІСЂР°С‰Р°РµРјСЃСЏ РІ РіР»Р°РІРЅРѕРµ РјРµРЅСЋ
    if prev_state is None:
        logger.info("BACK: prev_state is None, calling start()")
        await start(update, context)
    elif prev_state == 'main_menu':
        # Р•СЃР»Рё РІРѕР·РІСЂР°С‰Р°РµРјСЃСЏ РІ main_menu, СЂРµРґР°РєС‚РёСЂСѓРµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ
        logger.info("BACK: prev_state == 'main_menu', calling edit_main_menu")
        await edit_main_menu(update, context)
    elif prev_state == 'instruction_menu':
        await instruction(update, context)
    elif prev_state == 'instruction_platform':
        # Р’РѕР·РІСЂР°С‰Р°РµРјСЃСЏ Рє РІС‹Р±РѕСЂСѓ РїР»Р°С‚С„РѕСЂРјС‹
        await instruction(update, context)

    elif prev_state == 'payment':
        # РџРѕСЃР»Рµ Р°РєС‚РёРІР°С†РёРё РєР»СЋС‡Р° РІРѕР·РІСЂР°С‰Р°РµРјСЃСЏ РІ РіР»Р°РІРЅРѕРµ РјРµРЅСЋ
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
    """РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    try:
        await safe_edit_or_reply(update.message, 'рџ”„ РџСЂРёРЅСѓРґРёС‚РµР»СЊРЅР°СЏ РїСЂРѕРІРµСЂРєР° СЃРµСЂРІРµСЂРѕРІ...')
        
        # РџСЂРѕРІРµСЂСЏРµРј РІСЃРµ СЃРµСЂРІРµСЂС‹
        health_results = server_manager.check_all_servers_health()
        new_client_health = new_client_manager.check_all_servers_health()
        
        # Р¤РѕСЂРјРёСЂСѓРµРј РѕС‚С‡РµС‚
        message = "рџ”Ќ Р РµР·СѓР»СЊС‚Р°С‚С‹ РїСЂРёРЅСѓРґРёС‚РµР»СЊРЅРѕР№ РїСЂРѕРІРµСЂРєРё:\n\n"
        
        # РћСЃРЅРѕРІРЅС‹Рµ СЃРµСЂРІРµСЂС‹
        message += "РћСЃРЅРѕРІРЅС‹Рµ СЃРµСЂРІРµСЂС‹:\n"
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
                    message += f"{status_icon} {server_name} (РѕС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РґР°РЅРЅС‹С…)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        message += "\nРЎРµСЂРІРµСЂС‹ РґР»СЏ РЅРѕРІС‹С… РєР»РёРµРЅС‚РѕРІ:\n"
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
                    message += f"{status_icon} {server_name} (РѕС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РґР°РЅРЅС‹С…)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        # РЎС‚Р°С‚РёСЃС‚РёРєР°
        total_servers = len(health_results) + len(new_client_health)
        online_servers = sum(1 for is_healthy in list(health_results.values()) + list(new_client_health.values()) if is_healthy)
        total_clients_all = total_clients_main + total_clients_new
        active_clients_all = active_clients_main + active_clients_new
        expired_clients_all = expired_clients_main + expired_clients_new
        
        message += f"\nРЎС‚Р°С‚РёСЃС‚РёРєР° СЃРµСЂРІРµСЂРѕРІ:\n"
        message += f"Р’СЃРµРіРѕ СЃРµСЂРІРµСЂРѕРІ: {total_servers}\n"
        message += f"РћРЅР»Р°Р№РЅ: {online_servers}\n"
        message += f"РћС„Р»Р°Р№РЅ: {total_servers - online_servers}\n"
        message += f"Р”РѕСЃС‚СѓРїРЅРѕСЃС‚СЊ: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"РЎС‚Р°С‚РёСЃС‚РёРєР° РєР»РёРµРЅС‚РѕРІ:\n"
        message += f"Р’СЃРµРіРѕ РєР»РёРµРЅС‚РѕРІ: {total_clients_all}\n"
        message += f"РђРєС‚РёРІРЅС‹С…: {active_clients_all}\n"
        message += f"РСЃС‚РµРєС€РёС…: {expired_clients_all}\n\n"
        message += f"Р’СЂРµРјСЏ РїСЂРѕРІРµСЂРєРё: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await safe_edit_or_reply(update.message, message, parse_mode="HTML")
        
    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ force_check_servers")
        await safe_edit_or_reply(update.message, f'РћС€РёР±РєР° РїСЂРё РїСЂРѕРІРµСЂРєРµ СЃРµСЂРІРµСЂРѕРІ: {e}')

# ===== Р¤РЈРќРљР¦РР Р”Р›РЇ Р РђР‘РћРўР« РЎ Р‘РђР›Р›РђРњР Р Р Р•Р¤Р•Р РђР›РђРњР =====

async def points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєР°Р·С‹РІР°РµС‚ Р±Р°Р»Р»С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    history = await get_points_history(user_id, 5)
    points_days = await get_config('points_days_per_point', '14')
    
    message = (
        f"*Р’Р°С€Рё Р±Р°Р»Р»С‹*\n\n"
        f"РўРµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ: *{mdv2(points_info['points'])} Р±Р°Р»Р»РѕРІ*\n"
        f"Р’СЃРµРіРѕ Р·Р°СЂР°Р±РѕС‚Р°РЅРѕ: {mdv2(points_info['total_earned'])}\n"
        f"Р’СЃРµРіРѕ РїРѕС‚СЂР°С‡РµРЅРѕ: {mdv2(points_info['total_spent'])}\n\n"
        f"*1 Р±Р°Р»Р» \\= {mdv2(points_days)} РґРЅРµР№ VPN\\!*\n\n"
    )
    
    if history:
        message += "*РџРѕСЃР»РµРґРЅРёРµ РѕРїРµСЂР°С†РёРё:*\n"
        for trans in history:
            icon = "\\+" if trans['type'] == 'earned' else "\\-"
            date_str = datetime.datetime.fromtimestamp(trans['created_at']).strftime('%d.%m %H:%M')
            message += f"{icon} {mdv2(trans['amount'])} \\- {mdv2(trans['description'])} \\({mdv2(date_str)}\\)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("РџРѕС‚СЂР°С‚РёС‚СЊ Р±Р°Р»Р»С‹", callback_data="spend_points")],
        [InlineKeyboardButton("РџРѕРґРµР»РёС‚СЊСЃСЏ СЃСЃС‹Р»РєРѕР№", callback_data="referral")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="back")]
    ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"points_callback: failed to edit message: {e}")

async def spend_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєР°Р·С‹РІР°РµС‚ РјРµРЅСЋ С‚СЂР°С‚С‹ Р±Р°Р»Р»РѕРІ"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '14')
    
    if points_info['points'] < 1:
        message = (
            f"{UIEmojis.ERROR} *РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ*\n\n"
            "РЈ РІР°СЃ РЅРµС‚ Р±Р°Р»Р»РѕРІ РґР»СЏ С‚СЂР°С‚С‹\\.\n"
            "РџСЂРёРіР»Р°С€Р°Р№С‚Рµ РґСЂСѓР·РµР№, С‡С‚РѕР±С‹ Р·Р°СЂР°Р±РѕС‚Р°С‚СЊ Р±Р°Р»Р»С‹\\!\n\n"
            f"1 СЂРµС„РµСЂР°Р» \\= {mdv2(points_days)} РґРЅРµР№ VPN"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("РџРѕРґРµР»РёС‚СЊСЃСЏ СЃСЃС‹Р»РєРѕР№", callback_data="referral")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="points")]
        ])
    else:
        message = (
            f"*РџРѕС‚СЂР°С‚РёС‚СЊ Р±Р°Р»Р»С‹*\n\n"
            f"РЈ РІР°СЃ РµСЃС‚СЊ: *{mdv2(points_info['points'])} Р±Р°Р»Р»РѕРІ*\n\n"
            f"*Р”РѕСЃС‚СѓРїРЅС‹Рµ РїРѕРєСѓРїРєРё:*\n"
            f"вЂў 1 Р±Р°Р»Р» \\= {mdv2(points_days)} РґРЅРµР№ VPN\n"
            f"вЂў 1 Р±Р°Р»Р» \\= РїСЂРѕРґР»РµРЅРёРµ РЅР° {mdv2(points_days)} РґРЅРµР№\n\n"
            f"Р’С‹Р±РµСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"РљСѓРїРёС‚СЊ {mdv2(points_days)} РґРЅРµР№ Р·Р° 1 Р±Р°Р»Р»", callback_data="buy_with_points")],
            [InlineKeyboardButton(f"РџСЂРѕРґР»РёС‚СЊ РєР»СЋС‡ РЅР° {mdv2(points_days)} РґРЅРµР№ Р·Р° 1 Р±Р°Р»Р»", callback_data="extend_with_points")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="points")]
        ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"spend_points_callback: failed to edit message: {e}")

async def buy_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєСѓРїРєР° VPN Р·Р° Р±Р°Р»Р»С‹ - РІС‹Р±РѕСЂ СЃРµСЂРІРµСЂР°"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ!")
        return
    
    # РЎРѕС…СЂР°РЅСЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїРѕРєСѓРїРєРµ Р·Р° Р±Р°Р»Р»С‹
    context.user_data["pending_period"] = "points_month"
    context.user_data["pending_price"] = "1 Р±Р°Р»Р»"
    
    # РџРµСЂРµС…РѕРґРёРј Рє РІС‹Р±РѕСЂСѓ СЃРµСЂРІРµСЂР°
    await server_selection_menu(update, context)

async def extend_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р° Р·Р° Р±Р°Р»Р»С‹ - РІС‹Р±РѕСЂ РєР»СЋС‡Р°"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="spend_points")]
        ])
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ!", reply_markup=keyboard, menu_type='extend_key')
        return
    
    # РС‰РµРј Р°РєС‚РёРІРЅС‹Рµ РєР»СЋС‡Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
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
                            # Р”РѕР±Р°РІР»СЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РІСЂРµРјРµРЅРё РёСЃС‚РµС‡РµРЅРёСЏ
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            if expiry_timestamp > 0:
                                expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M')
                                client['expiry_str'] = expiry_str
                            else:
                                client['expiry_str'] = 'вЂ”'
                            all_clients.append(client)
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё РєР»РёРµРЅС‚РѕРІ СЃ СЃРµСЂРІРµСЂР° {server['name']}: {e}")

        if not all_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="spend_points")]
            ])
            await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РЈ РІР°СЃ РЅРµС‚ Р°РєС‚РёРІРЅС‹С… РєР»СЋС‡РµР№ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ!", reply_markup=keyboard, menu_type='extend_key')
            return
        
        # Р•СЃР»Рё С‚РѕР»СЊРєРѕ РѕРґРёРЅ РєР»СЋС‡ - РїСЂРѕРґР»РµРІР°РµРј СЃСЂР°Р·Сѓ
        if len(all_clients) == 1:
            client = all_clients[0]
            await extend_selected_key_with_points(update, context, client, user_id)
            return
        
        # РџРѕРєР°Р·С‹РІР°РµРј СЃРїРёСЃРѕРє РєР»СЋС‡РµР№ РґР»СЏ РІС‹Р±РѕСЂР°
        keyboard_buttons = []
        for i, client in enumerate(all_clients, 1):
            email = client['email']
            server_name = client.get('server_name', 'РќРµРёР·РІРµСЃС‚РЅРѕ')
            expiry_str = client.get('expiry_str', 'вЂ”')
            
            # РЎРѕР·РґР°РµРј РєРѕСЂРѕС‚РєРёР№ ID РґР»СЏ РєР»СЋС‡Р°
            import hashlib
            short_id = hashlib.md5(f"{user_id}:{email}:extend_points".encode()).hexdigest()[:8]
            extension_keys_cache[short_id] = {
                'email': email,
                'xui': client['xui'],
                'server_name': server_name,
                'user_id': user_id
            }
            
            button_text = f"РљР»СЋС‡ #{i} ({server_name}) - {expiry_str}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"extend_points_key:{short_id}")])
        
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="spend_points")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        points_days = await get_config('points_days_per_point', '14')
        message = (
            f"{UIStyles.header('РџСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р° Р·Р° Р±Р°Р»Р»С‹')}\n\n"
            f"<b>РЈ РІР°СЃ РµСЃС‚СЊ:</b> {points_info['points']} Р±Р°Р»Р»РѕРІ\n"
            f"<b>1 Р±Р°Р»Р»</b> = РїСЂРѕРґР»РµРЅРёРµ РЅР° {points_days} РґРЅРµР№\n\n"
            f"{UIStyles.description('Р’С‹Р±РµСЂРёС‚Рµ РєР»СЋС‡ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ:')}"
        )
        
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type='extend_key')
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё СЃРїРёСЃРєР° РєР»СЋС‡РµР№: {e}")
        await safe_edit_or_reply_universal(update.callback_query.message, "вќЊ РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё СЃРїРёСЃРєР° РєР»СЋС‡РµР№.", menu_type='extend_key')

async def extend_selected_key_with_points(update: Update, context: ContextTypes.DEFAULT_TYPE, client: dict, user_id: str):
    """РџСЂРѕРґР»РµРІР°РµС‚ РІС‹Р±СЂР°РЅРЅС‹Р№ РєР»СЋС‡ Р·Р° Р±Р°Р»Р»С‹"""
    try:
        xui = client['xui']
        email = client['email']
        server_name = client.get('server_name', 'РќРµРёР·РІРµСЃС‚РЅРѕ')
        
        # РџСЂРѕРґР»РµРІР°РµРј РєР»СЋС‡ РЎРќРђР§РђР›Рђ
        points_days = int(await get_config('points_days_per_point', '14'))
        response = xui.extendClient(email, points_days)
        if response and response.status_code == 200:
            # РљР»СЋС‡ РїСЂРѕРґР»РµРЅ СѓСЃРїРµС€РЅРѕ - РўР•РџР•Р Р¬ СЃРїРёСЃС‹РІР°РµРј Р±Р°Р»Р»С‹
            success = await spend_points(user_id, 1, f"РџСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р° {email} Р·Р° Р±Р°Р»Р»С‹", bot=context.bot)
            if not success:
                # Р•СЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ СЃРїРёСЃР°С‚СЊ Р±Р°Р»Р»С‹, РѕС‚РєР°С‚С‹РІР°РµРј РїСЂРѕРґР»РµРЅРёРµ
                try:
                    # РћС‚РєР°С‚С‹РІР°РµРј РїСЂРѕРґР»РµРЅРёРµ (СѓРјРµРЅСЊС€Р°РµРј РЅР° С‚Рµ Р¶Рµ РґРЅРё)
                    xui.extendClient(email, -points_days)
                    logger.warning(f"Rolled back extension for key {email} due to points spending failure")
                except Exception as e:
                    logger.error(f"Failed to rollback extension for key {email} after points failure: {e}")
                    # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ
                    await notify_admin(context.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєР°С‚РёС‚СЊ РїСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р° РїРѕСЃР»Рµ РЅРµСѓРґР°С‡РЅРѕРіРѕ СЃРїРёСЃР°РЅРёСЏ Р±Р°Р»Р»РѕРІ:\nРљР»СЋС‡: {email}\nРџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: {user_id}\nРћС€РёР±РєР°: {str(e)}")
                await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё СЃРїРёСЃР°РЅРёРё Р±Р°Р»Р»РѕРІ!", menu_type='extend_key')
                return
            # РћС‡РёС‰Р°РµРј СЃС‚Р°СЂС‹Рµ СѓРІРµРґРѕРјР»РµРЅРёСЏ РѕР± РёСЃС‚РµС‡РµРЅРёРё РґР»СЏ РїСЂРѕРґР»РµРЅРЅРѕРіРѕ РєР»СЋС‡Р°
            if notification_manager:
                await notification_manager.clear_key_notifications(user_id, email)
            
            # РџРѕР»СѓС‡Р°РµРј РЅРѕРІРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ
            clients_response = xui.list()
            expiry_str = "вЂ”"
            if clients_response.get('success', False):
                for inbound in clients_response.get('obj', []):
                    settings = json.loads(inbound.get('settings', '{}'))
                    for client in settings.get('clients', []):
                        if client.get('email') == email:
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else 'вЂ”'
                            break
            
            message = UIMessages.key_extended_message(
                email=email,
                server_name=server_name,
                days=points_days,
                expiry_str=expiry_str,
                period=None  # Р”Р»СЏ РїСЂРѕРґР»РµРЅРёСЏ Р·Р° Р±Р°Р»Р»С‹ РїРµСЂРёРѕРґ РЅРµ СѓРєР°Р·С‹РІР°РµРј
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
            ])
            
            await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')
        else:
            # РљР»СЋС‡ РЅРµ РїСЂРѕРґР»РµРЅ - Р±Р°Р»Р»С‹ РЅРµ СЃРїРёСЃС‹РІР°Р»РёСЃСЊ, РїСЂРѕСЃС‚Рѕ СЃРѕРѕР±С‰Р°РµРј РѕР± РѕС€РёР±РєРµ
            await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё РїСЂРѕРґР»РµРЅРёРё РєР»СЋС‡Р°.", menu_type='extend_key')
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРѕРґР»РµРЅРёСЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ РєР»СЋС‡Р° Р·Р° Р±Р°Р»Р»С‹: {e}")
        # Р‘Р°Р»Р»С‹ РЅРµ СЃРїРёСЃС‹РІР°Р»РёСЃСЊ, РїСЂРѕСЃС‚Рѕ СЃРѕРѕР±С‰Р°РµРј РѕР± РѕС€РёР±РєРµ
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё РїСЂРѕРґР»РµРЅРёРё.", menu_type='extend_key')

async def extend_points_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚С‡РёРє РІС‹Р±РѕСЂР° РєР»СЋС‡Р° РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ Р·Р° Р±Р°Р»Р»С‹"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    callback_data = update.callback_query.data
    
    # РР·РІР»РµРєР°РµРј short_id РёР· callback_data
    if not callback_data.startswith("extend_points_key:"):
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РќРµРІРµСЂРЅС‹Р№ Р·Р°РїСЂРѕСЃ!", menu_type='extend_key')
        return
    
    short_id = callback_data.split(":", 1)[1]
    
    # РџРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР»СЋС‡Рµ РёР· РєСЌС€Р°
    if short_id not in extension_keys_cache:
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓСЃС‚Р°СЂРµР»!", menu_type='extend_key')
        return
    
    key_info = extension_keys_cache[short_id]
    
    # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РєР»СЋС‡ РїСЂРёРЅР°РґР»РµР¶РёС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
    if key_info['user_id'] != user_id:
        await safe_edit_or_reply_universal(update.callback_query.message, f"{UIEmojis.ERROR} Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ!", menu_type='extend_key')
        return
    
    # РЎРѕР·РґР°РµРј РѕР±СЉРµРєС‚ client РґР»СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
    client = {
        'email': key_info['email'],
        'xui': key_info['xui'],
        'server_name': key_info['server_name']
    }
    
    # РџСЂРѕРґР»РµРІР°РµРј РєР»СЋС‡
    await extend_selected_key_with_points(update, context, client, user_id)

async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РџРѕРєР°Р·С‹РІР°РµС‚ СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ РёРЅС„РѕСЂРјР°С†РёСЋ"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    
    # Р”РѕР±Р°РІР»СЏРµРј Р»РѕРіРёСЂРѕРІР°РЅРёРµ РґР»СЏ РґРёР°РіРЅРѕСЃС‚РёРєРё
    logger.info(f"REFERRAL_CALLBACK: user_id={user_id}")
    
    stats = await get_referral_stats(user_id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '30')
    
    # Р›РѕРіРёСЂСѓРµРј РїРѕР»СѓС‡РµРЅРЅСѓСЋ СЃС‚Р°С‚РёСЃС‚РёРєСѓ
    logger.info(f"REFERRAL_CALLBACK: stats={stats}, points={points_info}")
    
    # Р“РµРЅРµСЂРёСЂСѓРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃСЃС‹Р»РєСѓ
    referral_code = generate_referral_code(user_id)
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ СЂРµС„РµСЂР°Р»СЊРЅРѕРіРѕ РјРµРЅСЋ
    message = (
        f"{UIStyles.header('Р РµС„РµСЂР°Р»СЊРЅР°СЏ РїСЂРѕРіСЂР°РјРјР°')}\n\n"
        f"<b>Р’Р°С€Рё Р±Р°Р»Р»С‹:</b> {UIStyles.highlight(str(points_info['points']))}\n\n"
        f"<b>РЎС‚Р°С‚РёСЃС‚РёРєР° СЂРµС„РµСЂР°Р»РѕРІ:</b>\n"
        f"Р’СЃРµРіРѕ РїСЂРёРіР»Р°С€РµРЅРѕ: {stats['total_referrals']}\n"
        f"РЈСЃРїРµС€РЅС‹С… СЂРµС„РµСЂР°Р»РѕРІ: {stats['successful_referrals']}\n"
        f"РћР¶РёРґР°СЋС‚ РїРѕРєСѓРїРєРё: {stats['pending_referrals']}\n\n"
        f"<b>РљР°Рє Р·Р°СЂР°Р±РѕС‚Р°С‚СЊ Р±Р°Р»Р»С‹:</b>\n"
        f"1. РџРѕРґРµР»РёС‚РµСЃСЊ СЃСЃС‹Р»РєРѕР№ СЃ РґСЂСѓР·СЊСЏРјРё\n"
        f"2. Р”СЂСѓРі РїРµСЂРµС…РѕРґРёС‚ РїРѕ СЃСЃС‹Р»РєРµ\n"
        f"3. Р•СЃР»Рё РґСЂСѓРі РќРРљРћР“Р”Рђ РЅРµ РїРѕР»СЊР·РѕРІР°Р»СЃСЏ Р±РѕС‚РѕРј - РѕРЅ РїРѕРєСѓРїР°РµС‚ Рё РІС‹ РїРѕР»СѓС‡Р°РµС‚Рµ 1 Р±Р°Р»Р»!\n"
        f"4. Р•СЃР»Рё РґСЂСѓРі РЈР–Р• РїРѕР»СЊР·РѕРІР°Р»СЃСЏ Р±РѕС‚РѕРј - Р±Р°Р»Р» РЅРµ РІС‹РґР°РµС‚СЃСЏ\n"
        f"5. 1 Р±Р°Р»Р» = {points_days} РґРЅРµР№ VPN Р±РµСЃРїР»Р°С‚РЅРѕ!\n\n"
        f"{UIStyles.warning_message('Р’Р°Р¶РЅРѕ: Р‘Р°Р»Р» РІС‹РґР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ Р·Р° РїСЂРёРІР»РµС‡РµРЅРёРµ РЅРѕРІС‹С… РєР»РёРµРЅС‚РѕРІ!')}\n\n"
        f"<b>Р’Р°С€Р° СЂРµС„РµСЂР°Р»СЊРЅР°СЏ СЃСЃС‹Р»РєР°:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"<b>РљР°Рє РїРѕРґРµР»РёС‚СЊСЃСЏ:</b>\n"
        f"{UIStyles.description('вЂў РќР°Р¶РјРёС‚Рµ РЅР° СЃСЃС‹Р»РєСѓ РІС‹С€Рµ, С‡С‚РѕР±С‹ СЃРєРѕРїРёСЂРѕРІР°С‚СЊ')}\n"
        + UIStyles.description('вЂў РР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РєРЅРѕРїРєСѓ "РџРѕРґРµР»РёС‚СЊСЃСЏ РІ Telegram"')
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"РџРѕРґРµР»РёС‚СЊСЃСЏ РІ Telegram", url=f"https://t.me/share/url?url={referral_link}")],
        [UIButtons.back_button()]
    ])
    
    await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='referral_menu')

async def rename_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚С‡РёРє РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёСЏ РєР»СЋС‡Р°"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    short_id = query.data.split(':')[1]
    
    try:
        # РС‰РµРј РєР»СЋС‡ РїРѕ short_id
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
                            # РџСЂРѕРІРµСЂСЏРµРј short_id
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
                logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРёСЃРєРµ РєР»СЋС‡Р° РЅР° СЃРµСЂРІРµСЂРµ {server['name']}: {e}")
                continue
        
        if not key_email:
            await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ!")
            return
        
        # РЎРѕС…СЂР°РЅСЏРµРј email РєР»СЋС‡Р° Рё message_id РІ РєРѕРЅС‚РµРєСЃС‚Рµ РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµРіРѕ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ
        context.user_data['rename_key_email'] = key_email
        context.user_data['rename_message_id'] = query.message.message_id
        context.user_data['rename_chat_id'] = query.message.chat_id
        
        # Р—Р°РїСЂР°С€РёРІР°РµРј РЅРѕРІРѕРµ РёРјСЏ РєР»СЋС‡Р°
        message = (
            f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
            f"<b>РўРµРєСѓС‰РёР№ РєР»СЋС‡:</b> <code>{key_email}</code>\n\n"
            f"{UIStyles.description('Р’РІРµРґРёС‚Рµ РЅРѕРІРѕРµ РёРјСЏ РґР»СЏ РєР»СЋС‡Р° (РјР°РєСЃРёРјСѓРј 50 СЃРёРјРІРѕР»РѕРІ):')}\n\n"
            f"{UIStyles.warning_message('РРјСЏ Р±СѓРґРµС‚ РѕС‚РѕР±СЂР°Р¶Р°С‚СЊСЃСЏ РІ СЃРїРёСЃРєРµ РІР°С€РёС… РєР»СЋС‡РµР№')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        await safe_edit_or_reply_universal(query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='rename_key')
        
        # РЈСЃС‚Р°РЅР°РІР»РёРІР°РµРј СЃРѕСЃС‚РѕСЏРЅРёРµ РѕР¶РёРґР°РЅРёСЏ РІРІРѕРґР° РёРјРµРЅРё
        context.user_data['waiting_for_key_name'] = True
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РІ rename_key_callback: {e}")
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёРё РєР»СЋС‡Р°!")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """РћР±СЂР°Р±РѕС‚С‡РёРє С‚РµРєСЃС‚РѕРІС‹С… СЃРѕРѕР±С‰РµРЅРёР№ РґР»СЏ РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёСЏ РєР»СЋС‡РµР№"""
    if not await check_private_chat(update):
        return
    
    # РџСЂРѕРІРµСЂСЏРµРј, РѕР¶РёРґР°РµРј Р»Рё РјС‹ РІРІРѕРґ РёРјРµРЅРё РєР»СЋС‡Р°
    if not context.user_data.get('waiting_for_key_name', False):
        return
    
    user_id = str(update.message.from_user.id)
    new_name = update.message.text.strip()
    
    # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"РќРµ СѓРґР°Р»РѕСЃСЊ СѓРґР°Р»РёС‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ: {e}")
    
    # РџРѕР»СѓС‡Р°РµРј РґР°РЅРЅС‹Рµ РёР· РєРѕРЅС‚РµРєСЃС‚Р°
    message_id = context.user_data.get('rename_message_id')
    chat_id = context.user_data.get('rename_chat_id')
    
    if not message_id or not chat_id:
        logger.error("РќРµ РЅР°Р№РґРµРЅС‹ message_id РёР»Рё chat_id РІ РєРѕРЅС‚РµРєСЃС‚Рµ")
        return
    
    # Р”Р°РЅРЅС‹Рµ РґР»СЏ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ РїРѕР»СѓС‡РµРЅС‹ РёР· РєРѕРЅС‚РµРєСЃС‚Р°
    
    # Р’Р°Р»РёРґР°С†РёСЏ РёРјРµРЅРё
    if len(new_name) > 50:
        error_message = (
            f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
            f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> РРјСЏ РєР»СЋС‡Р° СЃР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ!\n\n"
            f"{UIStyles.description('РњР°РєСЃРёРјСѓРј 50 СЃРёРјРІРѕР»РѕРІ. РџРѕРїСЂРѕР±СѓР№С‚Рµ РµС‰Рµ СЂР°Р·.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            # Р РµРґР°РєС‚РёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ С‡РµСЂРµР· Р±РѕС‚Р°
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
            logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        return
    
    if not new_name:
        error_message = (
            f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
            f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> РРјСЏ РєР»СЋС‡Р° РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹Рј!\n\n"
            f"{UIStyles.description('Р’РІРµРґРёС‚Рµ РєРѕСЂСЂРµРєС‚РЅРѕРµ РёРјСЏ РґР»СЏ РєР»СЋС‡Р°.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            # Р РµРґР°РєС‚РёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ С‡РµСЂРµР· Р±РѕС‚Р°
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
            logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        return
    
    try:
        key_email = context.user_data.get('rename_key_email')
        if not key_email:
            error_message = (
                f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
                f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РІ РєРѕРЅС‚РµРєСЃС‚Рµ!"
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
                logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
            return
        
        # РќР°С…РѕРґРёРј СЃРµСЂРІРµСЂ СЃ РєР»СЋС‡РѕРј
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            error_message = (
                f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
                f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> РљР»СЋС‡ РЅРµ РЅР°Р№РґРµРЅ РЅР° СЃРµСЂРІРµСЂР°С…!"
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
                logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
            return
        
        # РћР±РЅРѕРІР»СЏРµРј РёРјСЏ РєР»СЋС‡Р°
        response = xui.updateClientName(key_email, new_name)
        
        if response and response.status_code == 200:
            # РћС‡РёС‰Р°РµРј СЃРѕСЃС‚РѕСЏРЅРёРµ
            context.user_data.pop('waiting_for_key_name', None)
            context.user_data.pop('rename_key_email', None)
            context.user_data.pop('rename_message_id', None)
            context.user_data.pop('rename_chat_id', None)
            
            # РџРѕРєР°Р·С‹РІР°РµРј СѓСЃРїРµС€РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РІ С‚РѕРј Р¶Рµ РѕРєРЅРµ
            success_message = (
                f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
                f"{UIEmojis.SUCCESS} <b>РљР»СЋС‡ СѓСЃРїРµС€РЅРѕ РїРµСЂРµРёРјРµРЅРѕРІР°РЅ!</b>\n\n"
                f"<b>РќРѕРІРѕРµ РёРјСЏ:</b> {new_name}\n"
                f"<b>Email:</b> <code>{key_email}</code>\n\n"
                f"{UIStyles.description('РРјСЏ Р±СѓРґРµС‚ РѕС‚РѕР±СЂР°Р¶Р°С‚СЊСЃСЏ РІ СЃРїРёСЃРєРµ РІР°С€РёС… РєР»СЋС‡РµР№')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("РњРѕРё РєР»СЋС‡Рё", callback_data="mykey")],
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
                logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        else:
            error_message = (
                f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
                f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±РЅРѕРІРёС‚СЊ РёРјСЏ РєР»СЋС‡Р° РЅР° СЃРµСЂРІРµСЂРµ!"
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
                logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
    
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРё РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёРё РєР»СЋС‡Р°: {e}")
        error_message = (
            f"{UIStyles.header('РџРµСЂРµРёРјРµРЅРѕРІР°РЅРёРµ РєР»СЋС‡Р°')}\n\n"
            f"{UIEmojis.ERROR} <b>РћС€РёР±РєР°:</b> {str(e)}"
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
            logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {edit_e}")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    
    # РћС‡РёС‰Р°РµРј СЃРѕСЃС‚РѕСЏРЅРёРµ РІСЃРµС… ConversationHandler'РѕРІ РїСЂРё РІС…РѕРґРµ РІ Р°РґРјРёРЅ РјРµРЅСЋ
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
        [InlineKeyboardButton("Р›РѕРіРё", callback_data="admin_errors")],
        [InlineKeyboardButton("РџСЂРѕРІРµСЂРєР° СЃРµСЂРІРµСЂРѕРІ", callback_data="admin_check_servers")],
        [InlineKeyboardButton("РЈРІРµРґРѕРјР»РµРЅРёСЏ", callback_data="admin_notifications")],
        [InlineKeyboardButton("Р Р°СЃСЃС‹Р»РєР°", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("РР·РјРµРЅРёС‚СЊ РґРЅРё Р·Р° Р±Р°Р»Р»", callback_data="admin_set_days_start")],
        [UIButtons.back_button()],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("admin_menu: message is None")
        return
    
    # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ Р°РґРјРёРЅ-РјРµРЅСЋ СЃ С„РѕС‚Рѕ
    admin_menu_text = UIMessages.admin_menu_message()
    await safe_edit_or_reply_universal(message, admin_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')


# ===== Р РђРЎРЎР«Р›РљРђ Р”Р›РЇ РђР”РњРРќРђ =====
BROADCAST_WAITING_TEXT = 1001
BROADCAST_CONFIRM = 1002

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.callback_query.message, 'РќРµС‚ РґРѕСЃС‚СѓРїР°.')
        return
    await update.callback_query.answer()
    # РЎРѕС…СЂР°РЅСЏРµРј РёСЃС…РѕРґРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РґР»СЏ РґР°Р»СЊРЅРµР№С€РёС… СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёР№
    context.user_data['broadcast_text'] = None
    context.user_data['broadcast_msg_chat_id'] = update.callback_query.message.chat_id
    context.user_data['broadcast_msg_id'] = update.callback_query.message.message_id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("в†ђ РќР°Р·Р°Рґ", callback_data="admin_broadcast_back")]])
    await safe_edit_or_reply_universal(update.callback_query.message, UIMessages.broadcast_intro_message(), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type='broadcast')
    return BROADCAST_WAITING_TEXT

async def admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    text = update.message.text
    context.user_data['broadcast_text'] = text
    # РЈРґР°Р»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ Р°РґРјРёРЅР° СЃ С‚РµРєСЃС‚РѕРј
    try:
        await update.message.delete()
    except Exception:
        pass
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("РћС‚РїСЂР°РІРёС‚СЊ", callback_data="admin_broadcast_send")],
        [InlineKeyboardButton("в†ђ РќР°Р·Р°Рґ", callback_data="admin_broadcast_back")]
    ])
    # Р РµРґР°РєС‚РёСЂСѓРµРј РёСЃС…РѕРґРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РЅР° РїСЂРµРґРїСЂРѕСЃРјРѕС‚СЂ
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
        logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ СЂР°СЃСЃС‹Р»РєРё: {e}")
        # Fallback: РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
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
            text=f"{UIEmojis.ERROR} РўРµРєСЃС‚ СЂР°СЃСЃС‹Р»РєРё РїСѓСЃС‚.",
            menu_type='broadcast'
        )
        return ConversationHandler.END

    # РџРѕР»СѓС‡Р°РµРј СЃРїРёСЃРѕРє РїРѕР»СѓС‡Р°С‚РµР»РµР№ Рё РёСЃРєР»СЋС‡Р°РµРј Р°РґРјРёРЅРѕРІ
    recipients = await get_all_user_ids()
    admin_set = set(str(a) for a in ADMIN_IDS)
    recipients = [uid for uid in recipients if str(uid) not in admin_set]
    total = len(recipients)
    sent = 0
    failed = 0
    # СЃРѕР±РёСЂР°РµРј РїРѕРґСЂРѕР±РЅСѓСЋ СЃС‚Р°С‚РёСЃС‚РёРєСѓ
    details = []  # [{'user_id': str, 'status': 'ok'|'failed'}]
    batch = 40

    # Р“РѕС‚РѕРІРёРј РёСЃС…РѕРґРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ Рє РїРѕРєР°Р·Сѓ РїСЂРѕРіСЂРµСЃСЃР°
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"<b>РћС‚РїСЂР°РІРєР° СЂР°СЃСЃС‹Р»РєРё</b>\n\nРћС‚РїСЂР°РІР»РµРЅРѕ: 0/{total}. РћС€РёР±РѕРє: 0.",
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
            # Р»С‘РіРєР°СЏ Р·Р°РґРµСЂР¶РєР° РјРµР¶РґСѓ СЃРѕРѕР±С‰РµРЅРёСЏРјРё
            await asyncio.sleep(0.05)
        # РїР°СѓР·Р° РјРµР¶РґСѓ Р±Р°С‚С‡Р°РјРё
        await asyncio.sleep(1.0)
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=msg_id,
                text=f"<b>РћС‚РїСЂР°РІРєР° СЂР°СЃСЃС‹Р»РєРё</b>\n\nРћС‚РїСЂР°РІР»РµРЅРѕ: {sent}/{total}. РћС€РёР±РѕРє: {failed}.",
                parse_mode="HTML",
                menu_type='broadcast'
            )
        except Exception:
            pass

    # СЃРѕС…СЂР°РЅСЏРµРј РґРµС‚Р°Р»Рё РІ user_data РґР»СЏ РєРЅРѕРїРѕРє
    context.user_data['broadcast_details'] = details
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Р­РєСЃРїРѕСЂС‚ CSV", callback_data="admin_broadcast_export")],
        [InlineKeyboardButton("в†ђ РќР°Р·Р°Рґ", callback_data="admin_broadcast_back")]
    ])
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=msg_id,
            text=f"<b>Р Р°СЃСЃС‹Р»РєР° Р·Р°РІРµСЂС€РµРЅР°</b>\n\nРЈСЃРїРµС€РЅРѕ: {sent}, РѕС€РёР±РѕРє: {failed} РёР· {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ С„РёРЅР°Р»СЊРЅРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ СЂР°СЃСЃС‹Р»РєРё: {e}")
        await safe_send_message_with_photo(
            context.bot,
            chat_id=chat_id,
            text=f"<b>Р Р°СЃСЃС‹Р»РєР° Р·Р°РІРµСЂС€РµРЅР°</b>\n\nРЈСЃРїРµС€РЅРѕ: {sent}, РѕС€РёР±РѕРє: {failed} РёР· {total}.",
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='broadcast'
        )
    return ConversationHandler.END

async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    
    # РћС‡РёС‰Р°РµРј СЃРѕСЃС‚РѕСЏРЅРёРµ СЂР°СЃСЃС‹Р»РєРё
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
    await context.bot.send_document(chat_id=update.effective_user.id, document=bio, caption="РћС‚С‡С‘С‚ СЂР°СЃСЃС‹Р»РєРё")

# Р РµРіРёСЃС‚СЂРёСЂСѓРµРј РєРѕРјР°РЅРґС‹
if __name__ == '__main__':
    # РЎРѕР·РґР°РµРј HTTPXRequest СЃ СѓРІРµР»РёС‡РµРЅРЅС‹РјРё С‚Р°Р№РјР°СѓС‚Р°РјРё РґР»СЏ СЃС‚Р°Р±РёР»СЊРЅРѕР№ СЂР°Р±РѕС‚С‹
    http_request = HTTPXRequest(
        connection_pool_size=8,  # Р Р°Р·РјРµСЂ РїСѓР»Р° СЃРѕРµРґРёРЅРµРЅРёР№
        connect_timeout=30.0,    # РўР°Р№РјР°СѓС‚ РЅР° СѓСЃС‚Р°РЅРѕРІРєСѓ СЃРѕРµРґРёРЅРµРЅРёСЏ (СѓРІРµР»РёС‡РµРЅ СЃ РґРµС„РѕР»С‚РЅС‹С… 5)
        read_timeout=30.0,       # РўР°Р№РјР°СѓС‚ РЅР° С‡С‚РµРЅРёРµ РѕС‚РІРµС‚Р° (СѓРІРµР»РёС‡РµРЅ СЃ РґРµС„РѕР»С‚РЅС‹С… 5)
        write_timeout=30.0,      # РўР°Р№РјР°СѓС‚ РЅР° РѕС‚РїСЂР°РІРєСѓ РґР°РЅРЅС‹С…
        pool_timeout=30.0        # РўР°Р№РјР°СѓС‚ РѕР¶РёРґР°РЅРёСЏ СЃРІРѕР±РѕРґРЅРѕРіРѕ СЃРѕРµРґРёРЅРµРЅРёСЏ РІ РїСѓР»Рµ
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(http_request).post_init(on_startup).build()
    
    # РЎРѕР·РґР°РµРј Flask РїСЂРёР»РѕР¶РµРЅРёРµ РґР»СЏ webhook'РѕРІ
    webhook_app = create_webhook_app(app)
    
    # Р—Р°РїСѓСЃРєР°РµРј webhook СЃРµСЂРІРµСЂ РІ РѕС‚РґРµР»СЊРЅРѕРј РїРѕС‚РѕРєРµ
    def run_webhook():
        webhook_app.run(host='0.0.0.0', port=5000, debug=False)
    
    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("Webhook СЃРµСЂРІРµСЂ Р·Р°РїСѓС‰РµРЅ РЅР° РїРѕСЂС‚Сѓ 5000")
    
    # Р”РѕР±Р°РІР»СЏРµРј РіР»РѕР±Р°Р»СЊРЅСѓСЋ РѕР±СЂР°Р±РѕС‚РєСѓ РѕС€РёР±РѕРє
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('mykey', mykey))
    app.add_handler(CommandHandler('instruction', instruction))
   
    app.add_handler(CommandHandler('check_servers', force_check_servers))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^instr_"))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^back_instr$"))
    app.add_handler(CallbackQueryHandler(extend_key_callback, pattern="^ext_key:"))
    app.add_handler(CallbackQueryHandler(extend_period_callback, pattern="^ext_per:"))

    # ConversationHandler РґР»СЏ РёРЅС‚РµСЂР°РєС‚РёРІРЅРѕР№ РЅР°СЃС‚СЂРѕР№РєРё РґРЅРµР№ Р·Р° Р±Р°Р»Р»
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
    # Р”РѕР±Р°РІР»СЏРµРј РѕР±СЂР°Р±РѕС‚С‡РёРєРё РґР»СЏ Р°РґРјРёРЅ-РјРµРЅСЋ
    app.add_handler(CallbackQueryHandler(admin_errors, pattern="^admin_errors$"))
    app.add_handler(CallbackQueryHandler(admin_errors, pattern="^admin_errors_refresh$"))
    app.add_handler(CallbackQueryHandler(admin_check_servers, pattern="^admin_check_servers$"))
    app.add_handler(CallbackQueryHandler(admin_notifications, pattern="^admin_notifications$"))
    app.add_handler(CallbackQueryHandler(admin_notifications, pattern="^admin_notifications_refresh$"))
    
    # Р Р°СЃСЃС‹Р»РєР°
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
    # Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє СЌРєСЃРїРѕСЂС‚Р°, С‡С‚РѕР±С‹ СЂР°Р±РѕС‚Р°Р» Рё РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ РґРёР°Р»РѕРіР°
    app.add_handler(CallbackQueryHandler(admin_broadcast_export, pattern="^admin_broadcast_export$"))
    # Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РєРЅРѕРїРєРё СЂР°СЃСЃС‹Р»РєРё (РЅР° СЃР»СѓС‡Р°Р№ РµСЃР»Рё ConversationHandler Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ)
    app.add_handler(CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$"))
    # Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РєРЅРѕРїРєРё РёР·РјРµРЅРµРЅРёСЏ РґРЅРµР№ (РЅР° СЃР»СѓС‡Р°Р№ РµСЃР»Рё ConversationHandler Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ)
    app.add_handler(CallbackQueryHandler(admin_set_days_start, pattern="^admin_set_days_start$"))
    # Р“Р»РѕР±Р°Р»СЊРЅС‹Р№ РѕР±СЂР°Р±РѕС‚С‡РёРє РґР»СЏ РєРЅРѕРїРєРё РЅР°Р·Р°Рґ РІ СЂР°СЃСЃС‹Р»РєРµ
    app.add_handler(CallbackQueryHandler(admin_broadcast_cancel, pattern="^admin_broadcast_back$"))

    
    # РћР±СЂР°Р±РѕС‚С‡РёРєРё РґР»СЏ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃРёСЃС‚РµРјС‹
    app.add_handler(CallbackQueryHandler(points_callback, pattern="^points$"))
    app.add_handler(CallbackQueryHandler(spend_points_callback, pattern="^spend_points$"))
    app.add_handler(CallbackQueryHandler(buy_with_points_callback, pattern="^buy_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_with_points_callback, pattern="^extend_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_points_key_callback, pattern="^extend_points_key:"))
    app.add_handler(CallbackQueryHandler(referral_callback, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(rename_key_callback, pattern="^rename_key:"))
    
    # РћР±СЂР°Р±РѕС‚С‡РёРє С‚РµРєСЃС‚РѕРІС‹С… СЃРѕРѕР±С‰РµРЅРёР№ РґР»СЏ РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёСЏ РєР»СЋС‡РµР№
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    app.run_polling()
