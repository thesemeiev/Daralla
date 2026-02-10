"""
Сервис для работы с X-UI API (async httpx)
"""
import base64
import logging
import json
import uuid
import datetime
import httpx
from typing import List
from urllib.parse import quote, urlparse
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


def _verify_from_host(host: str) -> bool:
    """True if HTTPS, False for HTTP."""
    return host.startswith("https://")


class X3:
    """Класс для работы с X-UI панелью управления VPN (async)"""

    def __init__(self, login, password, host, vpn_host=None, subscription_port=2096, subscription_url=None):
        self.login = login
        self.password = password
        self.host = host
        self.vpn_host = vpn_host  # IP/домен VPN сервера (если отличается от панели)
        self.subscription_port = subscription_port if subscription_port is not None else 2096
        self.subscription_url = (subscription_url or "").strip() or None  # Базовый URL подписки (порт 2096 и т.п.)
        self._client: httpx.AsyncClient | None = None
        self.data = {"username": self.login, "password": self.password}
        self._logged_in = False
        self._verify = _verify_from_host(host)
        logger.debug(f"XUI объект создан для {host} (подключение будет выполнено при первом использовании)")

    async def _login(self):
        """Выполняет вход в XUI панель"""
        try:
            try:
                login_response = await self._client.post(
                    f"{self.host}/login", data=self.data, timeout=30.0
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, Exception) as e:
                if "ssl" in str(e).lower() or "certificate" in str(e).lower():
                    logger.warning(f"SSL ошибка при подключении к {self.host}, пробуем без проверки сертификата")
                    await self._client.aclose()
                    self._client = httpx.AsyncClient(verify=False, timeout=30.0)
                    login_response = await self._client.post(
                        f"{self.host}/login", data=self.data, timeout=30.0
                    )
                else:
                    raise
            logger.info(f"XUI Login Response - Status: {login_response.status_code}")
            logger.info(f"XUI Login Response - Text: {login_response.text[:200]}...")
            if login_response.status_code != 200:
                logger.error(f"Ошибка входа в XUI: {login_response.status_code} - {login_response.text}")
                raise Exception(f"Login failed with status {login_response.status_code}")
            if "error" in login_response.text.lower() or "invalid" in login_response.text.lower():
                logger.error(f"Ошибка аутентификации: {login_response.text[:200]}")
                raise Exception("Authentication failed")
        except Exception as e:
            logger.error(f"Ошибка при подключении к XUI серверу {self.host}: {e}")
            raise

    async def _ensure_connected(self):
        """Проверяет подключение и подключается при необходимости"""
        if not self._logged_in:
            if self._client is None:
                self._client = httpx.AsyncClient(verify=self._verify, timeout=30.0)
            try:
                logger.info(f"Попытка подключения к XUI серверу: {self.host}")
                await self._login()
                self._logged_in = True
            except Exception as e:
                logger.error(f"Ошибка подключения к XUI серверу {self.host}: {e}")
                raise

    async def _reconnect(self):
        """Переподключается к серверу при истечении сессии"""
        logger.info(f"Переподключение к серверу {self.host}")
        if self._client is not None:
            await self._client.aclose()
        self._client = httpx.AsyncClient(verify=self._verify, timeout=30.0)
        await self._login()
        self._logged_in = True

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def addClient(self, day, tg_id, user_email, timeout=15, hours=None, key_name="", inbound_id=None, limit_ip=None, flow=None):
        """
        Добавляет нового клиента на сервер

        Args:
            day: Количество дней действия ключа
            tg_id: Telegram ID пользователя
            user_email: Email клиента
            timeout: Таймаут запроса
            hours: Количество часов (для тестовых ключей)
            key_name: Имя ключа или токен подписки (сохраняется в subId)
            inbound_id: ID inbound'а (если None, используется первый доступный)
            limit_ip: Лимит IP-адресов (если None, используется 1)
            flow: Flow для VLESS (например xtls-rprx-vision), если нужен; None — не передавать
        """
        await self._ensure_connected()
        protocol = None
        if inbound_id is None:
            try:
                inbounds_list = await self.list(timeout=timeout)
                if not inbounds_list.get('success', False) or not inbounds_list.get('obj'):
                    raise Exception("Не удалось получить список inbounds или список пуст")
                
                # Берем первый inbound из списка
                first_inbound = inbounds_list['obj'][0]
                inbound_id = first_inbound.get('id')
                protocol = first_inbound.get('protocol', 'vless').lower()
                if not inbound_id:
                    raise Exception("Не найден ID у первого inbound")
                logger.info(f"Используется inbound_id={inbound_id}, protocol={protocol} для добавления клиента {user_email}")
            except Exception as e:
                logger.error(f"Ошибка получения inbound_id: {e}")
                # Fallback: используем 1 (старое поведение)
                inbound_id = 1
                protocol = 'vless'  # По умолчанию VLESS
                logger.warning(f"Используется fallback inbound_id=1, protocol={protocol}")
        else:
            try:
                inbounds_list = await self.list(timeout=timeout)
                if inbounds_list.get('success', False) and inbounds_list.get('obj'):
                    for inbound in inbounds_list['obj']:
                        if inbound.get('id') == inbound_id:
                            protocol = inbound.get('protocol', 'vless').lower()
                            break
                if not protocol:
                    protocol = 'vless'  # По умолчанию VLESS
                    logger.warning(f"Не удалось определить протокол для inbound_id={inbound_id}, используем {protocol}")
            except Exception as e:
                logger.warning(f"Ошибка определения протокола для inbound_id={inbound_id}: {e}, используем vless")
                protocol = 'vless'
        
        if hours is not None:
            # Для тестовых ключей используем часы
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (hours * 3600000)
        else:
            # Для обычных ключей используем дни
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (86400000 * day)
        header = {"Accept": "application/json"}
        # limitIp используем из параметра или по умолчанию 1
        limit_ip_value = limit_ip if limit_ip is not None else 1
        
        # Генерируем UUID для id/password
        client_uuid = str(uuid.uuid1())
        
        # Формируем данные клиента в зависимости от протокола
        if protocol == 'trojan':
            # Для TROJAN нужен password вместо id
            client_data = {
                "password": client_uuid,  # Для TROJAN используется password
                "email": str(user_email),
                "limitIp": limit_ip_value,
                "totalGB": 0,
                "expiryTime": x_time,
                "enable": True,
                "tgId": str(tg_id),
                "subId": key_name,  # Сохраняем имя ключа в поле subId
            }
            logger.info(f"Создание TROJAN клиента {user_email} с password={client_uuid[:8]}...")
        else:
            # Для VLESS и других протоколов используется id
            client_data = {
                "id": client_uuid,  # Для VLESS используется id
                "email": str(user_email),
                "limitIp": limit_ip_value,
                "totalGB": 0,
                "expiryTime": x_time,
                "enable": True,
                "tgId": str(tg_id),
                "subId": key_name,  # Сохраняем имя ключа в поле subId
            }
            if flow and str(flow).strip():
                client_data["flow"] = str(flow).strip()
                logger.info(f"Создание {protocol.upper()} клиента {user_email} с flow={client_data['flow']}")
            logger.info(f"Создание {protocol.upper()} клиента {user_email} с id={client_uuid[:8]}...")
        logger.info(f"Создание клиента {user_email} на сервере {self.host} с limitIp={limit_ip_value} (передан limit_ip={limit_ip})")
        data1 = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_data]})
        }
        logger.info(f"Добавление клиента: {user_email} на сервер {self.host}, inbound_id={inbound_id}")
        try:
            response = await self._client.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
            logger.info(f"XUI addClient Response - Status: {response.status_code}")
            logger.info(f"XUI addClient Response - Text: {response.text[:200]}...")
            
            # Проверяем JSON ответ на наличие поля success
            try:
                response_json = response.json()
                if not response_json.get('success', False):
                    error_msg = response_json.get('msg', 'Unknown error')
                    # Если ошибка "Duplicate email", это не критично - клиент уже существует
                    if 'duplicate email' in error_msg.lower() or 'duplicate' in error_msg.lower():
                        logger.info(f"Клиент с email {user_email} уже существует, это нормально")
                        # Возвращаем успешный ответ, так как клиент уже создан
                        return response
                    logger.error(f"XUI addClient вернул success=false: {error_msg}")
                    raise Exception(f"XUI API error: {error_msg}")
            except (json.JSONDecodeError, ValueError):
                # Если ответ не JSON, проверяем статус код
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ, возможно истекла сессия. Переподключаюсь...")
                await self._reconnect()
                response = await self._client.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
                logger.info(f"XUI addClient Response после переподключения - Status: {response.status_code}")
                logger.info(f"XUI addClient Response после переподключения - Text: {response.text[:200]}...")
                
                # Проверяем JSON ответ после переподключения
                try:
                    response_json = response.json()
                    if not response_json.get('success', False):
                        error_msg = response_json.get('msg', 'Unknown error')
                        logger.error(f"XUI addClient после переподключения вернул success=false: {error_msg}")
                        raise Exception(f"XUI API error: {error_msg}")
                except (json.JSONDecodeError, ValueError):
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            return response
        except Exception as e:
            logger.error(f"Ошибка при добавлении клиента {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def extendClient(self, user_email, extend_days, timeout=15, flow=None):
        """
        Продлевает срок действия ключа клиента
        :param user_email: Email клиента
        :param extend_days: Количество дней для продления
        :param timeout: Таймаут запроса
        :param flow: Flow для VLESS (сохраняется при обновлении), None — не менять
        :return: Response объект
        """
        await self._ensure_connected()
        try:
            # Сначала получаем информацию о клиенте
            inbounds_data = await self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("Не удалось получить список клиентов")
            
            client_found = False
            client_data = None
            inbound_id = None
            protocol = None
            
            # Ищем клиента по email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        protocol = inbound.get('protocol', 'vless').lower()
                        
                        # Вычисляем новое время истечения
                        current_expiry = int(client.get('expiryTime', 0))
                        if current_expiry == 0:
                            # Если время истечения не установлено, начинаем с текущего времени
                            current_expiry = int(datetime.datetime.now().timestamp() * 1000)
                        
                        # Добавляем дни к текущему времени истечения
                        new_expiry = current_expiry + (extend_days * 86400000)  # 86400000 мс = 1 день
                        client_data['expiryTime'] = new_expiry
                        
                        logger.info(f"Продление ключа {user_email}: старое время истечения = {current_expiry}, новое = {new_expiry}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"Клиент с email {user_email} не найден")
            
            # Для TROJAN используем password, для других протоколов - id
            if protocol == 'trojan':
                client_identifier = client_data.get('password') or client_data.get('id')
            else:
                client_identifier = client_data.get('id')
            
            if not client_identifier:
                raise KeyError(f"Не найден идентификатор клиента (id/password) для протокола {protocol}")
            
            # Сохраняем flow для VLESS при обновлении (API может не возвращать flow, иначе слетает)
            if protocol == 'vless' and flow is not None:
                client_data['flow'] = (flow.strip() if isinstance(flow, str) else str(flow)).strip() or ''
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            logger.info(f"Продление клиента: {user_email} на сервере {self.host} на {extend_days} дней")
            response = await self._client.post(f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}', 
                                   headers=header, json=data, timeout=timeout)
            
            logger.info(f"XUI extendClient Response - Status: {response.status_code}")
            logger.info(f"XUI extendClient Response - Text: {response.text[:200]}...")
            
            # Проверяем JSON ответ на наличие поля success
            try:
                response_json = response.json()
                if not response_json.get('success', False):
                    error_msg = response_json.get('msg', 'Unknown error')
                    logger.error(f"XUI extendClient вернул success=false: {error_msg}")
                    raise Exception(f"XUI API error: {error_msg}")
            except (json.JSONDecodeError, ValueError):
                # Если ответ не JSON, проверяем статус код
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ при продлении, переподключаюсь...")
                await self._reconnect()
                response = await self._client.post(f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI extendClient Response после переподключения - Status: {response.status_code}")
                
                # Проверяем JSON ответ после переподключения
                try:
                    response_json = response.json()
                    if not response_json.get('success', False):
                        error_msg = response_json.get('msg', 'Unknown error')
                        logger.error(f"XUI extendClient после переподключения вернул success=false: {error_msg}")
                        raise Exception(f"XUI API error: {error_msg}")
                except (json.JSONDecodeError, ValueError):
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при продлении клиента {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def get_client_count(self, timeout=15):
        """Подсчитывает общее количество клиентов на сервере"""
        await self._ensure_connected()
        try:
            response_data = await self.list(timeout=timeout)
            logger.info(f"XUI list response: {response_data}")
            if 'obj' not in response_data:
                logger.error(f"Неожиданный формат ответа XUI: {response_data}")
                return 0
            inbounds = response_data['obj']
            total_clients = 0
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                total_clients += len(settings.get("clients", []))
            return total_clients
        except Exception as e:
            logger.error(f"Ошибка при подсчете клиентов на {self.host}: {e}")
            return 0

    async def get_clients_status_count(self, timeout=15):
        """Подсчитывает количество клиентов по статусу (активные/истекшие)"""
        try:
            response_data = await self.list(timeout=timeout)
            if 'obj' not in response_data:
                logger.error(f"Неожиданный формат ответа XUI: {response_data}")
                return 0, 0, 0
            
            inbounds = response_data['obj']
            total_clients = 0
            active_clients = 0
            expired_clients = 0
            current_time = int(datetime.datetime.now().timestamp() * 1000)
            
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                clients = settings.get("clients", [])
                total_clients += len(clients)
                
                for client in clients:
                    # Проверяем, активен ли клиент (не истек ли срок)
                    expiry_time = client.get('expiryTime', 0)
                    if expiry_time == 0 or current_time < expiry_time:
                        active_clients += 1
                    else:
                        expired_clients += 1
            
            return total_clients, active_clients, expired_clients
        except Exception as e:
            logger.error(f"Ошибка при подсчете статуса клиентов на {self.host}: {e}")
            return 0, 0, 0
    
    async def get_client_ips(self, client_id, inbound_id, timeout=15):
        """
        Получает список IP-адресов подключенных клиентов через API 3x-ui
        Если у клиента есть активные IP-адреса, значит он онлайн
        
        Args:
            client_id: ID клиента (id для VLESS, password для TROJAN)
            inbound_id: ID inbound'а
            timeout: Таймаут запроса
            
        Returns:
            list: Список IP-адресов или пустой список
        """
        await self._ensure_connected()
        try:
            # Пробуем разные варианты endpoint'ов
            endpoints = [
                f'{self.host}/panel/api/inbounds/listClientIps/{inbound_id}?clientId={client_id}',
                f'{self.host}/panel/api/inbounds/getClientIps/{inbound_id}/{client_id}',
                f'{self.host}/panel/api/inbounds/{inbound_id}/listClientIps/{client_id}',
            ]
            
            for url in endpoints:
                try:
                    response = await self._client.get(url, timeout=timeout)
                    if response.status_code == 200:
                        data = response.json()
                        # Разные форматы ответа
                        if isinstance(data, dict):
                            ips = data.get('obj', data.get('ips', data.get('data', [])))
                        elif isinstance(data, list):
                            ips = data
                        else:
                            ips = []
                        
                        if ips and isinstance(ips, list) and len(ips) > 0:
                            logger.debug(f"Найдено {len(ips)} IP-адресов для клиента {client_id}")
                            return ips
                except Exception as e:
                    logger.debug(f"Endpoint {url} не сработал: {e}")
                    continue
            
            return []
        except Exception as e:
            logger.debug(f"Ошибка получения IP-адресов для клиента {client_id}: {e}")
            return []
    
    def _has_active_traffic(self, upload, download):
        """
        Проверяет, есть ли у клиента активный трафик (нагружает ли он канал)
        
        Логика: если upload > 0 ИЛИ download > 0, значит клиент передает/принимает данные
        и нагружает канал сервера
        
        Args:
            upload: Текущее значение upload (байты)
            download: Текущее значение download (байты)
            
        Returns:
            bool: True если есть трафик (клиент нагружает канал), False если нет
        """
        # Если есть upload или download, клиент нагружает канал
        return upload > 0 or download > 0
    
    async def get_online_clients_ids(self, timeout=15):
        """
        Получает список ID клиентов, которые сейчас онлайн через API X-UI
        
        Использует эндпоинт /panel/api/inbounds/onlines
        
        Returns:
            tuple: (online_ids: set, success: bool) - множество ID клиентов и флаг успешности
        """
        await self._ensure_connected()
        try:
            url = f'{self.host}/panel/api/inbounds/onlines'
            response = await self._client.post(url, timeout=timeout)
            
            if response.status_code != 200:
                logger.warning(f"Ошибка получения онлайн клиентов: HTTP {response.status_code}")
                return set(), False
            
            data = response.json()
            if not data.get('success', False):
                logger.warning(f"API вернул success=False: {data.get('msg', '')}")
                return set(), False
            
            online_ids = data.get('obj', [])
            # Если obj=None, это означает "нет онлайн клиентов", а не ошибка
            if online_ids is None:
                logger.debug(f"API вернул obj=None - нет онлайн клиентов на сервере {self.host}")
                return set(), True  # Возвращаем пустой set, но success=True
            
            if not isinstance(online_ids, list):
                logger.warning(f"Неожиданный формат ответа: obj не является списком, тип: {type(online_ids)}, значение: {online_ids}")
                return set(), False
            
            # API возвращает ID в формате "tg_id_uuid" или "tg_id_число"
            # Возвращаем как есть для сравнения с полным форматом
            online_ids_set = set()
            for online_id in online_ids:
                online_id_str = str(online_id).strip()
                if online_id_str:
                    online_ids_set.add(online_id_str)
            
            logger.debug(f"Получено {len(online_ids)} онлайн клиентов через API: {online_ids}")
            return online_ids_set, True
            
        except Exception as e:
            logger.warning(f"Ошибка получения онлайн клиентов через API: {e}")
            return set(), False
    
    async def get_online_clients_count(self, timeout=15):
        """
        Подсчитывает количество клиентов, которые сейчас онлайн (нагружают канал)
        
        Использует API X-UI для точного определения онлайн-статуса:
        1. Сначала пытается использовать /panel/api/inbounds/onlines (самый точный метод)
        2. Если API недоступен, использует fallback - проверку трафика
        
        Это правильный подход для capacity planning:
        - Каждый снимок показывает количество клиентов с активным трафиком в момент времени
        - Среднее значение = сумма всех снимков / количество снимков
        - Это показывает типичную нагрузку на канал
        
        Args:
            timeout: Таймаут запроса
        
        Returns:
            tuple: (total_active, online_count, offline_count)
        """
        try:
            logger.debug(f"Получение списка клиентов с сервера {self.host}")
            response_data = await self.list(timeout=timeout)
            
            if not response_data:
                logger.warning(f"Пустой ответ от сервера {self.host}")
                return 0, 0, 0
                
            if 'obj' not in response_data:
                logger.error(f"Неожиданный формат ответа XUI: ключи={list(response_data.keys())}")
                return 0, 0, 0
            
            inbounds = response_data['obj']
            if not inbounds:
                logger.warning(f"Нет inbounds на сервере {self.host}")
                return 0, 0, 0
            
            logger.debug(f"Найдено {len(inbounds)} inbounds на сервере {self.host}")
            
            total_active = 0
            online_count = 0
            offline_count = 0
            current_time = int(datetime.datetime.now().timestamp() * 1000)
            
            # Получаем список онлайн клиентов через API (единственный метод)
            online_client_ids, api_available = await self.get_online_clients_ids(timeout=timeout)
            
            if not api_available:
                logger.warning(f"API /onlines недоступен на сервере {self.host}, возвращаем 0 онлайн клиентов")
                # Если API недоступен, считаем что все клиенты офлайн
                # Подсчитываем только активных клиентов
                for inbound in inbounds:
                    try:
                        settings_str = inbound.get('settings', '{}')
                        if not settings_str:
                            continue
                        settings = json.loads(settings_str)
                        clients = settings.get("clients", [])
                        for client in clients:
                            expiry_time = client.get('expiryTime', 0)
                            if expiry_time == 0 or current_time < expiry_time:
                                total_active += 1
                                offline_count += 1
                    except Exception:
                        continue
                
                logger.info(f"Сервер {self.host}: активных={total_active}, нагружают канал=0, не нагружают={offline_count} (API недоступен)")
                return total_active, 0, offline_count
            
            logger.info(f"Используется API /onlines для определения онлайн-статуса. Получено {len(online_client_ids)} онлайн ID: {list(online_client_ids)[:10]}")
            
            # Подсчитываем клиентов
            for inbound in inbounds:
                try:
                    inbound_id = inbound.get('id')
                    settings_str = inbound.get('settings', '{}')
                    if not settings_str:
                        continue
                    settings = json.loads(settings_str)
                    clients = settings.get("clients", [])
                    
                    # Определяем протокол для правильного получения ID клиента
                    protocol = inbound.get('protocol', 'vless').lower()
                    
                    for client in clients:
                        # Проверяем, активен ли клиент (не истек ли срок)
                        expiry_time = client.get('expiryTime', 0)
                        if expiry_time == 0 or current_time < expiry_time:
                            total_active += 1
                            email = client.get('email')
                            
                            is_online = False
                            
                            # Используем только API /onlines для определения онлайн-статуса
                            # API возвращает EMAIL клиента в формате "tg_id_uuid" или "tg_id_число"
                            # Сравниваем email клиента напрямую с тем, что вернул API
                            if email:
                                email_str = str(email)
                                
                                # Проверяем точное совпадение email
                                if email_str in online_client_ids:
                                    is_online = True
                                    logger.debug(f"Клиент {email} онлайн (определено через API, email: {email_str})")
                                else:
                                    # Логируем для отладки, почему не нашли совпадение (только для первых нескольких клиентов)
                                    if total_active <= 5 or online_count == 0:
                                        logger.info(f"Клиент {email} не найден в онлайн списке. Email: {email_str}, онлайн ID из API: {list(online_client_ids)[:5]}")
                            else:
                                if total_active <= 5:
                                    logger.info(f"Клиент не имеет email (protocol={protocol})")
                            
                            if is_online:
                                online_count += 1
                            else:
                                offline_count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"Ошибка парсинга settings для inbound {inbound.get('id')}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Ошибка обработки inbound {inbound.get('id')}: {e}")
                    continue
            
            logger.info(f"Сервер {self.host}: активных={total_active}, нагружают канал={online_count}, не нагружают={offline_count} (метод: API /onlines)")
            return total_active, online_count, offline_count
        except Exception as e:
            logger.error(f"Ошибка при подсчете онлайн клиентов на {self.host}: {e}", exc_info=True)
            return 0, 0, 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def client_exists(self, user_email):
        """Проверяет существование клиента по email"""
        await self._ensure_connected()
        for inbound in await self.list()['obj']:
            settings = json.loads(inbound['settings'])
            for client in settings.get("clients", []):
                if client['email'] == user_email:
                    return True
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def get_client_expiry_time(self, user_email, timeout=15):
        """
        Получает время истечения клиента по email.
        
        Returns:
            int: Unix timestamp в секундах, или None если клиент не найден
        """
        await self._ensure_connected()
        try:
            inbounds_list = await self.list(timeout=timeout)
            if inbounds_list.get('success', False) and inbounds_list.get('obj'):
                for inbound in inbounds_list['obj']:
                    settings = json.loads(inbound.get('settings', '{}'))
                    clients = settings.get('clients', [])
                    for client in clients:
                        if client.get('email') == user_email:
                            expiry_time_ms = client.get('expiryTime', 0)
                            if expiry_time_ms > 0:
                                # Конвертируем из миллисекунд в секунды
                                return expiry_time_ms // 1000
                            return None
            return None
        except Exception as e:
            logger.error(f"Ошибка получения времени истечения клиента {user_email}: {e}")
            return None

    async def get_client_info(self, user_email, timeout=15):
        """
        Получает полную информацию о клиенте по email.
        
        Returns:
            dict: Информация о клиенте (client_data, inbound_id, protocol) или None
        """
        await self._ensure_connected()
        try:
            inbounds_list = await self.list(timeout=timeout)
            if inbounds_list.get('success', False) and inbounds_list.get('obj'):
                for inbound in inbounds_list['obj']:
                    settings = json.loads(inbound.get('settings', '{}'))
                    clients = settings.get('clients', [])
                    for client in clients:
                        if client.get('email') == user_email:
                            protocol = inbound.get('protocol', 'vless').lower()
                            return {
                                'client': client,
                                'inbound_id': inbound.get('id'),
                                'protocol': protocol
                            }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о клиенте {user_email}: {e}")
            return None
    
    async def get_clients_by_tg_id(self, tg_id, timeout=15):
        """
        Получает список всех клиентов для указанного Telegram ID.
        
        Args:
            tg_id: Telegram ID пользователя
            
        Returns:
            list: Список словарей с информацией о клиентах:
                  [{'email': str, 'client': dict, 'inbound_id': str, 'protocol': str}, ...]
        """
        await self._ensure_connected()
        clients_list = []
        try:
            inbounds_list = await self.list(timeout=timeout)
            if inbounds_list.get('success', False) and inbounds_list.get('obj'):
                for inbound in inbounds_list['obj']:
                    settings = json.loads(inbound.get('settings', '{}'))
                    clients = settings.get('clients', [])
                    for client in clients:
                        # Проверяем tgId (может быть строкой или числом)
                        client_tg_id = str(client.get('tgId', ''))
                        if client_tg_id == str(tg_id):
                            protocol = inbound.get('protocol', 'vless').lower()
                            clients_list.append({
                                'email': client.get('email'),
                                'client': client,
                                'inbound_id': inbound.get('id'),
                                'protocol': protocol
                            })
            return clients_list
        except Exception as e:
            logger.error(f"Ошибка получения клиентов по tg_id {tg_id}: {e}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def setClientExpiry(self, user_email, expiry_timestamp, timeout=15, flow=None):
        """
        Устанавливает точное время истечения клиента.
        
        Args:
            user_email: Email клиента
            expiry_timestamp: Unix timestamp в секундах (будет конвертирован в миллисекунды)
            timeout: Таймаут запроса
            flow: Flow для VLESS (сохраняется при обновлении), None — не менять
        
        Returns:
            Response объект или None если клиент не найден
        """
        await self._ensure_connected()
        try:
            client_info = await self.get_client_info(user_email, timeout=timeout)
            if not client_info:
                logger.warning(f"Клиент {user_email} не найден для установки времени истечения")
                return None
            
            client_data = client_info['client'].copy()
            inbound_id = client_info['inbound_id']
            protocol = client_info.get('protocol', 'vless').lower()
            
            # Для TROJAN используем password, для других протоколов - id
            if protocol == 'trojan':
                client_identifier = client_data.get('password') or client_data.get('id')
            else:
                client_identifier = client_data.get('id')
            
            if not client_identifier:
                raise KeyError(f"Не найден идентификатор клиента (id/password) для протокола {protocol}")
            
            # Конвертируем timestamp из секунд в миллисекунды (X-UI использует миллисекунды)
            expiry_time_ms = expiry_timestamp * 1000
            
            # Обновляем expiryTime
            old_expiry = client_data.get('expiryTime', 0)
            if old_expiry == expiry_time_ms:
                logger.debug(f"Время истечения для клиента {user_email} уже равно {expiry_timestamp}, обновление не требуется")
                return None
            
            client_data['expiryTime'] = expiry_time_ms
            logger.info(f"Установка времени истечения для клиента {user_email}: {old_expiry // 1000} -> {expiry_timestamp}")
            
            # Сохраняем flow для VLESS при обновлении (API может не возвращать flow, иначе слетает)
            if protocol == 'vless' and flow is not None:
                client_data['flow'] = (flow.strip() if isinstance(flow, str) else str(flow)).strip() or ''
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            response = await self._client.post(
                f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}',
                headers=header,
                json=data,
                timeout=timeout
            )
            logger.info(f"XUI setClientExpiry Response - Status: {response.status_code}")
            
            # Проверяем JSON ответ
            try:
                response_json = response.json()
                if not response_json.get('success', False):
                    error_msg = response_json.get('msg', 'Unknown error')
                    logger.error(f"XUI setClientExpiry вернул success=false: {error_msg}")
                    raise Exception(f"XUI API error: {error_msg}")
            except (json.JSONDecodeError, ValueError):
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ при установке времени истечения, переподключаюсь...")
                await self._reconnect()
                response = await self._client.post(
                    f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}',
                    headers=header,
                    json=data,
                    timeout=timeout
                )
                logger.info(f"XUI setClientExpiry Response после переподключения - Status: {response.status_code}")
                
                try:
                    response_json = response.json()
                    if not response_json.get('success', False):
                        error_msg = response_json.get('msg', 'Unknown error')
                        logger.error(f"XUI setClientExpiry после переподключения вернул success=false: {error_msg}")
                        raise Exception(f"XUI API error: {error_msg}")
                except (json.JSONDecodeError, ValueError):
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при установке времени истечения клиента {user_email}: {e}")
            raise

    async def updateClientLimitIp(self, user_email, limit_ip, timeout=15, flow=None):
        """
        Обновляет limitIp клиента.
        
        Args:
            user_email: Email клиента
            limit_ip: Новое значение limitIp
            timeout: Таймаут запроса
            flow: Flow для VLESS (сохраняется при обновлении), None — не менять
        
        Returns:
            Response объект или None если клиент не найден
        """
        await self._ensure_connected()
        try:
            client_info = await self.get_client_info(user_email, timeout=timeout)
            if not client_info:
                logger.warning(f"Клиент {user_email} не найден для обновления limitIp")
                return None
            
            client_data = client_info['client'].copy()
            inbound_id = client_info['inbound_id']
            protocol = client_info.get('protocol', 'vless').lower()
            
            # Для TROJAN используем password, для других протоколов - id
            if protocol == 'trojan':
                client_identifier = client_data.get('password') or client_data.get('id')
            else:
                client_identifier = client_data.get('id')
            
            if not client_identifier:
                raise KeyError(f"Не найден идентификатор клиента (id/password) для протокола {protocol}")
            
            # Обновляем limitIp
            # ВАЖНО: Если limitIp отсутствует в данных клиента, нужно его установить
            # Проверяем наличие ключа 'limitIp' в данных клиента
            old_limit_ip = client_data.get('limitIp')
            # Если limitIp отсутствует (None) или равен 0, или отличается от нужного значения - обновляем
            if old_limit_ip is None or old_limit_ip == 0 or old_limit_ip != limit_ip:
                # Нужно обновить
                old_limit_ip_display = old_limit_ip if old_limit_ip is not None else "не установлен"
                client_data['limitIp'] = limit_ip
                logger.info(f"Обновление limitIp для клиента {user_email}: {old_limit_ip_display} -> {limit_ip}")
            else:
                logger.debug(f"limitIp для клиента {user_email} уже равен {limit_ip}, обновление не требуется")
                return None
            
            # Сохраняем flow для VLESS при обновлении (API может не возвращать flow, иначе слетает)
            if protocol == 'vless' and flow is not None:
                client_data['flow'] = (flow.strip() if isinstance(flow, str) else str(flow)).strip() or ''
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            response = await self._client.post(
                f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}',
                headers=header,
                json=data,
                timeout=timeout
            )
            logger.info(f"XUI updateClientLimitIp Response - Status: {response.status_code}")
            
            # Проверяем JSON ответ
            try:
                response_json = response.json()
                if not response_json.get('success', False):
                    error_msg = response_json.get('msg', 'Unknown error')
                    logger.error(f"XUI updateClientLimitIp вернул success=false: {error_msg}")
                    raise Exception(f"XUI API error: {error_msg}")
            except (json.JSONDecodeError, ValueError):
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении limitIp клиента {user_email}: {e}")
            raise

    async def sync_flow_for_all_clients(self, flow_value: str, timeout=15) -> tuple:
        """
        Обновляет flow у всех VLESS-клиентов на сервере.
        
        Args:
            flow_value: Новое значение flow (например xtls-rprx-vision), или пустая строка/None чтобы снять flow.
            timeout: Таймаут запросов.
        
        Returns:
            (updated_count, error_messages): количество обновлённых клиентов и список ошибок.
        """
        await self._ensure_connected()
        updated = 0
        errors = []
        try:
            inbounds_list = await self.list(timeout=timeout)
            if not inbounds_list.get('success', False) or not inbounds_list.get('obj'):
                return 0, ["Не удалось получить список inbounds"]
            flow_val = (flow_value or "").strip() or None
            header = {"Accept": "application/json"}
            for inbound in inbounds_list['obj']:
                protocol = (inbound.get('protocol') or 'vless').lower()
                if protocol == 'trojan':
                    continue  # flow только для VLESS
                inbound_id = inbound.get('id')
                try:
                    settings = json.loads(inbound.get('settings', '{}'))
                except Exception as e:
                    errors.append(f"inbound {inbound_id}: ошибка парсинга settings — {e}")
                    continue
                clients = settings.get('clients', [])
                for client in clients:
                    client_data = dict(client)
                    if flow_val:
                        client_data['flow'] = flow_val
                    else:
                        client_data.pop('flow', None)
                    client_identifier = client_data.get('id')
                    if not client_identifier:
                        continue
                    try:
                        data = {
                            "id": inbound_id,
                            "settings": json.dumps({"clients": [client_data]})
                        }
                        resp = await self._client.post(
                            f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}',
                            headers=header, json=data, timeout=timeout
                        )
                        if resp.status_code == 200:
                            try:
                                j = resp.json()
                                if j.get('success', False):
                                    updated += 1
                                    logger.info(f"Обновлён flow для клиента {client.get('email', '?')} (inbound {inbound_id})")
                                else:
                                    errors.append(f"{client.get('email', '?')}: {j.get('msg', 'unknown')}")
                            except (json.JSONDecodeError, ValueError):
                                errors.append(f"{client.get('email', '?')}: ответ не JSON")
                        else:
                            errors.append(f"{client.get('email', '?')}: HTTP {resp.status_code}")
                    except Exception as e:
                        errors.append(f"{client.get('email', '?')}: {e}")
            return updated, errors
        except Exception as e:
            logger.error(f"Ошибка sync_flow_for_all_clients: {e}")
            return updated, errors + [str(e)]

    async def _list_internal(self, timeout=15, skip_health_check=False):
        """Внутренний метод для получения списка inbounds (без retry)"""
        await self._ensure_connected()
        try:
            url = f'{self.host}/panel/api/inbounds/list'
            
            # Пропускаем health check ping для быстрой проверки здоровья
            if not skip_health_check:
                try:
                    health_check = await self._client.get(f'{self.host}/ping', timeout=5)
                    logger.debug(f"Проверка доступности сервера {self.host}: {health_check.status_code}")
                except Exception as e:
                    logger.debug(f"Сервер {self.host} недоступен для ping: {e}")
            
            # В httpx AsyncClient.get() нет параметра json, поэтому используем request()
            response = await self._client.request("GET", url, json=self.data, timeout=timeout)
            logger.debug(f"XUI API Response - URL: {url}, Status: {response.status_code}")
            if not skip_health_check:
                logger.info(f"XUI API Response - URL: {url}")
                logger.info(f"XUI API Response - Status: {response.status_code}")
                logger.debug(f"XUI API Response - Text: {response.text[:200]}...")
            
            # Проверяем статус ответа
            if response.status_code != 200:
                logger.error(f"XUI API вернул неверный статус: {response.status_code} для URL {url}")
                if response.status_code == 404:
                    logger.error(f"Endpoint не найден на сервере {self.host}. Возможно, сервер не поддерживает API или требует обновления.")
                    return {'success': False, 'error': '404 Not Found', 'obj': []}  # Возвращаем структуру, совместимую с ожидаемым форматом
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # Проверяем, что ответ не пустой
            if not response.text.strip():
                logger.error("XUI API вернул пустой ответ")
                raise Exception("Пустой ответ от сервера")
            
            # Проверяем, что ответ начинается с '{' или '[' (признак JSON)
            if not response.text.strip().startswith(('{', '[')):
                logger.error(f"XUI API вернул не-JSON ответ: {response.text[:200]}")
                # Если получили HTML вместо JSON, возможно сессия истекла
                if "<html" in response.text.lower() or "login" in response.text.lower():
                    logger.warning("Обнаружена истекшая сессия, переподключаюсь...")
                    await self._reconnect()
                    # Повторяем запрос после переподключения
                    response = await self._client.request(
                        "GET",
                        f'{self.host}/panel/api/inbounds/list',
                        json=self.data,
                        timeout=timeout,
                    )
                    logger.info(f"XUI API Response после переподключения - Status: {response.status_code}")
                    logger.info(f"XUI API Response после переподключения - Text: {response.text[:500]}...")
                    
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    
                    if not response.text.strip().startswith(('{', '[')):
                        raise Exception(f"Неверный формат ответа после переподключения: {response.text[:200]}")
                
                else:
                    raise Exception(f"Неверный формат ответа: {response.text[:200]}")
            
            try:
                return response.json()
            except json.JSONDecodeError as json_error:
                logger.error(f"Ошибка парсинга JSON: {json_error}")
                logger.error(f"Ответ сервера: {response.text[:500]}")
                raise Exception(f"Ошибка парсинга JSON: {json_error}")
                
        except Exception as e:
            if not skip_health_check:
                logger.error(f"Ошибка при запросе к XUI API: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2)
    )
    async def list(self, timeout=15):
        """Получает список всех inbounds и клиентов (с retry для надежности)"""
        return await self._list_internal(timeout=timeout, skip_health_check=False)
    
    async def get_client_traffic(self, user_email: str, timeout=15):
        """
        Получает статистику трафика клиента из 3x-ui
        
        Args:
            user_email: Email клиента
            timeout: Таймаут запроса
            
        Returns:
            dict с полями: upload (bytes), download (bytes), total (bytes) или None если не найдено
        """
        await self._ensure_connected()
        try:
            # Пробуем получить статистику через API 3x-ui
            # 3x-ui может предоставлять статистику через разные endpoints
            # Попробуем несколько вариантов
            
            # Вариант 1: Через /panel/api/inbounds/list (может содержать статистику в clientStats)
            inbounds_list = await self.list(timeout=timeout)
            if inbounds_list.get('success', False) and inbounds_list.get('obj'):
                for inbound in inbounds_list['obj']:
                    settings = json.loads(inbound.get('settings', '{}'))
                    clients = settings.get('clients', [])
                    for client in clients:
                        if client.get('email') == user_email:
                            # Проверяем, есть ли статистика в clientStats
                            # clientStats может быть списком или словарем
                            client_stats = inbound.get('clientStats', [])
                            
                            # Логируем структуру для отладки
                            if client_stats:
                                logger.debug(f"clientStats для inbound {inbound.get('id')}: type={type(client_stats)}, sample={str(client_stats)[:200]}")
                            
                            # Если clientStats - это список
                            if isinstance(client_stats, list):
                                for stat in client_stats:
                                    if stat.get('email') == user_email:
                                        upload = stat.get('up', 0) or stat.get('upload', 0)  # Upload в байтах
                                        download = stat.get('down', 0) or stat.get('download', 0)  # Download в байтах
                                        total = stat.get('total', 0)  # Total в байтах
                                        logger.info(f"Найдена статистика трафика для {user_email}: upload={upload}, download={download}, total={total}")
                                        return {
                                            "upload": upload,
                                            "download": download,
                                            "total": total
                                        }
                            
                            # Если clientStats - это словарь (ключ = email)
                            elif isinstance(client_stats, dict):
                                stat = client_stats.get(user_email)
                                if stat:
                                    upload = stat.get('up', 0) or stat.get('upload', 0)
                                    download = stat.get('down', 0) or stat.get('download', 0)
                                    total = stat.get('total', 0)
                                    logger.info(f"Найдена статистика трафика для {user_email}: upload={upload}, download={download}, total={total}")
                                    return {
                                        "upload": upload,
                                        "download": download,
                                        "total": total
                                    }
            
            # Если статистика не найдена, логируем структуру ответа для отладки
            logger.warning(f"Статистика трафика для клиента {user_email} не найдена в 3x-ui")
            logger.debug(f"Структура ответа 3x-ui (первые 500 символов): {str(inbounds_list)[:500]}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики трафика для {user_email}: {e}")
            return None
    
    async def list_quick(self, timeout=5):
        """
        Быстрая проверка доступности сервера без retry (для health check)
        Используется только для проверки здоровья, не для реальных операций
        """
        return await self._list_internal(timeout=timeout, skip_health_check=True)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def deleteClient(self, user_email, timeout=15):
        """Удаляет клиента по email"""
        try:
            inbounds_list = await self.list(timeout=timeout)
            
            # Проверяем структуру ответа
            if not isinstance(inbounds_list, dict):
                logger.warning(f"Неожиданный формат ответа от list() для удаления клиента {user_email}: {type(inbounds_list)}")
                raise KeyError(f"Ответ от list() не является словарем: {type(inbounds_list)}")
            
            # Безопасно получаем список inbounds
            inbounds = inbounds_list.get('obj', [])
            if not isinstance(inbounds, list):
                logger.warning(f"Ключ 'obj' в ответе от list() не является списком для удаления клиента {user_email}: {type(inbounds)}")
                raise KeyError(f"Ключ 'obj' не является списком: {type(inbounds)}")
            
            for inbound in inbounds:
                if not isinstance(inbound, dict):
                    continue
                
                # Безопасно получаем settings
                settings_str = inbound.get('settings')
                if not settings_str:
                    continue
                
                try:
                    settings = json.loads(settings_str)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Ошибка парсинга settings для inbound {inbound.get('id', 'unknown')}: {e}")
                    continue
                
                # Безопасно получаем список клиентов
                clients = settings.get("clients", [])
                if not isinstance(clients, list):
                    continue
                
                for client in clients:
                    if not isinstance(client, dict):
                        continue
                    
                    # Проверяем email
                    if client.get('email') != user_email:
                        continue
                    
                    # Определяем протокол inbound
                    protocol = inbound.get('protocol', 'vless').lower()
                    inbound_id = inbound.get('id')
                    
                    if not inbound_id:
                        logger.warning(f"Inbound не имеет 'id' для клиента {user_email}")
                        continue
                    
                    # Для TROJAN используем password, для других протоколов - id
                    if protocol == 'trojan':
                        client_id = client.get('password') or client.get('id')
                        if not client_id:
                            logger.warning(f"Клиент {user_email} найден (TROJAN), но не имеет 'password' или 'id' в inbound {inbound_id}")
                            continue
                    else:
                        client_id = client.get('id')
                        if not client_id:
                            logger.warning(f"Клиент {user_email} найден, но не имеет 'id' в inbound {inbound_id}")
                            continue
                    
                    url = f"{self.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                    logger.info(f"Удаляю {protocol.upper()} клиента: inbound_id={inbound_id}, client_id={client_id}, email={user_email}")
                    result = await self._client.post(url, timeout=timeout)
                    logger.info(f"Ответ XUI: status_code={getattr(result, 'status_code', None)}, text={getattr(result, 'text', None)[:200] if hasattr(result, 'text') else None}")
                    if getattr(result, 'status_code', None) == 200:
                        logger.info(f"Клиент успешно удалён: {user_email} (протокол: {protocol})")
                    else:
                        logger.warning(f"Неожиданный статус код при удалении клиента {user_email}: {getattr(result, 'status_code', None)}")
                    return result
            
            logger.warning(f"Клиент с email={user_email} не найден ни в одном inbound")
            return None
            
        except KeyError as e:
            # Пробрасываем KeyError как есть, чтобы retry мог обработать
            logger.error(f"KeyError при удалении клиента {user_email}: {e}")
            raise
        except Exception as e:
            # Другие ошибки логируем и пробрасываем
            logger.error(f"Ошибка при удалении клиента {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def updateClientName(self, user_email, new_name, timeout=15):
        """
        Обновляет имя ключа (сохраняет в поле subId)
        :param user_email: Email клиента
        :param new_name: Новое имя ключа
        :param timeout: Таймаут запроса
        :return: Response объект
        """
        await self._ensure_connected()
        try:
            # Сначала получаем информацию о клиенте
            inbounds_data = await self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("Не удалось получить список клиентов")
            
            client_found = False
            client_data = None
            inbound_id = None
            protocol = None
            
            # Ищем клиента по email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        protocol = inbound.get('protocol', 'vless').lower()
                        
                        # Обновляем имя ключа в поле subId
                        client_data['subId'] = new_name
                        
                        logger.info(f"Обновление имени ключа {user_email}: новое имя = {new_name}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"Клиент с email {user_email} не найден")
            
            # Для TROJAN используем password, для других протоколов - id
            if protocol == 'trojan':
                client_identifier = client_data.get('password') or client_data.get('id')
            else:
                client_identifier = client_data.get('id')
            
            if not client_identifier:
                raise KeyError(f"Не найден идентификатор клиента (id/password) для протокола {protocol}")
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            response = await self._client.post(f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}', headers=header, json=data, timeout=timeout)
            logger.info(f"XUI updateClientName Response - Status: {response.status_code}")
            logger.info(f"XUI updateClientName Response - Text: {response.text[:200]}...")
            
            # Проверяем JSON ответ на наличие поля success
            try:
                response_json = response.json()
                if not response_json.get('success', False):
                    error_msg = response_json.get('msg', 'Unknown error')
                    logger.error(f"XUI updateClientName вернул success=false: {error_msg}")
                    raise Exception(f"XUI API error: {error_msg}")
            except (json.JSONDecodeError, ValueError):
                # Если ответ не JSON, проверяем статус код
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ при обновлении имени, переподключаюсь...")
                await self._reconnect()
                response = await self._client.post(f'{self.host}/panel/api/inbounds/updateClient/{client_identifier}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI updateClientName Response после переподключения - Status: {response.status_code}")
                
                # Проверяем JSON ответ после переподключения
                try:
                    response_json = response.json()
                    if not response_json.get('success', False):
                        error_msg = response_json.get('msg', 'Unknown error')
                        logger.error(f"XUI updateClientName после переподключения вернул success=false: {error_msg}")
                        raise Exception(f"XUI API error: {error_msg}")
                except (json.JSONDecodeError, ValueError):
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            logger.info(f"Имя ключа успешно обновлено: {user_email} -> {new_name}")
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении имени ключа {user_email}: {e}")
            raise

    async def link(self, user_id: str, server_name: str = None):
        """
        Генерирует ссылку для клиента (VLESS или TROJAN в зависимости от протокола inbound'а)
        
        Args:
            user_id: Email клиента
            server_name: Название сервера для tag (если не указано, используется user_id)
        """
        await self._ensure_connected()
        inbounds_list = await self.list()['obj']
        for inbounds in inbounds_list:
            settings = json.loads(inbounds['settings'])
            stream = json.loads(inbounds['streamSettings'])

            client = next((c for c in settings.get("clients", []) if c['email'] == user_id), None)
            if not client:
                continue

            # Определяем протокол inbound'а
            protocol = inbounds.get('protocol', 'vless').lower()
            
            # Используем vpn_host если указан, иначе берем из host панели
            if self.vpn_host:
                # Если vpn_host указан, используем его
                host_part = self.vpn_host.split('//')[-1] if '//' in self.vpn_host else self.vpn_host
                host = host_part.split(':')[0] if ':' in host_part else host_part
                logger.info(f"Используется VPN host из конфигурации: {host}")
            else:
                # Иначе используем IP панели (как раньше)
                host_part = self.host.split('//')[-1]
                host = host_part.split(':')[0] if ':' in host_part else host_part
                logger.info(f"Используется host панели для VPN: {host}")
            
            port = inbounds.get('port', 443)
            network = stream.get('network', 'tcp')
            security = stream.get('security', 'reality')
            
            # Получаем параметры из streamSettings
            xhttp_settings = stream.get('xhttpSettings', {})
            reality = stream.get('realitySettings', {})
            
            # XHTTP параметры
            path = xhttp_settings.get('path', '/')
            xhttp_host = xhttp_settings.get('host', '')
            mode = xhttp_settings.get('mode', 'auto')
            
            # Reality параметры
            pbk = reality.get('publicKey', '')
            if not pbk and 'settings' in reality:
                pbk = reality.get('settings', {}).get('publicKey', '')
            
            fingerprint = reality.get('fingerprint', 'chrome')
            spx = reality.get('spiderX', '/') or '/'
            
            # SNI: для XHTTP берем из xhttpSettings.host, иначе из realitySettings
            if network == 'xhttp' and xhttp_host:
                sni = xhttp_host
            else:
                sni = reality.get('serverName') or (reality.get('target', '').split(':')[0] if reality.get('target') else '') or 'google.com'
            
            # ShortId: может быть строкой или массивом
            short_ids = reality.get('shortIds', [''])
            sid = short_ids[0] if isinstance(short_ids, list) and short_ids else (short_ids if isinstance(short_ids, str) else '')

            # Используем название сервера в tag, если указано, иначе используем user_id
            # Tag должен быть URL-encoded для правильной работы в VPN клиентах
            if server_name:
                tag = quote(server_name, safe='')
            else:
                # Получаем название бренда из переменных окружения для fallback tag
                import os
                vpn_brand_name = os.getenv('VPN_BRAND_NAME', 'Daralla').strip()
                tag = f"{vpn_brand_name}-{user_id}"

            # Генерируем ссылку в зависимости от протокола
            if protocol == 'trojan':
                # TROJAN TCP Reality
                # Для TROJAN password может быть в client['password'] или client['id']
                password = client.get('password') or client.get('id', '')
                
                # Параметры для TROJAN Reality
                # V2RayTun требует параметр type (transport method)
                params = [
                    ("type", network),  # Добавляем type для совместимости с V2RayTun
                    ("security", security),
                    ("pbk", pbk),
                    ("fp", fingerprint),
                    ("sni", sni),
                    ("sid", sid),
                    ("spx", quote(spx)),
                ]
                
                query = "&".join(f"{k}={v}" for k, v in params if v)  # Пропускаем пустые значения
                trojan_link = f"trojan://{quote(password)}@{host}:{port}?{query}#{tag}"
                
                logger.info(f"Сгенерирована TROJAN ссылка для {user_id}: tag='{tag}', server_name='{server_name}'")
                logger.info(f"Полная TROJAN ссылка (первые 200 символов): {trojan_link[:200]}...")
                logger.debug(f"Полная TROJAN ссылка: {trojan_link}")
                logger.debug(f"Параметры ссылки: host={host}, port={port}, network={network}, security={security}")
                
                return trojan_link
            else:
                # VLESS (по умолчанию)
                # Строго в правильном порядке, включая новые параметры.
                # flow обязателен для Vision/Reality — без него VPN-клиент не парсит flow.
                params = [
                    ("type", network),
                ]
                client_flow = (client.get("flow") or "").strip() or None
                if client_flow:
                    params.append(("flow", quote(client_flow, safe="")))
                
                # Добавляем параметры XHTTP если это XHTTP
                if network == "xhttp":
                    params.append(("encryption", "none"))
                    if path:
                        params.append(("path", quote(path)))
                    if xhttp_host:
                        params.append(("host", xhttp_host))
                    if mode:
                        params.append(("mode", mode))
                
                # Добавляем остальные параметры
                params.extend([
                    ("security", security),
                    ("pbk", pbk),
                    ("fp", fingerprint),
                    ("sni", sni),
                    ("sid", sid),
                    ("spx", quote(spx)),
                ])
                
                query = "&".join(f"{k}={v}" for k, v in params)
                vless_link = f"vless://{client['id']}@{host}:{port}?{query}#{tag}"
                
                # Логируем сгенерированную ссылку для отладки
                logger.info(f"Сгенерирована VLESS ссылка для {user_id}: tag='{tag}', server_name='{server_name}'")
                logger.info(f"Полная VLESS ссылка (первые 200 символов): {vless_link[:200]}...")
                logger.debug(f"Полная VLESS ссылка: {vless_link}")
                logger.debug(f"Параметры ссылки: host={host}, port={port}, network={network}, security={security}")
                
                return vless_link

        return 'Клиент не найден.'
    
    async def get_subscription_link(self, user_email: str) -> str:
        """
        Получает подписочную ссылку (sub link) для клиента из X-UI
        
        В 3x-ui подписочные ссылки доступны через эндпоинт /sub/<subId>,
        где subId - это значение поля subId клиента.
        
        Args:
            user_email: Email клиента
            
        Returns:
            Подписочная ссылка вида http://host:port/sub/<subId>
            или пустая строка, если клиент не найден
        """
        await self._ensure_connected()
        try:
            inbounds_list = await self.list()
            if not inbounds_list.get('success', False):
                logger.warning(f"Не удалось получить список inbounds для подписочной ссылки")
                return ""
            
            # Ищем клиента по email
            for inbound in inbounds_list.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        sub_id = client.get('subId', '')
                        if sub_id:
                            # Формируем подписочную ссылку
                            host_part = self.host.split('//')[-1]
                            # Убираем /panel если есть
                            if '/panel' in host_part:
                                host_part = host_part.split('/panel')[0]
                            subscription_link = f"{self.host.split('//')[0]}//{host_part}/sub/{sub_id}"
                            logger.info(f"Подписочная ссылка для {user_email}: {subscription_link}")
                            return subscription_link
                        else:
                            logger.warning(f"Клиент {user_email} найден, но subId пуст")
                            return ""
            
            logger.warning(f"Клиент с email {user_email} не найден для получения подписочной ссылки")
            return ""
        except Exception as e:
            logger.error(f"Ошибка получения подписочной ссылки для {user_email}: {e}")
            return ""
    
    async def get_subscription_links(self, user_email: str, server_name: str = None, flow_override: str = None) -> List[str]:
        """
        Получает VLESS ссылки напрямую из X-UI subscription endpoint.
        
        X-UI в ряде версий не добавляет flow в URL подписки, из‑за чего VPN-клиент не парсит flow.
        Если передан flow_override, он подставляется в каждую VLESS-ссылку (если flow ещё нет).
        
        Args:
            user_email: Email клиента
            server_name: Название сервера для замены tag в ссылках
            flow_override: Значение flow (например xtls-rprx-vision) — подставить в VLESS-ссылки, если отсутствует
        Returns:
            Список VLESS ссылок из X-UI subscription endpoint (с обновленным tag и при необходимости flow)
        """
        await self._ensure_connected()
        try:
            inbounds_list = await self.list()
            if not inbounds_list.get('success', False):
                logger.warning(f"Не удалось получить список inbounds для subscription links")
                return []
            
            # Ищем клиента по email
            for inbound in inbounds_list.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        sub_id = client.get('subId', '')
                        if not sub_id:
                            logger.warning(f"Клиент {user_email} найден, но subId пуст")
                            return []
                        
                        # Формируем URL subscription endpoint X-UI
                        if self.subscription_url:
                            base = self.subscription_url.rstrip('/')
                        else:
                            p = urlparse(self.host)
                            hostname = p.hostname or (p.netloc.split(':')[0] if p.netloc else '')
                            base = f"{p.scheme}://{hostname}:{self.subscription_port}"
                        subscription_url = f"{base}/sub/{sub_id}"
                        
                        # Получаем ссылки из X-UI subscription endpoint
                        try:
                            # Используем сессию без авторизации для публичного endpoint
                            response = await self._client.get(subscription_url, timeout=10)
                            if response.status_code == 200:
                                # X-UI может возвращать тело подписки в base64 (стандартный формат) или plain text
                                text = response.text.strip()
                                try:
                                    decoded = base64.b64decode(text)
                                    decoded_str = decoded.decode('utf-8')
                                    if 'vless://' in decoded_str or 'trojan://' in decoded_str or 'vmess://' in decoded_str:
                                        text = decoded_str
                                except Exception:
                                    pass
                                links = [line.strip() for line in text.split('\n') if line.strip()]
                                
                                # Заменяем tag (название) в ссылках на название сервера, если указано
                                # X-UI может возвращать ссылки с доменом в tag (например, ghosttunnel.space)
                                # Мы заменяем его на красивое название бренда
                                flow_val = (flow_override or "").strip() or None
                                updated_links = []
                                encoded_server_name = quote(server_name, safe='') if server_name else None
                                for link in links:
                                    # При необходимости подставляем flow в VLESS (X-UI часто не добавляет в подписку)
                                    if flow_val and link.startswith("vless://") and "flow=" not in link.split("#")[0]:
                                        before_hash, after_hash = (link.split("#", 1) if "#" in link else (link, None))
                                        if "?" in before_hash:
                                            base, qs = before_hash.split("?", 1)
                                            new_qs = qs + "&flow=" + quote(flow_val, safe="")
                                        else:
                                            base, new_qs = before_hash, "flow=" + quote(flow_val, safe="")
                                        link = f"{base}?{new_qs}" + ("#" + after_hash if after_hash is not None else "")
                                        logger.debug(f"Добавлен flow={flow_val} в VLESS-ссылку подписки")
                                    if server_name:
                                        # VLESS ссылка имеет формат: vless://...?#tag
                                        if '#' in link:
                                            parts = link.split('#', 1)
                                            link_without_tag = parts[0]
                                            updated_link = f"{link_without_tag}#{encoded_server_name}"
                                        else:
                                            updated_link = f"{link}#{encoded_server_name}"
                                    else:
                                        updated_link = link
                                    updated_links.append(updated_link)
                                links = updated_links
                                if server_name:
                                    logger.info(f"Обновлены tag в {len(links)} ссылках на '{server_name}'")
                                if flow_val:
                                    logger.info(f"Подставлен flow в VLESS-ссылки подписки (flow_override={flow_val})")
                                if links:
                                    logger.info(f"Пример обновленной ссылки (первые 150 символов): {links[0][:150]}...")
                                
                                logger.info(f"Получено {len(links)} ссылок из X-UI subscription endpoint для {user_email}")
                                return links
                            else:
                                logger.warning(f"X-UI subscription endpoint вернул статус {response.status_code}")
                                return []
                        except Exception as e:
                            logger.error(f"Ошибка получения ссылок из X-UI subscription endpoint: {e}")
                            return []
            
            logger.warning(f"Клиент с email {user_email} не найден для получения subscription links")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения subscription links для {user_email}: {e}")
            return []

