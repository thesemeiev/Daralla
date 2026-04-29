"""Platega integration configuration helpers."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


PLATEGA_BASE_URL = (os.getenv("PLATEGA_BASE_URL") or "https://api.platega.io").strip().rstrip("/")
PLATEGA_CREATE_PATH = (os.getenv("PLATEGA_CREATE_PATH") or "/transaction/process").strip()
if not PLATEGA_CREATE_PATH.startswith("/"):
    PLATEGA_CREATE_PATH = f"/{PLATEGA_CREATE_PATH}"

PLATEGA_MERCHANT_ID = (os.getenv("PLATEGA_MERCHANT_ID") or "").strip()
PLATEGA_SECRET = (os.getenv("PLATEGA_SECRET") or "").strip()
PLATEGA_CURRENCY = (os.getenv("PLATEGA_CURRENCY") or "RUB").strip().upper()
PLATEGA_PAYMENT_METHOD = _env_int("PLATEGA_PAYMENT_METHOD", 2)
PLATEGA_RETURN_URL = (os.getenv("PLATEGA_RETURN_URL") or "").strip()
PLATEGA_FAILED_URL = (os.getenv("PLATEGA_FAILED_URL") or "").strip()

