"""Имена стабильных пакетов трафика группы (без зависимостей от шаблонов/квот)."""


def group_limited_bucket_stable_name(group_id: int) -> str:
    return f"group:{int(group_id)}:limited"
