"""
Конфигурация модуля событий.
"""
import os

EVENTS_MODULE_ENABLED = os.environ.get("EVENTS_MODULE_ENABLED", "").strip().lower() in ("1", "true", "yes")
EVENTS_SUPPORT_URL = (os.environ.get("EVENTS_SUPPORT_URL") or os.environ.get("SUPPORT_URL") or "https://t.me/DarallaSupport").strip()
