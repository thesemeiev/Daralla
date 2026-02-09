"""Unit tests for Telegram initData verification (webhook_auth.verify_telegram_init_data)."""
import hmac
import hashlib
import json
import os
import time
import urllib.parse

import pytest

from bot.handlers.webhooks.webhook_auth import verify_telegram_init_data


def _build_valid_init_data(telegram_user_id: int, auth_date: int = None) -> str:
    """Build init_data string with valid HMAC for TELEGRAM_TOKEN from env."""
    token = os.environ.get("TELEGRAM_TOKEN", "test_token")
    if auth_date is None:
        auth_date = int(time.time())
    user_json = json.dumps({"id": telegram_user_id})
    parsed = {"auth_date": [str(auth_date)], "user": [user_json]}
    data_check_string_parts = [f"{k}={parsed[k][0]}" for k in sorted(parsed.keys())]
    data_check_string = "\n".join(data_check_string_parts)
    secret_key = hmac.new(
        b"WebAppData",
        token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    parsed["hash"] = [calculated_hash]
    return "&".join(f"{k}={urllib.parse.quote(parsed[k][0])}" for k in sorted(parsed.keys()))


def test_verify_telegram_init_data_valid():
    """Valid init_data with correct HMAC returns telegram user id as string."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    init_data = _build_valid_init_data(123)
    assert verify_telegram_init_data(init_data) == "123"


def test_verify_telegram_init_data_invalid_hash():
    """Init_data with wrong hash returns None."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    init_data = _build_valid_init_data(456)
    # Corrupt hash: replace last character
    init_data = init_data[:-1] + ("0" if init_data[-1] != "0" else "1")
    assert verify_telegram_init_data(init_data) is None


def test_verify_telegram_init_data_expired_auth_date():
    """Init_data with auth_date older than 24 hours returns None."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    auth_date = int(time.time()) - (25 * 60 * 60)
    init_data = _build_valid_init_data(789, auth_date=auth_date)
    assert verify_telegram_init_data(init_data) is None


def test_verify_telegram_init_data_missing_hash():
    """Init_data without hash returns None."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    init_data = "auth_date=1234567890&user=%7B%22id%22%3A%20123%7D"
    assert verify_telegram_init_data(init_data) is None


def test_verify_telegram_init_data_missing_auth_date():
    """Init_data without auth_date returns None."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    user_obj = {"id": 123}
    # Build with hash but no auth_date
    parsed = {"user": [json.dumps(user_obj)]}
    token = os.environ.get("TELEGRAM_TOKEN", "test_token")
    data_check_string = "\n".join(f"{k}={parsed[k][0]}" for k in sorted(parsed.keys()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    init_data = f"user={urllib.parse.quote(parsed['user'][0])}&hash={calculated_hash}"
    assert verify_telegram_init_data(init_data) is None


def test_verify_telegram_init_data_missing_user():
    """Init_data without user returns None."""
    os.environ["TELEGRAM_TOKEN"] = "test_token"
    auth_date = int(time.time())
    parsed = {"auth_date": [str(auth_date)]}
    token = os.environ.get("TELEGRAM_TOKEN", "test_token")
    data_check_string = "\n".join(f"{k}={parsed[k][0]}" for k in sorted(parsed.keys()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    init_data = f"auth_date={auth_date}&hash={calculated_hash}"
    assert verify_telegram_init_data(init_data) is None
