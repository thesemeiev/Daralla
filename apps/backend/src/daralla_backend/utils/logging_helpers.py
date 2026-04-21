"""Shared helpers for consistent and safe logging."""

from __future__ import annotations

import json
import logging
from typing import Mapping


_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "token",
    "secret",
    "password",
}


def mask_secret(value: object, *, keep_start: int = 4, keep_end: int = 2) -> str:
    """Mask sensitive values while preserving small prefix/suffix for debugging."""
    if value is None:
        return ""
    raw = str(value)
    if not raw:
        return ""
    if len(raw) <= keep_start + keep_end + 1:
        return "*" * len(raw)
    return f"{raw[:keep_start]}***{raw[-keep_end:]}"


def sanitize_headers(headers: Mapping[str, object] | None) -> dict[str, str]:
    """Return headers suitable for logs: sensitive keys are masked."""
    if not headers:
        return {}
    clean: dict[str, str] = {}
    for key, value in headers.items():
        key_str = str(key)
        key_lower = key_str.lower()
        if key_lower in _SENSITIVE_KEYS:
            clean[key_str] = mask_secret(value)
        else:
            clean[key_str] = str(value)
    return clean


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    """
    Emit structured one-line JSON log with a stable schema.

    The resulting payload always contains:
      - event: event name
      - additional key/value fields passed in **fields
    """
    payload = {"event": event, **fields}
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
