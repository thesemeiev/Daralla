"""
Quart Blueprint: CRUD for notification rules + test send.
"""
import logging

import telegram
from quart import Blueprint, request, jsonify

from bot.services.admin_notifications_service import (
    create_rule,
    delete_rule,
    list_rules,
    notification_chat_id,
    render_test_message,
    update_rule,
    validate_event_type,
)
from bot.web.routes.admin_common import _cors_headers, admin_route

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_notifications", __name__)

    @bp.route("/api/admin/notification-rules", methods=["GET", "OPTIONS"])
    @admin_route
    async def api_list_rules(request, admin_id):
        rules = await list_rules()
        return jsonify({"rules": rules}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules", methods=["POST"])
    @admin_route
    async def api_create_rule(request, admin_id):
        data = await request.get_json(silent=True) or {}
        event_type = (data.get("event_type") or "").strip()
        trigger_hours = data.get("trigger_hours")
        message_template = (data.get("message_template") or "").strip()

        if not validate_event_type(event_type):
            return jsonify({"error": "Invalid event_type"}), 400, _cors_headers()
        if trigger_hours is None or not isinstance(trigger_hours, (int, float)):
            return jsonify({"error": "trigger_hours is required (integer)"}), 400, _cors_headers()
        if not message_template:
            return jsonify({"error": "message_template is required"}), 400, _cors_headers()

        trigger_hours = int(trigger_hours)
        if event_type == 'expiry_warning' and trigger_hours > 0:
            trigger_hours = -trigger_hours
        elif event_type == 'no_subscription' and trigger_hours < 0:
            trigger_hours = abs(trigger_hours)

        repeat_every_hours = int(data.get("repeat_every_hours") or 0)
        max_repeats = int(data.get("max_repeats") or 1)
        if repeat_every_hours < 0:
            repeat_every_hours = 0
        if max_repeats < 1:
            max_repeats = 1

        rule = await create_rule(
            event_type=event_type,
            trigger_hours=trigger_hours,
            message_template=message_template,
            repeat_every_hours=repeat_every_hours,
            max_repeats=max_repeats,
        )
        return jsonify({"rule": rule}), 201, _cors_headers()

    @bp.route("/api/admin/notification-rules/<int:rule_id>", methods=["PUT", "OPTIONS"])
    @admin_route
    async def api_update_rule(request, admin_id, rule_id):
        data = await request.get_json(silent=True) or {}
        fields = {}
        if "event_type" in data:
            et = (data["event_type"] or "").strip()
            if not validate_event_type(et):
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
        if "repeat_every_hours" in data:
            fields["repeat_every_hours"] = max(0, int(data["repeat_every_hours"] or 0))
        if "max_repeats" in data:
            fields["max_repeats"] = max(1, int(data["max_repeats"] or 1))

        if not fields:
            return jsonify({"error": "No fields to update"}), 400, _cors_headers()

        rule = await update_rule(rule_id, fields)
        if not rule:
            return jsonify({"error": "Rule not found"}), 404, _cors_headers()
        return jsonify({"rule": rule}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules/<int:rule_id>", methods=["DELETE"])
    @admin_route
    async def api_delete_rule(request, admin_id, rule_id):
        deleted = await delete_rule(rule_id)
        if not deleted:
            return jsonify({"error": "Rule not found"}), 404, _cors_headers()
        return jsonify({"ok": True}), 200, _cors_headers()

    @bp.route("/api/admin/notification-rules-test", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_test_send(request, admin_id):
        data = await request.get_json(silent=True) or {}
        raw_template = (data.get("message_template") or "").strip()
        if not raw_template:
            return jsonify({"error": "message_template is required"}), 400, _cors_headers()

        message_text = await render_test_message(raw_template)

        chat_id = await notification_chat_id(admin_id)
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
