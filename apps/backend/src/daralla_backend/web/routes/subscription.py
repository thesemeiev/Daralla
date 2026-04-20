"""
Quart Blueprint: GET /sub/<token> (subscription VLESS links).
Async implementation — no asyncio.new_event_loop / run_until_complete.
"""
from quart import Blueprint, request

from bot.services.subscription_route_service import handle_subscription_request


def create_subscription_blueprint(bot_app):
    bp = Blueprint("subscription", __name__)

    @bp.route("/sub/<token>", methods=["GET", "OPTIONS"])
    async def subscription(token):
        body, status, headers = await handle_subscription_request(
            token=token,
            method=request.method,
            headers=dict(request.headers),
        )
        if headers is None:
            return body, status
        return body, status, headers

    return bp
