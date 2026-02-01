"""
Конфигурация модуля событий.
"""
import os

EVENTS_MODULE_ENABLED = os.environ.get("EVENTS_MODULE_ENABLED", "").strip().lower() in ("1", "true", "yes")
