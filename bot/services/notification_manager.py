"""
Модуль для работы с уведомлениями
Содержит всю логику отправки уведомлений, метрики и мониторинг
"""

import asyncio
import datetime
import logging

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List

from ..db import (
    init_notifications_db,
    record_notification_metrics,
    cleanup_old_notifications,
    get_notification_stats,
    get_notification_settings,
    set_notification_setting,
    is_subscription_notification_sent,
    mark_subscription_notification_sent,
)
from ..utils import UIMessages, calculate_time_remaining

logger = logging.getLogger(__name__)


class NotificationManager:
    """Менеджер уведомлений с метриками и мониторингом"""
    
    def __init__(self, bot, server_manager, admin_ids: List[int]):
        self.bot = bot
        self.server_manager = server_manager
        self.admin_ids = admin_ids
        self.is_running = False
        
        # Настройки уведомлений по умолчанию
        self.default_settings = {
            'check_interval': '300',  # 5 минут
            'cleanup_interval': '86400',  # 24 часа
            'days_to_keep': '30',
            'enable_metrics': 'true'
        }
    
    async def initialize(self):
        """Инициализация менеджера уведомлений"""
        try:
            await init_notifications_db()
            
            # Загружаем настройки
            settings = await get_notification_settings()
            for key, default_value in self.default_settings.items():
                if key not in settings:
                    await set_notification_setting(key, default_value)
            
            logger.info("Менеджер уведомлений инициализирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка инициализации менеджера уведомлений: {e}")
            return False
    
    async def start(self):
        """Запуск менеджера уведомлений"""
        if self.is_running:
            logger.warning("Менеджер уведомлений уже запущен")
            return
        
        self.is_running = True
        
        # Запускаем задачи
        asyncio.create_task(self._expiry_notifications_task())
        asyncio.create_task(self._cleanup_task())
        asyncio.create_task(self._metrics_task())
        
        logger.info("Менеджер уведомлений запущен")

    async def _expiry_notifications_task(self):
        """Задача для проверки истекающих подписок"""
        logger.info("Запуск задачи уведомлений об истечении подписок")
        await asyncio.sleep(10) # Даем боту загрузиться
        
        while self.is_running:
            try:
                await self._check_expiring_subscriptions()
                
                settings = await get_notification_settings()
                interval = int(settings.get('check_interval', '300'))
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Ошибка в задаче уведомлений: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_task(self):
        """Задача для очистки старых записей"""
        while self.is_running:
            try:
                settings = await get_notification_settings()
                days_to_keep = int(settings.get('days_to_keep', '30'))
                
                deleted_count = await cleanup_old_notifications(days_to_keep)
                if deleted_count > 0:
                    logger.info(f"Очищено {deleted_count} старых записей уведомлений")
                
                # Ждем сутки
                await asyncio.sleep(86400)
                
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
                await asyncio.sleep(3600)
    
    async def _metrics_task(self):
        """Задача для сбора метрик"""
        while self.is_running:
            try:
                await self._collect_metrics()
                # Собираем метрики каждые 12 часов
                await asyncio.sleep(43200)
            except Exception as e:
                logger.error(f"Ошибка в задаче метрик: {e}")
                await asyncio.sleep(3600)
    
    async def _check_expiring_subscriptions(self):
        """Проверяет истекающие подписки из account_expiry_cache (Remnawave) и отправляет уведомления"""
        try:
            from ..db.accounts_db import get_accounts_expiring_soon
            now_ts = int(datetime.datetime.now().timestamp())
            window_3d = 259200
            window_1d = 86400
            window_1h = 3600
            accounts = await get_accounts_expiring_soon(now_ts, window_1h, window_1d, window_3d)
            if not accounts:
                return
            now = datetime.datetime.now()
            notifications_sent = 0
            for row in accounts:
                try:
                    account_id = row["account_id"]
                    expires_at = row["expires_at"]
                    user_id = str(account_id)
                    subscription_id = 0
                    expiry_time = datetime.datetime.fromtimestamp(expires_at)
                    time_diff = expiry_time - now
                    notification_type = None
                    if time_diff.total_seconds() > 0:
                        if time_diff.total_seconds() <= window_1h:
                            notification_type = "1hour"
                        elif time_diff.total_seconds() <= window_1d:
                            notification_type = "1day"
                        elif time_diff.total_seconds() <= window_3d:
                            notification_type = "3days"
                    if notification_type:
                        time_remaining = calculate_time_remaining(expires_at)
                        success = await self._send_subscription_expiry_notification(
                            user_id, subscription_id, notification_type, time_remaining,
                            time_diff.days, expiry_time
                        )
                        if success:
                            notifications_sent += 1
                except Exception as e:
                    logger.error(f"Ошибка обработки account_id={row.get('account_id')}: {e}")
            if notifications_sent > 0:
                logger.info(f"Отправлено {notifications_sent} уведомлений")
        except Exception as e:
            logger.error(f"Ошибка в _check_expiring_subscriptions: {e}")
    
    async def _send_subscription_expiry_notification(
        self, user_id: str, subscription_id: int, notification_type: str,
        time_remaining: str, days_until_expiry: int, expiry_datetime=None
    ) -> bool:
        """Отправляет уведомление об истекающей подписке"""
        try:
            # Проверка отправки за последние 24 часа для защиты от спама
            if await is_subscription_notification_sent(user_id, subscription_id, notification_type):
                return False
            
            from ..db.accounts_db import get_telegram_chat_id_for_account
            account_id = int(user_id) if user_id.isdigit() else None
            chat_id = await get_telegram_chat_id_for_account(account_id) if account_id is not None else None
            if chat_id is None:
                logger.debug(f"Пропуск уведомления для user_id={user_id}: нет Telegram (веб-only без привязки)")
                return False
            
            message_text = UIMessages.subscription_expiring_message(time_remaining, days_until_expiry, expiry_datetime)
            
            from ..utils import UIButtons
            webapp_button = UIButtons.create_webapp_button(
                action='subscriptions',
                text="Открыть в приложении"
            )
            
            # Создаем клавиатуру только с deep link кнопкой
            buttons = []
            if webapp_button:
                buttons.append([webapp_button])
            
            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
            
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                
                await mark_subscription_notification_sent(user_id, subscription_id, notification_type)
                await record_notification_metrics(notification_type, True)
                return True
                
            except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
                # Если бот заблокирован, помечаем в метриках
                is_blocked = "Chat not found" in str(e) or isinstance(e, telegram.error.Forbidden)
                await record_notification_metrics(notification_type, False, is_blocked=is_blocked)
                # Чтобы больше не пытаться слать этому пользователю сегодня
                await mark_subscription_notification_sent(user_id, subscription_id, notification_type)
                return False
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
            return False
    
    async def _collect_metrics(self):
        """Собирает и анализирует метрики"""
        try:
            stats = await get_notification_stats(7)
            if stats.get('total_sent', 0) > 0:
                success_rate = stats.get('success_rate', 0)
                if success_rate < 80:
                    await self._notify_admin(f"Внимание! Низкий процент доставки уведомлений: {success_rate:.1f}%")
        except Exception as e:
            logger.error(f"Ошибка сбора метрик: {e}")
    
    async def _notify_admin(self, message: str):
        """Отправляет уведомление админу"""
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(chat_id=admin_id, text=f"[VPNBot NOTIFICATIONS]\n{message}")
            except Exception:
                pass
