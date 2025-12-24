"""
Утилиты для работы с временем в московском часовом поясе
"""
import datetime
import pytz


# Московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def get_moscow_time():
    """
    Возвращает текущее время в московском часовом поясе
    
    Returns:
        datetime.datetime: Текущее время в МСК
    """
    return datetime.datetime.now(MOSCOW_TZ)


def timestamp_to_moscow(timestamp):
    """
    Конвертирует Unix timestamp в datetime в московском часовом поясе
    
    Args:
        timestamp: Unix timestamp (int или float)
    
    Returns:
        datetime.datetime: Время в МСК
    """
    # Создаем UTC datetime из timestamp
    utc_dt = datetime.datetime.utcfromtimestamp(timestamp)
    utc_dt = pytz.utc.localize(utc_dt)
    # Конвертируем в московское время
    return utc_dt.astimezone(MOSCOW_TZ)


def format_datetime_moscow(dt, format_str='%d.%m.%Y %H:%M'):
    """
    Форматирует datetime в строку (предполагается, что dt уже в МСК)
    
    Args:
        dt: datetime объект
        format_str: Формат строки
    
    Returns:
        str: Отформатированная строка
    """
    if dt.tzinfo is None:
        # Если нет информации о часовом поясе, считаем что это UTC
        dt = pytz.utc.localize(dt)
        dt = dt.astimezone(MOSCOW_TZ)
    elif dt.tzinfo != MOSCOW_TZ:
        # Конвертируем в МСК если нужно
        dt = dt.astimezone(MOSCOW_TZ)
    
    return dt.strftime(format_str)


def format_timestamp_moscow(timestamp, format_str='%d.%m.%Y %H:%M'):
    """
    Форматирует Unix timestamp в строку в московском часовом поясе
    
    Args:
        timestamp: Unix timestamp (int или float)
        format_str: Формат строки
    
    Returns:
        str: Отформатированная строка в МСК
    """
    dt = timestamp_to_moscow(timestamp)
    return dt.strftime(format_str)

