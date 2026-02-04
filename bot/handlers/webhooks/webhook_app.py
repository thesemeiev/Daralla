"""
Flask приложение для обработки webhook'ов от YooKassa
"""
import logging
from flask import Flask

logger = logging.getLogger(__name__)


def create_webhook_app(bot_app, app_context):
    """Создаёт Flask-приложение для webhook'ов. app_context доступен в маршрутах через current_app.config['BOT_CONTEXT']."""
    app = Flask(__name__)
    app.config["BOT_CONTEXT"] = app_context
    from .routes import register_all_blueprints
    register_all_blueprints(app, bot_app)
    return app
