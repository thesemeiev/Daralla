"""
Scope инбаундов на X-UI панели: какими inbound'ами управляет бот для сервера.

managed_inbound_ids пусто/null — legacy: все инбаунды (как раньше).
Задан список — ensure/cleanup/strict sync только в этих inbound'ах.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator, Optional, Set, Tuple


def parse_managed_inbound_ids(raw: Any) -> Optional[Set[int]]:
    """None = все инбаунды; иначе множество положительных id."""
    if raw is None:
        return None
    if isinstance(raw, set):
        ids = {int(x) for x in raw if _positive_int(x) is not None}
        return ids or None
    if isinstance(raw, (list, tuple)):
        ids: Set[int] = set()
        for x in raw:
            v = _positive_int(x)
            if v is not None:
                ids.add(v)
        return ids or None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if s.startswith("["):
            try:
                return parse_managed_inbound_ids(json.loads(s))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        ids = set()
        for part in s.replace(";", ",").split(","):
            v = _positive_int(part.strip())
            if v is not None:
                ids.add(v)
        return ids or None
    return None


def _positive_int(value: Any) -> Optional[int]:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def serialize_managed_inbound_ids(ids: Optional[Iterable[int]]) -> Optional[str]:
    parsed = parse_managed_inbound_ids(list(ids) if ids is not None else None)
    if parsed is None:
        return None
    return json.dumps(sorted(parsed))


def normalize_managed_inbound_ids_for_storage(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns:
        (stored_json_or_none, error_message)
    """
    if value is None:
        return None, None
    if isinstance(value, str) and not value.strip():
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return None, None

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                return None, "managed_inbound_ids: invalid JSON array"

    parsed = parse_managed_inbound_ids(value)
    if parsed is None:
        if value in (None, "", [], ()):
            return None, None
        return None, "managed_inbound_ids must be comma-separated positive integers"
    return serialize_managed_inbound_ids(parsed), None


def inbound_in_scope(inbound_id: Any, managed: Optional[Set[int]]) -> bool:
    if managed is None:
        return True
    v = _positive_int(inbound_id)
    return v is not None and v in managed


def primary_managed_inbound_id(managed: Optional[Set[int]]) -> Optional[int]:
    if not managed:
        return None
    return min(managed)


def iter_scoped_inbounds(
    inbounds: Iterable[dict], managed: Optional[Set[int]]
) -> Iterator[dict]:
    for inv in inbounds or []:
        if inbound_in_scope(inv.get("id"), managed):
            yield inv
