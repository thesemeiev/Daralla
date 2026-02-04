"""
Сервис для предоставления конфигурации серверов из базы данных
"""
import logging
from typing import List, Dict, Any
from ..db import get_server_groups, get_servers_config

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
            # Локация: из настроек сервера (админка), иначе Other
            location = (s.get("location") or "").strip() or "Other"
            
            if location not in result:
                result[location] = []
            
            cap = s.get("max_concurrent_clients")
            if cap is None: cap = 50
            try: cap = int(cap)
            except (TypeError, ValueError): cap = 50
            if cap <= 0: cap = 50
            
            # Приводим к формату, который ожидает MultiServerManager (config попадает в server["config"])
            result[location].append({
                "name": s["name"],
                "display_name": s["display_name"],
                "map_label": (s.get("map_label") or "").strip() or None,
                "host": s["host"],
                "login": s["login"],
                "password": s["password"],
                "vpn_host": s["vpn_host"],
                "lat": s["lat"],
                "lng": s["lng"],
                "group_id": s["group_id"],
                "subscription_port": s.get("subscription_port", 2096),
                "subscription_url": s.get("subscription_url"),
                "client_flow": (s.get("client_flow") or "").strip() or None,
                "location": location,
                "max_concurrent_clients": cap
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

