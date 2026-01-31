"""
UI компоненты для бота (эмодзи, стили, кнопки, сообщения)
"""
from telegram import InlineKeyboardButton


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
    def main_menu_buttons(is_admin=False):
        """Кнопки главного меню (Mini App + канал). is_admin не используется — админка только в вебе."""
        # Получаем WEBAPP_URL из bot.py
        webapp_url = None
        try:
            import sys
            bot_module = sys.modules.get('bot.bot')
            if bot_module:
                webapp_url = getattr(bot_module, 'WEBAPP_URL', None)
        except (ImportError, AttributeError):
            pass
        
        buttons = []
        
        # Добавляем кнопку мини-приложения, если доступна
        if webapp_url:
            from telegram import WebAppInfo
            buttons.append([InlineKeyboardButton("Открыть в приложении", web_app=WebAppInfo(url=webapp_url))])
        
        # Кнопка канала
        buttons.append([InlineKeyboardButton("Наш канал", url="https://t.me/DarallaNews")])
        
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
        # Получаем WEBAPP_URL из bot.py
        webapp_url = None
        try:
            import sys
            bot_module = sys.modules.get('bot.bot')
            if bot_module:
                webapp_url = getattr(bot_module, 'WEBAPP_URL', None)
        except (ImportError, AttributeError):
            pass
        
        if not webapp_url:
            return None
        
        # Если нужны параметры, добавляем их как query параметры
        if action or params:
            from urllib.parse import urlencode
            query_params = {}
            if action:
                if params:
                    query_params['startapp'] = f"{action}_{params}"
                else:
                    query_params['startapp'] = action
            url_with_params = f"{webapp_url}?{urlencode(query_params)}"
        else:
            url_with_params = webapp_url
        
        from telegram import InlineKeyboardButton, WebAppInfo
        return InlineKeyboardButton(text, web_app=WebAppInfo(url=url_with_params))


class UIMessages:
    """Шаблоны сообщений"""
    
    @staticmethod
    def welcome_message(is_new_user=False):
        """Приветственное сообщение"""
        # Разный заголовок для нового и существующего пользователя
        if is_new_user:
            header_text = 'Добро пожаловать в Daralla VPN!'
        else:
            header_text = 'Рады снова видеть вас в Daralla VPN!'
        
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
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
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
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
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
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
            )
            return message

