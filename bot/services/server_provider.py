"""
Сервис для предоставления конфигурации серверов из базы данных
"""
import logging
from typing import List, Dict, Any
from ..db.subscribers_db import get_server_groups, get_servers_config

logger = logging.getLogger(__name__)

class ServerProvider:
    """Провайдер конфигурации серверов и групп из БД"""
    
    @staticmethod
    async def get_all_servers_by_location() -> Dict[str, List[Dict[str, Any]]]:
        """
        Возвращает все серверы, сгруппированные по локациям (для обратной совместимости)
        В новой модели локации могут быть частью display_name или отдельным полем, 
        но пока мы используем старый формат для MultiServerManager.
        """
        servers = await get_servers_config(only_active=True)
        
        # Для обратной совместимости мы можем попытаться извлечь локацию из имени или display_name,
        # либо просто вернуть плоский список под ключом "All"
        # Но лучше всего сгруппировать по тому, как это было раньше.
        # Поскольку в новой базе нет поля location, мы будем использовать "Default" 
        # или извлекать из display_name (например "🇵🇱 Poland - 1" -> "Poland")
        
        result = {}
        for s in servers:
            # Пытаемся определить локацию
            location = "Other"
            display_name = s.get("display_name", "")
            if "Poland" in display_name: location = "Poland"
            elif "Netherlands" in display_name: location = "Netherlands"
            elif "Russia" in display_name: location = "Russia"
            elif "Latvia" in display_name: location = "Latvia"
            
            if location not in result:
                result[location] = []
            
            # Приводим к формату, который ожидает MultiServerManager
            result[location].append({
                "name": s["name"],
                "display_name": s["display_name"],
                "host": s["host"],
                "login": s["login"],
                "password": s["password"],
                "vpn_host": s["vpn_host"],
                "lat": s["lat"],
                "lng": s["lng"],
                "group_id": s["group_id"]
            })
            
        return result

    @staticmethod
    async def get_servers_for_group(group_id: int) -> List[Dict[str, Any]]:
        """Возвращает список серверов для конкретной группы"""
        servers = await get_servers_config(group_id=group_id, only_active=True)
        return servers

    @staticmethod
    async def get_group_load_stats() -> List[Dict[str, Any]]:
        """Возвращает статистику загрузки по группам"""
        groups = await get_server_groups(only_active=False)
        # Здесь можно добавить логику подсчета подписок на группу
        return groups

