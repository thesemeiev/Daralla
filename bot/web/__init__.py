"""
Quart-based web application for HTTP API and webhooks.

For now this package exposes only `create_quart_app`, which mirrors the
signature of `handlers.webhooks.create_webhook_app(bot_app)` but uses Quart
instead of Flask and adds an async `/health` endpoint.
"""

from .app_quart import create_quart_app

__all__ = ["create_quart_app"]

