"""
Поле client_flow в конфиге сервера (БД бота / админка) — значение поля flow у клиентов на панели
3x-ui (например ``xtls-rprx-vision`` для VLESS). Пустое в БД — сброс flow на клиентах.

Какой inbound/протокол на сервере — решаете вы; бот не отделяет trojan от остальных для этого поля.

Синхронизация на ноды: при сохранении сервера в админке запускается фоновый sync по всем
клиентам панели; регулярный reconcile подписок тоже выравнивает flow с этим полем.
"""

from __future__ import annotations

from typing import Any, FrozenSet, Optional, Tuple

ALLOWED_CLIENT_FLOW_VALUES: FrozenSet[str] = frozenset(
    {
        "xtls-rprx-vision",
    }
)


def normalize_client_flow_for_storage(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Приводит значение из запроса к тому, что пишем в БД.

    Returns:
        (stored_value, error_message). stored_value None — flow выключен.
        error_message — текст для JSON error (400), если значение недопустимо.
    """
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "client_flow must be a string or null"
    s = value.strip()
    if not s:
        return None, None
    if s in ALLOWED_CLIENT_FLOW_VALUES:
        return s, None
    return None, "client_flow must be null, empty, or xtls-rprx-vision"
