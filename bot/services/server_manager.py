"""
Менеджер для управления несколькими VPN серверами
"""
import logging
import datetime
import time
from .xui_service import X3

logger = logging.getLogger(__name__)

# Константы для кэширования и Circuit Breaker
HEALTH_CHECK_CACHE_TTL = 30  # Кэшируем результаты проверки на 30 секунд
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # После 3 неудач не проверяем сразу
CIRCUIT_BREAKER_COOLDOWN = 300  # 5 минут до следующей попытки после множественных неудач


class MultiServerManager:
    """Менеджер для управления несколькими VPN серверами по локациям"""
    
    def __init__(self, servers_by_location):
        self.servers_by_location = {}
        self.server_health = {}  # Словарь для отслеживания состояния серверов
        self.servers = []  # Плоский список всех серверов
        # Кэш для результатов проверки здоровья (Circuit Breaker pattern)
        self._health_check_cache = {}  # {server_name: {'result': bool, 'timestamp': float, 'cached': bool}}
        
        # Инициализируем серверы по локациям
        for location, servers_config in servers_by_location.items():
            self.servers_by_location[location] = []
            
            for server_config in servers_config:
                try:
                    # Создаем X3 объект (полностью ленивая инициализация - подключение при первом использовании)
                    x3_server = X3(
                        login=server_config["login"],
                        password=server_config["password"], 
                        host=server_config["host"],
                        vpn_host=server_config.get("vpn_host")  # IP/домен VPN сервера (если отличается от панели)
                    )
                    # Всегда добавляем сервер в список, подключение произойдет при первом использовании
                    server_info = {
                        "name": server_config["name"],
                        "x3": x3_server,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    # Инициализируем состояние сервера как "неизвестно" (будет проверено при первом использовании)
                    self.server_health[server_config["name"]] = {
                        "status": "unknown",
                        "last_check": None,
                        "last_error": None,
                        "consecutive_failures": 0,
                        "uptime_percentage": 0.0
                    }
                    logger.info(f"Сервер {server_config['name']} ({location}) добавлен (подключение при первом использовании)")
                except Exception as e:
                    # Если не удалось создать X3 объект (очень редкий случай)
                    logger.warning(f"Ошибка создания X3 объекта для {server_config['name']} ({location}): {e}")
                    server_info = {
                        "name": server_config["name"],
                        "x3": None,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    self.server_health[server_config["name"]] = {
                        "status": "offline",
                        "last_check": datetime.datetime.now(),
                        "last_error": str(e),
                        "consecutive_failures": 1,
                        "uptime_percentage": 0.0
                    }
    
    def get_server_by_name(self, server_name):
        """Возвращает конкретный сервер по имени"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return server["x3"], server["name"]
        raise Exception(f"Сервер {server_name} не найден или недоступен")
    
    def get_server_config(self, server_name):
        """Возвращает конфигурацию сервера по имени"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return server.get("config", {})
        return {}
    
    def get_server_with_least_clients_in_location(self, location):
        """Возвращает сервер с наименьшим количеством клиентов в конкретной локации"""
        if location not in self.servers_by_location:
            raise Exception(f"Локация {location} не найдена")
        
        servers = self.servers_by_location[location]
        if not servers:
            raise Exception(f"Нет доступных серверов в локации {location}")
        
        min_clients = float('inf')
        selected_server = None
        
        for server in servers:
            try:
                client_count = server["x3"].get_client_count()
                logger.info(f"Сервер {server['name']} ({location}): {client_count} клиентов")
                
                if client_count < min_clients:
                    min_clients = client_count
                    selected_server = server
            except Exception as e:
                logger.error(f"Ошибка при получении количества клиентов с сервера {server['name']} ({location}): {e}")
                continue
        
        if selected_server is None:
            # Если все серверы недоступны, используем первый
            selected_server = servers[0]
            logger.warning(f"Все серверы в локации {location} недоступны, использую {selected_server['name']}")
        
        logger.info(f"Выбран сервер {selected_server['name']} ({location}) с {min_clients} клиентами")
        logger.info(f"Reality настройки будут проверены для сервера: {selected_server['name']}")
        return selected_server["x3"], selected_server["name"]
    
    def get_server_by_user_choice(self, location, user_choice):
        """Возвращает сервер согласно выбору пользователя в конкретной локации"""
        if user_choice == "auto":
            return self.get_server_with_least_clients_in_location(location)
        else:
            return self.get_server_by_name(user_choice)
    
    def get_best_location_server(self):
        """Возвращает сервер с наименьшей нагрузкой из всех локаций
        
        Raises:
            Exception: Если нет доступных серверов в любой локации
        """
        best_server = None
        min_clients = float('inf')
        best_location = None
        
        for location, servers in self.servers_by_location.items():
            try:
                server, server_name = self.get_server_with_least_clients_in_location(location)
                # Проверяем, что сервер действительно доступен
                if server is None:
                    logger.warning(f"Сервер в локации {location} недоступен")
                    continue
                # Получаем количество клиентов для сравнения
                client_count = server.get_client_count()
                if client_count < min_clients:
                    min_clients = client_count
                    best_server = server
                    best_location = location
            except Exception as e:
                logger.error(f"Ошибка при получении сервера из локации {location}: {e}")
                continue
        
        if best_server is None:
            logger.error("Нет доступных серверов в любой локации")
            raise Exception("Нет доступных серверов в любой локации")
        
        logger.info(f"Выбрана лучшая локация: {best_location} с {min_clients} клиентами")
        return best_server, best_location
    
    def find_client_on_any_server(self, user_email):
        """Ищет клиента на любом из серверов"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                try:
                    if server["x3"] and server["x3"].client_exists(user_email):
                        logger.info(f"Клиент {user_email} найден на сервере {server['name']} ({location})")
                        return server["x3"], server["name"]
                except Exception as e:
                    logger.error(f"Ошибка при поиске клиента на сервере {server['name']} ({location}): {e}")
                    continue
        return None, None
    
    def check_server_health(self, server_name, force_check=False):
        """
        Проверяет здоровье конкретного сервера с кэшированием и Circuit Breaker
        
        Args:
            server_name: Имя сервера
            force_check: Если True, игнорирует кэш и Circuit Breaker (для принудительной проверки)
        
        Returns:
            bool: True если сервер доступен, False если недоступен
        """
        server_info = None
        for server in self.servers:
            if server["name"] == server_name:
                server_info = server
                break
        
        if not server_info:
            return False
        
        current_time = time.time()
        
        # Проверяем кэш (Circuit Breaker pattern)
        if not force_check and server_name in self._health_check_cache:
            cached_result = self._health_check_cache[server_name]
            cache_age = current_time - cached_result['timestamp']
            
            # Если результат кэширован и еще свежий, возвращаем его
            if cached_result.get('cached', False) and cache_age < HEALTH_CHECK_CACHE_TTL:
                return cached_result['result']
            
            # Circuit Breaker: если сервер был недоступен много раз подряд, не проверяем сразу
            health_status = self.server_health.get(server_name, {})
            consecutive_failures = health_status.get("consecutive_failures", 0)
            last_check_time = health_status.get("last_check")
            
            if consecutive_failures >= CIRCUIT_BREAKER_FAILURE_THRESHOLD and last_check_time:
                # Проверяем, прошло ли достаточно времени с последней проверки
                time_since_last_check = (datetime.datetime.now() - last_check_time).total_seconds()
                if time_since_last_check < CIRCUIT_BREAKER_COOLDOWN:
                    # Используем кэшированный результат, если он есть
                    if cached_result.get('cached', False):
                        logger.debug(f"Circuit Breaker активен для {server_name}, используем кэш (неудач: {consecutive_failures})")
                        return cached_result['result']
                    # Если кэша нет, возвращаем False без проверки
                    logger.debug(f"Circuit Breaker активен для {server_name}, пропускаем проверку (неудач: {consecutive_failures})")
                    return False
        
        # Выполняем реальную проверку
        try:
            if server_info["x3"] is None:
                # Пытаемся переподключиться только если не в режиме Circuit Breaker
                if not force_check:
                    health_status = self.server_health.get(server_name, {})
                    consecutive_failures = health_status.get("consecutive_failures", 0)
                    if consecutive_failures >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                        # Не пытаемся переподключаться, если Circuit Breaker активен
                        logger.debug(f"Circuit Breaker: пропускаем переподключение для {server_name}")
                        return False
                
                # Пытаемся переподключиться
                server_config = server_info["config"]
                server_info["x3"] = X3(
                    login=server_config["login"],
                    password=server_config["password"], 
                    host=server_config["host"]
                )
            
            # Проверяем доступность API (используем быструю проверку без retry)
            try:
                response = server_info["x3"].list_quick(timeout=5)  # Быстрая проверка без retry
            except Exception as quick_check_error:
                # Если быстрая проверка не удалась, это нормально - сервер недоступен
                raise quick_check_error
            
            if response and 'obj' in response:
                # Сервер доступен
                self.server_health[server_name]["status"] = "online"
                self.server_health[server_name]["last_check"] = datetime.datetime.now()
                self.server_health[server_name]["last_error"] = None
                self.server_health[server_name]["consecutive_failures"] = 0
                
                # Обновляем кэш
                self._health_check_cache[server_name] = {
                    'result': True,
                    'timestamp': current_time,
                    'cached': True
                }
                return True
            else:
                raise Exception("Неверный ответ от сервера")
                
        except Exception as e:
            # Сервер недоступен
            self.server_health[server_name]["status"] = "offline"
            self.server_health[server_name]["last_check"] = datetime.datetime.now()
            self.server_health[server_name]["last_error"] = str(e)
            self.server_health[server_name]["consecutive_failures"] += 1
            
            # Если сервер долго недоступен, помечаем X3 как None
            if self.server_health[server_name]["consecutive_failures"] > 3:
                server_info["x3"] = None
            
            # Обновляем кэш с отрицательным результатом
            self._health_check_cache[server_name] = {
                'result': False,
                'timestamp': current_time,
                'cached': True
            }
            
            logger.debug(f"Сервер {server_name} недоступен: {e} (неудач: {self.server_health[server_name]['consecutive_failures']})")
            return False
    
    def check_all_servers_health(self, force_check=False):
        """
        Проверяет здоровье всех серверов с кэшированием
        
        Args:
            force_check: Если True, игнорирует кэш (для принудительной проверки)
        
        Returns:
            dict: {server_name: bool} - результаты проверки
        """
        results = {}
        for server in self.servers:
            server_name = server["name"]
            results[server_name] = self.check_server_health(server_name, force_check=force_check)
        return results
    
    def get_server_health_status(self):
        """Возвращает статус здоровья всех серверов"""
        return self.server_health
    
    def get_healthy_servers(self):
        """Возвращает список доступных серверов"""
        healthy_servers = []
        for server in self.servers:
            if self.server_health[server["name"]]["status"] == "online":
                healthy_servers.append(server)
        return healthy_servers

