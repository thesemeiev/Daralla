"""
UI компоненты для бота (эмодзи, стили, кнопки, сообщения)
"""
from telegram import InlineKeyboardButton
from ..navigation import NavigationBuilder, CallbackData


class UIEmojis:
    """Эмодзи для интерфейса"""
    # Навигация
    BACK = "←"
    NEXT = "→"
    PREV = "←"
    CLOSE = "✕"
    REFRESH = "↻"
    
    # Дополнительные для кнопок
    EDIT = ""  # Для переименования
    ADD = ""  # Для добавления/покупки
    ARROW_LEFT = "←"  # Для пагинации
    ARROW_RIGHT = "→"  # Для пагинации
    
    # Статусы
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    INFO = "i"  # Информация


class UIStyles:
    """Стили форматирования текста"""
    
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


class UIButtons:
    """Шаблоны кнопок для единообразия"""
    
    @staticmethod
    def main_menu_buttons(is_admin=False):
        """Кнопки главного меню"""
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
            buttons.append([InlineKeyboardButton("📱 Открыть мини-приложение", web_app=WebAppInfo(url=webapp_url))])
        
        # Оставляем старые кнопки для плавного перехода
        buttons.extend([
            [InlineKeyboardButton("Купить", callback_data=CallbackData.BUY_VPN)],
            [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU), 
             InlineKeyboardButton("Инструкция", callback_data=CallbackData.INSTRUCTION)],
            [InlineKeyboardButton("Наш канал", url="https://t.me/DarallaNews")],
        ])
        
        if is_admin:
            buttons.append([InlineKeyboardButton("Админ-меню", callback_data=CallbackData.ADMIN_MENU)])
        
        return buttons
    
    @staticmethod
    def back_button():
        """Кнопка назад"""
        return NavigationBuilder.create_back_button()
    
    @staticmethod
    def refresh_button(callback_data="refresh"):
        """Кнопка обновления"""
        return InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=callback_data)


class UIMessages:
    """Шаблоны сообщений"""
    
    @staticmethod
    def welcome_message():
        """Приветственное сообщение"""
        # Проверяем, доступно ли мини-приложение
        webapp_available = False
        try:
            import sys
            bot_module = sys.modules.get('bot.bot')
            if bot_module:
                webapp_available = bool(getattr(bot_module, 'WEBAPP_URL', None))
        except (ImportError, AttributeError):
            pass
        
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        
        message = (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.description('Мультисерверный VPN-сервис с высокой скоростью и надежностью.')}\n\n"
        )
        
        if webapp_available:
            message += (
                f"{UIStyles.info_message('💡 Рекомендуем использовать мини-приложение для удобного управления подписками, покупок и просмотра инструкций.')}\n\n"
            )
        
        message += f"{UIStyles.warning_message(warning_msg)}"
        
        return message
    
    @staticmethod
    def buy_menu_message():
        """Сообщение меню покупки"""
        return (
            f"{UIStyles.header('Выберите период подписки')}\n\n"
            f"{UIStyles.description('Доступные тарифы:')}\n"
            f"• <b>1 месяц</b> — 150₽\n"
            f"• <b>3 месяца</b> — 350₽"
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
    def subscription_expiring_message(time_remaining, days_until_expiry, expiry_datetime=None):
        """Сообщение об истекающей подписке"""
        # Форматируем дату истечения, если передана
        expiry_str = ""
        if expiry_datetime:
            expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
        
        if days_until_expiry == 0:
            # Менее чем через час - срочное уведомление
            message = (
                f"⚠️ <b>СРОЧНО! Ваша подписка истекает менее чем через час!</b>\n\n"
                f"⏰ Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f"📅 Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку сейчас, чтобы не потерять доступ к VPN.\n\n"
                f"💳 <b>Цены:</b>\n"
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
            )
            return message
        elif days_until_expiry <= 1:
            # Завтра или сегодня - важное уведомление
            day_text = "завтра" if days_until_expiry == 1 else "сегодня"
            message = (
                f"⚠️ <b>Ваша подписка истекает {day_text}!</b>\n\n"
                f"⏰ Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f"📅 Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку заранее, чтобы не прерывать использование VPN.\n\n"
                f"💳 <b>Цены:</b>\n"
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
            )
            return message
        else:
            # За несколько дней - информационное напоминание
            message = (
                f"ℹ️ <b>Напоминание: ваша подписка истекает через {days_until_expiry} дней</b>\n\n"
                f"⏰ Осталось: <b>{time_remaining}</b>\n"
            )
            if expiry_str:
                message += f"📅 Истекает: <b>{expiry_str}</b>\n"
            message += (
                f"\n"
                f"Продлите подписку заранее, чтобы не прерывать использование VPN.\n\n"
                f"💳 <b>Цены:</b>\n"
                f"• 1 месяц — 150₽\n"
                f"• 3 месяца — 350₽ (выгоднее)\n"
            )
            return message
    
    # Старые методы для ключей удалены - теперь работаем только с подписками
    

