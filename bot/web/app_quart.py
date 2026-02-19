"""
Quart application for HTTP API and webhooks (заменяет прежнее Flask webhook app).
Создаёт Quart app, /health и регистрирует все blueprints (payment, subscription, api_*, admin*, events*, static).
"""

import logging
import os

from quart import Quart, jsonify

logger = logging.getLogger(__name__)


def create_quart_app(bot_app=None) -> Quart:
    """Создаёт Quart-приложение для HTTP API и webhook'ов (payment, subscription, api, admin, events, static)."""
    app = Quart(__name__)

    @app.route("/health", methods=["GET"])
    async def health() -> tuple[dict, int]:
        """Simple health-check endpoint for load balancers / monitors."""
        return {"status": "ok"}, 200

    # Optionally register all existing blueprints. Use skip_subscription=True
    # so the async subscription blueprint (subscription) is used instead.
    if bot_app is not None:
        try:
            from bot.web.routes import create_subscription_blueprint
            from bot.web.routes.api_auth import create_blueprint as create_api_auth_blueprint
            from bot.web.routes.api_user import create_blueprint as create_api_user_blueprint
            from bot.web.routes.payment import create_blueprint as create_payment_blueprint
            from bot.web.routes.api_public import create_blueprint as create_api_public_blueprint
            from bot.web.routes.static import bp as static_bp
            from bot.web.routes.admin_check import create_blueprint as create_admin_check_blueprint
            from bot.web.routes.admin_users import create_blueprint as create_admin_users_blueprint
            from bot.web.routes.admin_subscriptions import create_blueprint as create_admin_subscriptions_blueprint
            from bot.web.routes.admin_stats import create_blueprint as create_admin_stats_blueprint
            from bot.web.routes.admin_charts import create_blueprint as create_admin_charts_blueprint
            from bot.web.routes.admin_broadcast import create_blueprint as create_admin_broadcast_blueprint
            from bot.web.routes.admin_servers import create_blueprint as create_admin_servers_blueprint
            from bot.web.routes.admin_notifications import create_blueprint as create_admin_notifications_blueprint

            app.register_blueprint(create_payment_blueprint(bot_app))
            try:
                from bot.events import EVENTS_MODULE_ENABLED
                if EVENTS_MODULE_ENABLED:
                    from bot.web.routes.events import create_blueprint as create_events_blueprint
                    app.register_blueprint(create_events_blueprint())
            except ImportError:
                pass
            app.register_blueprint(create_subscription_blueprint(bot_app))
            app.register_blueprint(create_api_public_blueprint(bot_app))
            app.register_blueprint(create_api_auth_blueprint(bot_app))
            app.register_blueprint(create_api_user_blueprint(bot_app))
            app.register_blueprint(create_admin_check_blueprint(bot_app))
            app.register_blueprint(create_admin_users_blueprint(bot_app))
            app.register_blueprint(create_admin_subscriptions_blueprint(bot_app))
            app.register_blueprint(create_admin_stats_blueprint(bot_app))
            app.register_blueprint(create_admin_charts_blueprint(bot_app))
            app.register_blueprint(create_admin_broadcast_blueprint(bot_app))
            app.register_blueprint(create_admin_servers_blueprint(bot_app))
            app.register_blueprint(create_admin_notifications_blueprint(bot_app))
            app.register_blueprint(static_bp)
            logger.info(
                "Registered webhook blueprints on Quart app "
                "(payment, subscription, api_public, api_auth, api_user, admin*, events*, static=async)"
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

