# Переход на py3xui

**Статус: выполнен.** Класс `X3` в `bot/services/xui_service.py` реализован через библиотеку [py3xui](https://github.com/iwatkot/py3xui) (AsyncApi). Публичный интерфейс сохранён для совместимости.

Ниже — справочный план миграции (как было сделано).

## 1. Установка

```bash
pip install py3xui
```

В `requirements.txt` добавить строку:
```
py3xui>=0.5.5
```

## 2. Соответствие методов (X3 → py3xui)

| Твой метод | py3xui | Примечание |
|------------|--------|------------|
| `client_exists(email)` | `await api.client.get_by_email(email) is not None` | Прямая замена |
| `get_client_info(email)` | `await api.client.get_by_email(email)` | Вернёт объект `Client` (Pydantic), при необходимости привести к dict |
| `get_client_expiry_time(email)` | `(await api.client.get_by_email(email)).expiry_time` | Поле есть в `Client` |
| `list()` | `await api.inbound.get_list()` | py3xui возвращает `list[Inbound]`, а не `{success, obj}` — см. п. 4 |
| `addClient(...)` | `await api.client.add(inbound_id, [Client(...)])` | Нужно собирать объект `Client` (id, email, limit_ip, expiry_time, flow, tg_id, sub_id) |
| `setClientExpiry(email, ts, flow=...)` | Получить клиента, выставить `expiry_time`, вызвать `api.client.update(client.id, client)` | При смене flow — обновить и flow |
| `extendClient(email, days, flow=...)` | То же: взять клиента, прибавить дни к `expiry_time`, `update` | |
| `updateClientLimitIp(email, limit_ip, flow=...)` | Получить клиента, выставить `limit_ip`, `update` | |
| `updateClientName(email, new_name)` | Получить клиента, выставить `sub_id` (или аналог имени), `update` | В 3x-ui имя часто хранится в subId |
| `deleteClient(email)` | Сначала `get_by_email(email)` → взять `client.id`; найти inbound (см. ниже) → `api.client.delete(inbound_id, client.id)` | py3xui удаляет по `(inbound_id, client_uuid)` |
| `get_online_clients_count()` | `len(await api.client.online())` | `online()` возвращает список email |
| `get_client_traffic(email)` | Через `get_by_email` у Client есть поля `up`, `down`, `total` или использовать `get_traffic_by_id(client.id)` если есть | Уточнить по актуальной версии py3xui |

## 3. Чего в py3xui нет — оставить свою реализацию

Эти вещи в библиотеке не предусмотрены, их нужно оставить в проекте (но можно вызывать поверх py3xui данных):

- **`link(user_id, server_name)`** — генерация VLESS/TROJAN ссылки по своим правилам (vpn_host, Reality/XHTTP, tag). Оставить текущую логику, получая список inbounds через `api.inbound.get_list()` и разбирая параметры из объектов Inbound.
- **`get_subscription_links(user_email, server_name, flow_override)`** — твой формат подписочного URL и подстановка flow. Оставить свою реализацию; при необходимости брать список inbounds через py3xui.
- **`sync_flow_for_all_clients(flow_value)`** — массовое обновление flow по всем клиентам. Реализовать циклом: `inbound.get_list()` → по каждому inbound и клиенту обновить flow → `api.client.update(...)`.
- **Доп. параметры сервера**: `vpn_host`, `subscription_port`, `subscription_url` — не входят в py3xui, хранить в своей обёртке и использовать в `link()` и `get_subscription_links()`.

## 4. Формат `list()` и совместимость

Сейчас код ожидает ответ в виде:

```python
{"success": True, "obj": [{"id": 1, "protocol": "vless", "settings": "{...}", "streamSettings": {...}, ...}, ...]}
```

У py3xui `api.inbound.get_list()` возвращает `list[Inbound]` (Pydantic-модели).

Варианты:

**A) Адаптер (рекомендуется)**  
Ввести тонкий класс-обёртку (например, сохранить имя `X3` или назвать `X3Adapter`), который внутри создаёт `AsyncApi`, при первом обращении делает `await api.login()`, и реализует те же методы, что и сейчас:

- Для операций с клиентами — делегирует в `api.client.*` / `api.inbound.get_list()`.
- Для `list()` — получает `await api.inbound.get_list()`, конвертирует каждый `Inbound` в словарь в формате `{ "id", "protocol", "settings", "streamSettings", ... }`, и возвращает `{"success": True, "obj": [...]}`. Так весь существующий код (subscription_manager, sync_manager, xui_service для link/get_subscription_links и т.д.) продолжит работать без правок.

**B) Постепенно менять вызовы**  
Переписать все места, где используется `xui.list()` и разбор `response['obj']`, на работу с `list[Inbound]` и полями моделей. Объём изменений больше (sync_manager, xui_service в нескольких местах).

## 5. Где создаётся X3 и как перейти на py3xui

Сейчас:

- `bot/services/server_manager.py`: в цикле создаётся `X3(login=..., password=..., host=..., vpn_host=..., subscription_port=..., subscription_url=...)`.
- Ожидается интерфейс: `x3` с методами `addClient`, `extendClient`, `setClientExpiry`, `updateClientLimitIp`, `updateClientName`, `deleteClient`, `list`, `client_exists`, `get_client_info`, `get_client_expiry_time`, `get_online_clients_count`, `get_client_traffic`, `link`, `get_subscription_links`, при необходимости `sync_flow_for_all_clients`, `list_quick`.

Шаги:

1. Добавить в проект адаптер (см. п. 6).
2. В `server_manager.py` вместо создания `X3(...)` создавать адаптер, в конструктор которого передать:
   - аргументы для `AsyncApi(host, username, password, use_tls_verify=not host.startswith("https://"))` (или по необходимости отключать проверку TLS),
   - плюс `vpn_host`, `subscription_port`, `subscription_url`.
3. В адаптере хранить `AsyncApi` и эти доп. параметры; при первом вызове любого метода вызывать `await self._api.login()` (аналог твоего `_ensure_connected`).
4. Остальной код (subscription_manager, sync_manager, api_admin, subscription route и т.д.) продолжает вызывать те же методы у `server["x3"]` — меняется только реализация внутри адаптера.

## 6. Пример структуры адаптера

Файл можно оставить `bot/services/xui_service.py` или вынести в `bot/services/xui_adapter.py`:

```python
# bot/services/xui_service.py (или xui_adapter.py)

import logging
from py3xui import AsyncApi
from py3xui import Client  # для add/update

logger = logging.getLogger(__name__)


class X3:
    """Обёртка над py3xui AsyncApi с тем же интерфейсом, что и раньше."""

    def __init__(self, login, password, host, vpn_host=None, subscription_port=2096, subscription_url=None):
        self._api = AsyncApi(
            host,
            login,
            password,
            use_tls_verify=host.startswith("https://"),
        )
        self.login = login
        self.password = password
        self.host = host
        self.vpn_host = vpn_host
        self.subscription_port = subscription_port or 2096
        self.subscription_url = (subscription_url or "").strip() or None
        self._logged_in = False

    async def _ensure_login(self):
        if not self._logged_in:
            await self._api.login()
            self._logged_in = True

    async def list(self, timeout=15):
        await self._ensure_login()
        inbounds = await self._api.inbound.get_list()
        # Конвертировать list[Inbound] в формат {"success": True, "obj": [...]}
        obj = [_inbound_to_dict(inb) for inb in inbounds]
        return {"success": True, "obj": obj}

    async def client_exists(self, user_email):
        await self._ensure_login()
        return (await self._api.client.get_by_email(user_email)) is not None

    async def get_client_info(self, user_email, timeout=15):
        await self._ensure_login()
        c = await self._api.client.get_by_email(user_email)
        if c is None:
            return None
        return _client_to_dict(c)  # реализовать по полям Client

    async def deleteClient(self, user_email, timeout=15):
        await self._ensure_login()
        client = await self._api.client.get_by_email(user_email)
        if not client:
            return
        inbound_id = await _find_inbound_id_for_client(self._api, user_email)
        if inbound_id is not None:
            await self._api.client.delete(inbound_id, client.id)

    # addClient, setClientExpiry, extendClient, updateClientLimitIp, updateClientName —
    # реализовать через Client(...) и api.client.add / api.client.update.
    # link(), get_subscription_links(), sync_flow_for_all_clients() — оставить твою логику,
    # но брать данные через self.list() (уже в формате obj) или через api.inbound.get_list().
```

Функции `_inbound_to_dict`, `_client_to_dict`, `_find_inbound_id_for_client` нужно реализовать по структуре моделей py3xui (Inbound/Client), чтобы получать тот же формат, что и текущий парсинг по `response['obj']` и `inbound['settings']`.

## 7. Удаление клиента по email (inbound_id)

В py3xui `client.delete(inbound_id, client_uuid)` требует оба аргумента. По email у тебя есть только клиент. Варианты:

- Если у `Client` в py3xui при `get_by_email` приходит `inbound_id` — использовать его.
- Если нет — один раз получить `inbounds = await api.inbound.get_list()` и по каждому inbound смотреть, есть ли в его клиентах этот email; как только нашли — вызвать `api.client.delete(inbound.id, client.id)`. Эту логику вынести в `_find_inbound_id_for_client` и использовать в `deleteClient` в адаптере.

## 8. Порядок внедрения

1. Добавить `py3xui` в зависимости, убедиться что тесты/приложение поднимаются.
2. Реализовать адаптер в одном файле (оставив старый X3 закомментированным или под другим именем).
3. Реализовать в адаптере по очереди: `_ensure_login`, `list` (с конвертацией), `client_exists`, `get_client_info`, `get_client_expiry_time`, `deleteClient`, `addClient`, `setClientExpiry`, `extendClient`, `updateClientLimitIp`, `updateClientName`, `get_online_clients_count`, `get_client_traffic`.
4. Перенести в адаптер вызовы `link`, `get_subscription_links`, `sync_flow_for_all_clients` (логику оставить, данные брать из py3xui или из своего `list()`).
5. В `server_manager` переключить создание на новый X3 (адаптер).
6. Прогнать тесты и ручные сценарии (подписка, синхронизация, админка).
7. Удалить старый реализационный код (тысячи строк в xui_service.py), оставив только адаптер и кастомные методы.

После перехода логика входа, ретраев и сессии будет в py3xui; твой код станет короче и проще поддерживать. Если позже перейдёшь на Quart или один общий event loop, адаптер можно оставить тем же — он уже async.
