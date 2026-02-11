"""
Quart application for handling HTTP API and webhooks.

This is the async counterpart to `bot.handlers.webhooks.webhook_app.create_webhook_app`.
At this initial step it:
- creates a Quart app
- registers a simple `/health` endpoint
- optionally registers all existing blueprints if `bot_app` is provided
"""

import logging
import os

from quart import Quart, jsonify

logger = logging.getLogger(__name__)


def create_quart_app(bot_app=None) -> Quart:
    """
    Creates a Quart application for HTTP API and webhooks.

    Mirrors the signature of `create_webhook_app(bot_app)` so it can be
    gradually adopted without breaking existing call sites.
    """
    app = Quart(__name__)

    @app.route("/health", methods=["GET"])
    async def health() -> tuple[dict, int]:
        """Simple health-check endpoint for load balancers / monitors."""
        return {"status": "ok"}, 200

    # Optionally register all existing blueprints. Use skip_subscription=True
    # so the async subscription blueprint (subscription_quart) is used instead.
    if bot_app is not None:
        try:
            from bot.web.routes import create_subscription_blueprint
            from bot.web.routes.api_auth_quart import create_blueprint as create_api_auth_quart_blueprint
            from bot.web.routes.api_user_quart import create_blueprint as create_api_user_quart_blueprint
            from bot.web.routes.payment_quart import create_blueprint as create_payment_quart_blueprint
            from bot.web.routes.api_public_quart import create_blueprint as create_api_public_quart_blueprint
            from bot.web.routes.static_quart import bp as static_quart_bp
            from bot.web.routes.admin_check_quart import create_blueprint as create_admin_check_quart_blueprint
            from bot.web.routes.admin_users_quart import create_blueprint as create_admin_users_quart_blueprint
            from bot.web.routes.admin_subscriptions_quart import create_blueprint as create_admin_subscriptions_quart_blueprint
            from bot.web.routes.admin_stats_quart import create_blueprint as create_admin_stats_quart_blueprint
            from bot.web.routes.admin_charts_quart import create_blueprint as create_admin_charts_quart_blueprint
            from bot.web.routes.admin_broadcast_quart import create_blueprint as create_admin_broadcast_quart_blueprint
            from bot.web.routes.admin_servers_quart import create_blueprint as create_admin_servers_quart_blueprint
            from bot.handlers.webhooks.routes import register_all_blueprints

            app.register_blueprint(create_payment_quart_blueprint(bot_app))
            app.register_blueprint(create_subscription_blueprint(bot_app))
            app.register_blueprint(create_api_public_quart_blueprint(bot_app))
            app.register_blueprint(create_api_auth_quart_blueprint(bot_app))
            app.register_blueprint(create_api_user_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_check_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_users_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_subscriptions_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_stats_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_charts_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_broadcast_quart_blueprint(bot_app))
            app.register_blueprint(create_admin_servers_quart_blueprint(bot_app))
            register_all_blueprints(
                app, bot_app,
                skip_payment=True, skip_subscription=True, skip_api_public=True,
                skip_api_auth=True, skip_api_user=True,
                skip_api_admin=True, skip_static=True,
            )
            app.register_blueprint(static_quart_bp)
            logger.info(
                "Registered webhook blueprints on Quart app "
                "(payment, subscription, api_public, api_auth, api_user, admin*, static=async)"
            )
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("Failed to register blueprints on Quart app: %s", e, exc_info=True)

    return app


if __name__ == "__main__":
    # Local development entrypoint:
    #   python -m bot.web.app_quart
    # This runs Quart with no `bot_app` integration (only /health and static routes
    # that do not depend on bot state). In production, prefer an ASGI server.
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("PORT", "8080"))
    app = create_quart_app()
    app.run(host="0.0.0.0", port=port)

