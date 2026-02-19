"""
Модуль для работы с уведомлениями
Содержит всю логику отправки уведомлений, метрики и мониторинг
"""

import asyncio
import datetime
import logging
import time

import aiosqlite
import telegram
from telegram import InlineKeyboardMarkup
from typing import List

from ..db import (
    DB_PATH,
    init_notifications_db,
    record_notification_metrics,
    cleanup_old_notifications,
    get_notification_stats,
    get_notification_settings,
    set_notification_setting,
    mark_subscription_notification_sent,
    get_active_notification_rules,
    get_notification_send_count,
    get_last_notification_send_time,
)
from ..utils import calculate_time_remaining
from ..db.notifications_db import render_structured_template

logger = logging.getLogger(__name__)


class NotificationManager:
    """Менеджер уведомлений с метриками и мониторингом"""
    
    def __init__(self, bot, server_manager, admin_ids: List[int]):
        self.bot = bot
        self.server_manager = server_manager
        self.admin_ids = admin_ids
        self.is_running = False
        
        self.default_settings = {
            'check_interval': '300',
            'cleanup_interval': '86400',
            'days_to_keep': '30',
            'enable_metrics': 'true'
        }
    
    async def initialize(self):
        """Инициализация менеджера уведомлений"""
        try:
            await init_notifications_db()
            
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
        
        asyncio.create_task(self._expiry_notifications_task())
        asyncio.create_task(self._cleanup_task())
        asyncio.create_task(self._metrics_task())
        
        logger.info("Менеджер уведомлений запущен")

    async def _expiry_notifications_task(self):
        """Задача для проверки истекающих подписок"""
        logger.info("Запуск задачи уведомлений об истечении подписок")
        await asyncio.sleep(10)
        
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
                
                await asyncio.sleep(86400)
                
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
                await asyncio.sleep(3600)
    
    async def _metrics_task(self):
        """Задача для сбора метрик"""
        while self.is_running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(43200)
            except Exception as e:
                logger.error(f"Ошибка в задаче метрик: {e}")
                await asyncio.sleep(3600)
    
    # ── rule-based engine ──

    async def _check_expiring_subscriptions(self):
        """Загружает активные правила и обрабатывает каждое."""
        try:
            rules = await get_active_notification_rules()
            if not rules:
                return

            settings = await get_notification_settings()
            check_interval = int(settings.get('check_interval', '300'))

            expiry_rules = [r for r in rules if r['event_type'] == 'expiry_warning']
            no_sub_rules = [r for r in rules if r['event_type'] == 'no_subscription']

            subscriptions = None
            if expiry_rules:
                from ..db.subscriptions_db import get_all_active_subscriptions
                subscriptions = await get_all_active_subscriptions()

            for rule in expiry_rules:
                try:
                    await self._process_expiry_rule(rule, check_interval, subscriptions or [])
                except Exception as e:
                    logger.error(f"Ошибка обработки правила {rule.get('id')}: {e}")

            for rule in no_sub_rules:
                try:
                    await self._process_no_sub_rule(rule, check_interval)
                except Exception as e:
                    logger.error(f"Ошибка обработки правила {rule.get('id')}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в _check_expiring_subscriptions: {e}")

    async def _process_expiry_rule(self, rule: dict, check_interval: int, subscriptions: list):
        """Обрабатывает правило типа expiry_warning.

        trigger_hours отрицательное (напр. -72 = за 3 дня до истечения).
        Находим подписки, истекающие в пределах |trigger_hours| от текущего момента.
        Повторная отправка управляется repeat_every_hours / max_repeats.
        """
        if not subscriptions:
            return

        now_ts = int(time.time())
        offset_seconds = abs(rule['trigger_hours']) * 3600
        repeat_every = rule.get('repeat_every_hours', 0)
        max_repeats = rule.get('max_repeats', 1)
        notification_type = f"rule_{rule['id']}"
        notifications_sent = 0

        for sub in subscriptions:
            expires_at = sub['expires_at']
            if expires_at <= now_ts or expires_at > now_ts + offset_seconds:
                continue
            try:
                user_id = sub['user_id']
                subscription_id = sub['id']
                if not await self._should_send(
                    user_id, subscription_id, notification_type,
                    repeat_every, max_repeats, now_ts,
                ):
                    continue
                success = await self._send_rule_notification(
                    rule, user_id, subscription_id, notification_type,
                    expires_at=expires_at,
                )
                if success:
                    notifications_sent += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке expiry rule {rule['id']} для sub {sub.get('id')}: {e}")

        if notifications_sent > 0:
            logger.info(f"Правило {rule['id']} (expiry_warning): отправлено {notifications_sent} уведомлений")

    async def _process_no_sub_rule(self, rule: dict, check_interval: int):
        """Обрабатывает правило типа no_subscription.

        trigger_hours положительное (напр. 168 = через 7 дней после потери подписки).
        Находим пользователей без активных подписок, ставших неактивными >= trigger_hours назад.
        Повторная отправка управляется repeat_every_hours / max_repeats.
        """
        now_ts = int(time.time())
        offset_seconds = rule['trigger_hours'] * 3600
        cutoff = now_ts - offset_seconds
        repeat_every = rule.get('repeat_every_hours', 0)
        max_repeats = rule.get('max_repeats', 1)

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT u.user_id,
                       COALESCE(MAX(s.expires_at), u.first_seen) AS became_inactive_at
                FROM users u
                LEFT JOIN subscriptions s
                    ON s.subscriber_id = u.id AND s.status != 'deleted'
                WHERE NOT EXISTS (
                    SELECT 1 FROM subscriptions s2
                    WHERE s2.subscriber_id = u.id
                      AND s2.status = 'active'
                      AND s2.expires_at > ?
                )
                GROUP BY u.id
                HAVING became_inactive_at <= ?
            ''', (now_ts, cutoff)) as cur:
                rows = await cur.fetchall()

        if not rows:
            return

        notification_type = f"rule_{rule['id']}"
        notifications_sent = 0

        for row in rows:
            try:
                user_id = row['user_id']
                if not await self._should_send(
                    user_id, 0, notification_type,
                    repeat_every, max_repeats, now_ts,
                ):
                    continue
                success = await self._send_rule_notification(
                    rule, user_id, 0, notification_type,
                )
                if success:
                    notifications_sent += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке no_sub rule {rule['id']} для user {row['user_id']}: {e}")

        if notifications_sent > 0:
            logger.info(f"Правило {rule['id']} (no_subscription): отправлено {notifications_sent} уведомлений")

    # ── repeat logic ──

    @staticmethod
    async def _should_send(
        user_id: str, subscription_id: int, notification_type: str,
        repeat_every_hours: int, max_repeats: int, now_ts: int,
    ) -> bool:
        """Определяет, нужно ли отправлять уведомление с учётом повторов."""
        count = await get_notification_send_count(user_id, subscription_id, notification_type)
        if count >= max_repeats:
            return False
        if count == 0:
            return True
        if repeat_every_hours <= 0:
            return False
        last_sent = await get_last_notification_send_time(user_id, subscription_id, notification_type)
        if last_sent is None:
            return True
        return (now_ts - last_sent) >= repeat_every_hours * 3600

    # ── sending ──

    @staticmethod
    def _render_template(template: str, *, expires_at: int = None) -> str:
        """Подставляет плейсхолдеры в шаблон сообщения (JSON или legacy)."""
        return render_structured_template(template, expires_at=expires_at)

    async def _send_rule_notification(
        self, rule: dict, user_id: str, subscription_id: int,
        notification_type: str, *, expires_at: int = None,
    ) -> bool:
        """Универсальная отправка уведомления по правилу."""
        try:
            from ..db.users_db import get_telegram_chat_id_for_notification
            chat_id = await get_telegram_chat_id_for_notification(user_id)
            if chat_id is None:
                return False

            message_text = self._render_template(rule['message_template'], expires_at=expires_at)

            from ..utils import UIButtons
            buttons = []
            if subscription_id:
                webapp_button = UIButtons.create_webapp_button(
                    action='extend_subscription',
                    params=subscription_id,
                    text="Открыть в приложении"
                )
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
                is_blocked = "Chat not found" in str(e) or isinstance(e, telegram.error.Forbidden)
                await record_notification_metrics(notification_type, False, is_blocked=is_blocked)
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
