"""
Утилиты для очистки extension_messages
"""
import time
import logging

logger = logging.getLogger(__name__)

# TTL для записей extension_messages (7 дней в секундах)
EXTENSION_MESSAGES_TTL = 7 * 24 * 60 * 60  # 604800 секунд


def cleanup_extension_messages(extension_messages_dict, payment_id=None):
    """
    Очищает extension_messages
    
    Args:
        extension_messages_dict: Словарь extension_messages
        payment_id: Если указан, удаляет только эту запись. Иначе удаляет все старые записи.
    """
    if payment_id:
        # Удаляем конкретную запись
        if payment_id in extension_messages_dict:
            del extension_messages_dict[payment_id]
            logger.debug(f"Удалена запись extension_messages для payment_id={payment_id}")
    else:
        # Удаляем все записи старше TTL
        current_time = time.time()
        to_remove = []
        
        for pid, data in extension_messages_dict.items():
            if isinstance(data, dict):
                timestamp = data.get('timestamp', 0)
                if current_time - timestamp > EXTENSION_MESSAGES_TTL:
                    to_remove.append(pid)
            else:
                # Старый формат (tuple) - удаляем сразу
                to_remove.append(pid)
        
        for pid in to_remove:
            del extension_messages_dict[pid]
        
        if to_remove:
            logger.info(f"Очищено {len(to_remove)} старых записей из extension_messages")

