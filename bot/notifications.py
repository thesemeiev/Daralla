"""
Модуль для работы с уведомлениями
Содержит всю логику отправки уведомлений, метрики и мониторинг
"""

import asyncio
import datetime
import logging
import traceback
from typing import Dict, List, Optional, Tuple

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

try:
    from .notifications_db import (
        init_notifications_db,
        is_notification_sent,
        mark_notification_sent,
        record_notification_metrics,
        record_notification_effectiveness,
        cleanup_old_notifications,
        get_notification_stats,
        get_daily_notification_stats,
        clear_user_notifications,
        clear_key_notifications,
        get_notification_settings,
        set_notification_setting
    )
except ImportError:
    from notifications_db import (
        init_notifications_db,
        is_notification_sent,
        mark_notification_sent,
        record_notification_metrics,
        record_notification_effectiveness,
        cleanup_old_notifications,
        get_notification_stats,
        get_daily_notification_stats,
        clear_user_notifications,
        clear_key_notifications,
        get_notification_settings,
        set_notification_setting
    )

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
            'check_interval': '60',  # тестово 1 минута (было 300)
            'cleanup_interval': '3600',  # тестово 1 час (было 86400)
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
        """Задача для проверки истекающих ключей"""
        logger.info("Запуск задачи уведомлений об истечении ключей")
        
        # Ждем 30 секунд после запуска
        await asyncio.sleep(30)
        
        while self.is_running:
            try:
                await self.check_expiring_keys()
                
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
        """Проверяет все ключи пользователей на истечение и отправляет уведомления"""
        logger.info("Проверка истекающих ключей...")
        
        try:
            all_users_keys = {}
            
            # Получаем все ключи со всех серверов
            for server in self.server_manager.servers:
                try:
                    xui = server["x3"]
                    server_name = server['name']
                    inbounds = xui.list()['obj']
                    
                    for inbound in inbounds:
                        settings = json.loads(inbound['settings'])
                        clients = settings.get("clients", [])
                        
                        for client in clients:
                            email = client.get('email', '')
                            # Ищем пользовательские ключи (не тестовые)
                            if '_' in email:
                                user_id = email.split('_')[0]
                                if user_id not in all_users_keys:
                                    all_users_keys[user_id] = []
                                
                                client_info = client.copy()
                                client_info['server_name'] = server_name
                                all_users_keys[user_id].append(client_info)
                                
                except Exception as e:
                    logger.error(f"Ошибка получения ключей с сервера {server['name']}: {e}")
                    continue
            
            # Проверяем каждого пользователя
            now = datetime.datetime.now()
            notifications_sent = 0
            
            for user_id, user_keys in all_users_keys.items():
                try:
                    for key in user_keys:
                        email = key.get('email', '')
                        expiry_time_ms = key.get('expiryTime', 0)
                        
                        if expiry_time_ms == 0:
                            continue  # Ключ без времени истечения
                        
                        # Конвертируем время истечения
                        expiry_time = datetime.datetime.fromtimestamp(expiry_time_ms / 1000)
                        time_diff = expiry_time - now
                        
                        # Определяем тип уведомления (только для активных ключей)
                        notification_type = None
                        if time_diff.total_seconds() > 0:  # Ключ еще активен
                            if time_diff.total_seconds() <= 3600:  # Меньше 1 часа
                                notification_type = "1hour"
                            elif time_diff.total_seconds() <= 86400:  # Меньше 1 дня
                                notification_type = "1day"
                            elif time_diff.total_seconds() <= 259200:  # Меньше 3 дней
                                notification_type = "3days"
                        
                        # Вычисляем точное оставшееся время
                        if notification_type:
                            # Импортируем функцию вычисления времени
                            try:
                                from .bot import calculate_time_remaining
                            except ImportError:
                                from bot import calculate_time_remaining
                            
                            time_remaining = calculate_time_remaining(expiry_time_ms / 1000)
                            
                            success = await self._send_expiry_notification(
                                user_id, email, notification_type, time_remaining, 
                                key.get('server_name', ''), time_diff.days
                            )
                            
                            if success:
                                notifications_sent += 1
                                
                except Exception as e:
                    logger.error(f"Ошибка обработки ключей пользователя {user_id}: {e}")
                    continue
            
            if notifications_sent > 0:
                logger.info(f"Отправлено {notifications_sent} уведомлений об истечении ключей")
            
            # Очищаем старые записи уведомлений
            await self._cleanup_expired_notifications(all_users_keys, now)
            
        except Exception as e:
            logger.error(f"Ошибка в check_expiring_keys: {e}")
            await self._notify_admin(f"Ошибка в check_expiring_keys: {e}\n{traceback.format_exc()}")
    
    async def _send_expiry_notification(self, user_id: str, email: str, notification_type: str, 
                                      time_remaining: str, server_name: str, days_until_expiry: int) -> bool:
        """Отправляет уведомление об истекающем ключе"""
        try:
            # Проверяем, не отправляли ли уже это уведомление
            if await is_notification_sent(user_id, email, notification_type):
                return False
            
            # Создаем сообщение
            message = self._create_expiry_message(email, server_name, time_remaining)
            
            # Создаем клавиатуру
            keyboard = self._create_expiry_keyboard(email, user_id)
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Отмечаем как отправленное
            await mark_notification_sent(user_id, email, notification_type, server_name)
            
            # Записываем метрики
            await record_notification_metrics(notification_type, True)
            
            # Записываем эффективность
            await record_notification_effectiveness(
                user_id, email, notification_type, 
                action_taken=None, days_until_expiry=days_until_expiry
            )
            
            logger.info(f"Отправлено уведомление {notification_type} пользователю {user_id} для ключа {email}")
            return True
            
        except telegram.error.Forbidden as e:
            # Пользователь заблокировал бота или удалил чат
            logger.warning(f"Пользователь {user_id} заблокировал бота или удалил чат: {e}")
            
            # ВАЖНО: НЕ удаляем записи! Отмечаем как отправленное, чтобы не пытаться снова
            await mark_notification_sent(user_id, email, notification_type, server_name)
            
            # Записываем метрики
            await record_notification_metrics(notification_type, False, user_blocked=True)
            
            return False
            
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Пользователь {user_id} заблокировал бота или удалил чат: {e}")
                # ВАЖНО: НЕ удаляем записи! Отмечаем как отправленное
                await mark_notification_sent(user_id, email, notification_type, server_name)
                await record_notification_metrics(notification_type, False, user_blocked=True)
            else:
                logger.error(f'BadRequest ошибка отправки уведомления пользователю {user_id}: {e}')
                await record_notification_metrics(notification_type, False)
            return False
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
            await record_notification_metrics(notification_type, False)
            return False
    
    def _create_expiry_message(self, email: str, server_name: str, time_remaining: str) -> str:
        """Создает сообщение об истекающем ключе"""
        try:
            from .bot import UIMessages  # Импортируем здесь, чтобы избежать циклического импорта
        except ImportError:
            from bot import UIMessages
        
        return UIMessages.key_expiring_message(email, server_name, time_remaining)
    
    def _create_deletion_message(self, email: str, server_name: str, days_expired: int) -> str:
        """Создает сообщение об удаленном ключе"""
        try:
            from .bot import UIMessages  # Импортируем здесь, чтобы избежать циклического импорта
        except ImportError:
            from bot import UIMessages
        
        return UIMessages.key_deleted_message(email, server_name, days_expired)
    
    async def _send_deletion_notification(self, user_id: str, email: str, server_name: str, days_expired: int) -> bool:
        """Отправляет уведомление об удаленном ключе"""
        try:
            # Проверяем, не отправляли ли уже это уведомление
            if await is_notification_sent(user_id, email, "deleted"):
                return False
            
            # Создаем сообщение
            message = self._create_deletion_message(email, server_name, days_expired)
            
            # Создаем клавиатуру
            keyboard = self._create_deletion_keyboard()
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Отмечаем как отправленное
            await mark_notification_sent(user_id, email, "deleted", server_name)
            
            # Записываем метрики
            await record_notification_metrics("deleted", True)
            
            logger.info(f"Отправлено уведомление об удалении ключа пользователю {user_id} для ключа {email}")
            return True
            
        except telegram.error.Forbidden as e:
            # Пользователь заблокировал бота или удалил чат
            logger.warning(f"Пользователь {user_id} заблокировал бота или удалил чат (deletion notification): {e}")
            await mark_notification_sent(user_id, email, "deleted", server_name)
            await record_notification_metrics("deleted", False, user_blocked=True)
            return False
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Пользователь {user_id} заблокировал бота или удалил чат (deletion notification): {e}")
                await mark_notification_sent(user_id, email, "deleted", server_name)
                await record_notification_metrics("deleted", False, user_blocked=True)
            else:
                logger.error(f'BadRequest ошибка отправки уведомления об удалении пользователю {user_id}: {e}')
                await record_notification_metrics("deleted", False)
            return False
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении пользователю {user_id}: {e}")
            await record_notification_metrics("deleted", False)
            return False
    
    def _create_deletion_keyboard(self) -> InlineKeyboardMarkup:
        """Создает клавиатуру для уведомления об удаленном ключе"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Купить новый ключ", callback_data="buy_menu")],
            [InlineKeyboardButton("Мои ключи", callback_data="mykey")]
        ])
    
    def _create_expiry_keyboard(self, email: str, user_id: str = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру для уведомления об истекающем ключе"""
        import hashlib
        
        # Создаем короткий ID для кнопки продления (используем тот же формат, что и в extend_key_callback)
        if user_id:
            short_id = hashlib.md5(f"{user_id}:{email}".encode()).hexdigest()[:8]
        else:
            # Fallback для случаев, когда user_id не передан
            short_id = hashlib.md5(f"extend:{email}".encode()).hexdigest()[:8]
        
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Продлить ключ", callback_data=f"ext_key:{short_id}")],
            [InlineKeyboardButton("Мои ключи", callback_data="mykey")]
        ])
    
    async def _cleanup_expired_notifications(self, all_users_keys: Dict, now: datetime.datetime):
        """Очищает записи уведомлений для истекших или удаленных ключей"""
        try:
            # Получаем все отправленные уведомления
            # (Логика очистки будет реализована в notifications_db.py)
            pass  # Пока оставляем пустым, логика очистки уже есть в базе данных
            
        except Exception as e:
            logger.error(f"Ошибка очистки уведомлений: {e}")
    
    async def clear_key_notifications(self, user_id: str, email: str) -> bool:
        """Очищает все уведомления для конкретного ключа (при продлении)"""
        try:
            from .notifications_db import clear_key_notifications as clear_key_notifications_db
            return await clear_key_notifications_db(user_id, email)
        except Exception as e:
            logger.error(f"Ошибка очистки уведомлений для ключа {email}: {e}")
            return False
    
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
    
    async def record_key_extension(self, user_id: str, key_email: str):
        """Записывает факт продления ключа для анализа эффективности"""
        try:
            # Находим последнее уведомление для этого ключа
            # и отмечаем, что пользователь продлил ключ
            await record_notification_effectiveness(
                user_id, key_email, "extension", 
                action_taken="extended"
            )
            
        except Exception as e:
            logger.error(f"Ошибка записи продления ключа: {e}")

# Импорты для работы с UI
try:
    from .bot import UIEmojis
except ImportError:
    try:
        from bot import UIEmojis
    except ImportError:
        # Fallback если импорт не удался
        class UIEmojis:
            REFRESH = "↻"

# Импорт json для работы с настройками
import json
