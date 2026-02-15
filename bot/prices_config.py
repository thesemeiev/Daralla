"""
Единый источник цен на подписки.
Читает из переменных окружения PRICE_MONTH, PRICE_3MONTH (.env).
Используется в боте (уведомления, API) и доступен для веб-приложения.
"""
import os

PRICE_MONTH = int(os.getenv("PRICE_MONTH", "150"))
PRICE_3MONTH = int(os.getenv("PRICE_3MONTH", "350"))

PRICES = {
    "month": PRICE_MONTH,
    "3month": PRICE_3MONTH,
}
