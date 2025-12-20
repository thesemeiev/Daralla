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
        buttons = [
            [InlineKeyboardButton("Купить", callback_data=CallbackData.BUY_VPN)],
            [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU), 
             InlineKeyboardButton("Инструкция", callback_data=CallbackData.INSTRUCTION)],
            [InlineKeyboardButton("Наш канал", url="https://t.me/DarallaNews")],
        ]
        
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
    def subscription_expiring_message(time_remaining, days_until_expiry):
        """Сообщение об истекающей подписке"""
        if days_until_expiry == 0:
            return (
                f"{UIEmojis.WARNING} <b>Ваша подписка истекает менее чем через час!</b>\n\n"
                f"Осталось: <b>{time_remaining}</b>\n\n"
                f"Продлите подписку, чтобы продолжить пользоваться VPN без перерывов.\n\n"
                f"Используйте команду /mysubs для продления."
            )
        elif days_until_expiry <= 1:
            return (
                f"{UIEmojis.WARNING} <b>Ваша подписка истекает через {days_until_expiry} день!</b>\n\n"
                f"Осталось: <b>{time_remaining}</b>\n\n"
                f"Продлите подписку, чтобы продолжить пользоваться VPN без перерывов.\n\n"
                f"Используйте команду /mysubs для продления."
            )
        else:
            return (
                f"{UIEmojis.WARNING} <b>Ваша подписка истекает через {days_until_expiry} дней</b>\n\n"
                f"Осталось: <b>{time_remaining}</b>\n\n"
                f"Продлите подписку заранее, чтобы не прерывать использование VPN.\n\n"
                f"Используйте команду /mysubs для продления."
            )
    
    # Старые методы для ключей удалены - теперь работаем только с подписками
    

