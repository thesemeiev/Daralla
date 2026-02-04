"""
Фундамент: конфигурация из env и пути приложения.
Не импортирует domain или application (db, services, handlers).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта (Daralla), затем data и логи
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)

# Пути
PROJECT_ROOT = _PROJECT_ROOT
DATA_DIR = _PROJECT_ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"
APP_LOG_PATH = LOGS_DIR / "bot.log"

# --- Env ---
def _str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _int_list(key: str, default: list[int] | None = None) -> list[int]:
    s = _str(key)
    if not s:
        return default or []
    return [int(x.strip()) for x in s.split(",") if x.strip()]


# Обязательные
TELEGRAM_TOKEN = _str("TELEGRAM_TOKEN")
ADMIN_IDS = _int_list("ADMIN_ID") or _int_list("ADMIN_IDS")

# YooKassa
YOOKASSA_SHOP_ID = _str("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = _str("YOOKASSA_SECRET_KEY")

# Webhook / Mini App
WEBHOOK_URL = _str("WEBHOOK_URL")
SUBSCRIPTION_URL = _str("SUBSCRIPTION_URL")  # опционально, иначе используется WEBHOOK_URL
if WEBHOOK_URL and "/webhook/" in WEBHOOK_URL:
    WEBAPP_URL = WEBHOOK_URL.split("/webhook/")[0].rstrip("/") + "/"
elif WEBHOOK_URL:
    WEBAPP_URL = WEBHOOK_URL.rstrip("/") + "/"
else:
    WEBAPP_URL = None

# Изображения меню
IMAGE_PATHS = {
    "main_menu": "images/main_menu.jpg",
    "payment_success": "images/payment_success.jpg",
    "payment_failed": "images/payment_failed.jpg",
}

# Бренд VPN
VPN_BRAND_NAME = " Daralla VPN"

# Remnawave (опционально; если заданы — подписки через Remnawave)
REMNAWAVE_BASE_URL = _str("REMNAWAVE_BASE_URL")
REMNAWAVE_ADMIN_USERNAME = _str("REMNAWAVE_ADMIN_USERNAME")
REMNAWAVE_ADMIN_PASSWORD = _str("REMNAWAVE_ADMIN_PASSWORD")


def validate_required() -> None:
    """Проверка обязательных переменных. Вызывать при старте."""
    if not TELEGRAM_TOKEN:
        raise ValueError(
            "TELEGRAM_TOKEN не найден в переменных окружения. "
            "Проверьте .env или переменные окружения."
        )


def ensure_dirs() -> None:
    """Создаёт data и logs при первом обращении."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
