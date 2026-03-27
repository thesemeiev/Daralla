"""
Менеджер для управления несколькими VPN серверами
"""
import asyncio
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
    """Менеджер для управления несколькими VPN серверами, сгруппированными по group_id"""
    
    def __init__(self, servers_by_group=None):
        self.servers_by_group = {}   # {group_id: [server_info, ...]}
        self.server_health = {}
        self.servers = []            # Плоский список всех серверов
        self._health_check_cache = {}
        
        if servers_by_group:
            self.init_from_config(servers_by_group)

    def init_from_config(self, servers_by_group):
        """Инициализирует серверы из переданной конфигурации {group_id: [server_config, ...]}"""
        self.servers_by_group = {}
        self.servers = []
        
        for group_id, servers_config in servers_by_group.items():
            self.servers_by_group[group_id] = []
            
            for server_config in servers_config:
                try:
                    x3_server = X3(
                        login=server_config["login"],
                        password=server_config["password"], 
                        host=server_config["host"],
                        vpn_host=server_config.get("vpn_host"),
                        subscription_port=server_config.get("subscription_port", 2096),
                        subscription_url=server_config.get("subscription_url")
                    )
                    server_info = {
                        "name": server_config["name"],
                        "x3": x3_server,
                        "config": server_config,
                        "group_id": server_config.get("group_id")
                    }
                    self.servers_by_group[group_id].append(server_info)
                    self.servers.append(server_info)
                    if server_config["name"] not in self.server_health:
                        self.server_health[server_config["name"]] = {
                            "status": "unknown",
                            "last_check": None,
                            "last_error": None,
                            "consecutive_failures": 0,
                            "uptime_percentage": 0.0
                        }
                    logger.info(f"Сервер {server_config['name']} добавлен (группа: {group_id})")
                except Exception as e:
                    logger.warning(f"Ошибка создания X3 объекта для {server_config['name']} (группа {group_id}): {e}")
                    server_info = {
                        "name": server_config["name"],
                        "x3": None,
                        "config": server_config,
                        "group_id": server_config.get("group_id")
                    }
                    self.servers_by_group[group_id].append(server_info)
                    self.servers.append(server_info)
                    self.server_health[server_config["name"]] = {
                        "status": "offline",
                        "last_check": datetime.datetime.now(),
                        "last_error": str(e),
                        "consecutive_failures": 1,
                        "uptime_percentage": 0.0
                    }

    def get_servers_by_group(self, group_id: int):
        """Возвращает список серверов, принадлежащих конкретной группе"""
        if group_id is None:
            return self.servers
        return [s for s in self.servers if s.get("group_id") == group_id]
    
    def get_server_by_name(self, server_name):
        """Возвращает конкретный сервер по имени"""
        for server in self.servers:
            if server["name"].lower() == server_name.lower():
                return server["x3"], server["name"]
        raise Exception(f"Сервер {server_name} не найден или недоступен")
    
    def get_server_config(self, server_name):
        """Возвращает конфигурацию сервера по имени"""
        for server in self.servers:
            if server["name"].lower() == server_name.lower():
                return server.get("config", {})
        return {}
    
    async def check_server_health(self, server_name, force_check=False):
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
                    host=server_config["host"],
                    vpn_host=server_config.get("vpn_host"),
                    subscription_port=server_config.get("subscription_port", 2096),
                    subscription_url=server_config.get("subscription_url")
                )
            
            # Проверяем доступность API (используем быструю проверку без retry)
            try:
                response = await server_info["x3"].list_quick(timeout=5)  # Быстрая проверка без retry
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
            # Ошибка при проверке здоровья сервера
            health_status = self.server_health.get(server_name, {
                "status": "unknown",
                "last_check": None,
                "last_error": None,
                "consecutive_failures": 0,
                "uptime_percentage": 0.0
            })

            # Увеличиваем счётчик подряд идущих неудач
            health_status["consecutive_failures"] = health_status.get("consecutive_failures", 0) + 1
            health_status["last_check"] = datetime.datetime.now()
            health_status["last_error"] = str(e)

            # Порог, после которого считаем сервер реально офлайн для всех
            FAILURE_THRESHOLD_FOR_OFFLINE = 2

            if health_status["consecutive_failures"] >= FAILURE_THRESHOLD_FOR_OFFLINE:
                # Сервер считаем недоступным
                health_status["status"] = "offline"

                # Если сервер долго недоступен, помечаем X3 как None
                if health_status["consecutive_failures"] > 3:
                    server_info["x3"] = None

                # Обновляем кэш с отрицательным результатом
                self._health_check_cache[server_name] = {
                    'result': False,
                    'timestamp': current_time,
                    'cached': True
                }

                self.server_health[server_name] = health_status
                logger.debug(
                    f"Сервер {server_name} недоступен: {e} "
                    f"(неудач подряд: {health_status['consecutive_failures']})"
                )
                return False

            # Если неудача первая/реже порога и раньше сервер был online,
            # считаем это временным глюком: статус оставляем online и возвращаем True,
            # чтобы UI не скакал между online/offline.
            if health_status.get("status") == "online":
                self.server_health[server_name] = health_status
                logger.debug(
                    f"Временная ошибка проверки {server_name}: {e} "
                    f"(неудач подряд: {health_status['consecutive_failures']}), "
                    f"оставляем статус online"
                )
                return True

            # Для остальных случаев (сервер уже не online) считаем его недоступным
            health_status["status"] = "offline"
            self.server_health[server_name] = health_status

            self._health_check_cache[server_name] = {
                'result': False,
                'timestamp': current_time,
                'cached': True
            }

            logger.debug(
                f"Сервер {server_name} недоступен: {e} "
                f"(неудач подряд: {health_status['consecutive_failures']})"
            )
            return False
    
    async def check_all_servers_health(self, force_check=False):
        """
        Проверяет здоровье всех серверов с кэшированием.
        Ошибка проверки одного сервера не прерывает проверку остальных.
        Проверки выполняются параллельно (время ~max по нодам, не сумма).
        """
        if not self.servers:
            return {}
        names = [s["name"] for s in self.servers]
        tasks = [self.check_server_health(name, force_check=force_check) for name in names]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        results = {}
        for server_name, outcome in zip(names, outcomes):
            if isinstance(outcome, Exception):
                logger.warning("Проверка здоровья сервера %s не удалась: %s", server_name, outcome)
                results[server_name] = False
            else:
                results[server_name] = outcome
        return results
    
    def get_server_health_status(self):
        """Возвращает статус здоровья всех серверов"""
        return self.server_health

    async def get_server_load_data(self):
        """Возвращает данные о нагрузке (онлайн-клиенты) для каждого сервера через X-UI API.
        Один запрос средних по БД; опрос панелей параллельно с таймаутом на ноду."""
        from ..db.servers_db import get_server_load_averages

        if not self.servers:
            logger.warning("servers пуст, возвращаем пустые данные нагрузки")
            return []

        averages_all = await get_server_load_averages(period_hours=24)
        load_timeout = 15.0

        async def fetch_one(server):
            server_name = server.get("name", "Unknown")
            xui = server.get("x3")
            server_avg = averages_all.get(server_name, {})

            def row_offline():
                return {
                    'server_name': server_name,
                    'online_clients': 0,
                    'total_active': 0,
                    'offline_clients': 0,
                    'avg_online_24h': server_avg.get('avg_online', 0),
                    'max_online_24h': server_avg.get('max_online', 0),
                    'min_online_24h': server_avg.get('min_online', 0),
                    'samples_24h': server_avg.get('samples', 0),
                    'load_percentage': 0,
                }

            if not xui:
                logger.warning("Сервер %s: XUI объект недоступен", server_name)
                return row_offline()

            try:
                total_active, online_count, offline_count = await asyncio.wait_for(
                    xui.get_online_clients_count(),
                    timeout=load_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Таймаут нагрузки для %s (>%ss)", server_name, load_timeout)
                return row_offline()
            except Exception as e:
                logger.error(
                    "Ошибка получения данных о нагрузке с сервера %s: %s",
                    server_name,
                    e,
                    exc_info=True,
                )
                return row_offline()

            capacity = (server.get("config") or {}).get("max_concurrent_clients") or 50
            if capacity <= 0:
                capacity = 50
            load_percentage = min(100, round((online_count / capacity) * 100, 1))

            return {
                'server_name': server_name,
                'online_clients': online_count,
                'total_active': total_active,
                'offline_clients': offline_count,
                'avg_online_24h': server_avg.get('avg_online', 0),
                'max_online_24h': server_avg.get('max_online', 0),
                'min_online_24h': server_avg.get('min_online', 0),
                'samples_24h': server_avg.get('samples', 0),
                'load_percentage': load_percentage,
            }

        logger.info("Обработка %s серверов (параллельно)", len(self.servers))
        server_data = await asyncio.gather(*[fetch_one(s) for s in self.servers])
        server_data.sort(key=lambda x: x['online_clients'], reverse=True)
        return server_data
