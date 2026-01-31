"""
Вспомогательные функции
"""
import datetime
import logging

logger = logging.getLogger(__name__)


def calculate_time_remaining(expiry_timestamp, show_expired_as_negative=False):
    """
    Вычисляет оставшееся время до деактивации ключа
    """
    if not expiry_timestamp or expiry_timestamp == 0:
        return "—"
    
    try:
        # Конвертируем timestamp в datetime
        expiry_dt = datetime.datetime.fromtimestamp(expiry_timestamp)
        now = datetime.datetime.now()
        
        # Вычисляем разность
        time_diff = expiry_dt - now
        
        if time_diff.total_seconds() <= 0:
            if show_expired_as_negative:
                # Показываем, сколько времени прошло с момента истечения
                expired_diff = now - expiry_dt
                days = expired_diff.days
                hours, remainder = divmod(expired_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                time_parts = []
                if days > 0:
                    time_parts.append(f"{days} дн.")
                if hours > 0:
                    time_parts.append(f"{hours} ч.")
                if minutes > 0:
                    time_parts.append(f"{minutes} мин.")
                
                if not time_parts:
                    return "Только что истек"
                
                return f"Истек {time_parts[0]}" if len(time_parts) == 1 else f"Истек {' '.join(time_parts)}"
            else:
                return "Истек"
        
        # Извлекаем дни, часы и минуты
        days = time_diff.days
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        # Формируем строку
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} дн.")
        if hours > 0:
            time_parts.append(f"{hours} ч.")
        if minutes > 0:
            time_parts.append(f"{minutes} мин.")
        
        if not time_parts:
            return "Менее минуты"
        
        return " ".join(time_parts)
        
    except Exception as e:
        logger.error(f"Ошибка вычисления оставшегося времени: {e}")
        return "—"
