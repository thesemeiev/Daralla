"""
Сервис для предоставления конфигурации серверов из базы данных
"""
import logging
from typing import List, Dict, Any
from ..db.servers_db import get_servers_config

logger = logging.getLogger(__name__)

class ServerProvider:
    """Провайдер конфигурации серверов и групп из БД"""
    
    @staticmethod
    async def get_all_servers_by_group() -> Dict[int, List[Dict[str, Any]]]:
        """Возвращает все активные серверы, сгруппированные по group_id."""
        servers = await get_servers_config(only_active=True)
        
        result: Dict[int, List[Dict[str, Any]]] = {}
        for s in servers:
            gid = s["group_id"]
            if gid not in result:
                result[gid] = []
            
            cap = s.get("max_concurrent_clients")
            if cap is None: cap = 50
            try: cap = int(cap)
            except (TypeError, ValueError): cap = 50
            if cap <= 0: cap = 50
            
            result[gid].append({
                "name": s["name"],
                "display_name": s["display_name"],
                "map_label": (s.get("map_label") or "").strip() or None,
                "host": s["host"],
                "login": s["login"],
                "password": s["password"],
                "vpn_host": s["vpn_host"],
                "lat": s["lat"],
                "lng": s["lng"],
                "group_id": gid,
                "subscription_port": s.get("subscription_port", 2096),
                "subscription_url": s.get("subscription_url"),
                "client_flow": (s.get("client_flow") or "").strip() or None,
                "location": (s.get("location") or "").strip() or None,
                "max_concurrent_clients": cap
            })
            
        return result
