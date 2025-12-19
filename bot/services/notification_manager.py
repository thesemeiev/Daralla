"""
Модуль для работы с уведомлениями
Содержит всю логику отправки уведомлений, метрики и мониторинг
"""

import asyncio
import datetime
import logging
import traceback
import json
import aiosqlite
from typing import Dict, List, Optional, Tuple

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from ..db import (
    init_notifications_db,
    record_notification_metrics,
    cleanup_old_notifications,
    get_notification_stats,
    get_daily_notification_stats,
    clear_user_notifications,
    get_notification_settings,
    set_notification_setting,
    is_subscription_notification_sent,
    mark_subscription_notification_sent,
    clear_subscription_notifications,
    record_subscription_notification_effectiveness
)

logger = logging.getLogger(__name__)

# Импорты для работы с UI
try:
    from ..utils import UIEmojis
except ImportError:
    try:
        from ..bot import UIEmojis
    except ImportError:
        # Fallback если импорт не удался
        class UIEmojis:
            REFRESH = "↻"

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
            'enable_metrics': 'true',
            'enable_effectiveness_tracking': 'true'
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
    
    async def stop(self):
        """Остановка менеджера уведомлений"""
        self.is_running = False
        logger.info("Менеджер уведомлений остановлен")
    
    async def _expiry_notifications_task(self):
        """Задача для проверки истекающих подписок"""
        logger.info("Запуск задачи уведомлений об истечении подписок")
        
        # Ждем 30 секунд после запуска
        await asyncio.sleep(30)
        
        while self.is_running:
            try:
                await self.check_expiring_keys()  # Проверяет только подписки
                
                # Получаем интервал проверки из настроек
                settings = await get_notification_settings()
                interval = int(settings.get('check_interval', '300'))
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Ошибка в задаче уведомлений: {e}")
                await self._notify_admin(f"Ошибка в задаче уведомлений: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(60)  # Ждем минуту при ошибке
    
    async def _cleanup_task(self):
        """Задача для очистки старых записей"""
        while self.is_running:
            try:
                settings = await get_notification_settings()
                cleanup_interval = int(settings.get('cleanup_interval', '86400'))
                days_to_keep = int(settings.get('days_to_keep', '30'))
                
                await asyncio.sleep(cleanup_interval)
                
                if self.is_running:
                    deleted_count = await cleanup_old_notifications(days_to_keep)
                    if deleted_count > 0:
                        logger.info(f"Очищено {deleted_count} старых записей уведомлений")
                
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
                await asyncio.sleep(3600)  # Ждем час при ошибке
    
    async def _metrics_task(self):
        """Задача для сбора метрик"""
        while self.is_running:
            try:
                # Собираем метрики каждые 6 часов
                await asyncio.sleep(21600)
                
                if self.is_running:
                    await self._collect_metrics()
                
            except Exception as e:
                logger.error(f"Ошибка в задаче метрик: {e}")
                await asyncio.sleep(3600)  # Ждем час при ошибке
    
    async def check_expiring_keys(self):
        """Проверяет все подписки пользователей на истечение и отправляет уведомления"""
        logger.info("Проверка истекающих подписок...")
        
        try:
            # Проверяем только подписки (старая логика ключей удалена)
            await self._check_expiring_subscriptions()
            
        except Exception as e:
            logger.error(f"Ошибка в check_expiring_keys: {e}")
            await self._notify_admin(f"Ошибка в check_expiring_keys: {e}\n{traceback.format_exc()}")
    
    async def _check_expiring_subscriptions(self):
        """Проверяет активные подписки на истечение и отправляет уведомления"""
        try:
            from ..db.subscribers_db import get_all_active_subscriptions
            subscriptions = await get_all_active_subscriptions()
            
            if not subscriptions:
                return
            
            now = datetime.datetime.now()
            notifications_sent = 0
            
            for sub in subscriptions:
                try:
                    user_id = sub['user_id']
                    expires_at = sub['expires_at']
                    subscription_id = sub['id']
                    
                    # Конвертируем время истечения
                    expiry_time = datetime.datetime.fromtimestamp(expires_at)
                    time_diff = expiry_time - now
                    
                    # Определяем тип уведомления (только для активных подписок)
                    notification_type = None
                    if time_diff.total_seconds() > 0:  # Подписка еще активна
                        if time_diff.total_seconds() <= 3600:  # Меньше 1 часа
                            notification_type = "1hour"
                        elif time_diff.total_seconds() <= 86400:  # Меньше 1 дня
                            notification_type = "1day"
                        elif time_diff.total_seconds() <= 259200:  # Меньше 3 дней
                            notification_type = "3days"
                    
                    # Вычисляем точное оставшееся время
                    if notification_type:
                        try:
                            from ..utils import calculate_time_remaining
                        except ImportError:
                            from ..bot import calculate_time_remaining
                        
                        time_remaining = calculate_time_remaining(expires_at)
                        
                        success = await self._send_subscription_expiry_notification(
                            user_id, subscription_id, notification_type, time_remaining,
                            time_diff.days
                        )
                        
                        if success:
                            notifications_sent += 1
                            
                except Exception as e:
                    logger.error(f"Ошибка обработки подписки {sub.get('id', 'unknown')}: {e}")
                    continue
            
            if notifications_sent > 0:
                logger.info(f"Отправлено {notifications_sent} уведомлений об истечении подписок")
                
        except Exception as e:
            logger.error(f"Ошибка в _check_expiring_subscriptions: {e}")
    
    async def _send_subscription_expiry_notification(
        self, user_id: str, subscription_id: int, notification_type: str,
        time_remaining: str, days_until_expiry: int
    ) -> bool:
        """Отправляет уведомление об истекающей подписке"""
        try:
            # Проверяем, не отправляли ли мы уже уведомление этого типа для этой подписки
            # Защита от спама: проверяем, было ли отправлено уведомление за последние 24 часа
            if await is_subscription_notification_sent(user_id, subscription_id, notification_type):
                logger.debug(f"Уведомление {notification_type} для подписки {subscription_id} уже отправлено пользователю {user_id}")
                return False
            
            # Получаем текст уведомления
            from ..utils import UIMessages, UIEmojis
            message_text = UIMessages.subscription_expiring_message(
                time_remaining, days_until_expiry
            )
            
            # Создаем клавиатуру с кнопкой продления
            from ..navigation import NavigationBuilder, CallbackData
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.REFRESH} Продлить подписку", callback_data=f"extend_sub:{subscription_id}")],
                [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.MYKEYS_MENU)],
                [NavigationBuilder.create_main_menu_button()]
            ])
            
            # Отправляем уведомление
            try:
                await self.bot.send_message(
                    chat_id=int(user_id),
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                
                # Отмечаем как отправленное
                await mark_subscription_notification_sent(user_id, subscription_id, notification_type)
                
                # Записываем метрики
                await record_notification_metrics(notification_type, True)
                
                # Записываем эффективность
                await record_subscription_notification_effectiveness(
                    user_id, subscription_id, notification_type,
                    action_taken=None, days_until_expiry=days_until_expiry
                )
                
                logger.info(f"Отправлено уведомление {notification_type} об истечении подписки {subscription_id} пользователю {user_id}")
                return True
                
            except telegram.error.Forbidden as e:
                # Пользователь заблокировал бота
                logger.warning(f"Пользователь {user_id} заблокировал бота: {e}")
                await mark_subscription_notification_sent(user_id, subscription_id, notification_type)
                await record_notification_metrics(notification_type, False, user_blocked=True)
                return False
                
            except telegram.error.BadRequest as e:
                if "Chat not found" in str(e):
                    logger.warning(f"Пользователь {user_id} заблокировал бота или удалил чат: {e}")
                    await mark_subscription_notification_sent(user_id, subscription_id, notification_type)
                    await record_notification_metrics(notification_type, False, user_blocked=True)
                else:
                    logger.error(f'BadRequest ошибка отправки уведомления пользователю {user_id}: {e}')
                    await record_notification_metrics(notification_type, False)
                return False
                
            except Exception as send_error:
                logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {send_error}")
                await record_notification_metrics(notification_type, False)
                return False
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об истечении подписки: {e}")
            return False
    
    # Методы для ключей удалены - теперь работаем только с подписками
    
    async def _collect_metrics(self):
        """Собирает и анализирует метрики"""
        try:
            stats = await get_notification_stats(7)  # За последние 7 дней
            
            if stats.get('total_sent', 0) > 0:
                success_rate = stats.get('success_rate', 0)
                blocked_users = stats.get('blocked_users', 0)
                
                # Отправляем отчет админу, если есть проблемы
                if success_rate < 80 or blocked_users > 10:
                    await self._notify_admin(
                        f" Отчет по уведомлениям (7 дней):\n"
                        f"• Всего отправлено: {stats.get('total_sent', 0)}\n"
                        f"• Успешно: {stats.get('success_count', 0)}\n"
                        f"• Неудачно: {stats.get('failed_count', 0)}\n"
                        f"• Заблокированных: {blocked_users}\n"
                        f"• Процент успеха: {success_rate:.1f}%"
                    )
            
        except Exception as e:
            logger.error(f"Ошибка сбора метрик: {e}")
    
    async def _notify_admin(self, message: str):
        """Отправляет уведомление админу"""
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id, 
                    text=f"❗️[VPNBot NOTIFICATIONS]\n{message}"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    async def get_notification_dashboard(self) -> str:
        """Создает дашборд с метриками уведомлений"""
        try:
            stats = await get_notification_stats(7)
            daily_stats = await get_daily_notification_stats()
            
            dashboard = f" <b>Дашборд уведомлений (7 дней)</b>\n\n"
            
            # Общая статистика
            dashboard += f" <b>Общая статистика:</b>\n"
            dashboard += f"• Всего отправлено: {stats.get('total_sent', 0)}\n"
            dashboard += f"• Успешно: {stats.get('success_count', 0)}\n"
            dashboard += f"• Неудачно: {stats.get('failed_count', 0)}\n"
            dashboard += f"• Заблокированных: {stats.get('blocked_users', 0)}\n"
            dashboard += f"• Процент успеха: {stats.get('success_rate', 0):.1f}%\n\n"
            
            # Статистика по типам
            dashboard += f" <b>По типам уведомлений:</b>\n"
            for type_stat in stats.get('type_stats', []):
                dashboard += f"• {type_stat['type']}: {type_stat['total_sent']} "
                dashboard += f"({type_stat['success_rate']:.1f}% успех)\n"
            
            # Эффективность
            effectiveness = stats.get('effectiveness_stats', {})
            if effectiveness:
                dashboard += f"\n <b>Эффективность:</b>\n"
                for action, count in effectiveness.items():
                    dashboard += f"• {action}: {count}\n"
            
            # Ежедневная статистика (последние 5 дней)
            if daily_stats:
                dashboard += f"\n <b>Ежедневная статистика:</b>\n"
                for day_stat in daily_stats[:5]:
                    dashboard += f"• {day_stat['date']}: {day_stat['total_sent']} "
                    dashboard += f"({day_stat['success_rate']:.1f}%)\n"
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Ошибка создания дашборда: {e}")
            return f"❌ Ошибка загрузки дашборда: {e}"
    
    # Метод record_key_extension удален - используйте record_subscription_extension

    async def record_subscription_extension(self, user_id: str, subscription_id: int):
        """Записывает факт продления подписки для анализа эффективности"""
        try:
            # Находим последнее уведомление для этой подписки
            # и отмечаем, что пользователь продлил подписку
            await record_subscription_notification_effectiveness(
                user_id, subscription_id, "extension", 
                action_taken="extended"
            )
            
            # Очищаем уведомления об истечении для этой подписки
            await clear_subscription_notifications(user_id, subscription_id)
            
        except Exception as e:
            logger.error(f"Ошибка записи продления подписки: {e}")

