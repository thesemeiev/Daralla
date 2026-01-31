"""
Flask приложение для обработки webhook'ов от YooKassa
"""
import logging
from flask import Flask

logger = logging.getLogger(__name__)


def create_webhook_app(bot_app):
    """Создает Flask приложение для обработки webhook'ов от YooKassa"""
    app = Flask(__name__)
    from .routes import register_all_blueprints
    register_all_blueprints(app, bot_app)

    return app
