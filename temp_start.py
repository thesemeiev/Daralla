import logging
import html
from logging.handlers import RotatingFileHandler
import datetime
import json
import uuid
import os
import requests
import asyncio
from dotenv import load_dotenv
import pathlib
import telegram
from telegram.helpers import escape_markdown

async def safe_edit_or_reply(message, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    if message is None:
        logger.error("safe_edit_or_reply: message is None")
        return
    
    # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРµ Р»РѕРіРёСЂРѕРІР°РЅРёРµ РґР»СЏ РѕС‚Р»Р°РґРєРё
    logger.info(f"SAFE_EDIT_OR_REPLY: message={message}, text_length={len(text) if text else 0}, reply_markup={reply_markup is not None}")
    
    # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё Сѓ СЃРѕРѕР±С‰РµРЅРёСЏ С„РѕС‚Рѕ
    if message.photo:
        # Р•СЃР»Рё СЃРѕРѕР±С‰РµРЅРёРµ СЃРѕРґРµСЂР¶РёС‚ С„РѕС‚Рѕ, РёСЃРїРѕР»СЊР·СѓРµРј edit_caption
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return
        except Exception as e:
            logger.warning(f"Failed to edit caption, falling back to reply: {e}")
            # Fallback: РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
            await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return
    
    # РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РїРѕРїС‹С‚РѕРє РґР»СЏ СЃРµС‚РµРІС‹С… РѕС€РёР±РѕРє
    max_retries = 3
    retry_delay = 2  # СЃРµРєСѓРЅРґС‹
    
    for attempt in range(max_retries):
        try:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return  # РЈСЃРїРµС€РЅРѕ РѕС‚РїСЂР°РІР»РµРЅРѕ
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_text'):
                # РџСЂРѕР±СѓРµРј РѕС‚РїСЂР°РІРёС‚СЊ РєР°Рє РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РїРѕРІС‚РѕСЂРЅС‹РјРё РїРѕРїС‹С‚РєР°РјРё
                for reply_attempt in range(max_retries):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                        return  # РЈСЃРїРµС€РЅРѕ РѕС‚РїСЂР°РІР»РµРЅРѕ
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"РЎРµС‚РµРІР°СЏ РѕС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ СЃРѕРѕР±С‰РµРЅРёСЏ (РїРѕРїС‹С‚РєР° {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕСЃР»Рµ {max_retries} РїРѕРїС‹С‚РѕРє: {net_err}")
                            raise
            elif "can't parse entities" in str(e).lower() and hasattr(message, 'reply_text'):
                # Р¤РѕР»Р±СЌРє: РѕС‚РїСЂР°РІР»СЏРµРј РєР°Рє РѕР±С‹С‡РЅС‹Р№ С‚РµРєСЃС‚ Р±РµР· С„РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёСЏ
                await message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=disable_web_page_preview
                )
                return
            elif "Message is not modified" in str(e):
                # РРіРЅРѕСЂРёСЂСѓРµРј СЌС‚Сѓ РѕС€РёР±РєСѓ, С‚Р°Рє РєР°Рє СЃРѕРѕР±С‰РµРЅРёРµ СѓР¶Рµ СЃРѕРґРµСЂР¶РёС‚ РЅСѓР¶РЅРѕРµ СЃРѕРґРµСЂР¶РёРјРѕРµ
                return
            else:
                raise
        except telegram.error.NetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"РЎРµС‚РµРІР°СЏ РѕС€РёР±РєР° РїСЂРё СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРё СЃРѕРѕР±С‰РµРЅРёСЏ (РїРѕРїС‹С‚РєР° {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕСЃР»Рµ {max_retries} РїРѕРїС‹С‚РѕРє: {e}")
                # РџРѕСЃР»РµРґРЅСЏСЏ РїРѕРїС‹С‚РєР° - РїСЂРѕР±СѓРµРј РѕС‚РїСЂР°РІРёС‚СЊ РєР°Рє РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
                if hasattr(message, 'reply_text'):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                    except:
                        raise e  # Р•СЃР»Рё Рё СЌС‚Рѕ РЅРµ СѓРґР°Р»РѕСЃСЊ, РїСЂРѕР±СЂР°СЃС‹РІР°РµРј РёСЃС…РѕРґРЅСѓСЋ РѕС€РёР±РєСѓ
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
    """Р‘РµР·РѕРїР°СЃРЅР°СЏ РѕС‚РїСЂР°РІРєР° РёР»Рё СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ СЃ С„РѕС‚Рѕ"""
    if message is None:
        logger.error("safe_edit_or_reply_photo: message is None")
        return
    
    # РџСЂРѕРІРµСЂСЏРµРј СЃСѓС‰РµСЃС‚РІРѕРІР°РЅРёРµ С„Р°Р№Р»Р°
    if not os.path.exists(photo_path):
        logger.warning(f"Photo file not found: {photo_path}, falling back to text message")
        await safe_edit_or_reply(message, caption, reply_markup, parse_mode, disable_web_page_preview)
        return
    
    # РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РїРѕРїС‹С‚РѕРє РґР»СЏ СЃРµС‚РµРІС‹С… РѕС€РёР±РѕРє
    max_retries = 3
    retry_delay = 2  # СЃРµРєСѓРЅРґС‹
    
    for attempt in range(max_retries):
        try:
            # РџС‹С‚Р°РµРјСЃСЏ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ
            with open(photo_path, 'rb') as photo_file:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_file,
                        caption=caption,
                        parse_mode=parse_mode
                    ),
                    reply_markup=reply_markup
                )
            return  # РЈСЃРїРµС€РЅРѕ РѕС‚РїСЂР°РІР»РµРЅРѕ
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_photo'):
                # РџСЂРѕР±СѓРµРј РѕС‚РїСЂР°РІРёС‚СЊ РєР°Рє РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РїРѕРІС‚РѕСЂРЅС‹РјРё РїРѕРїС‹С‚РєР°РјРё
                for reply_attempt in range(max_retries):
                    try:
                        with open(photo_path, 'rb') as photo_file:
                            await message.reply_photo(
                                photo=photo_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode=parse_mode
                            )
                        return  # РЈСЃРїРµС€РЅРѕ РѕС‚РїСЂР°РІР»РµРЅРѕ
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"РЎРµС‚РµРІР°СЏ РѕС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ С„РѕС‚Рѕ (РїРѕРїС‹С‚РєР° {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ С„РѕС‚Рѕ РїРѕСЃР»Рµ {max_retries} РїРѕРїС‹С‚РѕРє: {net_err}")
                            raise
            elif "can't parse entities" in str(e) and hasattr(message, 'reply_photo'):
                # Р¤РѕР»Р±СЌРє: РѕС‚РїСЂР°РІР»СЏРµРј РєР°Рє РѕР±С‹С‡РЅС‹Р№ С‚РµРєСЃС‚ Р±РµР· С„РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёСЏ
                with open(photo_path, 'rb') as photo_file:
                    await message.reply_photo(
                        photo=photo_file,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                return
            elif "Message is not modified" in str(e):
                # РЎРѕРѕР±С‰РµРЅРёРµ РЅРµ РёР·РјРµРЅРёР»РѕСЃСЊ, СЌС‚Рѕ РЅРѕСЂРјР°Р»СЊРЅРѕ
                return
            else:
                # Р”СЂСѓРіРёРµ РѕС€РёР±РєРё - РїСЂРѕР±СѓРµРј РѕС‚РїСЂР°РІРёС‚СЊ РєР°Рє РЅРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
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
                        raise e  # Р•СЃР»Рё Рё СЌС‚Рѕ РЅРµ СѓРґР°Р»РѕСЃСЊ, РїСЂРѕР±СЂР°СЃС‹РІР°РµРј РёСЃС…РѕРґРЅСѓСЋ РѕС€РёР±РєСѓ
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
    """РЈРЅРёРІРµСЂСЃР°Р»СЊРЅР°СЏ С„СѓРЅРєС†РёСЏ РґР»СЏ РѕС‚РїСЂР°РІРєРё/СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№ СЃ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРёРј РІС‹Р±РѕСЂРѕРј С„РѕС‚Рѕ РёР»Рё С‚РµРєСЃС‚Р°"""
    if message is None:
        logger.error("safe_edit_or_reply_universal: message is None")
        return
    
    # Р•СЃР»Рё СѓРєР°Р·Р°РЅ С‚РёРї РјРµРЅСЋ Рё РµСЃС‚СЊ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‰РµРµ РёР·РѕР±СЂР°Р¶РµРЅРёРµ, РёСЃРїРѕР»СЊР·СѓРµРј С„РѕС‚Рѕ
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            await safe_edit_or_reply_photo(message, photo_path, text, reply_markup, parse_mode, disable_web_page_preview)
            return
    
    # РРЅР°С‡Рµ РёСЃРїРѕР»СЊР·СѓРµРј РѕР±С‹С‡РЅРѕРµ С‚РµРєСЃС‚РѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
    await safe_edit_or_reply(message, text, reply_markup, parse_mode, disable_web_page_preview)

async def safe_send_message_with_photo(bot, chat_id, text, reply_markup=None, parse_mode=None, menu_type=None):
    """Р‘РµР·РѕРїР°СЃРЅР°СЏ РѕС‚РїСЂР°РІРєР° СЃРѕРѕР±С‰РµРЅРёСЏ СЃ С„РѕС‚Рѕ С‡РµСЂРµР· Р±РѕС‚Р°"""
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
    """Р‘РµР·РѕРїР°СЃРЅРѕРµ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ СЃ С„РѕС‚Рѕ С‡РµСЂРµР· Р±РѕС‚Р°"""
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            try:
                with open(photo_path, 'rb') as photo_file:
                    from telegram import InputMediaPhoto
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
                return
            except Exception as e:
                logger.warning(f"Failed to edit message with photo for menu_type {menu_type}: {e}")
    
    # Fallback to text message
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )


# РћРїСЂРµРґРµР»СЏРµРј РїСѓС‚СЊ Рє С„Р°Р№Р»Сѓ .env
current_dir = pathlib.Path(__file__).parent
project_root = current_dir.parent
env_path = project_root / '.env'

# Р—Р°РіСЂСѓР¶Р°РµРј .env РёР· РєРѕСЂРЅСЏ РїСЂРѕРµРєС‚Р°
if env_path.exists():
    load_dotenv(env_path)
else:
    print("Р’РќРРњРђРќРР•: Р¤Р°Р№Р» .env РЅРµ РЅР°Р№РґРµРЅ! РЎРѕР·РґР°Р№С‚Рµ С„Р°Р№Р» .env РІ РєРѕСЂРЅРµ РїСЂРѕРµРєС‚Р° СЃ РїРµСЂРµРјРµРЅРЅС‹РјРё РѕРєСЂСѓР¶РµРЅРёСЏ.")
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

def mdv2(s):
    return escape_markdown(str(s), version=2)
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from yookassa import Payment, Configuration
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# РРјРїРѕСЂС‚ РґР»СЏ webhook
from flask import Flask, request, jsonify
import threading
import hmac
import hashlib

from .keys_db import (
    init_payments_db, add_payment, get_payment, update_payment_status, get_all_pending_payments,
    get_pending_payment, cleanup_old_payments, cleanup_expired_pending_payments,
    init_referral_db, save_referral_connection, get_pending_referral, mark_referral_reward_given,
    add_points, spend_points, get_user_points, get_points_history, get_referral_stats,
    is_known_user, register_simple_user, get_all_user_ids,
    atomic_referral_reward, atomic_refund_points,
    get_config, set_config, get_all_config
)


from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_result

# ===== Р Р•Р¤Р•Р РђР›Р¬РќРђРЇ РЎРРЎРўР•РњРђ =====

# РЈРїСЂРѕС‰РµРЅРЅР°СЏ СЂРµС„РµСЂР°Р»СЊРЅР°СЏ СЃРёСЃС‚РµРјР° - РёСЃРїРѕР»СЊР·СѓРµРј С‚РѕР»СЊРєРѕ user_id

def generate_referral_code(user_id: str) -> str:
    """Р“РµРЅРµСЂРёСЂСѓРµС‚ РїСЂРѕСЃС‚РѕР№ СЂРµС„РµСЂР°Р»СЊРЅС‹Р№ РєРѕРґ РЅР° РѕСЃРЅРѕРІРµ user_id"""
    try:
        if not user_id:
            logger.error(f"GENERATE_REFERRAL_CODE: Invalid user_id - {user_id}")
            return None
            
        # РџСЂРѕСЃС‚РѕР№ РєРѕРґ - РїСЂРѕСЃС‚Рѕ user_id
        logger.info(f"GENERATE_REFERRAL_CODE: Generated simple code for user {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"GENERATE_REFERRAL_CODE: Critical error - {e}")
        return None

def decode_referral_code(code: str) -> str:
    """Р”РµРєРѕРґРёСЂСѓРµС‚ РїСЂРѕСЃС‚РѕР№ СЂРµС„РµСЂР°Р»СЊРЅС‹Р№ РєРѕРґ (РїСЂРѕСЃС‚Рѕ РІРѕР·РІСЂР°С‰Р°РµС‚ user_id)"""
    try:
        if not code:
            logger.error(f"DECODE_REFERRAL_CODE: Empty code")
            return None
            
        # РџСЂРѕСЃС‚Р°СЏ РїСЂРѕРІРµСЂРєР° - РєРѕРґ РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ С‡РёСЃР»РѕРј (user_id)
        if not code.isdigit():
            logger.warning(f"DECODE_REFERRAL_CODE: Invalid code format - {code}")
            return None
            
        logger.info(f"DECODE_REFERRAL_CODE: Valid code for user {code}")
        return code
        
    except Exception as e:
        logger.error(f"DECODE_REFERRAL_CODE: Critical error - {e}")
        return None




YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# РџРѕРґРґРµСЂР¶РєР° РЅРµСЃРєРѕР»СЊРєРёС… Р°РґРјРёРЅРѕРІ С‡РµСЂРµР· РїРµСЂРµРјРµРЅРЅСѓСЋ РѕРєСЂСѓР¶РµРЅРёСЏ
ADMIN_IDS_STR = os.getenv("ADMIN_ID", os.getenv("ADMIN_IDS", ""))
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()] if ADMIN_IDS_STR else []

# РџСѓС‚Рё Рє РёР·РѕР±СЂР°Р¶РµРЅРёСЏРј РґР»СЏ РјРµРЅСЋ
IMAGE_PATHS = {
    'main_menu': 'images/main_menu.jpg',
    'instruction_menu': 'images/instruction_menu.jpg',
    'instruction_platform': 'images/instruction_platform.jpg',
    'buy_menu': 'images/buy_menu.jpg',
    'mykeys_menu': 'images/mykeys_menu.jpg',
    'points_menu': 'images/points_menu.jpg',
    'referral_menu': 'images/referral_menu.jpg',
    'server_selection': 'images/server_selection.jpg',
    'extend_key': 'images/extend_key.jpg',
    'rename_key': 'images/rename_key.jpg',
    'admin_menu': 'images/admin_menu.jpg',
    'admin_errors': 'images/admin_errors.jpg',
    'admin_notifications': 'images/admin_notifications.jpg',
    'admin_check_servers': 'images/admin_check_servers.jpg',
    'broadcast': 'images/broadcast.jpg',
    'payment': 'images/payment.jpg',
    'payment_success': 'images/payment_success.jpg',
    'payment_failed': 'images/payment_failed.jpg',
    'instruction_android': 'images/instruction_android.jpg',
    'instruction_ios': 'images/instruction_ios.jpg',
    'instruction_windows': 'images/instruction_windows.jpg',
    'instruction_macos': 'images/instruction_macos.jpg',
    'instruction_linux': 'images/instruction_linux.jpg',
    'instruction_tv': 'images/instruction_tv.jpg',
    'instruction_faq': 'images/instruction_faq.jpg',
    'key_success': 'images/key_success.jpg',
    'payment_success_key': 'images/payment_success_key.jpg'
}

# РџСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹С… РїРµСЂРµРјРµРЅРЅС‹С…
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN РЅРµ РЅР°Р№РґРµРЅ РІ РїРµСЂРµРјРµРЅРЅС‹С… РѕРєСЂСѓР¶РµРЅРёСЏ! РЎРѕР·РґР°Р№С‚Рµ С„Р°Р№Р» bot/.env")

if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    print("Р’РќРРњРђРќРР•: YOOKASSA_SHOP_ID РёР»Рё YOOKASSA_SECRET_KEY РЅРµ РЅР°Р№РґРµРЅС‹!")

# РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ СЃРµСЂРІРµСЂРѕРІ РїРѕ Р»РѕРєР°С†РёСЏРј
SERVERS_BY_LOCATION = {
    "Finland": [
        { 
            "name": "Finland-1", 
            "host": os.getenv("XUI_HOST_FINLAND_1"),
            "login": os.getenv("XUI_LOGIN_FINLAND_1"),
            "password": os.getenv("XUI_PASSWORD_FINLAND_1")
        },
        



        
    ],
    "Latvia": [
        {
            "name": "Latvia-1",
            "host": os.getenv("XUI_HOST_LATVIA_1"),
            "login": os.getenv("XUI_LOGIN_LATVIA_1"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_1")
        },
        {
            "name": "Latvia-2",
            "host": os.getenv("XUI_HOST_LATVIA_2"),
            "login": os.getenv("XUI_LOGIN_LATVIA_2"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_2")
        }
    ],
    "Estonia": [
        {
            "name": "Estonia-1",
            "host": os.getenv("XUI_HOST_ESTONIA_1"),
            "login": os.getenv("XUI_LOGIN_ESTONIA_1"),
            "password": os.getenv("XUI_PASSWORD_ESTONIA_1")
        }
    ]
}

# РЎРѕР·РґР°РµРј РїР»РѕСЃРєРёР№ СЃРїРёСЃРѕРє РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ РґР»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
SERVERS = []
for location_servers in SERVERS_BY_LOCATION.values():
    SERVERS.extend(location_servers)

# РЎРµСЂРІРµСЂР° РґР»СЏ РЅРѕРІС‹С… РєР»РёРµРЅС‚РѕРІ (С‚РµРїРµСЂСЊ РїРѕ Р»РѕРєР°С†РёСЏРј)
NEW_CLIENT_SERVERS = SERVERS_BY_LOCATION

# РџСЂРѕРІРµСЂСЏРµРј РєРѕРЅС„РёРіСѓСЂР°С†РёСЋ СЃРµСЂРІРµСЂРѕРІ
for i, server in enumerate(SERVERS):
    if not server["host"] or not server["login"] or not server["password"]:
        print(f"Р’РќРРњРђРќРР•: РЎРµСЂРІРµСЂ {server['name']} РЅРµ РЅР°СЃС‚СЂРѕРµРЅ! РџСЂРѕРІРµСЂСЊС‚Рµ РїРµСЂРµРјРµРЅРЅС‹Рµ XUI_HOST_{server['name'].upper().replace('-', '_')}, XUI_LOGIN_{server['name'].upper().replace('-', '_')}, XUI_PASSWORD_{server['name'].upper().replace('-', '_')}")

# РќР°СЃС‚СЂР°РёРІР°РµРј С„Р°Р№Р»РѕРІС‹Р№ Р»РѕРі СЃ СЂРѕС‚Р°С†РёРµР№ РІ РїР°РїРєРµ data/logs
try:
    from .keys_db import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

logs_dir = os.path.join(DATA_DIR, 'logs')
os.makedirs(logs_dir, exist_ok=True)
app_log_path = os.path.join(logs_dir, 'bot.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(app_log_path, maxBytes=1_048_576, backupCount=3, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def check_private_chat(update: Update) -> bool:
    """РџСЂРѕРІРµСЂСЏРµС‚, С‡С‚Рѕ РєРѕРјР°РЅРґР° РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РІ РїСЂРёРІР°С‚РЅРѕРј С‡Р°С‚Рµ.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ True РµСЃР»Рё С‡Р°С‚ РїСЂРёРІР°С‚РЅС‹Р№, False РµСЃР»Рё РЅРµС‚."""
    if update.effective_chat.type != 'private':
        await safe_edit_or_reply(update.message,
            f"{UIEmojis.WARNING} Р­С‚Р° РєРѕРјР°РЅРґР° СЂР°Р±РѕС‚Р°РµС‚ С‚РѕР»СЊРєРѕ РІ Р»РёС‡РЅС‹С… СЃРѕРѕР±С‰РµРЅРёСЏС….\n"
            f"РќР°РїРёС€РёС‚Рµ РјРЅРµ РІ Р»РёС‡РєСѓ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ VPN-РєР»СЋС‡Р°РјРё.",
            parse_mode="HTML"
        )
        return False
    return True

class X3:
    def __init__(self, login, password, host):
        self.login = login
        self.password = password
        self.host = host
        self.ses = requests.Session()
        
        # РћРїСЂРµРґРµР»СЏРµРј РїСЂРѕС‚РѕРєРѕР» Рё РЅР°СЃС‚СЂР°РёРІР°РµРј SSL СЃРѕРѕС‚РІРµС‚СЃС‚РІРµРЅРЅРѕ
        if host.startswith('https://'):
            self.ses.verify = True
        else:
            self.ses.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # РЈРІРµР»РёС‡РёРІР°РµРј С‚Р°Р№РјР°СѓС‚С‹ РґР»СЏ Р»СѓС‡С€РµР№ СЃС‚Р°Р±РёР»СЊРЅРѕСЃС‚Рё
        self.ses.timeout = (30, 30)  # (connect timeout, read timeout)
        
        self.data = {"username": self.login, "password": self.password}
        logger.info(f"РџРѕРґРєР»СЋС‡РµРЅРёРµ Рє XUI СЃРµСЂРІРµСЂСѓ: {host} (SSL: {self.ses.verify})")
        self._login()
    
    def _login(self):
        """Р’С‹РїРѕР»РЅСЏРµС‚ РІС…РѕРґ РІ XUI РїР°РЅРµР»СЊ"""
        try:
            # РџСЂРѕР±СѓРµРј СЃРЅР°С‡Р°Р»Р° СЃ С‚РµРєСѓС‰РёРјРё РЅР°СЃС‚СЂРѕР№РєР°РјРё
            try:
                login_response = self.ses.post(f"{self.host}/login", data=self.data, timeout=30)
            except requests.exceptions.SSLError:
                # Р•СЃР»Рё РїРѕР»СѓС‡РёР»Рё РѕС€РёР±РєСѓ SSL, РїСЂРѕР±СѓРµРј Р±РµР· РїСЂРѕРІРµСЂРєРё СЃРµСЂС‚РёС„РёРєР°С‚Р°
                logger.warning(f"SSL РѕС€РёР±РєР° РїСЂРё РїРѕРґРєР»СЋС‡РµРЅРёРё Рє {self.host}, РїСЂРѕР±СѓРµРј Р±РµР· РїСЂРѕРІРµСЂРєРё СЃРµСЂС‚РёС„РёРєР°С‚Р°")
                self.ses.verify = False
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                login_response = self.ses.post(f"{self.host}/login", data=self.data, timeout=30)
            
            logger.info(f"XUI Login Response - Status: {login_response.status_code}")
            logger.info(f"XUI Login Response - Text: {login_response.text[:200]}...")
            
            if login_response.status_code != 200:
                logger.error(f"РћС€РёР±РєР° РІС…РѕРґР° РІ XUI: {login_response.status_code} - {login_response.text}")
                raise Exception(f"Login failed with status {login_response.status_code}")
            
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РјС‹ РґРµР№СЃС‚РІРёС‚РµР»СЊРЅРѕ РІРѕС€Р»Рё (РѕР±С‹С‡РЅРѕ РІ РѕС‚РІРµС‚Рµ РµСЃС‚СЊ С‡С‚Рѕ-С‚Рѕ, СѓРєР°Р·С‹РІР°СЋС‰РµРµ РЅР° СѓСЃРїРµС€РЅС‹Р№ РІС…РѕРґ)
            if "error" in login_response.text.lower() or "invalid" in login_response.text.lower():
                logger.error(f"РћС€РёР±РєР° Р°СѓС‚РµРЅС‚РёС„РёРєР°С†РёРё: {login_response.text[:200]}")
                raise Exception("Authentication failed")
                
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРґРєР»СЋС‡РµРЅРёРё Рє XUI СЃРµСЂРІРµСЂСѓ {self.host}: {e}")
            raise

    def _reconnect(self):
        """РџРµСЂРµРїРѕРґРєР»СЋС‡Р°РµС‚СЃСЏ Рє СЃРµСЂРІРµСЂСѓ РїСЂРё РёСЃС‚РµС‡РµРЅРёРё СЃРµСЃСЃРёРё"""
        logger.info(f"РџРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёРµ Рє СЃРµСЂРІРµСЂСѓ {self.host}")
        self.ses = requests.Session()
        
        # Р’РѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµРј РЅР°СЃС‚СЂРѕР№РєРё SSL
        if self.host.startswith('https://'):
            self.ses.verify = True
        else:
            self.ses.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Р’РѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµРј СѓРІРµР»РёС‡РµРЅРЅС‹Рµ С‚Р°Р№РјР°СѓС‚С‹
        self.ses.timeout = (30, 30)
        
        self._login()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))


    def addClient(self, day, tg_id, user_email, timeout=15, hours=None, key_name=""):
        if hours is not None:
            # Р”Р»СЏ С‚РµСЃС‚РѕРІС‹С… РєР»СЋС‡РµР№ РёСЃРїРѕР»СЊР·СѓРµРј С‡Р°СЃС‹
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (hours * 3600000)
        else:
            # Р”Р»СЏ РѕР±С‹С‡РЅС‹С… РєР»СЋС‡РµР№ РёСЃРїРѕР»СЊР·СѓРµРј РґРЅРё
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (86400000 * day)
        header = {"Accept": "application/json"}
        client_data = {
            "id": str(uuid.uuid1()),
            "alterId": 90,
            "email": str(user_email),
            "limitIp": 1,
            "totalGB": 0,
            "expiryTime": x_time,
            "enable": True,
            "tgId": str(tg_id),
            "subId": key_name,  # РЎРѕС…СЂР°РЅСЏРµРј РёРјСЏ РєР»СЋС‡Р° РІ РїРѕР»Рµ subId
            "flow": "xtls-rprx-vision"
        }
        data1 = {
            "id": 1,
            "settings": json.dumps({"clients": [client_data]})
        }
        logger.info(f"Р”РѕР±Р°РІР»РµРЅРёРµ РєР»РёРµРЅС‚Р°: {user_email} РЅР° СЃРµСЂРІРµСЂ {self.host}")
        try:
            response = self.ses.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
            logger.info(f"XUI addClient Response - Status: {response.status_code}")
            logger.info(f"XUI addClient Response - Text: {response.text[:200]}...")
            
            # РџСЂРѕРІРµСЂСЏРµРј, РЅРµ РёСЃС‚РµРєР»Р° Р»Рё СЃРµСЃСЃРёСЏ
            if response.status_code == 200 and not response.text.strip():
                logger.warning("РџРѕР»СѓС‡РµРЅ РїСѓСЃС‚РѕР№ РѕС‚РІРµС‚, РІРѕР·РјРѕР¶РЅРѕ РёСЃС‚РµРєР»Р° СЃРµСЃСЃРёСЏ. РџРµСЂРµРїРѕРґРєР»СЋС‡Р°СЋСЃСЊ...")
                self._login()
                # РџРѕРІС‚РѕСЂСЏРµРј Р·Р°РїСЂРѕСЃ РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ
                response = self.ses.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
                logger.info(f"XUI addClient Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Status: {response.status_code}")
                logger.info(f"XUI addClient Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Text: {response.text[:200]}...")
            
            return response
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РґРѕР±Р°РІР»РµРЅРёРё РєР»РёРµРЅС‚Р° {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def extendClient(self, user_email, extend_days, timeout=15):
        """
        РџСЂРѕРґР»РµРІР°РµС‚ СЃСЂРѕРє РґРµР№СЃС‚РІРёСЏ РєР»СЋС‡Р° РєР»РёРµРЅС‚Р°
        :param user_email: Email РєР»РёРµРЅС‚Р°
        :param extend_days: РљРѕР»РёС‡РµСЃС‚РІРѕ РґРЅРµР№ РґР»СЏ РїСЂРѕРґР»РµРЅРёСЏ
        :param timeout: РўР°Р№РјР°СѓС‚ Р·Р°РїСЂРѕСЃР°
        :return: Response РѕР±СЉРµРєС‚
        """
        try:
            # РЎРЅР°С‡Р°Р»Р° РїРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР»РёРµРЅС‚Рµ
            inbounds_data = self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ СЃРїРёСЃРѕРє РєР»РёРµРЅС‚РѕРІ")
            
            client_found = False
            client_data = None
            inbound_id = None
            
            # РС‰РµРј РєР»РёРµРЅС‚Р° РїРѕ email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        
                        # Р’С‹С‡РёСЃР»СЏРµРј РЅРѕРІРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ
                        current_expiry = int(client.get('expiryTime', 0))
                        if current_expiry == 0:
                            # Р•СЃР»Рё РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅРѕ, РЅР°С‡РёРЅР°РµРј СЃ С‚РµРєСѓС‰РµРіРѕ РІСЂРµРјРµРЅРё
                            current_expiry = int(datetime.datetime.now().timestamp() * 1000)
                        
                        # Р”РѕР±Р°РІР»СЏРµРј РґРЅРё Рє С‚РµРєСѓС‰РµРјСѓ РІСЂРµРјРµРЅРё РёСЃС‚РµС‡РµРЅРёСЏ
                        new_expiry = current_expiry + (extend_days * 86400000)  # 86400000 РјСЃ = 1 РґРµРЅСЊ
                        client_data['expiryTime'] = new_expiry
                        
                        logger.info(f"РџСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р° {user_email}: СЃС‚Р°СЂРѕРµ РІСЂРµРјСЏ РёСЃС‚РµС‡РµРЅРёСЏ = {current_expiry}, РЅРѕРІРѕРµ = {new_expiry}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"РљР»РёРµРЅС‚ СЃ email {user_email} РЅРµ РЅР°Р№РґРµРЅ")
            
            # РћР±РЅРѕРІР»СЏРµРј РєР»РёРµРЅС‚Р°
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            logger.info(f"РџСЂРѕРґР»РµРЅРёРµ РєР»РёРµРЅС‚Р°: {user_email} РЅР° СЃРµСЂРІРµСЂРµ {self.host} РЅР° {extend_days} РґРЅРµР№")
            response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                   headers=header, json=data, timeout=timeout)
            
            logger.info(f"XUI extendClient Response - Status: {response.status_code}")
            logger.info(f"XUI extendClient Response - Text: {response.text[:200]}...")
            
            # РџСЂРѕРІРµСЂСЏРµРј, РЅРµ РёСЃС‚РµРєР»Р° Р»Рё СЃРµСЃСЃРёСЏ
            if response.status_code == 200 and not response.text.strip():
                logger.warning("РџРѕР»СѓС‡РµРЅ РїСѓСЃС‚РѕР№ РѕС‚РІРµС‚ РїСЂРё РїСЂРѕРґР»РµРЅРёРё, РїРµСЂРµРїРѕРґРєР»СЋС‡Р°СЋСЃСЊ...")
                self._login()
                response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI extendClient Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Status: {response.status_code}")
            
            return response
            
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїСЂРѕРґР»РµРЅРёРё РєР»РёРµРЅС‚Р° {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_client_count(self, timeout=15):
        """РџРѕРґСЃС‡РёС‚С‹РІР°РµС‚ РѕР±С‰РµРµ РєРѕР»РёС‡РµСЃС‚РІРѕ РєР»РёРµРЅС‚РѕРІ РЅР° СЃРµСЂРІРµСЂРµ"""
        try:
            response_data = self.list(timeout=timeout)
            logger.info(f"XUI list response: {response_data}")
            if 'obj' not in response_data:
                logger.error(f"РќРµРѕР¶РёРґР°РЅРЅС‹Р№ С„РѕСЂРјР°С‚ РѕС‚РІРµС‚Р° XUI: {response_data}")
                return 0
            inbounds = response_data['obj']
            total_clients = 0
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                total_clients += len(settings.get("clients", []))
            return total_clients
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРґСЃС‡РµС‚Рµ РєР»РёРµРЅС‚РѕРІ РЅР° {self.host}: {e}")
            return 0

    def get_clients_status_count(self, timeout=15):
        """РџРѕРґСЃС‡РёС‚С‹РІР°РµС‚ РєРѕР»РёС‡РµСЃС‚РІРѕ РєР»РёРµРЅС‚РѕРІ РїРѕ СЃС‚Р°С‚СѓСЃСѓ (Р°РєС‚РёРІРЅС‹Рµ/РёСЃС‚РµРєС€РёРµ)"""
        try:
            response_data = self.list(timeout=timeout)
            if 'obj' not in response_data:
                logger.error(f"РќРµРѕР¶РёРґР°РЅРЅС‹Р№ С„РѕСЂРјР°С‚ РѕС‚РІРµС‚Р° XUI: {response_data}")
                return 0, 0, 0
            
            inbounds = response_data['obj']
            total_clients = 0
            active_clients = 0
            expired_clients = 0
            current_time = int(datetime.datetime.now().timestamp() * 1000)
            
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                clients = settings.get("clients", [])
                total_clients += len(clients)
                
                for client in clients:
                    # РџСЂРѕРІРµСЂСЏРµРј, Р°РєС‚РёРІРµРЅ Р»Рё РєР»РёРµРЅС‚ (РЅРµ РёСЃС‚РµРє Р»Рё СЃСЂРѕРє)
                    expiry_time = client.get('expiryTime', 0)
                    if expiry_time == 0 or current_time < expiry_time:
                        active_clients += 1
                    else:
                        expired_clients += 1
            
            return total_clients, active_clients, expired_clients
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРґСЃС‡РµС‚Рµ СЃС‚Р°С‚СѓСЃР° РєР»РёРµРЅС‚РѕРІ РЅР° {self.host}: {e}")
            return 0, 0, 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def client_exists(self, user_email):
        for inbound in self.list()['obj']:
            settings = json.loads(inbound['settings'])
            for client in settings.get("clients", []):
                if client['email'] == user_email:
                    return True
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2)
    )
    def list(self, timeout=15):
        try:
            url = f'{self.host}/panel/api/inbounds/list'
            logger.info(f"РћС‚РїСЂР°РІРєР° Р·Р°РїСЂРѕСЃР° Рє {url}")
            
            # РџСЂРѕРІРµСЂСЏРµРј РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ СЃРµСЂРІРµСЂР°
            try:
                health_check = self.ses.get(f'{self.host}/ping', timeout=5)
                logger.info(f"РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё СЃРµСЂРІРµСЂР° {self.host}: {health_check.status_code}")
            except Exception as e:
                logger.warning(f"РЎРµСЂРІРµСЂ {self.host} РЅРµРґРѕСЃС‚СѓРїРµРЅ: {e}")
            
            response = self.ses.get(url, json=self.data, timeout=timeout)
            logger.info(f"XUI API Response - URL: {url}")
            logger.info(f"XUI API Response - Status: {response.status_code}, Headers: {dict(response.headers)}")
            logger.info(f"XUI API Response - Text: {response.text[:500]}...")  # Р›РѕРіРёСЂСѓРµРј РїРµСЂРІС‹Рµ 500 СЃРёРјРІРѕР»РѕРІ
            
            # РџСЂРѕРІРµСЂСЏРµРј СЃС‚Р°С‚СѓСЃ РѕС‚РІРµС‚Р°
            if response.status_code != 200:
                logger.error(f"XUI API РІРµСЂРЅСѓР» РЅРµРІРµСЂРЅС‹Р№ СЃС‚Р°С‚СѓСЃ: {response.status_code} РґР»СЏ URL {url}")
                if response.status_code == 404:
                    logger.error(f"Endpoint РЅРµ РЅР°Р№РґРµРЅ РЅР° СЃРµСЂРІРµСЂРµ {self.host}. Р’РѕР·РјРѕР¶РЅРѕ, СЃРµСЂРІРµСЂ РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚ API РёР»Рё С‚СЂРµР±СѓРµС‚ РѕР±РЅРѕРІР»РµРЅРёСЏ.")
                    return {'success': False, 'error': '404 Not Found', 'obj': []}  # Р’РѕР·РІСЂР°С‰Р°РµРј СЃС‚СЂСѓРєС‚СѓСЂСѓ, СЃРѕРІРјРµСЃС‚РёРјСѓСЋ СЃ РѕР¶РёРґР°РµРјС‹Рј С„РѕСЂРјР°С‚РѕРј
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РѕС‚РІРµС‚ РЅРµ РїСѓСЃС‚РѕР№
            if not response.text.strip():
                logger.error("XUI API РІРµСЂРЅСѓР» РїСѓСЃС‚РѕР№ РѕС‚РІРµС‚")
                raise Exception("РџСѓСЃС‚РѕР№ РѕС‚РІРµС‚ РѕС‚ СЃРµСЂРІРµСЂР°")
            
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РѕС‚РІРµС‚ РЅР°С‡РёРЅР°РµС‚СЃСЏ СЃ '{' РёР»Рё '[' (РїСЂРёР·РЅР°Рє JSON)
            if not response.text.strip().startswith(('{', '[')):
                logger.error(f"XUI API РІРµСЂРЅСѓР» РЅРµ-JSON РѕС‚РІРµС‚: {response.text[:200]}")
                # Р•СЃР»Рё РїРѕР»СѓС‡РёР»Рё HTML РІРјРµСЃС‚Рѕ JSON, РІРѕР·РјРѕР¶РЅРѕ СЃРµСЃСЃРёСЏ РёСЃС‚РµРєР»Р°
                if "<html" in response.text.lower() or "login" in response.text.lower():
                    logger.warning("РћР±РЅР°СЂСѓР¶РµРЅР° РёСЃС‚РµРєС€Р°СЏ СЃРµСЃСЃРёСЏ, РїРµСЂРµРїРѕРґРєР»СЋС‡Р°СЋСЃСЊ...")
                    self._reconnect()
                    # РџРѕРІС‚РѕСЂСЏРµРј Р·Р°РїСЂРѕСЃ РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ
                    response = self.ses.get(f'{self.host}/panel/api/inbounds/list', json=self.data, timeout=timeout)
                    logger.info(f"XUI API Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Status: {response.status_code}")
                    logger.info(f"XUI API Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Text: {response.text[:500]}...")
                    
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    
                    if not response.text.strip().startswith(('{', '[')):
                        raise Exception(f"РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РѕС‚РІРµС‚Р° РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ: {response.text[:200]}")
                
                else:
                    raise Exception(f"РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РѕС‚РІРµС‚Р°: {response.text[:200]}")
            
            try:
                return response.json()
            except json.JSONDecodeError as json_error:
                logger.error(f"РћС€РёР±РєР° РїР°СЂСЃРёРЅРіР° JSON: {json_error}")
                logger.error(f"РћС‚РІРµС‚ СЃРµСЂРІРµСЂР°: {response.text[:500]}")
                raise Exception(f"РћС€РёР±РєР° РїР°СЂСЃРёРЅРіР° JSON: {json_error}")
                
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё Р·Р°РїСЂРѕСЃРµ Рє XUI API: {e}")
            logger.error(f"Response status: {getattr(response, 'status_code', 'N/A')}")
            logger.error(f"Response text: {getattr(response, 'text', 'N/A')}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def deleteClient(self, user_email, timeout=15):
        for inbound in self.list(timeout=timeout)['obj']:
            settings = json.loads(inbound['settings'])
            for client in settings.get("clients", []):
                if client['email'] == user_email:
                    client_id = client['id']
                    inbound_id = inbound['id']
                    url = f"{self.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                    logger.info(f"РЈРґР°Р»СЏСЋ VLESS РєР»РёРµРЅС‚Р°: inbound_id={inbound_id}, client_id={client_id}, email={user_email}")
                    result = self.ses.post(url, timeout=timeout)
                    logger.info(f"РћС‚РІРµС‚ XUI: status_code={getattr(result, 'status_code', None)}, text={getattr(result, 'text', None)}")
                    if getattr(result, 'status_code', None) == 200:
                        logger.info(f"РљР»РёРµРЅС‚ СѓСЃРїРµС€РЅРѕ СѓРґР°Р»С‘РЅ: {user_email}")
                    return result
        logger.warning(f"РљР»РёРµРЅС‚ СЃ email={user_email} РЅРµ РЅР°Р№РґРµРЅ РЅРё РІ РѕРґРЅРѕРј inbound")
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def updateClientName(self, user_email, new_name, timeout=15):
        """
        РћР±РЅРѕРІР»СЏРµС‚ РёРјСЏ РєР»СЋС‡Р° (СЃРѕС…СЂР°РЅСЏРµС‚ РІ РїРѕР»Рµ subId)
        :param user_email: Email РєР»РёРµРЅС‚Р°
        :param new_name: РќРѕРІРѕРµ РёРјСЏ РєР»СЋС‡Р°
        :param timeout: РўР°Р№РјР°СѓС‚ Р·Р°РїСЂРѕСЃР°
        :return: Response РѕР±СЉРµРєС‚
        """
        try:
            # РЎРЅР°С‡Р°Р»Р° РїРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР»РёРµРЅС‚Рµ
            inbounds_data = self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ СЃРїРёСЃРѕРє РєР»РёРµРЅС‚РѕРІ")
            
            client_found = False
            client_data = None
            inbound_id = None
            
            # РС‰РµРј РєР»РёРµРЅС‚Р° РїРѕ email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        
                        # РћР±РЅРѕРІР»СЏРµРј РёРјСЏ РєР»СЋС‡Р° РІ РїРѕР»Рµ subId
                        client_data['subId'] = new_name
                        
                        logger.info(f"РћР±РЅРѕРІР»РµРЅРёРµ РёРјРµРЅРё РєР»СЋС‡Р° {user_email}: РЅРѕРІРѕРµ РёРјСЏ = {new_name}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"РљР»РёРµРЅС‚ СЃ email {user_email} РЅРµ РЅР°Р№РґРµРЅ")
            
            # РћР±РЅРѕРІР»СЏРµРј РєР»РёРµРЅС‚Р°
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', headers=header, json=data, timeout=timeout)
            logger.info(f"XUI updateClientName Response - Status: {response.status_code}")
            logger.info(f"XUI updateClientName Response - Text: {response.text[:200]}...")
            
            # РџСЂРѕРІРµСЂСЏРµРј, РЅРµ РёСЃС‚РµРєР»Р° Р»Рё СЃРµСЃСЃРёСЏ
            if response.status_code == 200 and not response.text.strip():
                logger.warning("РџРѕР»СѓС‡РµРЅ РїСѓСЃС‚РѕР№ РѕС‚РІРµС‚ РїСЂРё РѕР±РЅРѕРІР»РµРЅРёРё РёРјРµРЅРё, РїРµСЂРµРїРѕРґРєР»СЋС‡Р°СЋСЃСЊ...")
                self._login()
                response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI updateClientName Response РїРѕСЃР»Рµ РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ - Status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"РРјСЏ РєР»СЋС‡Р° СѓСЃРїРµС€РЅРѕ РѕР±РЅРѕРІР»РµРЅРѕ: {user_email} -> {new_name}")
            else:
                logger.error(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ РёРјРµРЅРё РєР»СЋС‡Р°: {response.status_code} - {response.text}")
            
            return response
            
        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїСЂРё РѕР±РЅРѕРІР»РµРЅРёРё РёРјРµРЅРё РєР»СЋС‡Р° {user_email}: {e}")
            raise

    def link(self, user_id: str):
        inbounds_list = self.list()['obj']
        for inbounds in inbounds_list:
            settings = json.loads(inbounds['settings'])
            stream = json.loads(inbounds['streamSettings'])

            client = next((c for c in settings.get("clients", []) if c['email'] == user_id), None)
            if not client:
                continue

            host_part = self.host.split('//')[-1]
            host = host_part.split(':')[0] if ':' in host_part else host_part
            port = inbounds.get('port', 443)
            reality = stream.get('realitySettings', {})
            reality_settings = reality.get('settings', {})
            pbk = reality_settings.get('publicKey', '')
            fingerprint = reality_settings.get('fingerprint', 'chrome')
            spx = reality_settings.get('spiderX', '/')
            dest = reality.get('dest', '')
            sni = dest.split(':')[0] if dest else 'google.com'
            logger.info(f"Reality РЅР°СЃС‚СЂРѕР№РєРё РґР»СЏ {self.host}: dest='{dest}', sni='{sni}'")
            short_ids = reality.get('shortIds', [''])
            sid = short_ids[0] if short_ids else ''
            network = stream.get('network', 'tcp')
            security = stream.get('security', 'reality')

            # РЎС‚СЂРѕРіРѕ РІ РїСЂР°РІРёР»СЊРЅРѕРј РїРѕСЂСЏРґРєРµ
            params = [
                ("type", network),
                ("security", security),
                ("flow", "xtls-rprx-vision"),
                ("pbk", pbk),
                ("fp", fingerprint),
                ("sni", sni),
                ("sid", sid),
                ("spx", quote(spx)),
            ]
            query = "&".join(f"{k}={v}" for k, v in params)
            tag = f"Daralla-{user_id}"

            return f"vless://{client['id']}@{host}:{port}?{query}#{tag}"

        return 'РљР»РёРµРЅС‚ РЅРµ РЅР°Р№РґРµРЅ.'

class MultiServerManager:
    def __init__(self, servers_by_location):
        self.servers_by_location = {}
        self.server_health = {}  # РЎР»РѕРІР°СЂСЊ РґР»СЏ РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ СЃРѕСЃС‚РѕСЏРЅРёСЏ СЃРµСЂРІРµСЂРѕРІ
        self.servers = []  # РџР»РѕСЃРєРёР№ СЃРїРёСЃРѕРє РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ
        
        # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј СЃРµСЂРІРµСЂС‹ РїРѕ Р»РѕРєР°С†РёСЏРј
        for location, servers_config in servers_by_location.items():
            self.servers_by_location[location] = []
            
            for server_config in servers_config:
                try:
                    x3_server = X3(
                        login=server_config["login"],
                        password=server_config["password"], 
                        host=server_config["host"]
                    )
                    server_info = {
                        "name": server_config["name"],
                        "x3": x3_server,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј СЃРѕСЃС‚РѕСЏРЅРёРµ СЃРµСЂРІРµСЂР°
                    self.server_health[server_config["name"]] = {
                        "status": "unknown",
                        "last_check": None,
                        "last_error": None,
                        "consecutive_failures": 0,
                        "uptime_percentage": 100.0
                    }
                    logger.info(f"РЎРµСЂРІРµСЂ {server_config['name']} ({location}) СѓСЃРїРµС€РЅРѕ РїРѕРґРєР»СЋС‡РµРЅ")
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЃРµСЂРІРµСЂСѓ {server_config['name']} ({location}): {e}")
                    # Р”Р°Р¶Рµ РµСЃР»Рё СЃРµСЂРІРµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ РїСЂРё РёРЅРёС†РёР°Р»РёР·Р°С†РёРё, РґРѕР±Р°РІР»СЏРµРј РµРіРѕ РІ СЃРїРёСЃРѕРє
                    server_info = {
                        "name": server_config["name"],
                        "x3": None,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    self.server_health[server_config["name"]] = {
                        "status": "offline",
                        "last_check": datetime.datetime.now(),
                        "last_error": str(e),
                        "consecutive_failures": 1,
                        "uptime_percentage": 0.0
                    }
    
    def get_server_by_name(self, server_name):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ РєРѕРЅРєСЂРµС‚РЅС‹Р№ СЃРµСЂРІРµСЂ РїРѕ РёРјРµРЅРё"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return server["x3"], server["name"]
        raise Exception(f"РЎРµСЂРІРµСЂ {server_name} РЅРµ РЅР°Р№РґРµРЅ РёР»Рё РЅРµРґРѕСЃС‚СѓРїРµРЅ")
    
    def get_server_with_least_clients_in_location(self, location):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРµСЂРІРµСЂ СЃ РЅР°РёРјРµРЅСЊС€РёРј РєРѕР»РёС‡РµСЃС‚РІРѕРј РєР»РёРµРЅС‚РѕРІ РІ РєРѕРЅРєСЂРµС‚РЅРѕР№ Р»РѕРєР°С†РёРё"""
        if location not in self.servers_by_location:
            raise Exception(f"Р›РѕРєР°С†РёСЏ {location} РЅРµ РЅР°Р№РґРµРЅР°")
        
        servers = self.servers_by_location[location]
        if not servers:
            raise Exception(f"РќРµС‚ РґРѕСЃС‚СѓРїРЅС‹С… СЃРµСЂРІРµСЂРѕРІ РІ Р»РѕРєР°С†РёРё {location}")
        
        min_clients = float('inf')
        selected_server = None
        
        for server in servers:
            try:
                client_count = server["x3"].get_client_count()
                logger.info(f"РЎРµСЂРІРµСЂ {server['name']} ({location}): {client_count} РєР»РёРµРЅС‚РѕРІ")
                
                if client_count < min_clients:
                    min_clients = client_count
                    selected_server = server
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё РєРѕР»РёС‡РµСЃС‚РІР° РєР»РёРµРЅС‚РѕРІ СЃ СЃРµСЂРІРµСЂР° {server['name']} ({location}): {e}")
                continue
        
        if selected_server is None:
            # Р•СЃР»Рё РІСЃРµ СЃРµСЂРІРµСЂС‹ РЅРµРґРѕСЃС‚СѓРїРЅС‹, РёСЃРїРѕР»СЊР·СѓРµРј РїРµСЂРІС‹Р№
            selected_server = servers[0]
            logger.warning(f"Р’СЃРµ СЃРµСЂРІРµСЂС‹ РІ Р»РѕРєР°С†РёРё {location} РЅРµРґРѕСЃС‚СѓРїРЅС‹, РёСЃРїРѕР»СЊР·СѓСЋ {selected_server['name']}")
        
        logger.info(f"Р’С‹Р±СЂР°РЅ СЃРµСЂРІРµСЂ {selected_server['name']} ({location}) СЃ {min_clients} РєР»РёРµРЅС‚Р°РјРё")
        logger.info(f"Reality РЅР°СЃС‚СЂРѕР№РєРё Р±СѓРґСѓС‚ РїСЂРѕРІРµСЂРµРЅС‹ РґР»СЏ СЃРµСЂРІРµСЂР°: {selected_server['name']}")
        return selected_server["x3"], selected_server["name"]
    
    def get_server_by_user_choice(self, location, user_choice):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРµСЂРІРµСЂ СЃРѕРіР»Р°СЃРЅРѕ РІС‹Р±РѕСЂСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ РєРѕРЅРєСЂРµС‚РЅРѕР№ Р»РѕРєР°С†РёРё"""
        if user_choice == "auto":
            return self.get_server_with_least_clients_in_location(location)
        else:
            return self.get_server_by_name(user_choice)
    
    def get_best_location_server(self):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРµСЂРІРµСЂ СЃ РЅР°РёРјРµРЅСЊС€РµР№ РЅР°РіСЂСѓР·РєРѕР№ РёР· РІСЃРµС… Р»РѕРєР°С†РёР№"""
        best_server = None
        min_clients = float('inf')
        best_location = None
        
        for location, servers in self.servers_by_location.items():
            try:
                server, server_name = self.get_server_with_least_clients_in_location(location)
                # РџРѕР»СѓС‡Р°РµРј РєРѕР»РёС‡РµСЃС‚РІРѕ РєР»РёРµРЅС‚РѕРІ РґР»СЏ СЃСЂР°РІРЅРµРЅРёСЏ
                client_count = server.get_client_count()
                if client_count < min_clients:
                    min_clients = client_count
                    best_server = server
                    best_location = location
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё СЃРµСЂРІРµСЂР° РёР· Р»РѕРєР°С†РёРё {location}: {e}")
                continue
        
        if best_server is None:
            raise Exception("РќРµС‚ РґРѕСЃС‚СѓРїРЅС‹С… СЃРµСЂРІРµСЂРѕРІ РІ Р»СЋР±РѕР№ Р»РѕРєР°С†РёРё")
        
        logger.info(f"Р’С‹Р±СЂР°РЅР° Р»СѓС‡С€Р°СЏ Р»РѕРєР°С†РёСЏ: {best_location} СЃ {min_clients} РєР»РёРµРЅС‚Р°РјРё")
        return best_server, best_location
    
    def find_client_on_any_server(self, user_email):
        """РС‰РµС‚ РєР»РёРµРЅС‚Р° РЅР° Р»СЋР±РѕРј РёР· СЃРµСЂРІРµСЂРѕРІ"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                try:
                    if server["x3"] and server["x3"].client_exists(user_email):
                        logger.info(f"РљР»РёРµРЅС‚ {user_email} РЅР°Р№РґРµРЅ РЅР° СЃРµСЂРІРµСЂРµ {server['name']} ({location})")
                        return server["x3"], server["name"]
                except Exception as e:
                    logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕРёСЃРєРµ РєР»РёРµРЅС‚Р° РЅР° СЃРµСЂРІРµСЂРµ {server['name']} ({location}): {e}")
                    continue
        return None, None
    
    
    def check_server_health(self, server_name):
        """РџСЂРѕРІРµСЂСЏРµС‚ Р·РґРѕСЂРѕРІСЊРµ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ СЃРµСЂРІРµСЂР°"""
        server_info = None
        for server in self.servers:
            if server["name"] == server_name:
                server_info = server
                break
        
        if not server_info:
            return False
        
        try:
            if server_info["x3"] is None:
                # РџС‹С‚Р°РµРјСЃСЏ РїРµСЂРµРїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ
                server_config = server_info["config"]
                server_info["x3"] = X3(
                    login=server_config["login"],
                    password=server_config["password"], 
                    host=server_config["host"]
                )
            
            # РџСЂРѕРІРµСЂСЏРµРј РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ API
            response = server_info["x3"].list(timeout=10)
            if response and 'obj' in response:
                # РЎРµСЂРІРµСЂ РґРѕСЃС‚СѓРїРµРЅ
                self.server_health[server_name]["status"] = "online"
                self.server_health[server_name]["last_check"] = datetime.datetime.now()
                self.server_health[server_name]["last_error"] = None
                self.server_health[server_name]["consecutive_failures"] = 0
                return True
            else:
                raise Exception("РќРµРІРµСЂРЅС‹Р№ РѕС‚РІРµС‚ РѕС‚ СЃРµСЂРІРµСЂР°")
                
        except Exception as e:
            # РЎРµСЂРІРµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ
            self.server_health[server_name]["status"] = "offline"
            self.server_health[server_name]["last_check"] = datetime.datetime.now()
            self.server_health[server_name]["last_error"] = str(e)
            self.server_health[server_name]["consecutive_failures"] += 1
            
            # Р•СЃР»Рё СЃРµСЂРІРµСЂ РґРѕР»РіРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ, РїРѕРјРµС‡Р°РµРј X3 РєР°Рє None
            if self.server_health[server_name]["consecutive_failures"] > 3:
                server_info["x3"] = None
            
            logger.warning(f"РЎРµСЂРІРµСЂ {server_name} РЅРµРґРѕСЃС‚СѓРїРµРЅ: {e}")
            return False
    
    def check_all_servers_health(self):
        """РџСЂРѕРІРµСЂСЏРµС‚ Р·РґРѕСЂРѕРІСЊРµ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ"""
        results = {}
        for server in self.servers:
            server_name = server["name"]
            results[server_name] = self.check_server_health(server_name)
        return results
    
    
    
    def get_server_health_status(self):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃС‚Р°С‚СѓСЃ Р·РґРѕСЂРѕРІСЊСЏ РІСЃРµС… СЃРµСЂРІРµСЂРѕРІ"""
        return self.server_health
    
    def get_healthy_servers(self):
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє РґРѕСЃС‚СѓРїРЅС‹С… СЃРµСЂРІРµСЂРѕРІ"""
        healthy_servers = []
        for server in self.servers:
            if self.server_health[server["name"]]["status"] == "online":
                healthy_servers.append(server)
        return healthy_servers

# РЎРѕР·РґР°РµРј РіР»РѕР±Р°Р»СЊРЅС‹Р№ СЌРєР·РµРјРїР»СЏСЂ РјРµРЅРµРґР¶РµСЂР° СЃРµСЂРІРµСЂРѕРІ
server_manager = MultiServerManager(SERVERS_BY_LOCATION)
# РњРµРЅРµРґР¶РµСЂ С‚РѕР»СЊРєРѕ РґР»СЏ РЅРѕРІС‹С… РєР»РёРµРЅС‚РѕРІ
new_client_manager = MultiServerManager(SERVERS_BY_LOCATION)

def calculate_time_remaining(expiry_timestamp, show_expired_as_negative=False):
    """
    Р’С‹С‡РёСЃР»СЏРµС‚ РѕСЃС‚Р°РІС€РµРµСЃСЏ РІСЂРµРјСЏ РґРѕ РґРµР°РєС‚РёРІР°С†РёРё РєР»СЋС‡Р°
    """
    if not expiry_timestamp or expiry_timestamp == 0:
        return "вЂ”"
    
    try:
        # РљРѕРЅРІРµСЂС‚РёСЂСѓРµРј timestamp РІ datetime
        expiry_dt = datetime.datetime.fromtimestamp(expiry_timestamp)
        now = datetime.datetime.now()
        
        # Р’С‹С‡РёСЃР»СЏРµРј СЂР°Р·РЅРѕСЃС‚СЊ
        time_diff = expiry_dt - now
        
        if time_diff.total_seconds() <= 0:
            if show_expired_as_negative:
                # РџРѕРєР°Р·С‹РІР°РµРј, СЃРєРѕР»СЊРєРѕ РІСЂРµРјРµРЅРё РїСЂРѕС€Р»Рѕ СЃ РјРѕРјРµРЅС‚Р° РёСЃС‚РµС‡РµРЅРёСЏ
                expired_diff = now - expiry_dt
                days = expired_diff.days
                hours, remainder = divmod(expired_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                time_parts = []
                if days > 0:
                    time_parts.append(f"{days} РґРЅ.")
                if hours > 0:
                    time_parts.append(f"{hours} С‡.")
                if minutes > 0:
                    time_parts.append(f"{minutes} РјРёРЅ.")
                
                if not time_parts:
                    return "РўРѕР»СЊРєРѕ С‡С‚Рѕ РёСЃС‚РµРє"
                
                return f"РСЃС‚РµРє {time_parts[0]}" if len(time_parts) == 1 else f"РСЃС‚РµРє {' '.join(time_parts)}"
            else:
                return "РСЃС‚РµРє"
        
        # РР·РІР»РµРєР°РµРј РґРЅРё, С‡Р°СЃС‹ Рё РјРёРЅСѓС‚С‹
        days = time_diff.days
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        # Р¤РѕСЂРјРёСЂСѓРµРј СЃС‚СЂРѕРєСѓ
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} РґРЅ.")
        if hours > 0:
            time_parts.append(f"{hours} С‡.")
        if minutes > 0:
            time_parts.append(f"{minutes} РјРёРЅ.")
        
        if not time_parts:
            return "РњРµРЅРµРµ РјРёРЅСѓС‚С‹"
        
        return " ".join(time_parts)
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РІС‹С‡РёСЃР»РµРЅРёСЏ РѕСЃС‚Р°РІС€РµРіРѕСЃСЏ РІСЂРµРјРµРЅРё: {e}")
        return "вЂ”"

def format_vpn_key_message(email, status, server, expiry, key, expiry_timestamp=None):
    """
    Р¤РѕСЂРјР°С‚РёСЂСѓРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ VPN РєР»СЋС‡Рµ
    """
    status_icon = UIEmojis.SUCCESS if status == "РђРєС‚РёРІРµРЅ" else UIEmojis.ERROR
    
    # Р’С‹С‡РёСЃР»СЏРµРј РѕСЃС‚Р°РІС€РµРµСЃСЏ РІСЂРµРјСЏ
    time_remaining = calculate_time_remaining(expiry_timestamp) if expiry_timestamp else "вЂ”"
    
    message = (
        f"{UIStyles.header('Р’Р°С€ VPN РєР»СЋС‡')}\n\n"
        f"<b>Email:</b> <code>{email}</code>\n"
        f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status_icon} {UIStyles.highlight(status)}\n"
        f"<b>РЎРµСЂРІРµСЂ:</b> {server}\n"
        f"<b>РћСЃС‚Р°Р»РѕСЃСЊ:</b> {time_remaining}\n\n"
        f"<code>{key}</code>\n"
        f"{UIStyles.description('РќР°Р¶РјРёС‚Рµ РЅР° РєР»СЋС‡ РІС‹С€Рµ, С‡С‚РѕР±С‹ СЃРєРѕРїРёСЂРѕРІР°С‚СЊ')}"
    )
    
    return message


async def check_user_has_existing_keys(user_id: str, server_manager) -> bool:
    """
    РџСЂРѕРІРµСЂСЏРµС‚, РµСЃС‚СЊ Р»Рё Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ РєР»СЋС‡Рё РЅР° СЃРµСЂРІРµСЂР°С…
    :param user_id: ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    :param server_manager: РњРµРЅРµРґР¶РµСЂ СЃРµСЂРІРµСЂРѕРІ
    :return: True РµСЃР»Рё РµСЃС‚СЊ РєР»СЋС‡Рё, False РµСЃР»Рё РЅРµС‚
    """
    try:
        logger.info(f"РџСЂРѕРІРµСЂРєР° СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… РєР»СЋС‡РµР№ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}")
        
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                server_name = server['name']
                inbounds = xui.list()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    
                    for client in clients:
                        email = client.get('email', '')
                        # РџСЂРѕРІРµСЂСЏРµРј, РїСЂРёРЅР°РґР»РµР¶РёС‚ Р»Рё РєР»СЋС‡ СЌС‚РѕРјСѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
                        if email.startswith(f"{user_id}_") or email.startswith(f"trial_{user_id}_"):
                            logger.info(f"РќР°Р№РґРµРЅ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ РєР»СЋС‡ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}: {email} РЅР° СЃРµСЂРІРµСЂРµ {server_name}")
                            return True
                            
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё РєР»СЋС‡РµР№ РЅР° СЃРµСЂРІРµСЂРµ {server['name']}: {e}")
                continue
        
        logger.info(f"РЈ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id} РЅРµС‚ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… РєР»СЋС‡РµР№")
        return False
        
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… РєР»СЋС‡РµР№ РґР»СЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ {user_id}: {e}")
        return False


# РљРѕРјР°РЅРґР° /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    user_id = str(update.effective_user.id)
    has_existing_keys = False  # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј РїРµСЂРµРјРµРЅРЅСѓСЋ
    
    # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРµ Р»РѕРіРёСЂРѕРІР°РЅРёРµ РґР»СЏ РѕС‚Р»Р°РґРєРё
    logger.info(f"START_DEBUG: user_id={user_id}, context.args={context.args}")
    
    # Р РµРіРёСЃС‚СЂР°С†РёСЋ РїРµСЂРµРЅРµСЃР»Рё РІ РєРѕРЅРµС† start РїРѕСЃР»Рµ РѕР±СЂР°Р±РѕС‚РєРё СЂРµС„РµСЂР°Р»Р° Рё РІС‹РґР°С‡Рё РєР»СЋС‡Р°
    
    # РџСЂРѕРІРµСЂСЏРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃСЃС‹Р»РєСѓ
    # Telegram РїРµСЂРµРґР°РµС‚ Р°СЂРіСѓРјРµРЅС‚С‹ РєРѕРјР°РЅРґС‹ /start РІ context.args
    referral_code = None
    
    # РЎРЅР°С‡Р°Р»Р° РїСЂРѕРІРµСЂСЏРµРј context.args (РѕСЃРЅРѕРІРЅРѕР№ СЃРїРѕСЃРѕР±)
    if context.args and len(context.args) > 0:
        logger.info(f"START_REFERRAL: context.args={context.args}")
        # РџСЂРѕРІРµСЂСЏРµРј, СЏРІР»СЏРµС‚СЃСЏ Р»Рё Р°СЂРіСѓРјРµРЅС‚ С‡РёСЃР»РѕРј (user_id)
        if context.args[0].isdigit():
            referral_code = context.args[0]
            logger.info(f"START_REFERRAL: Found referral code in context.args: {referral_code}")
        else:
            logger.info(f"START_REFERRAL: context.args[0] is not a digit: {context.args[0]}")
    else:
        logger.info(f"START_REFERRAL: context.args is empty or None: {context.args}")
    
    # Р•СЃР»Рё РЅРµ РЅР°С€Р»Рё РІ context.args, РїСЂРѕРІРµСЂСЏРµРј update.message.text (СЂРµР·РµСЂРІРЅС‹Р№ СЃРїРѕСЃРѕР±)
    if not referral_code and update.message and update.message.text:
        logger.info(f"START_REFERRAL: Checking message text: {update.message.text}")
        import re
        # РС‰РµРј С‡РёСЃР»РѕРІС‹Рµ ID РІ С‚РµРєСЃС‚Рµ СЃРѕРѕР±С‰РµРЅРёСЏ
        match = re.search(r'(\d+)', update.message.text)
        if match:
            referral_code = match.group(1)
            logger.info(f"START_REFERRAL: Found referral code in message text: {referral_code}")
        else:
            logger.info(f"START_REFERRAL: No numeric ID found in message text")
    
    if referral_code:
        referrer_id = decode_referral_code(referral_code)
        
        if referrer_id and referrer_id != user_id:
            # Р›РѕРіРёСЂСѓРµРј РїРѕРїС‹С‚РєСѓ СЃРѕР·РґР°РЅРёСЏ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃРІСЏР·Рё
            logger.info(f"START_REFERRAL: referrer_id={referrer_id}, referred_id={user_id}")
            
            # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїР»Р°С‚РЅС‹Рµ РїРѕРєСѓРїРєРё
            has_paid_purchases = await is_known_user(user_id)
            
            # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ РєР»СЋС‡Рё РЅР° СЃРµСЂРІРµСЂР°С…
            has_existing_keys = await check_user_has_existing_keys(user_id, new_client_manager)
            
            if has_paid_purchases or has_existing_keys:
                # РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓР¶Рµ РёРјРµРµС‚ РїР»Р°С‚РЅС‹Рµ РїРѕРєСѓРїРєРё РёР»Рё РєР»СЋС‡Рё - СЂРµС„РµСЂР°Р»СЊРЅР°СЏ РЅР°РіСЂР°РґР° РЅРµ Р±СѓРґРµС‚ РІС‹РґР°РЅР°
                if has_paid_purchases:
                    logger.info(f"START_REFERRAL: User {user_id} has paid purchases, no referral reward")
                if has_existing_keys:
                    logger.info(f"START_REFERRAL: User {user_id} has existing keys on servers, no referral reward")
                welcome_text = UIMessages.welcome_referral_existing_user_message()
            else:
                # РџС‹С‚Р°РµРјСЃСЏ СЃРѕС…СЂР°РЅРёС‚СЊ СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃРІСЏР·СЊ
                connection_saved = await save_referral_connection(referrer_id, user_id, server_manager)
                
                # Р›РѕРіРёСЂСѓРµРј СЂРµР·СѓР»СЊС‚Р°С‚
                logger.info(f"START_REFERRAL: connection_saved={connection_saved}")
                
                if connection_saved:
                    days = await get_config('points_days_per_point', '14')
                    logger.info(f"START_REFERRAL: РџРѕР»СѓС‡РµРЅРѕ Р·РЅР°С‡РµРЅРёРµ days РёР· РєРѕРЅС„РёРіСѓСЂР°С†РёРё = {days}")
                    welcome_text = UIMessages.welcome_referral_new_user_message(days)
                else:
                    # РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ СѓР¶Рµ СѓС‡Р°СЃС‚РІРѕРІР°Р» РІ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃРёСЃС‚РµРјРµ вЂ” РїРѕРєР°Р·С‹РІР°РµРј РѕР±С‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ РєР°Рє РґР»СЏ РЅРµ РЅРѕРІРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
                    welcome_text = UIMessages.welcome_referral_existing_user_message()
        else:
            logger.info(f"START_DEBUG: Invalid referral - referrer_id={referrer_id}, user_id={user_id}")
            welcome_text = UIMessages.welcome_message()
    else:
        logger.info(f"START_DEBUG: No referral code found - context.args={context.args}, message_text={update.message.text if update.message else 'None'}")
        # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ РїСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ (С‚РѕР»СЊРєРѕ РµСЃР»Рё РЅРµ Р±С‹Р»Рѕ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃСЃС‹Р»РєРё)
        welcome_text = UIMessages.welcome_message()
    
    # РћС‡РёС‰Р°РµРј РЅР°РІРёРіР°С†РёРѕРЅРЅС‹Р№ СЃС‚РµРє Рё РґРѕР±Р°РІР»СЏРµРј РіР»Р°РІРЅРѕРµ РјРµРЅСЋ
    context.user_data['nav_stack'] = ['main_menu']
    logger.info(f"START: Initialized stack: {context.user_data['nav_stack']}")
    
    # РЎРѕР·РґР°РµРј РєРЅРѕРїРєРё РіР»Р°РІРЅРѕРіРѕ РјРµРЅСЋ РёСЃРїРѕР»СЊР·СѓСЏ РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return
    
    # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРµ Р»РѕРіРёСЂРѕРІР°РЅРёРµ РґР»СЏ РѕС‚Р»Р°РґРєРё
    logger.info(f"START_MESSAGE: message={message}, welcome_text_length={len(welcome_text) if welcome_text else 0}")
    
    # РђРІС‚РѕРІС‹РґР°С‡Р° РѕР±С‹С‡РЅРѕРіРѕ РєР»СЋС‡Р° РЅР° 14 РґРЅРµР№ РЅРѕРІРѕРјСѓ РєР»РёРµРЅС‚Сѓ (РїРѕ Р‘Р” СЂРµС„. СЃРёСЃС‚РµРјС‹)
    try:
        user_id_str = str(update.effective_user.id)
        is_new = not await is_known_user(user_id_str)
        
        # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё Сѓ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ РєР»СЋС‡Рё РЅР° СЃРµСЂРІРµСЂР°С… (РµСЃР»Рё РµС‰Рµ РЅРµ РїСЂРѕРІРµСЂСЏР»Рё)
        if not referral_code:
            has_existing_keys = await check_user_has_existing_keys(user_id_str, new_client_manager)
        # Р•СЃР»Рё Р±С‹Р»Р° СЂРµС„РµСЂР°Р»СЊРЅР°СЏ СЃСЃС‹Р»РєР°, has_existing_keys СѓР¶Рµ РїСЂРѕРІРµСЂРµРЅ РІС‹С€Рµ
        
        if is_new and not has_existing_keys:
            xui, server_name = new_client_manager.get_best_location_server()
            unique_email = f"{user_id_str}_{uuid.uuid4()}"
            response = xui.addClient(day=14, tg_id=user_id_str, user_email=unique_email, timeout=15)
            if response and getattr(response, 'status_code', None) == 200:
                link = xui.link(unique_email)
                expiry_time = datetime.datetime.now() + datetime.timedelta(days=14)
                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                expiry_ts = int(expiry_time.timestamp())
                welcome_text += "\n\n" + UIStyles.info_message("Р’Р°Рј РІС‹РґР°РЅ Р±РµСЃРїР»Р°С‚РЅС‹Р№ РєР»СЋС‡ РЅР° 14 РґРЅРµР№") + "\n\n"
                welcome_text += format_vpn_key_message(
                    email=unique_email,
                    status='РђРєС‚РёРІРµРЅ',
                    server=server_name,
                    expiry=expiry_str,
                    key=link,
                    expiry_timestamp=expiry_ts
                )
        elif is_new and has_existing_keys:
            logger.info(f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {user_id_str} РЅРѕРІС‹Р№ РІ Р‘Р”, РЅРѕ СѓР¶Рµ РёРјРµРµС‚ РєР»СЋС‡Рё РЅР° СЃРµСЂРІРµСЂР°С… - РїСЂРѕРїСѓСЃРєР°РµРј РІС‹РґР°С‡Сѓ")
        elif not is_new:
            logger.info(f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {user_id_str} СѓР¶Рµ РёР·РІРµСЃС‚РµРЅ РІ Р‘Р” - РїСЂРѕРїСѓСЃРєР°РµРј РІС‹РґР°С‡Сѓ")
    except Exception as e:
        logger.error(f"START free key issue error: {e}")

    # РўРµРїРµСЂСЊ, РєРѕРіРґР° РІСЃРµ РїСЂРѕРІРµСЂРєРё РІС‹РїРѕР»РЅРµРЅС‹, СЂРµРіРёСЃС‚СЂРёСЂСѓРµРј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    try:
        await register_simple_user(user_id)
    except Exception as e:
        logger.error(f"Register user failed: {e}")
    # РћС‚РїСЂР°РІР»СЏРµРј РјРµРЅСЋ СЃ С„РѕС‚Рѕ
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')

async def edit_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Р РµРґР°РєС‚РёСЂСѓРµС‚ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ РЅР° РіР»Р°РІРЅРѕРµ РјРµРЅСЋ"""
    # РЎРѕР·РґР°РµРј РєРЅРѕРїРєРё РіР»Р°РІРЅРѕРіРѕ РјРµРЅСЋ РёСЃРїРѕР»СЊР·СѓСЏ РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ РїСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
    welcome_text = UIMessages.welcome_message()
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("edit_main_menu: message is None")
        return
    
    logger.info(f"EDIT_MAIN_MENU: Р РµРґР°РєС‚РёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ {message.message_id}")
    try:
        # РћС‚РїСЂР°РІР»СЏРµРј РјРµРЅСЋ СЃ С„РѕС‚Рѕ
        await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')
        logger.info("EDIT_MAIN_MENU: РЎРѕРѕР±С‰РµРЅРёРµ СѓСЃРїРµС€РЅРѕ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРѕ")
    except Exception as e:
        logger.error(f"EDIT_MAIN_MENU: РћС€РёР±РєР° СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
        # Р•СЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ, РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ
        logger.info("EDIT_MAIN_MENU: Р’С‹Р·С‹РІР°РµРј start() РєР°Рє fallback")
        await start(update, context)

# РќРѕРІР°СЏ РєРѕРјР°РЅРґР° /instruction вЂ” СЃ РєРЅРѕРїРєР°РјРё РІС‹Р±РѕСЂР° РїР»Р°С‚С„РѕСЂРјС‹
async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    # Р”РѕР±Р°РІР»СЏРµРј С‚РµРєСѓС‰РµРµ СЃРѕСЃС‚РѕСЏРЅРёРµ РІ РЅР°РІРёРіР°С†РёРѕРЅРЅС‹Р№ СЃС‚РµРє
    if not context.user_data.get('nav_stack'):
        context.user_data['nav_stack'] = ['main_menu']
    stack = context.user_data['nav_stack']
    if not stack or stack[-1] != 'instruction_menu':
        push_nav(context, 'instruction_menu')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Android", callback_data="instr_android"), InlineKeyboardButton("iOS", callback_data="instr_ios")],
        [InlineKeyboardButton("Windows", callback_data="instr_windows"), InlineKeyboardButton("macOS", callback_data="instr_macos")],
        [InlineKeyboardButton("Linux", callback_data="instr_linux"), InlineKeyboardButton("Android TV", callback_data="instr_tv")],
        [InlineKeyboardButton("FAQ", callback_data="instr_faq")],
        [UIButtons.back_button()],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("instruction_menu: message is None")
        return
    
    # РСЃРїРѕР»СЊР·СѓРµРј РµРґРёРЅС‹Р№ СЃС‚РёР»СЊ РґР»СЏ СЃРѕРѕР±С‰РµРЅРёСЏ
    instruction_text = UIMessages.instruction_menu_message()
    await safe_edit_or_reply_universal(message, instruction_text, reply_markup=keyboard, parse_mode="HTML", menu_type='instruction_menu')

# РћР±СЂР°Р±РѕС‚РєР° РєРЅРѕРїРѕРє РёРЅСЃС‚СЂСѓРєС†РёРё
async def instruction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    texts = {
        "instr_android": (
            "<b>Android (v2RayTun, Hiddify)</b>\n"
            "1. Р’С‹Р±РµСЂРёС‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ:\n"
            "   вЂў <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">v2RayTun РёР· Google Play</a>\n"
            "   вЂў <a href=\"https://play.google.com/store/apps/details?id=app.hiddify.com\">Hiddify РёР· Google Play</a>\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. Р’ РїСЂРёР»РѕР¶РµРЅРёРё РЅР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "4. РџРѕРґРєР»СЋС‡РёС‚РµСЃСЊ Рє VPN.\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё С‚РµР»РµС„РѕРЅ.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),
        "instr_ios": (
            "<b>iPhone (v2RayTun, Hiddify)</b>\n"
            "1. Р’С‹Р±РµСЂРёС‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ:\n"
            "   вЂў <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=iphone\">v2RayTun РёР· App Store</a>\n"
            "   вЂў <a href=\"https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532?platform=iphone\">Hiddify РёР· App Store</a>\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. РћС‚РєСЂРѕР№С‚Рµ РІС‹Р±СЂР°РЅРЅРѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ.\n"
            "4. РќР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "5. Р’С‹Р±РµСЂРёС‚Рµ РґРѕР±Р°РІР»РµРЅРЅС‹Р№ РїСЂРѕС„РёР»СЊ Рё РїРѕРґРєР»СЋС‡РёС‚РµСЃСЊ.\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё С‚РµР»РµС„РѕРЅ.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),
        "instr_windows": (
            "<b>Windows (v2RayTun, Hiddify)</b>\n"
            "1. Р’С‹Р±РµСЂРёС‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ:\n"
            "   вЂў <a href=\"https://storage.v2raytun.com/v2RayTun_Setup.exe\">v2RayTun РґР»СЏ Windows</a>\n"
            "   вЂў <a href=\"https://app.hiddify.com/windows\">Hiddify РґР»СЏ Windows</a>\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. Р’ РІС‹Р±СЂР°РЅРЅРѕРј РїСЂРёР»РѕР¶РµРЅРёРё РЅР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "4. Р’РєР»СЋС‡РёС‚Рµ РїСЂРѕС„РёР»СЊ (РЅР°Р¶РјРёС‚Рµ РЅР° РїРµСЂРµРєР»СЋС‡Р°С‚РµР»СЊ РёР»Рё РєРЅРѕРїРєСѓ 'Р’РєР»СЋС‡РёС‚СЊ').\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё РєРѕРјРїСЊСЋС‚РµСЂ.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),
        "instr_macos": (
            "<b>Mac (v2RayTun, Hiddify)</b>\n"
            "1. Р’С‹Р±РµСЂРёС‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ:\n"
            "   вЂў <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=mac\">v2RayTun РґР»СЏ Mac</a>\n"
            "   вЂў <a href=\"https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532?platform=iphone\">Hiddify РґР»СЏ Mac</a>\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. Р’ РІС‹Р±СЂР°РЅРЅРѕРј РїСЂРёР»РѕР¶РµРЅРёРё РЅР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "4. Р’РєР»СЋС‡РёС‚Рµ РїСЂРѕС„РёР»СЊ (РЅР°Р¶РјРёС‚Рµ РЅР° РїРµСЂРµРєР»СЋС‡Р°С‚РµР»СЊ РёР»Рё РєРЅРѕРїРєСѓ 'Р’РєР»СЋС‡РёС‚СЊ').\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё Mac.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),
        "instr_tv": (
            "<b>Android TV (v2RayTun)</b>\n"
            "1. <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">РЎРєР°С‡Р°Р№С‚Рµ v2RayTun РґР»СЏ Android TV</a>.\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. Р’ v2RayTun РЅР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "4. Р’РєР»СЋС‡РёС‚Рµ РїСЂРѕС„РёР»СЊ (РЅР°Р¶РјРёС‚Рµ РЅР° РїРµСЂРµРєР»СЋС‡Р°С‚РµР»СЊ РёР»Рё РєРЅРѕРїРєСѓ 'Р’РєР»СЋС‡РёС‚СЊ').\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё Android TV.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),
        "instr_linux": (
            "<b>Linux (Hiddify)</b>\n"
            "1. <a href=\"https://app.hiddify.com/linux\">РЎРєР°С‡Р°Р№С‚Рµ Hiddify РґР»СЏ Linux</a>.\n"
            "2. Р’ Р±РѕС‚Рµ РЅР°Р¶РјРёС‚Рµ 'РњРѕРё РєР»СЋС‡Рё' Рё СЃРєРѕРїРёСЂСѓР№С‚Рµ VLESS-СЃСЃС‹Р»РєСѓ.\n"
            "3. Р’ Hiddify РЅР°Р¶РјРёС‚Рµ + в†’ Р”РѕР±Р°РІРёС‚СЊ РёР· Р±СѓС„РµСЂР° РѕР±РјРµРЅР°.\n"
            "4. Р’РєР»СЋС‡РёС‚Рµ РїСЂРѕС„РёР»СЊ (РЅР°Р¶РјРёС‚Рµ РЅР° РїРµСЂРµРєР»СЋС‡Р°С‚РµР»СЊ РёР»Рё РєРЅРѕРїРєСѓ 'Р’РєР»СЋС‡РёС‚СЊ').\n"
            "\n<b>РЎРѕРІРµС‚С‹:</b>\n- Р•СЃР»Рё РЅРµ СѓРґР°С‘С‚СЃСЏ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ, РїРѕРїСЂРѕР±СѓР№С‚Рµ РїРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ РїСЂРёР»РѕР¶РµРЅРёРµ РёР»Рё РєРѕРјРїСЊСЋС‚РµСЂ.\n- РСЃРїРѕР»СЊР·СѓР№С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅСѓ VPN-РїСЂРѕРіСЂР°РјРјСѓ РѕРґРЅРѕРІСЂРµРјРµРЅРЅРѕ.\n\n<b>Р‘РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ:</b> РќРµ РґРµР»РёС‚РµСЃСЊ СЃРІРѕРёРј VPN-РєР»СЋС‡РѕРј СЃ РґСЂСѓРіРёРјРё!"
        ),

        "instr_faq": (
            "<b>FAQ - Р§Р°СЃС‚С‹Рµ РІРѕРїСЂРѕСЃС‹</b>\n\n"
            "<b>VPN РЅРµ РїРѕРґРєР»СЋС‡Р°РµС‚СЃСЏ:</b>\n"
            "вЂў РџСЂРѕРІРµСЂСЊС‚Рµ РёРЅС‚РµСЂРЅРµС‚\n"
            "вЂў РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚Рµ v2RayTun\n"
            "вЂў РЎРєРѕРїРёСЂСѓР№С‚Рµ СЃСЃС‹Р»РєСѓ РїРѕР»РЅРѕСЃС‚СЊСЋ\n"
            "вЂў РћС‚РєР»СЋС‡РёС‚Рµ РґСЂСѓРіРёРµ VPN\n\n"
            "<b>РќРµ РёРјРїРѕСЂС‚РёСЂСѓРµС‚СЃСЏ РєР»СЋС‡:</b>\n"
            "вЂў РЎРєРѕРїРёСЂСѓР№С‚Рµ СЃСЃС‹Р»РєСѓ Р·Р°РЅРѕРІРѕ\n"
            "вЂў РџСЂРѕРІРµСЂСЊС‚Рµ 'vless://' РІ РЅР°С‡Р°Р»Рµ\n"
            "вЂў РћР±РЅРѕРІРёС‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ\n\n"
            "<b>РћРґРёРЅ РєР»СЋС‡ = РѕРґРЅРѕ СѓСЃС‚СЂРѕР№СЃС‚РІРѕ</b>\n"
            "<b>РџСЂРѕРґР»РµРЅРёРµ:</b> РљСѓРїРёС‚Рµ РЅРѕРІС‹Р№ РєР»СЋС‡ РёР»Рё РїСЂРѕРґР»РёС‚Рµ\n\n"
            "<b>РќСѓР¶РЅР° РїРѕРјРѕС‰СЊ?</b> РћР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ"
        )
    }
    if data == "back":
        await universal_back_callback(update, context)
        return
    elif data in ["instr_android", "instr_ios", "instr_windows", "instr_macos", "instr_linux", "instr_tv", "instr_faq"]:
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'instruction_platform':
            push_nav(context, 'instruction_platform')
        
        # РћРїСЂРµРґРµР»СЏРµРј menu_type РґР»СЏ РєР°Р¶РґРѕР№ РїР»Р°С‚С„РѕСЂРјС‹
        menu_type_map = {
            "instr_android": "instruction_android",
            "instr_ios": "instruction_ios", 
            "instr_windows": "instruction_windows",
            "instr_macos": "instruction_macos",
            "instr_linux": "instruction_linux",
            "instr_tv": "instruction_tv",
            "instr_faq": "instruction_faq"
        }
        
        menu_type = menu_type_map.get(data, 'instruction_platform')
        
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
    ])
    await safe_edit_or_reply_universal(query.message, texts.get(data, "РРЅСЃС‚СЂСѓРєС†РёСЏ РЅРµ РЅР°Р№РґРµРЅР°."), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type=menu_type)

async def update_payment_activation(payment_id: str, activated: int):
    import aiosqlite
    from .keys_db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET activated = ? WHERE payment_id = ?', (activated, payment_id))
        await db.commit()
    logger.info(f"РћР±РЅРѕРІР»РµРЅ СЃС‚Р°С‚СѓСЃ Р°РєС‚РёРІР°С†РёРё: payment_id={payment_id}, activated={activated}")


# === РћР±СЂР°Р±РѕС‚РєР° РїР»Р°С‚РµР¶РµР№ ===

async def handle_payment(update, context, price, period):
    logger.info(f"handle_payment РІС‹Р·РІР°РЅР°: price={price}, period={period}")
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'payment':
        push_nav(context, 'payment')
    user = update.effective_user if hasattr(update, 'effective_user') else update.from_user
    user_id = str(user.id)
    logger.info(f"handle_payment: user_id={user_id}")
    
    # РџРѕР»СѓС‡Р°РµРј РїСЂР°РІРёР»СЊРЅС‹Р№ РѕР±СЉРµРєС‚ СЃРѕРѕР±С‰РµРЅРёСЏ
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    logger.info(f"handle_payment: message={message}, message_id={getattr(message, 'message_id', 'None')}")
    try:
        # РџСЂРѕРІРµСЂРєР° РЅР° СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№ pending-РїР»Р°С‚С‘Р¶ РїРѕ user_id Рё period
        payment_info = await get_pending_payment(user_id, period)
        logger.info(f"РџСЂРѕРІРµСЂРєР° СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС… РїР»Р°С‚РµР¶РµР№: user_id={user_id}, period={period}, found={payment_info is not None}")
        
        # РџСЂРѕРІРµСЂСЏРµРј pending РїР»Р°С‚РµР¶Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Рё РѕС‚РјРµРЅСЏРµРј С‚РѕР»СЊРєРѕ РЅРµРѕРїР»Р°С‡РµРЅРЅС‹Рµ
        import aiosqlite
        from .keys_db import DB_PATH
        logger.info(f"HANDLE_PAYMENT: РџРѕРґРєР»СЋС‡Р°РµРјСЃСЏ Рє Р±Р°Р·Рµ РґР°РЅРЅС‹С… РїРѕ РїСѓС‚Рё: {DB_PATH}")
        async with aiosqlite.connect(DB_PATH) as db:
            # РџСЂРѕРІРµСЂСЏРµРј СЃСѓС‰РµСЃС‚РІРѕРІР°РЅРёРµ С‚Р°Р±Р»РёС†С‹ payments
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'") as cursor:
                table_exists = await cursor.fetchone()
                logger.info(f"HANDLE_PAYMENT: РўР°Р±Р»РёС†Р° payments СЃСѓС‰РµСЃС‚РІСѓРµС‚: {table_exists is not None}")
                if not table_exists:
                    logger.error("HANDLE_PAYMENT: РўР°Р±Р»РёС†Р° payments РЅРµ РЅР°Р№РґРµРЅР°! РЎРѕР·РґР°РµРј РµС‘...")
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
                    logger.info("HANDLE_PAYMENT: РўР°Р±Р»РёС†Р° payments СЃРѕР·РґР°РЅР°")
            
            # РџРѕР»СѓС‡Р°РµРј РІСЃРµ pending РїР»Р°С‚РµР¶Рё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
            async with db.execute('''
                SELECT payment_id, status FROM payments WHERE user_id = ? AND status = ?
            ''', (user_id, 'pending')) as cursor:
                pending_payments = await cursor.fetchall()
                logger.info(f"РќР°Р№РґРµРЅРѕ {len(pending_payments)} pending РїР»Р°С‚РµР¶РµР№ РґР»СЏ user_id={user_id}")
            
            # РџСЂРѕСЃС‚Рѕ РїРѕРјРµС‡Р°РµРј РІСЃРµ pending РїР»Р°С‚РµР¶Рё РєР°Рє РѕС‚РјРµРЅРµРЅРЅС‹Рµ РІ Р‘Р”
            # YooKassa Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РѕС‚РјРµРЅРёС‚ РёС… С‡РµСЂРµР· 15 РјРёРЅСѓС‚
            canceled_count = len(pending_payments)
            if canceled_count > 0:
                logger.info(f"РџРѕРјРµС‡Р°РµРј {canceled_count} pending РїР»Р°С‚РµР¶РµР№ РєР°Рє РѕС‚РјРµРЅРµРЅРЅС‹Рµ (YooKassa РѕС‚РјРµРЅРёС‚ РёС… Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё С‡РµСЂРµР· 15 РјРёРЅСѓС‚)")
            
            # РћР±РЅРѕРІР»СЏРµРј СЃС‚Р°С‚СѓСЃ РІ Р‘Р” РґР»СЏ РѕС‚РјРµРЅРµРЅРЅС‹С… РїР»Р°С‚РµР¶РµР№
            if canceled_count > 0:
                await db.execute('UPDATE payments SET status = ? WHERE user_id = ? AND status = ?', ('canceled', user_id, 'pending'))
                await db.commit()
                logger.info(f"РћС‚РјРµРЅРµРЅРѕ {canceled_count} pending РїР»Р°С‚РµР¶РµР№ РґР»СЏ user_id={user_id}")
        
        # 2. РЎРѕР·РґР°С‘Рј РЅРѕРІС‹Р№ РїР»Р°С‚С‘Р¶ РёР»Рё РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РїРѕРєСѓРїРєСѓ Р·Р° Р±Р°Р»Р»С‹
        now = int(datetime.datetime.now().timestamp())
        key_id = str(uuid.uuid4())
        unique_email = f'{user_id}_{key_id}'
        
        # РџСЂРѕРІРµСЂСЏРµРј, СЌС‚Рѕ РїРѕРєСѓРїРєР° Р·Р° Р±Р°Р»Р»С‹
        if period == "points_month":
            # РџРѕРєСѓРїРєР° Р·Р° Р±Р°Р»Р»С‹ - СЃРЅР°С‡Р°Р»Р° СЃРѕР·РґР°РµРј РєР»СЋС‡, РїРѕС‚РѕРј СЃРїРёСЃС‹РІР°РµРј Р±Р°Р»Р»С‹
            try:
                # РџСЂРѕРІРµСЂСЏРµРј Р±Р°Р»Р»С‹
                points_info = await get_user_points(user_id)
                if points_info['points'] < 1:
                    await safe_edit_or_reply(message, f"{UIEmojis.ERROR} РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ!")
                    return
                
                # РЎРѕР·РґР°РµРј VPN РєР»СЋС‡ РЎРќРђР§РђР›Рђ
                selected_location = context.user_data.get("selected_location", "auto")
                if selected_location == "auto":
                    # Р”Р»СЏ Р°РІС‚РѕРІС‹Р±РѕСЂР° РІС‹Р±РёСЂР°РµРј Р»СѓС‡С€СѓСЋ Р»РѕРєР°С†РёСЋ
                    xui, server_name = new_client_manager.get_best_location_server()
                else:
                    xui, server_name = new_client_manager.get_server_by_user_choice(selected_location, "auto")
                points_days = int(await get_config('points_days_per_point', '14'))
                response = xui.addClient(day=points_days, tg_id=user.id, user_email=unique_email, timeout=15)
                
                if response and getattr(response, 'status_code', None) == 200:
                    # РљР»СЋС‡ СЃРѕР·РґР°РЅ СѓСЃРїРµС€РЅРѕ - РўР•РџР•Р Р¬ СЃРїРёСЃС‹РІР°РµРј Р±Р°Р»Р»С‹
                    success = await spend_points(user_id, 1, "РџРѕРєСѓРїРєР° VPN Р·Р° Р±Р°Р»Р»С‹", bot=context.bot)
                    if not success:
                        # Р•СЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ СЃРїРёСЃР°С‚СЊ Р±Р°Р»Р»С‹, СѓРґР°Р»СЏРµРј СЃРѕР·РґР°РЅРЅС‹Р№ РєР»СЋС‡
                        try:
                            xui.removeClient(unique_email)
                            logger.warning(f"Removed key {unique_email} due to points spending failure")
                        except Exception as e:
                            logger.error(f"Failed to remove key {unique_email} after points failure: {e}")
                            # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ
                            await notify_admin(context.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РќРµ СѓРґР°Р»РѕСЃСЊ СѓРґР°Р»РёС‚СЊ РєР»СЋС‡ РїРѕСЃР»Рµ РЅРµСѓРґР°С‡РЅРѕРіРѕ СЃРїРёСЃР°РЅРёСЏ Р±Р°Р»Р»РѕРІ:\nРљР»СЋС‡: {unique_email}\nРџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: {user_id}\nРћС€РёР±РєР°: {str(e)}")
                        await safe_edit_or_reply(message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё СЃРїРёСЃР°РЅРёРё Р±Р°Р»Р»РѕРІ!")
                        return
                    expiry_time = datetime.datetime.now() + datetime.timedelta(days=points_days)
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
                        [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="back")]
                    ])
                    await safe_edit_or_reply(message, msg, reply_markup=keyboard, parse_mode="HTML")
                    
                    # Р›РѕРіРёРєР° СѓС‡С‘С‚Р° РїРѕРєСѓРїРѕРє РїРµСЂРµРЅРµСЃРµРЅР°; Р°РіСЂРµРіР°С‚С‹ РІ users РЅРµ РІРµРґС‘Рј
                    
                    # РџСЂРѕРІРµСЂСЏРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃРІСЏР·СЊ Рё РІС‹РґР°РµРј Р±Р°Р»Р»С‹ Р°С‚РѕРјР°СЂРЅРѕ
                    try:
                        referrer_id = await get_pending_referral(user_id)
                        if referrer_id:
                            # РђС‚РѕРјР°СЂРЅРѕ РІС‹РґР°РµРј РЅР°РіСЂР°РґСѓ
                            reward_success = await atomic_referral_reward(referrer_id, user_id, f"points_{key_id}", server_manager)
                            
                            if reward_success:
                                # РЈРІРµРґРѕРјР»СЏРµРј СЂРµС„РµСЂРµСЂР°
                                try:
                                    await context.bot.send_message(
                                        chat_id=referrer_id,
                                        text="РџРѕР·РґСЂР°РІР»СЏРµРј! Р’Р°С€ СЂРµС„РµСЂР°Р» РєСѓРїРёР» VPN Рё РІС‹ РїРѕР»СѓС‡РёР»Рё 1 Р±Р°Р»Р»!"
                                    )
                                except Exception as e:
                                    logger.error(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СѓРІРµРґРѕРјР»РµРЅРёСЏ СЂРµС„РµСЂРµСЂСѓ {referrer_id}: {e}")
                            else:
                                logger.error(f"РћС€РёР±РєР° РІС‹РґР°С‡Рё СЂРµС„РµСЂР°Р»СЊРЅРѕР№ РЅР°РіСЂР°РґС‹ РґР»СЏ {referrer_id}")
                                # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃРёСЃС‚РµРјС‹
                                await notify_admin(context.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РґР°С‚СЊ СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ РЅР°РіСЂР°РґСѓ:\nР РµС„РµСЂРµСЂ: {referrer_id}\nР РµС„РµСЂР°Р»: {user_id}\nРџР»Р°С‚РµР¶: points_{key_id}")
                    except Exception as e:
                        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё СЂРµС„РµСЂР°Р»СЊРЅРѕР№ РЅР°РіСЂР°РґС‹: {e}")
                        # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ СЂРµС„РµСЂР°Р»СЊРЅРѕР№ СЃРёСЃС‚РµРјС‹
                        await notify_admin(context.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё СЂРµС„РµСЂР°Р»СЊРЅРѕР№ РЅР°РіСЂР°РґС‹:\nР РµС„РµСЂРµСЂ: {referrer_id}\nР РµС„РµСЂР°Р»: {user_id}\nРћС€РёР±РєР°: {str(e)}")
                    
                    return
                else:
                    # РљР»СЋС‡ РЅРµ СЃРѕР·РґР°РЅ - Р±Р°Р»Р»С‹ РЅРµ СЃРїРёСЃС‹РІР°Р»РёСЃСЊ, РїСЂРѕСЃС‚Рѕ СЃРѕРѕР±С‰Р°РµРј РѕР± РѕС€РёР±РєРµ
                    await safe_edit_or_reply(message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РєР»СЋС‡Р°.")
                    return
                    
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїРѕРєСѓРїРєРё Р·Р° Р±Р°Р»Р»С‹: {e}")
                # Р‘Р°Р»Р»С‹ РЅРµ СЃРїРёСЃС‹РІР°Р»РёСЃСЊ, РїСЂРѕСЃС‚Рѕ СЃРѕРѕР±С‰Р°РµРј РѕР± РѕС€РёР±РєРµ
                await safe_edit_or_reply(message, f"{UIEmojis.ERROR} РћС€РёР±РєР° РїСЂРё РїРѕРєСѓРїРєРµ.")
                return
        
        # РћР±С‹С‡РЅР°СЏ РїРѕРєСѓРїРєР° Р·Р° РґРµРЅСЊРіРё
        try:
            payment = Payment.create({
                "amount": {"value": price, "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": f"https://t.me/{user.id}"},
                "capture": True,
                "description": f"VPN {period} РґР»СЏ {user_id}",
                "metadata": {
                    "user_id": user_id, 
                    "key_id": key_id, 
                    "type": period,
                    "selected_location": context.user_data.get("selected_location", "auto")
                },
                "receipt": {
                    "customer": {"email": f"{user_id}@vpn-x3.ru"},
                    "items": [{
                        "description": f"VPN {period} РґР»СЏ {user_id}",
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1
                    }]
                }
            })
            payment_id = payment.id
        except Exception as e:
            logger.exception(f"РћС€РёР±РєР° СЃРѕР·РґР°РЅРёСЏ РїР»Р°С‚РµР¶Р° РґР»СЏ user_id={user_id}")
            # РЈРІРµРґРѕРјР»СЏРµРј Р°РґРјРёРЅР° Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕР№ РѕС€РёР±РєРµ СЃРѕР·РґР°РЅРёСЏ РїР»Р°С‚РµР¶Р°
            await notify_admin(context.bot, f"рџљЁ РљР РРўРР§Р•РЎРљРђРЇ РћРЁРР‘РљРђ: РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ РїР»Р°С‚РµР¶:\nРџРѕР»СЊР·РѕРІР°С‚РµР»СЊ: {user_id}\nРџРµСЂРёРѕРґ: {period}\nР¦РµРЅР°: {price}\nРћС€РёР±РєР°: {str(e)}")
            await safe_edit_or_reply(message, 'РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РїР»Р°С‚РµР¶Р°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.')
            return
        
        # РџРѕРєР°Р·С‹РІР°РµРј СЃСЃС‹Р»РєСѓ РЅР° РѕРїР»Р°С‚Сѓ
        try:
            # РћРїСЂРµРґРµР»СЏРµРј РїРµСЂРµРјРµРЅРЅС‹Рµ РґР»СЏ С‚РµРєСЃС‚Р°
            if period.startswith('extend_'):
                # Р”Р»СЏ РїСЂРѕРґР»РµРЅРёСЏ СѓР±РёСЂР°РµРј РїСЂРµС„РёРєСЃ extend_
                actual_period = period.replace('extend_', '')
                period_text = "1 РјРµСЃСЏС†" if actual_period == "month" else "3 РјРµСЃСЏС†Р°"
            else:
                # Р”Р»СЏ РѕР±С‹С‡РЅРѕР№ РїРѕРєСѓРїРєРё
                period_text = "1 РјРµСЃСЏС†" if period == "month" else "3 РјРµСЃСЏС†Р°"
            payment_url = payment.confirmation.confirmation_url
            
            # РЎРѕС…СЂР°РЅСЏРµРј message_id РґР»СЏ РѕС‚СЃР»РµР¶РёРІР°РЅРёСЏ РїР»Р°С‚РµР¶Р°
            payment_message_ids[payment.id] = message.message_id
            logger.info(f"РЎРѕС…СЂР°РЅРµРЅ message_id {message.message_id} РґР»СЏ payment_id {payment.id}")
            logger.info(f"РўРµРєСѓС‰РµРµ СЃРѕСЃС‚РѕСЏРЅРёРµ payment_message_ids: {payment_message_ids}")
            
            # Р”Р»СЏ РїСЂРѕРґР»РµРЅРёСЏ СЃРѕС…СЂР°РЅСЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ СЃРѕРѕР±С‰РµРЅРёРё РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµРіРѕ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ
            if period.startswith('extend_'):
                extension_messages[payment.id] = (message.chat_id, message.message_id)
                logger.info(f"РЎРѕС…СЂР°РЅРµРЅР° РёРЅС„РѕСЂРјР°С†РёСЏ Рѕ СЃРѕРѕР±С‰РµРЅРёРё РїСЂРѕРґР»РµРЅРёСЏ: payment_id={payment.id}, chat_id={message.chat_id}, message_id={message.message_id}")
            
            # Р РµРґР°РєС‚РёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ СЃ РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР° РЅР° РёРЅС„РѕСЂРјР°С†РёСЋ РѕР± РѕРїР»Р°С‚Рµ
            try:
                # РџРѕР»СѓС‡Р°РµРј С‚РµРєСЃС‚ СЃРѕРѕР±С‰РµРЅРёСЏ РѕР± РѕРїР»Р°С‚Рµ
                payment_text = (
                    f"<b>РћРїР»Р°С‚Р° РїРѕРґРїРёСЃРєРё РЅР° {period_text}</b>\n\n"
                    f"РЎСѓРјРјР°: <b>{price}в‚Ѕ</b>\n"
                    f"РџРµСЂРёРѕРґ: <b>{period_text}</b>\n\n"
                    f"<a href='{payment_url}'>РџРµСЂРµР№С‚Рё Рє РѕРїР»Р°С‚Рµ</a>\n\n"
                    f"{UIEmojis.WARNING} <i>РЎСЃС‹Р»РєР° РґРµР№СЃС‚РІРёС‚РµР»СЊРЅР° 15 РјРёРЅСѓС‚</i>\n\n"
                    f"РџРѕСЃР»Рµ РѕРїР»Р°С‚С‹ РєР»СЋС‡ Р±СѓРґРµС‚ Р°РєС‚РёРІРёСЂРѕРІР°РЅ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё."
                )
                
                # РЎРѕР·РґР°РµРј РєРЅРѕРїРєСѓ "РќР°Р·Р°Рґ"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
                ])
                
                await safe_edit_or_reply_universal(message, payment_text, reply_markup=keyboard, parse_mode="HTML", menu_type='payment')
                logger.info(f"РћС‚СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР° РЅР° РёРЅС„РѕСЂРјР°С†РёСЋ РѕР± РѕРїР»Р°С‚Рµ: message_id={message.message_id}")
            except Exception as e:
                logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР°: {e}")
                # Р•СЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ РѕС‚СЂРµРґР°РєС‚РёСЂРѕРІР°С‚СЊ, СѓРґР°Р»СЏРµРј Рё РѕС‚РїСЂР°РІР»СЏРµРј РЅРѕРІРѕРµ
                try:
                    await message.delete()
                    logger.info(f"РЈРґР°Р»РµРЅРѕ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР°: message_id={message.message_id}")
                except Exception as delete_error:
                    logger.error(f"РќРµ СѓРґР°Р»РѕСЃСЊ СѓРґР°Р»РёС‚СЊ СЃРѕРѕР±С‰РµРЅРёРµ СЃ РјРµРЅСЋ РІС‹Р±РѕСЂР° РїРµСЂРёРѕРґР°: {delete_error}")
            
            # РџРѕРґРіРѕС‚Р°РІР»РёРІР°РµРј РјРµС‚Р°РґР°РЅРЅС‹Рµ РїР»Р°С‚РµР¶Р°
            payment_meta = {"price": price, "type": period, "key_id": key_id, "unique_email": unique_email}
            
            # Р”РѕР±Р°РІР»СЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїСЂРѕРґР»РµРЅРёРё, РµСЃР»Рё СЌС‚Рѕ РїСЂРѕРґР»РµРЅРёРµ РєР»СЋС‡Р°
            if period.startswith('extend_') and context.user_data.get('extension_key_email'):
                payment_meta['extension_key_email'] = context.user_data['extension_key_email']
                logger.info(f"Р”РѕР±Р°РІР»РµРЅР° РёРЅС„РѕСЂРјР°С†РёСЏ Рѕ РїСЂРѕРґР»РµРЅРёРё РІ РјРµС‚Р°РґР°РЅРЅС‹Рµ: {context.user_data['extension_key_email']}")
            
            await add_payment(user_id, payment.id, 'pending', now, payment_meta)
        except Exception as e:
            logger.exception(f"РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё СЃРѕРѕР±С‰РµРЅРёСЏ РѕР± РѕРїР»Р°С‚Рµ РґР»СЏ user_id={user_id}")
            await safe_edit_or_reply(message, 'РћС€РёР±РєР° РїСЂРё РѕС‚РїСЂР°РІРєРµ РёРЅС„РѕСЂРјР°С†РёРё РѕР± РѕРїР»Р°С‚Рµ.')
    except Exception as e:
        logger.exception(f"РћС€РёР±РєР° РІ handle_payment РґР»СЏ user_id={user_id}")
        await safe_edit_or_reply(message, 'РџСЂРѕРёР·РѕС€Р»Р° РІРЅСѓС‚СЂРµРЅРЅСЏСЏ РѕС€РёР±РєР°. РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ СѓР¶Рµ СѓРІРµРґРѕРјР»С‘РЅ.')
        await notify_admin(context.bot, f"РћС€РёР±РєР° РІ handle_payment РґР»СЏ user_id={user_id}: {e}\n{traceback.format_exc()}")



async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if not context.user_data.get('nav_stack'):
        context.user_data['nav_stack'] = ['main_menu']
    stack = context.user_data['nav_stack']
    if not stack or stack[-1] != 'mykeys_menu':
        push_nav(context, 'mykeys_menu')
    user = update.effective_user
    user_id = str(user.id)
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("mykeys_menu: message is None")
        return
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰СѓСЋ СЃС‚СЂР°РЅРёС†Сѓ РёР· callback_data РёР»Рё СѓСЃС‚Р°РЅР°РІР»РёРІР°РµРј 0
    current_page = 0
    if update.callback_query and update.callback_query.data.startswith('keys_page_'):
        try:
            current_page = int(update.callback_query.data.split('_')[2])
            logger.info(f"РџРµСЂРµС…РѕРґ РЅР° СЃС‚СЂР°РЅРёС†Сѓ {current_page} РґР»СЏ user_id={user_id}")
        except (ValueError, IndexError):
            current_page = 0
            logger.error(f"РћС€РёР±РєР° РїР°СЂСЃРёРЅРіР° РЅРѕРјРµСЂР° СЃС‚СЂР°РЅРёС†С‹: {update.callback_query.data}")
    
    try:
        # РС‰РµРј РєР»РёРµРЅС‚РѕРІ РЅР° РІСЃРµС… СЃРµСЂРІРµСЂР°С…
        all_clients = []
        unique_clients = {} # РЎР»РѕРІР°СЂСЊ РґР»СЏ С…СЂР°РЅРµРЅРёСЏ СѓРЅРёРєР°Р»СЊРЅС‹С… РєР»РёРµРЅС‚РѕРІ РїРѕ email
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(user_id) or client['email'].startswith(f'trial_{user_id}'):
                            client['server_name'] = server['name']  # Р”РѕР±Р°РІР»СЏРµРј РёРјСЏ СЃРµСЂРІРµСЂР°
                            if client['email'] not in unique_clients:
                                unique_clients[client['email']] = client
                                all_clients.append(client)
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё РєР»РёРµРЅС‚РѕРІ СЃ СЃРµСЂРІРµСЂР° {server['name']}: {e}")

        if not all_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} РќР°Р·Р°Рґ", callback_data="back")]
            ])
            await safe_edit_or_reply_universal(message, 'РЈ РІР°СЃ РЅРµС‚ Р°РєС‚РёРІРЅС‹С… РєР»СЋС‡РµР№.', reply_markup=keyboard, menu_type='mykeys_menu')
            return

        # РќР°СЃС‚СЂРѕР№РєРё РїР°РіРёРЅР°С†РёРё
        keys_per_page = 1  # РџРѕРєР°Р·С‹РІР°РµРј РїРѕ 1 РєР»СЋС‡Сѓ РЅР° СЃС‚СЂР°РЅРёС†Сѓ
        total_pages = (len(all_clients) + keys_per_page - 1) // keys_per_page
        
        # РћРіСЂР°РЅРёС‡РёРІР°РµРј С‚РµРєСѓС‰СѓСЋ СЃС‚СЂР°РЅРёС†Сѓ
        current_page = max(0, min(current_page, total_pages - 1))
        
        # РџРѕР»СѓС‡Р°РµРј РєР»СЋС‡Рё РґР»СЏ С‚РµРєСѓС‰РµР№ СЃС‚СЂР°РЅРёС†С‹
        start_idx = current_page * keys_per_page
        end_idx = start_idx + keys_per_page
        page_clients = all_clients[start_idx:end_idx]
        
        # Р¤РѕСЂРјРёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ РґР»СЏ С‚РµРєСѓС‰РµР№ СЃС‚СЂР°РЅРёС†С‹
        now = int(datetime.datetime.now().timestamp())
        page_text = f"{UIStyles.header(f'Р’Р°С€Рё РєР»СЋС‡Рё (СЃС‚СЂ. {current_page + 1}/{total_pages})')}\n\n"
        
        for i, client in enumerate(page_clients, start_idx + 1):
            expiry = int(client.get('expiryTime', 0) / 1000)
            is_active = client.get('enable', False) and expiry > now
            expiry_str = datetime.datetime.fromtimestamp(expiry).strftime('%d.%m.%Y %H:%M') if expiry else 'вЂ”'
            status = 'РђРєС‚РёРІРµРЅ' if is_active else 'РќРµР°РєС‚РёРІРµРЅ'
            server_name = client.get('server_name', 'РќРµРёР·РІРµСЃС‚РЅС‹Р№ СЃРµСЂРІРµСЂ')
            
            xui = None
            for server in server_manager.servers:
                if server['name'] == server_name:
                    xui = server['x3']
                    break
            
            if xui:
                link = xui.link(client["email"])
                
                # Р”РѕР±Р°РІР»СЏРµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР»СЋС‡Рµ
                status_icon = UIEmojis.SUCCESS if status == "РђРєС‚РёРІРµРЅ" else UIEmojis.ERROR
                
                # Р’С‹С‡РёСЃР»СЏРµРј РѕСЃС‚Р°РІС€РµРµСЃСЏ РІСЂРµРјСЏ
                time_remaining = calculate_time_remaining(expiry)
                
                # РџРѕР»СѓС‡Р°РµРј РёРјСЏ РєР»СЋС‡Р° РёР· РїРѕР»СЏ subId
                key_name = client.get('subId', '').strip()
                if key_name:
                    page_text += f"{UIStyles.subheader(f'{i}. {key_name}')}\n"
                else:
                    page_text += f"{UIStyles.subheader(f'{i}. РљР»СЋС‡ #{i}')}\n"
                
                page_text += f"<b>Email:</b> <code>{client['email']}</code>\n"
                page_text += f"<b>РЎС‚Р°С‚СѓСЃ:</b> {status_icon} {status}\n"
                page_text += f"<b>РЎРµСЂРІРµСЂ:</b> {server_name}\n"
                page_text += f"<b>РћСЃС‚Р°Р»РѕСЃСЊ:</b> {time_remaining}\n\n"
                page_text += f"<code>{link}</code>\n\n"
                page_text += f"{UIStyles.description('РќР°Р¶РјРёС‚Рµ РЅР° РєР»СЋС‡ РІС‹С€Рµ, С‡С‚РѕР±С‹ СЃРєРѕРїРёСЂРѕРІР°С‚СЊ')}\n\n"
        
        
        # РЎРѕР·РґР°РµРј РєР»Р°РІРёР°С‚СѓСЂСѓ СЃ РЅР°РІРёРіР°С†РёРµР№
        keyboard_buttons = []
        
        # РљРЅРѕРїРєР° "РџСЂРѕРґР»РёС‚СЊ" РґР»СЏ С‚РµРєСѓС‰РµРіРѕ РєР»СЋС‡Р° (РµСЃР»Рё РєР»СЋС‡ РЅРµ РёСЃС‚РµРє)
        current_client = page_clients[0] if page_clients else None
        if current_client:
            expiry = int(current_client.get('expiryTime', 0) / 1000)
            now = int(datetime.datetime.now().timestamp())
            # РџРѕРєР°Р·С‹РІР°РµРј РєРЅРѕРїРєСѓ РїСЂРѕРґР»РµРЅРёСЏ РµСЃР»Рё РєР»СЋС‡ Р°РєС‚РёРІРµРЅ РёР»Рё РёСЃС‚РµРє РјРµРЅРµРµ С‡РµРј 30 РґРЅРµР№ РЅР°Р·Р°Рґ
            if expiry > now - (30 * 24 * 3600):  # РњРѕР¶РЅРѕ РїСЂРѕРґР»РёС‚СЊ РІ С‚РµС‡РµРЅРёРµ 30 РґРЅРµР№ РїРѕСЃР»Рµ РёСЃС‚РµС‡РµРЅРёСЏ
                # РЎРѕР·РґР°РµРј РєРѕСЂРѕС‚РєРёР№ РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂ РґР»СЏ РєР»СЋС‡Р°
                import hashlib
                short_id = hashlib.md5(f"{user_id}:{current_client['email']}".encode()).hexdigest()[:8]
                extension_keys_cache[short_id] = current_client['email']
                keyboard_buttons.append([InlineKeyboardButton("РџСЂРѕРґР»РёС‚СЊ РєР»СЋС‡", callback_data=f"ext_key:{short_id}")])
            
            # РљРЅРѕРїРєР° РґР»СЏ РїРµСЂРµРёРјРµРЅРѕРІР°РЅРёСЏ РєР»СЋС‡Р°
            rename_short_id = hashlib.md5(f"rename:{current_client['email']}".encode()).hexdigest()[:8]
            keyboard_buttons.append([InlineKeyboardButton("РџРµСЂРµРёРјРµРЅРѕРІР°С‚СЊ РєР»СЋС‡", callback_data=f"rename_key:{rename_short_id}")])
        
        # РљРЅРѕРїРєРё РЅР°РІРёРіР°С†РёРё РїРѕ СЃС‚СЂР°РЅРёС†Р°Рј
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton(f"РџСЂРµРґ. {UIEmojis.PREV}", callback_data=f"keys_page_{current_page - 1}"))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(f"РЎР»РµРґ. {UIEmojis.NEXT}", callback_data=f"keys_page_{current_page + 1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        # РљРЅРѕРїРєР° "РќР°Р·Р°Рґ"
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ СЃ РїР°РіРёРЅР°С†РёРµР№
        await safe_edit_or_reply_universal(message, page_text, reply_markup=keyboard, parse_mode="HTML", menu_type='mykeys_menu')
        
    except Exception as e:
        logger.exception(f"РћС€РёР±РєР° РІ mykey РґР»СЏ user_id={user_id}: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} РќР°Р·Р°Рґ", callback_data="back")]
        ])
        await safe_edit_or_reply(message, f'{UIEmojis.ERROR} РћС€РёР±РєР°: {e}', reply_markup=keyboard)




async def init_all_db():
    from .keys_db import init_payments_db, DB_PATH, REFERRAL_DB_PATH, DATA_DIR
    from .notifications_db import init_notifications_db, NOTIFICATIONS_DB_PATH
    
    # РЎРѕР·РґР°РµРј РїР°РїРєСѓ data РµСЃР»Рё РµС‘ РЅРµС‚
    import os
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"РЎРѕР·РґР°РЅР°/РїСЂРѕРІРµСЂРµРЅР° РїР°РїРєР° РґР»СЏ Р±Р°Р· РґР°РЅРЅС‹С…: {DATA_DIR}")
    
    logger.info("РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ Р±Р°Р· РґР°РЅРЅС‹С…...")
    logger.info(f"РџСѓС‚СЊ Рє Р±Р°Р·Рµ РїР»Р°С‚РµР¶РµР№: {DB_PATH}")
    logger.info(f"РџСѓС‚СЊ Рє СЂРµС„РµСЂР°Р»СЊРЅРѕР№ Р±Р°Р·Рµ: {REFERRAL_DB_PATH}")
    logger.info(f"РџСѓС‚СЊ Рє Р±Р°Р·Рµ СѓРІРµРґРѕРјР»РµРЅРёР№: {NOTIFICATIONS_DB_PATH}")
    
    logger.info("Р’С‹Р·С‹РІР°РµРј init_payments_db()...")
    await init_payments_db()
    logger.info("init_payments_db() Р·Р°РІРµСЂС€РµРЅР°")
    logger.info("Р‘Р°Р·Р° РґР°РЅРЅС‹С… РїР»Р°С‚РµР¶РµР№ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅР°")
    
    await init_referral_db()  # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј СЂРµС„РµСЂР°Р»СЊРЅСѓСЋ СЃРёСЃС‚РµРјСѓ Рё РєРѕРЅС„РёРі
    logger.info("Р РµС„РµСЂР°Р»СЊРЅР°СЏ Р±Р°Р·Р° РґР°РЅРЅС‹С… РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅР°")
    
    await init_notifications_db()  # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј Р±Р°Р·Сѓ РґР°РЅРЅС‹С… СѓРІРµРґРѕРјР»РµРЅРёР№
    logger.info("Р‘Р°Р·Р° РґР°РЅРЅС‹С… СѓРІРµРґРѕРјР»РµРЅРёР№ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅР°")
    
    logger.info("Р’СЃРµ Р±Р°Р·С‹ РґР°РЅРЅС‹С… СѓСЃРїРµС€РЅРѕ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅС‹")


