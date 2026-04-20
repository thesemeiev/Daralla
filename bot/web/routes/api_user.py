"""
Quart Blueprint: /api/user/* and /api/subscriptions.
Async implementation — no asyncio.new_event_loop / run_until_complete.
"""
import logging
from quart import Blueprint
from bot.web.routes.api_user_account import (
    handle_api_user_avatar,
    handle_api_user_change_login,
    handle_api_user_change_password,
    handle_api_user_link_status,
    handle_api_user_link_telegram_start,
    handle_api_user_unlink_telegram,
    handle_api_user_web_access_setup,
)
from bot.web.routes.api_user_payments import (
    handle_api_user_payment_create,
    handle_api_user_payment_status,
)
from bot.web.routes.api_user_registration import handle_api_user_register
from bot.web.routes.api_user_subscriptions import (
    handle_api_subscriptions,
    handle_api_user_server_usage,
    handle_api_user_subscription_rename,
)
from bot.web.routes.api_user_common import auth_user_from_request

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("api_user", __name__)

    async def _auth():
        return await auth_user_from_request()

    @bp.route("/api/user/register", methods=["POST", "OPTIONS"])
    async def api_user_register():
        return await handle_api_user_register(_auth, logger)

    @bp.route("/api/subscriptions", methods=["GET", "OPTIONS"])
    async def api_subscriptions():
        return await handle_api_subscriptions(_auth, logger)

    @bp.route("/api/user/payment/create", methods=["POST", "OPTIONS"])
    async def api_user_payment_create():
        return await handle_api_user_payment_create(_auth, logger)

    @bp.route("/api/user/payment/status/<payment_id>", methods=["GET", "OPTIONS"])
    async def api_user_payment_status(payment_id):
        return await handle_api_user_payment_status(_auth, payment_id, logger)

    @bp.route("/api/user/subscription/<int:sub_id>/rename", methods=["POST", "OPTIONS"])
    async def api_user_subscription_rename(sub_id):
        return await handle_api_user_subscription_rename(_auth, sub_id, logger)

    @bp.route("/api/user/server-usage", methods=["GET", "OPTIONS"])
    async def api_user_server_usage():
        return await handle_api_user_server_usage(_auth, logger)

    @bp.route("/api/user/web-access/setup", methods=["POST", "OPTIONS"])
    async def api_user_web_access_setup():
        return await handle_api_user_web_access_setup(logger)

    @bp.route("/api/user/link-telegram/start", methods=["POST", "OPTIONS"])
    async def api_user_link_telegram_start():
        return await handle_api_user_link_telegram_start(_auth, logger)

    @bp.route("/api/user/link-status", methods=["GET", "OPTIONS"])
    async def api_user_link_status():
        return await handle_api_user_link_status(_auth, logger)

    @bp.route("/api/user/avatar", methods=["GET", "OPTIONS"])
    async def api_user_avatar():
        return await handle_api_user_avatar(_auth, logger)

    @bp.route("/api/user/change-password", methods=["POST", "OPTIONS"])
    async def api_user_change_password():
        return await handle_api_user_change_password(_auth, logger)

    @bp.route("/api/user/change-login", methods=["POST", "OPTIONS"])
    async def api_user_change_login():
        return await handle_api_user_change_login(_auth, logger)

    @bp.route("/api/user/unlink-telegram", methods=["POST", "OPTIONS"])
    async def api_user_unlink_telegram():
        return await handle_api_user_unlink_telegram(_auth, logger)

    return bp
