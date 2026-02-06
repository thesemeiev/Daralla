"""
Общие хелперы для админ-маршрутов: переходим на webhook_utils.
"""
from ...webhook_utils import handle_options

# Оставляем для обратной совместимости, но рекомендуем использовать webhook_utils
def options_response():
    """⚠️ DEPRECATED: используй handle_options() из webhook_utils вместо этого"""
    return handle_options()

