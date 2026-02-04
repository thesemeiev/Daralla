"""
Blueprint: all /api/admin/* routes.
Тонкая обёртка над пакетом admin для сохранения импорта create_blueprint(bot_app).
"""
from .admin import create_blueprint
