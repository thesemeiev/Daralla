"""Small helper utilities for api_user routes."""

from __future__ import annotations


def cryptocloud_extract_address(result):
    """Extract wallet address from CryptoCloud invoice payload."""
    if not isinstance(result, dict):
        return ""
    for key in ("address", "payment_address", "wallet_address", "crypto_address"):
        raw = result.get(key)
        if raw is not None and raw != "":
            if isinstance(raw, str):
                s = raw.strip()
                if s and s.lower() not in ("none", "null"):
                    return s
            else:
                return str(raw).strip()
    for nested_key in ("wallet", "payment", "deposit"):
        block = result.get(nested_key)
        if isinstance(block, dict):
            for key in ("address", "payment_address"):
                x = block.get(key)
                if x is not None and x != "":
                    if isinstance(x, str):
                        s = x.strip()
                        if s:
                            return s
                    else:
                        return str(x).strip()
    return ""


def normalize_map_lat_lng(lat, lng):
    """Return validated map coordinates as float tuple or (None, None)."""
    if lat is None or lng is None:
        return None, None
    if isinstance(lat, str) and not str(lat).strip():
        return None, None
    if isinstance(lng, str) and not str(lng).strip():
        return None, None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
        return None, None
    return lat_f, lng_f
