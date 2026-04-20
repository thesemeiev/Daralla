"""Service layer for admin notification rules routes."""

from __future__ import annotations

import time

from bot.db.notifications_db import (
    create_notification_rule,
    delete_notification_rule,
    get_all_notification_rules,
    get_notification_rule_by_id,
    render_structured_template,
    update_notification_rule,
)
from bot.db.users_db import get_telegram_chat_id_for_notification

VALID_EVENT_TYPES = {"expiry_warning", "no_subscription"}


def validate_event_type(event_type: str) -> bool:
    return event_type in VALID_EVENT_TYPES


def normalize_trigger_hours(event_type: str, trigger_hours: int) -> int:
    if event_type == "expiry_warning" and trigger_hours > 0:
        return -trigger_hours
    if event_type == "no_subscription" and trigger_hours < 0:
        return abs(trigger_hours)
    return trigger_hours


async def list_rules():
    return await get_all_notification_rules()


async def create_rule(event_type: str, trigger_hours: int, message_template: str, repeat_every_hours: int, max_repeats: int):
    trigger_hours = normalize_trigger_hours(event_type, trigger_hours)
    rule_id = await create_notification_rule(
        event_type,
        trigger_hours,
        message_template,
        repeat_every_hours=repeat_every_hours,
        max_repeats=max_repeats,
    )
    return await get_notification_rule_by_id(rule_id)


async def update_rule(rule_id: int, fields: dict):
    existing = await get_notification_rule_by_id(rule_id)
    if not existing:
        return None
    et = fields.get("event_type", existing["event_type"])
    if "trigger_hours" in fields:
        fields["trigger_hours"] = normalize_trigger_hours(et, fields["trigger_hours"])
    await update_notification_rule(rule_id, **fields)
    return await get_notification_rule_by_id(rule_id)


async def delete_rule(rule_id: int) -> bool:
    return await delete_notification_rule(rule_id)


async def render_test_message(raw_template: str):
    sample_expiry = int(time.time()) + 3 * 86400
    return render_structured_template(raw_template, expires_at=sample_expiry)


async def notification_chat_id(user_id: str):
    return await get_telegram_chat_id_for_notification(user_id)
