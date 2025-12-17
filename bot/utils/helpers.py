"""
Вспомогательные функции
"""
import datetime
import json
import logging
from .ui import UIEmojis, UIStyles

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


def format_vpn_key_message(email, status, server, expiry, key, expiry_timestamp=None):
    """
    Форматирует сообщение с информацией о VPN ключе
    """
    status_icon = UIEmojis.SUCCESS if status == "Активен" else UIEmojis.ERROR
    
    # Вычисляем оставшееся время
    time_remaining = calculate_time_remaining(expiry_timestamp) if expiry_timestamp else "—"
    
    message = (
        f"{UIStyles.header('Ваш VPN ключ')}\n\n"
        f"<b>Email:</b> <code>{email}</code>\n"
        f"<b>Статус:</b> {status_icon} {UIStyles.highlight(status)}\n"
        f"<b>Сервер:</b> {server}\n"
        f"<b>Осталось:</b> {time_remaining}\n\n"
        f"<code>{key}</code>\n"
        f"{UIStyles.description('Нажмите на ключ выше, чтобы скопировать')}"
    )
    
    return message


async def check_user_has_existing_keys(user_id: str, server_manager) -> bool:
    """
    Проверяет, есть ли у пользователя существующие ключи на серверах
    :param user_id: ID пользователя
    :param server_manager: Менеджер серверов
    :return: True если есть ключи, False если нет
    """
    try:
        logger.info(f"Проверка существующих ключей для пользователя {user_id}")
        
        # Сначала проверяем доступность серверов через кэш (1 попытка на сервер)
        server_health_cache = {}
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = server_manager.check_server_health(server_name, force_check=False)
            server_health_cache[server_name] = is_healthy
        
        for server in server_manager.servers:
            server_name = server['name']
            
            # Пропускаем недоступные серверы (проверено через кэш)
            if not server_health_cache.get(server_name, False):
                logger.debug(f"Сервер {server_name} недоступен (из кэша), пропускаем проверку")
                continue
            
            try:
                xui = server["x3"]
                if xui is None:
                    logger.warning(f"Сервер {server_name} недоступен, пропускаем проверку")
                    continue
                
                # Используем list_quick() для получения списка (1 попытка, без retry)
                # Доступность сервера уже проверена через кэш выше
                inbounds = xui.list_quick()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    
                    for client in clients:
                        email = client.get('email', '')
                        # Проверяем, принадлежит ли ключ этому пользователю
                        if email.startswith(f"{user_id}_") or email.startswith(f"trial_{user_id}_"):
                            logger.info(f"Найден существующий ключ для пользователя {user_id}: {email} на сервере {server_name}")
                            return True
                            
            except Exception as e:
                logger.error(f"Ошибка проверки ключей на сервере {server['name']}: {e}")
                continue
        
        logger.info(f"У пользователя {user_id} нет существующих ключей")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка проверки существующих ключей для пользователя {user_id}: {e}")
        return False

