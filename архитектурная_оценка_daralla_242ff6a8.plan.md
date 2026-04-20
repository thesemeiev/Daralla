---
name: Архитектурная оценка Daralla
overview: Проверил архитектуру, зависимости, рантайм и quality hotspots. План переводит проект в надежный и прозрачный модульный монолит без перехода на микросервисы.
todos:
  - id: baseline-metrics
    content: "Зафиксировать базовые метрики текущего монолита: latency/error-rate по /api/*, webhook SLA, время деплоя и частоту инцидентов."
    status: pending
  - id: refactor-hotspots
    content: "Провести приоритетный рефакторинг hotspots: webapp/app.js, bot/web/routes/api_user.py, bot/services/xui_service.py, bot/services/subscription_manager.py."
    status: pending
  - id: strengthen-tests
    content: Добавить unit/integration/e2e тесты на ключевые пользовательские, подписочные и платежные сценарии с порогами покрытия.
    status: pending
  - id: improve-observability
    content: Внедрить структурные логи, correlation-id, метрики и алерты для API, фоновых задач и интеграций.
    status: pending
  - id: harden-operations
    content: Укрепить CI/CD и runtime: безопасный deploy, healthchecks/readiness, runbook, backup-restore drill.
    status: pending
  - id: architecture-governance
    content: Зафиксировать архитектурные правила (слои, границы модулей, API контракты, ADR) и проверить их линтерами/чеклистами.
    status: pending
isProject: false
---

# Оценка архитектуры и план эволюции

## Текущее состояние (по коду)
- Проект уже является **модульным монолитом**, а не «плоским» монолитом:
  - единый runtime: [`bot/bot.py`](bot/bot.py)
  - единый контейнер: [`docker-compose.yml`](docker-compose.yml)
  - единая БД SQLite: [`bot/db/__init__.py`](bot/db/__init__.py)
  - frontend + backend в одном деплое: [`webapp/app.js`](webapp/app.js), [`bot/web/routes/static.py`](bot/web/routes/static.py)
- Главный технический риск сейчас — **крупные и сильно связанные файлы**, а не отсутствие микросервисов:
  - [`webapp/app.js`](webapp/app.js) (~7967 строк)
  - [`webapp/style.css`](webapp/style.css) (~5620 строк)
  - [`bot/web/routes/api_user.py`](bot/web/routes/api_user.py) (~915 строк)
  - [`bot/services/xui_service.py`](bot/services/xui_service.py) (~1062 строки)
  - [`bot/services/subscription_manager.py`](bot/services/subscription_manager.py) (~909 строк)
- Тесты есть, но не покрывают главные hotspots в достаточной глубине: [`tests/`](tests/)

## Рекомендация
- **Да, рефакторинг нужен.**
- **Микросервисы не нужны для ваших текущих целей.**
- Оптимально: сделать **прозрачный и надежный модульный монолит** с четкими границами, тестами, наблюдаемостью и предсказуемым релизным процессом.

## Почему фокус на монолите правильный
- В текущем коде сильная связность через общий контекст и общую БД:
  - [`bot/app_context.py`](bot/app_context.py)
  - [`bot/db/__init__.py`](bot/db/__init__.py)
- Много orchestration в HTTP-роутах, поэтому сначала нужно отделить transport от domain:
  - [`bot/web/routes/api_user.py`](bot/web/routes/api_user.py)
  - [`bot/web/routes/admin_subscriptions.py`](bot/web/routes/admin_subscriptions.py)
- Операционная сложность микросервисов добавит риски раньше времени, а текущий CI/CD рассчитан на единый деплой:
  - [` .github/workflows/deploy.yml`](.github/workflows/deploy.yml)

## Целевой путь (без микросервисов)

```mermaid
flowchart LR
  currentState[CurrentMonolith] --> moduleBoundaries[ClearModuleBoundaries]
  moduleBoundaries --> testSafetyNet[TestSafetyNet]
  testSafetyNet --> observability[ObservabilityAndAlerts]
  observability --> reliableOps[ReliableOperations]
  reliableOps --> transparentProject[TransparentAndMaintainableMonolith]
```

## Этапы
1. **Архитектурная ясность (1-2 недели)**
   - Разбить крупные файлы на модули с четкой ответственностью:
     - [`webapp/app.js`](webapp/app.js)
     - [`bot/web/routes/api_user.py`](bot/web/routes/api_user.py)
     - [`bot/services/xui_service.py`](bot/services/xui_service.py)
     - [`bot/services/subscription_manager.py`](bot/services/subscription_manager.py)
   - Утвердить правила слоев: `routes -> services -> db`, без бизнес-логики в роутинге.
   - Добавить ADR-документ(ы) по ключевым решениям.
2. **Тестовый каркас и качество (1-2 недели)**
   - Добавить тесты на критичные пользовательские потоки: регистрация, trial, платеж, продление, синхронизация.
   - Для фронтенда ввести минимальный тестовый контур и линтер.
   - В CI добавить пороги качества: покрытие и базовые quality gates.
3. **Наблюдаемость и отказоустойчивость (1-2 недели)**
   - Ввести structured logging и correlation-id для вебхуков, API и фоновых задач.
   - Добавить метрики по платежам, sync и ошибкам интеграций.
   - Настроить алерты на деградации: webhook errors, sync failures, payment stuck.
4. **Надежные операции (1-2 недели)**
   - Укрепить deploy-процесс: проверка health/readiness после релиза, rollback-чеклист.
   - Регулярно тестировать backup/restore сценарий.
   - Описать runbook инцидентов для типовых сбоев.

## Риски и как снизить
- Риск регрессий при распиле крупных файлов → делать инкрементально и прикрывать интеграционными тестами.
- Риск роста сложности без пользы → каждый этап завершать измеримым результатом (SLO, MTTR, частота инцидентов, время релиза).
- Риск непонятного кода после рефакторинга → фиксировать архитектурные правила и code review checklist в документации.