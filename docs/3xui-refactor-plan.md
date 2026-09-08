# План рефакторинга под 3x-ui v3+

## Цель

Перевести проект с модели "обходить ограничения старой 3x-ui" к модели "управлять продуктом и политиками поверх современной 3x-ui".

Главная идея:
- 3x-ui уже стал более зрелой мульти-серверной платформой;
- Daralla не должен дублировать то, что панель делает лучше;
- Daralla должен управлять доступом, политиками, жизненным циклом подписок, health-логикой и продуктовым сценариями.

---

## Принципы архитектуры

1. Источник истины — база данных Daralla.
2. 3x-ui — транспорт/исполнение/хостинг, а не центр бизнес-логики.
3. Группы серверов и health monitoring — остаются, но становятся проще.
4. Sync и reconcile — только для поддержания согласованности, а не как основная бизнес-логика.
5. Вся логика, которая дублирует нативные возможности 3x-ui, должна быть сокращена.
6. Новый слой политики должен решать: кто, куда, когда и по каким правилам может быть подключён.

---

## Что оставить

### 1. Server groups
Группы серверов остаются важной частью архитектуры.

Нужны:
- логическая группировка серверов;
- выбор pool для подписки;
- соблюдение локаций/трафика/доступности;
- operational контроль.

Но их модель должна стать проще:
- `group` = набор доступных серверов;
- `server` = endpoint/agent;
- `subscription` = привязка к группе/политике;
- не держать сложную графовую логику внутри каждого сервера.

### 2. MultiServerManager
Оставить как runtime registry и health-aware coordinator.

Его задача:
- держать активный список серверов;
- проверять health;
- отдавать доступные серверы под текущие политики;
- не превращать его в "многоуровневую фабрику бизнес-логики".

### 3. SyncManager
Оставить как механизм согласованности между Daralla и 3x-ui.

Нужные сценарии:
- sync from DB to panel;
- cleanup stale state;
- enforce active/inactive policy;
- detect drift;
- resolve missing/extra clients.

Главное: sync должен быть чистым и понятным, а не разросшимся "методом правки всего подряд".

### 4. Subscription lifecycle
Оставить как центральный продуктовый слой.

Тут должны быть:
- активация;
- деактивация;
- продление;
- привязка к группе/серверу;
- статусы и события.

Это именно ценность Daralla, а не 3x-ui.

---

## Что сократить и убрать

### 1. Избыточный кастомный reconcile
Если 3x-ui уже умеет делать большую часть нативной синхронизации корректнее, то ряд ручных reconcile-процессов надо уменьшить.

Убрать/сократить:
- сложные ветки "исправить состояние на каждом сервере";
- дублирование логики в нескольких слоях;
- ручные попытки "достроить" то, что должно быть нативным поведением panel.

### 2. Ручные обходы старых допущений
Нужно убрать код, который существует только потому, что когда-то проект рассчитывал на старые API-предположения.

Примеры:
- кастомные адаптации под старые схемы клиента;
- повторяющиеся проверки типовых проблем панели;
- логика на уровне "если panel ведёт себя как старый API, тогда делаем X" в бизнес-процессах.

### 3. Сложные server-to-subscription привязки
Если привязка к серверу уже выражена через группу и политический слой, то не нужно держать тяжёлую графовую модель "подписка -> серверы -> состояния -> обвязки".

Нужно оставить минимально необходимое:
- подписка привязана к группе или серверу;
- сервер выбирается по политике и health;
- panel is authoritative runtime state.

---

## Что добавить

### 1. Policy layer
Новый слой должен решать бизнес-правила и ставить их выше низкоуровневых вызовов панели.

Пример ответственности:
- подходит ли подписка для этой группы;
- доступен ли сервер по health;
- какой сервер выбрать при резервировании;
- какие типы клиентов активны/неактивны;
- можно ли применять fallback;
- что делать при stale state.

### 2. Drift detection
Introduce бизнес-слой, который понимает:
- client есть в DB, но не на панели;
- client есть на панели, но не в DB;
- client привязан к другому серверу, než ожидалось;
- подписка активна, но нет активных panel entries;
- сервер в группе считается healthy, но реально деградирует.

### 3. Fallback and resilience layer
Нужно добавить понятный сценарий:
- основной сервер недоступен;
- резервный сервер доступен;
- policy decides how to move/switch active assignment;
- admin or automation sees reason clearly.

### 4. Clear service responsibilities
Нужно разделить ответственности так, чтобы не было "всё в одном сервисе".

Recommended split:
- `panel_adapter` — low-level 3x-ui API integration
- `server_registry` — state of servers and groups
- `sync_service` — enforce DB->panel consistency
- `policy_service` — selection, routing, fallback
- `subscription_service` — lifecycle and state
- `observability_service` — health, drift, warnings

---

## План по фазам

### Фаза 1. Анализ и стабилизация
Цель: остановить лавину новых костылей.

Задачи:
- собрать все места, где проект обходит 3x-ui API;
- выделить старые ветки, привязанные к legacy assumptions;
- зафиксировать текущую корректность тестами;
- определить критические сценарии for drift, sync, health.

Результат:
- понятный список кастомных обходов;
- список мест, которые нужно обнулить;
- baseline тестов для ключевых бизнес-процессов.

### Фаза 2. Сокращение кастомной логики
Цель: уменьшить дублирование и убрать работы, которые уже делают нативные функции 3x-ui.

Задачи:
- убрать/обернуть legacy compatibility logic;
- оставить минимально необходимый panel adapter;
- сократить custom reconcile loops;
- перевести server routing в policy-first модель.

Результат:
- thinner adapter layer;
- меньше уязвимых мест;
- меньше конфликтов между panel и DB.

### Фаза 3. Новый policy layer
Цель: сделать Daralla действительно "операторской" системой, а не копией панели.

Задачи:
- появление policy service;
- server selection logic;
- health/fallback logic;
- drift detection;
- clear subscription-to-group rules.

Результат:
- управляемый доступ;
- прозрачные правила; 
- меньше ручных операций.

### Фаза 4. Оптимизация и масштабирование
Цель: сделать архитектуру устойчивой к росту количества серверов, клиентов и групп.

Задачи:
- повысить observability;
- сделать deterministic sync;
- добавить operational metrics;
- снизить risk multi-server drift.

Результат:
- поддерживаемая multi-node модель;
- лучшее понимание состояния в production;
- меньшая вероятность разрушительного рассинхрона.

---

## Приоритетность

### High priority
1. Убрать legacy-обходы и кастомные compatibility ветки.
2. Разделить panel adapter и business logic.
3. Упростить server group model.
4. Добавить drift detection.
5. Внедрить policy layer for routing and fallback.

### Medium priority
1. Улучшить health scoring.
2. Сделать unified sync/cleanup policy.
3. Сформировать observability around panel health and client state.

### Low priority
1. Дополнительные административные фичи.
2. Значительное расширение UI/операционных панелей.
3. Новые модели управления, пока основа не стабилизирована.

---

## Критерии успеха

Проект можно считать успешным, если:
- 3x-ui используется как runtime backend, а не как "деньги и логика";
- Daralla явно управляет политиками, а не кастомными обходами;
- sync drift сокращён до управляемого уровня;
- health и fallback работают предсказуемо;
- код стал проще, понятнее и легче сопровождать;
- нет дублирования между `server_manager`, `sync_manager`, `subscription_manager` и panel adapter.

---

## Итог

Правильный путь — не строить собственную "панель поверх панели". Правильный путь — сделать Daralla системным оркестратором:
- серверы;
- группы;
- подписки;
- политика доступа;
- health and resilience;
- sync consistency;
- product logic.

3x-ui v3+ уже достаточно зрелый, чтобы удерживать базовый runtime, а Daralla должна концентрироваться на ценности продукта, а не на костылях совместимости.

---

## Следующий шаг

Нужно перейти от этого документа к конкретному refactor map:
- что именно убрать в текущих сервисах;
- как поменять ответственность между модулями;
- какой порядок модификаций по файлам и сервисам;

---

## Операционный план по файлам и сервисам

### 1. Разделить низкоуровневый адаптер от бизнес-логики

#### Оставить как thin adapter
- `apps/backend/src/daralla_backend/services/xui_panel_client.py`
- `apps/backend/src/daralla_backend/services/xui_helpers.py`
- `apps/backend/src/daralla_backend/services/xui_service.py` в части, связанной с raw panel operations

#### Что должно уйти из бизнес-логики
- кастомные ветки, которые пытаются воспроизвести поведение панели;
- прямые обходы legacy API-несовместимости;
- код, который принимает решения о server state на уровне panel internals.

#### Что сделать
- ограничить адаптер только тем, что нужно для вызова панели;
- перевести принятие решений о выборе сервера, группы и политики в отдельный слой;
- убрать “магические” ветви в `xui_service` там, где логика фактически уже сырая и дублирует panel behavior.

### 2. Упростить `MultiServerManager`

Файл:
- `apps/backend/src/daralla_backend/services/server_manager.py`

#### Что оставить
- registry of servers;
- health status;
- active/inactive state;
- group view by server group;
- runtime selection of candidate servers.

#### Что убрать
- сложную бизнес-логику выбора и синка, которая по факту дублирует policy layer;
- обработку деталей panel state внутри manager;
- слишком много действий, которые должны жить в `policy_service` / `subscription_service`.

#### Цель после рефакторинга
`MultiServerManager` должен быть registry + selector, а не “оркестратор всего жизненного цикла подписки”.

### 3. Выделить `PolicyService`

Новый сервис, который должен отвечать за:
- доступность группы;
- подходящий сервер под подписку;
- fallback rule;
- health-based routing;
- правила для активной/неактивной подписки;
- server selection for drift and recovery.

#### Пример ответственности
- “эта подписка может работать только в группе A”; 
- “сервер X недоступен, используем Y”; 
- “в группе нет живых серверов — удерживаем состояние и сигнализируем”; 
- “подписка активна, но panel drift detected — попробовать recover or mark stale”.

### 4. Упростить `SyncManager`

Файл:
- `apps/backend/src/daralla_backend/services/sync_manager.py`

#### Что оставить
- serialisation of sync operations;
- DB->panel convergence;
- cleanup of stale state;
- periodic reconciliation of active subscriptions.

#### Что сократить
- все ветки, которые включают тонкую business logic по каждому серверу без явного policy context;
- слишком большой набор “исправлений” panel drift без ясного правила;
- дублирование с `SubscriptionManager`.

#### Цель после рефакторинга
`SyncManager` должен быть чистым executor согласованности, а не местом, где решаются сложные policy rules.

### 5. Сузить роль `SubscriptionManager`

Файл:
- `apps/backend/src/daralla_backend/services/subscription_manager.py`

#### Что оставить
- lifecycle of subscription state;
- billing/renewal flows aligned with product rules;
- assignment of subscriptions to groups or servers;
- status transitions.

#### Что убрать/перенести
- direct low-level server operations, где это уже покрыто panel adapter;
- “repair logic” in place of proper policy and drift detection;
- hand-crafted server-specific workarounds.

#### Итог
`SubscriptionManager` должен управлять бизнес-формой подписки, а не повторять детали работы 3x-ui в каждом сценарии.

### 6. Чётко разделить `DB` и `panel` источники истины

Существующие файлы:
- `apps/backend/src/daralla_backend/db/servers_db.py`
- `apps/backend/src/daralla_backend/db/subscriptions_db.py`

#### Правило
- DB = canonical source for product state;
- panel = runtime + execution state;
- drift is an operational fact, not a reason to build a huge custom repair system.

#### Что важно
- не держать у себя одновременно слишком много “временных фиксов” для panel state;
- использовать явный статус `drift`, `stale`, `recovered`, `failed`;
- держать объяснение, почему state differs.

### 7. Добавить `drift` и `health` service

Новый слой, который должен отвечать за:
- состояние сходства между DB и panel;
- health score per server;
- warnings and operational incidents;
- recovery actions after failed sync.

#### Минимальный список состояний
- `healthy`
- `degraded`
- `stale`
- `drift`
- `unavailable`
- `recovered`

### 8. Существенно сократить кастомную compatibility logic

Файлы, которые могут быть пересмотрены:
- `xui_helpers.py`
- `xui_panel_client.py`
- `xui_service.py`

#### Правило
Если функциональность уже существует как нативная capability панели, то Daralla не должен дублировать ее в своём code path.

#### Приоритет задач
1. Упрощение raw client layer;
2. Сокращение incompatible protocol branches;
3. Сокращение legacy assumptions;
4. Сведение всех panel idiosyncrasies в одном place.

---

## Рекомендуемый порядок внедрения

### Sprint 1 — стабилизация
- зафиксировать текущие сценарии sync и drift;
- выявить все legacy branch-ветки;
- добавить тесты на базовые сценарии mismatched state;
- снять часть ручных repair logic в отдельный diagnostic layer.

### Sprint 2 — выделение policy layer
- создать новый policy service;
- перенести из server manager и subscription manager правила выбора сервера;
- привязать group selection к политике;
- дать fallback logic и health-driven semantics.

### Sprint 3 — clean-up adapter layer
- сделать thin 3x-ui adapter;
- убрать повторяющиеся ветки в panel client;
- ограничить panel access to essential operations;
- устранить устаревшие compatibility assumptions.

### Sprint 4 — drift and observability
- добавить health scoring and drift monitoring;
- визуализировать bad states;
- сделать operational logs for recovery and sync anomalies.

### Sprint 5 — reduction and simplification
- удалить старый code path, который больше не нужен;
- упростить многослойный sync;
- уменьшить риск “дублирования логики по всем сервисам”.

---

## Ключевая метрика успеха

После рефакторинга должно стать так:
- `server_manager` = registry and health selector;
- `sync_manager` = consistency executor;
- `subscription_manager` = product lifecycle;
- `policy_service` = routing, health and fallback decisions;
- `xui_panel_client` = thin API adapter;
- `drift/health` layers = operational visibility and recovery.

Если после такого разбиения всё ещё остаются тяжёлые ветви “исправить состояние панели” внутри subscription logic — архитектура ещё сыровата.

---

## Итоговая цель

Требуется не “переписать 3x-ui внутри Daralla”, а сделать Daralla как продуктовый orchestration layer над 3x-ui v3+.

То есть:
- 3x-ui = runtime and panel backend;
- Daralla = access control, policy, subscription lifecycle, health logic, operational intelligence.

Это основная точка, вокруг которой строится вся дальнейшая работа.

---

## Следующий практический шаг

Следующим действием нужно начать не с новых фич, а с разборки текущих зависимостей между:
- `server_manager.py`
- `sync_manager.py`
- `subscription_manager.py`
- `xui_service.py`
- `xui_panel_client.py`

Именно там сейчас можно найти максимальный набор кастомных обходов и лишней логики, которую надо вырезать до того, как проект уйдёт слишком далеко в сторону собственных panel logic костылей.
- какие тесты дописать перед изменениями.
