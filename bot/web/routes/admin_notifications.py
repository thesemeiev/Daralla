"""
Quart Blueprint: CRUD for notification rules + test send.
"""
import logging

import telegram
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db.notifications_db import (
    get_all_notification_rules,
    create_notification_rule,
    update_notification_rule,
    delete_notification_rule,
    get_notification_rule_by_id,
    render_structured_template,
)
from bot.db.users_db import get_telegram_chat_id_for_notification

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = {'expiry_warning', 'no_subscription'}


def create_blueprint(bot_app):
    bp = Blueprint("admin_notifications", __name__)

    @bp.route("/api/admin/notification-rules", methods=["GET", "OPTIONS"])
    @admin_route
    async def api_list_rules(request, admin_id):
        rules = await get_all_notification_rules()
        return jsonify({"rules": rules}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules", methods=["POST"])
    @admin_route
    async def api_create_rule(request, admin_id):
        data = await request.get_json(silent=True) or {}
        event_type = (data.get("event_type") or "").strip()
        trigger_hours = data.get("trigger_hours")
        message_template = (data.get("message_template") or "").strip()

        if event_type not in VALID_EVENT_TYPES:
            return jsonify({"error": "Invalid event_type"}), 400, _cors_headers()
        if trigger_hours is None or not isinstance(trigger_hours, (int, float)):
            return jsonify({"error": "trigger_hours is required (integer)"}), 400, _cors_headers()
        if not message_template:
            return jsonify({"error": "message_template is required"}), 400, _cors_headers()

        rule_id = await create_notification_rule(event_type, int(trigger_hours), message_template)
        rule = await get_notification_rule_by_id(rule_id)
        return jsonify({"rule": rule}), 201, _cors_headers()

    @bp.route("/api/admin/notification-rules/<int:rule_id>", methods=["PUT", "OPTIONS"])
    @admin_route
    async def api_update_rule(request, admin_id, rule_id):
        existing = await get_notification_rule_by_id(rule_id)
        if not existing:
            return jsonify({"error": "Rule not found"}), 404, _cors_headers()

        data = await request.get_json(silent=True) or {}
        fields = {}
        if "event_type" in data:
            et = (data["event_type"] or "").strip()
            if et not in VALID_EVENT_TYPES:
                return jsonify({"error": "Invalid event_type"}), 400, _cors_headers()
            fields["event_type"] = et
        if "trigger_hours" in data:
            fields["trigger_hours"] = int(data["trigger_hours"])
        if "message_template" in data:
            tpl = (data["message_template"] or "").strip()
            if not tpl:
                return jsonify({"error": "message_template cannot be empty"}), 400, _cors_headers()
            fields["message_template"] = tpl
        if "is_active" in data:
            fields["is_active"] = 1 if data["is_active"] else 0

        if not fields:
            return jsonify({"error": "No fields to update"}), 400, _cors_headers()

        await update_notification_rule(rule_id, **fields)
        rule = await get_notification_rule_by_id(rule_id)
        return jsonify({"rule": rule}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules/<int:rule_id>", methods=["DELETE"])
    @admin_route
    async def api_delete_rule(request, admin_id, rule_id):
        deleted = await delete_notification_rule(rule_id)
        if not deleted:
            return jsonify({"error": "Rule not found"}), 404, _cors_headers()
        return jsonify({"ok": True}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules/test", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_test_send(request, admin_id):
        data = await request.get_json(silent=True) or {}
        raw_template = (data.get("message_template") or "").strip()
        if not raw_template:
            return jsonify({"error": "message_template is required"}), 400, _cors_headers()

        import time
        sample_expiry = int(time.time()) + 3 * 86400
        message_text = render_structured_template(raw_template, expires_at=sample_expiry)

        chat_id = await get_telegram_chat_id_for_notification(admin_id)
        if not chat_id:
            return jsonify({"error": "Не удалось найти ваш Telegram chat_id"}), 400, _cors_headers()

        try:
            bot = bot_app.bot
            await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="HTML")
            return jsonify({"ok": True}), 200, _cors_headers()
        except telegram.error.TelegramError as e:
            logger.error("Test send failed for admin %s: %s", admin_id, e)
            return jsonify({"error": f"Telegram error: {e}"}), 500, _cors_headers()

    return bp
