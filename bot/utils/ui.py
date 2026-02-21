"""
UI компоненты для бота (эмодзи, стили, кнопки, сообщения)
"""
import os
from telegram import InlineKeyboardButton

from ..prices_config import PRICE_MONTH, PRICE_3MONTH


def get_site_urls():
    """
    Возвращает (webapp_url, site_url) для кнопок «Открыть Mini App» и «Вернуться на сайт».
    site_url = WEBSITE_URL или webapp_url (fallback).
    URL нормализуется - гарантируется завершающий слеш для Telegram Web App.
    """
    webapp_url = None
    try:
        from ..app_context import get_ctx
        webapp_url = get_ctx().webapp_url
    except (RuntimeError, ImportError):
        pass
    
    # Нормализуем URL - добавляем завершающий слеш если его нет (для Telegram Web App обязательно)
    if webapp_url and not webapp_url.endswith('/'):
        webapp_url = webapp_url.rstrip('/') + '/'
    
    site_url = os.getenv("WEBSITE_URL", "").strip()
    if not site_url and webapp_url:
        site_url = webapp_url
    return webapp_url, site_url


class UIEmojis:
    """Эмодзи для интерфейса (используются в payment_processors и validators)"""
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"


class UIStyles:
    """Стили форматирования текста"""
    
    @staticmethod
    def header(text: str) -> str:
        """Основной заголовок"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def description(text: str) -> str:
        """Описание"""
        return f"<i>{text}</i>"
    
    @staticmethod
    def success_message(text: str) -> str:
        """Сообщение об успехе"""
        return f"{UIEmojis.SUCCESS} <b>{text}</b>"
    
    @staticmethod
    def warning_message(text: str) -> str:
        """Предупреждение"""
        return f"{UIEmojis.WARNING} <b>{text}</b>"


class UIButtons:
    """Шаблоны кнопок для единообразия"""
    
    @staticmethod
    def main_menu_buttons():
        """Кнопки главного меню (Mini App + канал)."""
        webapp_url = None
        try:
            from ..app_context import get_ctx
            webapp_url = get_ctx().webapp_url
        except (RuntimeError, ImportError):
            pass
        
        buttons = []
        
        # Добавляем кнопку мини-приложения, если доступна
        if webapp_url:
            from telegram import WebAppInfo
            # Нормализуем URL - гарантируем завершающий слеш (для Telegram Web App обязательно)
            normalized_url = webapp_url.rstrip('/') + '/' if webapp_url else None
            if normalized_url:
                buttons.append([InlineKeyboardButton("Открыть в приложении", web_app=WebAppInfo(url=normalized_url))])
        
        # Кнопка канала
        telegram_channel_url = os.getenv("TELEGRAM_CHANNEL_URL", "https://t.me/DarallaNews")
        buttons.append([InlineKeyboardButton("Наш канал", url=telegram_channel_url)])
        
        return buttons
    
    @staticmethod
    def create_webapp_button(action=None, params=None, text="Открыть в приложении"):
        """
        Создает кнопку для открытия мини-приложения.
        
        Args:
            action: Действие (например, 'extend_subscription', 'subscription', 'subscriptions')
            params: Параметры для действия (например, subscription_id)
            text: Текст кнопки (без эмодзи)
        
        Returns:
            InlineKeyboardButton или None, если WEBAPP_URL недоступен
        """
        webapp_url = None
        try:
            from ..app_context import get_ctx
            webapp_url = get_ctx().webapp_url
        except (RuntimeError, ImportError):
            pass
        
        if not webapp_url:
            return None
        
        # Нормализуем URL - гарантируем завершающий слеш перед добавлением query параметров
        # Telegram Web App требует завершающий слеш перед `?` (например: https://daralla.ru/?startapp=...)
        normalized_url = webapp_url.rstrip('/') + '/'
        
        # Если нужны параметры, добавляем их как query параметры
        if action or params:
            from urllib.parse import urlencode
            query_params = {}
            if action:
                if params:
                    query_params['startapp'] = f"{action}_{params}"
                else:
                    query_params['startapp'] = action
            url_with_params = f"{normalized_url}?{urlencode(query_params)}"
        else:
            url_with_params = normalized_url
        
        from telegram import InlineKeyboardButton, WebAppInfo
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=url_with_params))


class UIMessages:
    """Шаблоны сообщений"""
    
    @staticmethod
    def welcome_message(is_new_user=False):
        """Приветственное сообщение"""
        # Разный заголовок для нового и существующего пользователя
        vpn_brand_name = "Daralla VPN"
        try:
            from ..app_context import get_ctx
            vpn_brand_name = get_ctx().vpn_brand_name
        except (RuntimeError, ImportError):
            pass
        
        if is_new_user:
            header_text = f'Добро пожаловать в {vpn_brand_name}!'
        else:
            header_text = f'Рады снова видеть вас в {vpn_brand_name}!'
        
        return (
            f"{UIStyles.header(header_text)}\n\n"
            f"{UIStyles.description('Быстрый и стабильный доступ к серверам по всему миру.')}"
        )

    @staticmethod
    def subscription_expiring_message(time_remaining, days_until_expiry, expiry_datetime=None):
        """Сообщение об истекающей подписке"""
        # Форматируем дату истечения, если передана
        expiry_str = ""
        if expiry_datetime:
            expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
        
        if days_until_expiry == 0:
            # Менее чем через час - срочное уведомление
            message = (
                f" <b>СРОЧНО! Ваша подписка истекает!</b>\n\n"
                f" Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f" Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку сейчас, чтобы не потерять доступ к VPN.\n\n"
                f" <b>Цены:</b>\n"
                f"• 1 месяц — {PRICE_MONTH}₽\n"
                f"• 3 месяца — {PRICE_3MONTH}₽ (выгоднее)\n"
            )
            return message
        elif days_until_expiry <= 1:
            # Завтра или сегодня - важное уведомление
            message = (
                f" <b>Ваша подписка истекает!</b>\n\n"
                f" Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f" Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку заранее, чтобы не прерывать использование VPN.\n\n"
                f" <b>Цены:</b>\n"
                f"• 1 месяц — {PRICE_MONTH}₽\n"
                f"• 3 месяца — {PRICE_3MONTH}₽ (выгоднее)\n"
            )
            return message
        else:
            # За несколько дней - информационное напоминание
            message = (
                f" <b>Напоминание: ваша подписка истекает!</b>\n\n"
                f" Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f" Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку заранее, чтобы не прерывать использование VPN.\n\n"
                f" <b>Цены:</b>\n"
                f"• 1 месяц — {PRICE_MONTH}₽\n"
                f"• 3 месяца — {PRICE_3MONTH}₽ (выгоднее)\n"
            )
            return message

