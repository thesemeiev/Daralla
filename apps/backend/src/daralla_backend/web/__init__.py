"""
Quart-based web application for HTTP API and webhooks.
Экспортирует create_quart_app (payment, subscription, api_*, admin*, events, static).
"""

from .app_quart import create_quart_app

__all__ = ["create_quart_app"]

