"""
Менеджер для управления несколькими VPN серверами (конфигурация и отображение).
Подписки и выдача ключей — через Remnawave; X-UI панели не используются.
"""
import logging

logger = logging.getLogger(__name__)


class MultiServerManager:
    """Менеджер списка серверов по локациям (только конфиг и отображение, без X-UI)."""

    def __init__(self, servers_by_location=None):
        self.servers_by_location = {}
        self.server_health = {}
        self.servers = []
        if servers_by_location:
            self.init_from_config(servers_by_location)

    def init_from_config(self, servers_by_location):
        """Инициализирует серверы из переданной конфигурации (без подключения к X-UI)."""
        self.servers_by_location = {}
        self.servers = []
        for location, servers_config in servers_by_location.items():
            self.servers_by_location[location] = []
            for server_config in servers_config:
                server_info = {
                    "name": server_config["name"],
                    "x3": None,
                    "config": server_config,
                    "group_id": server_config.get("group_id"),
                }
                self.servers_by_location[location].append(server_info)
                self.servers.append(server_info)
                self.server_health[server_config["name"]] = {
                    "status": "unknown",
                    "last_check": None,
                    "last_error": None,
                    "consecutive_failures": 0,
                    "uptime_percentage": 0.0,
                }
                logger.info(
                    "Сервер %s (%s) добавлен (группа: %s)",
                    server_config["name"],
                    location,
                    server_config.get("group_id"),
                )

    def get_servers_by_group(self, group_id: int):
        """Возвращает список серверов группы."""
        if group_id is None:
            return self.servers
        return [s for s in self.servers if s.get("group_id") == group_id]

    def get_server_by_name(self, server_name):
        """Возвращает (None, имя) по имени — X-UI не используется."""
        for _location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return None, server["name"]
        raise Exception(f"Сервер {server_name} не найден")

    def get_server_config(self, server_name):
        """Возвращает конфигурацию сервера по имени."""
        for _location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return server.get("config", {})
        return {}

    def get_server_with_least_clients_in_location(self, location, group_id: int = None):
        """Без X-UI возвращает первый сервер в локации (нагрузка не учитывается)."""
        if location not in self.servers_by_location:
            raise Exception(f"Локация {location} не найдена")
        servers = self.servers_by_location[location]
        if group_id is not None:
            servers = [s for s in servers if s.get("group_id") == group_id]
        if not servers:
            raise Exception(f"Нет серверов в локации {location}" + (f" для группы {group_id}" if group_id else ""))
        first = servers[0]
        return None, first["name"]

    def get_server_by_user_choice(self, location, user_choice, group_id: int = None):
        """Возвращает сервер по выбору пользователя (без X-UI — по имени или первый в локации)."""
        if user_choice == "auto":
            return self.get_server_with_least_clients_in_location(location, group_id=group_id)
        return self.get_server_by_name(user_choice)

    def get_best_location_server(self, group_id: int = None):
        """Без X-UI возвращает (None, локация) — первый сервер из первой локации."""
        for location in self.servers_by_location:
            servers_in_loc = self.servers_by_location[location]
            if group_id is not None:
                servers_in_loc = [s for s in servers_in_loc if s.get("group_id") == group_id]
            if servers_in_loc:
                return None, location
        raise Exception("Нет доступных серверов")

    def find_client_on_any_server(self, user_email, group_id: int = None):
        """Без X-UI поиск клиента не выполняется."""
        return None, None

    def check_server_health(self, server_name, force_check=False):
        """Без X-UI проверка панели не выполняется — возвращаем True (unknown)."""
        if server_name not in self.server_health:
            return False
        self.server_health[server_name]["status"] = "unknown"
        return True

    def check_all_servers_health(self, force_check=False):
        """Помечает все серверы как unknown и возвращает True для каждого."""
        return {s["name"]: True for s in self.servers}

    def get_server_health_status(self):
        """Возвращает текущий словарь статусов (все unknown без X-UI)."""
        return self.server_health

    def get_healthy_servers(self):
        """Без X-UI возвращаем все серверы с unknown как «доступные» для отображения."""
        return [s for s in self.servers if self.server_health.get(s["name"], {}).get("status") != "offline"]
