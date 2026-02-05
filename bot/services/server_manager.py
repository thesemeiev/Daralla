"""
Кэш маркеров на карте (данные из ServerProvider).
Используется API: /api/servers, /api/user/server-usage.
"""
import logging

logger = logging.getLogger(__name__)


class MultiServerManager:
    """Кэш маркеров на карте (название + положение)."""

    def __init__(self, servers_by_location=None):
        self.servers_by_location = {}
        self.servers = []
        if servers_by_location:
            self.init_from_config(servers_by_location)

    def init_from_config(self, servers_by_location):
        """Обновляет кэш из конфигурации (ServerProvider.get_all_servers_by_location)."""
        self.servers_by_location = {}
        self.servers = []
        for location, servers_config in servers_by_location.items():
            self.servers_by_location[location] = []
            for server_config in servers_config:
                server_info = {
                    "name": server_config["name"],
                    "config": server_config,
                }
                self.servers_by_location[location].append(server_info)
                self.servers.append(server_info)
        logger.debug("Маркеры на карте обновлены: %d", len(self.servers))
