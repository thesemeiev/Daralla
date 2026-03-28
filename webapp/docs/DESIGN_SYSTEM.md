# Дизайн-система Daralla (webapp)

Краткий гайд для новых экранов и правок. Полный набор токенов задаётся в [`style.css`](../style.css) в `:root` и `[data-theme="light"]`.

## Принципы

1. **Акцент** (`--accent`) — кнопки, ссылки, фокус, выделение. **Семантика** — `--color-success` / ошибки через `--error-text` и токены danger, не смешивать с акцентом по площади.
2. **Отступы** — сетка 8px: `--space-xs` (4px) … `--space-xl` (32px).
3. **Радиусы** — `--radius-sm` (8px), `--radius-md` (10px), `--radius-lg` (12px).
4. **Типографика** — заголовки: `font-family: var(--font-display)` (Outfit). Тело: `var(--font-body)` (Inter + системный стек).

## Таблица токенов (имя → назначение)

| Токен | Тёмная тема (идея) | Светлая тема |
|-------|-------------------|--------------|
| `--accent` | #4a9eff | тот же |
| `--accent-hover` / `--accent-active` | Состояния кнопок | тот же |
| `--accent-muted` … `--accent-ring` | Полупрозрачные варианты для фона, бордеров, focus ring | переопределены мягче в `[data-theme="light"]` |
| `--color-success` | #34c759 | тот же |
| `--color-danger` | #ff6b6b | через error-токены |
| `--bg-page` | #1a1a1a | #f5f5f5 |
| `--bg-elevated` / `--card-bg` | #1c1e22 | #f0f0f4 |
| `--bg-page-mesh` | Радиальный акцент над фоном | слабее |
| `--text-primary` / `--text-secondary` / `--text-tertiary` | Основной / вторичный / подписи | см. CSS |
| `--border-subtle` / `--border-strong` | = границы карточек | см. CSS |
| `--shadow-card` / `--shadow-float` / `--shadow-modal` | Карточки / модалки | светлая тема — лёгкие тени |
| `--font-display` | Outfit | тот же |
| `--font-body` | Inter, system-ui… | тот же |

Полные значения смотрите в начале `style.css`.

## Как добавлять экран

1. Фон страницы наследуется от `body` (mesh + шум); не задавайте лишний сплошной `#000`.
2. Карточки: `background: var(--card-bg)`, `border: 1px solid var(--card-border)`, `border-radius: var(--radius-lg)`, при необходимости `box-shadow: var(--shadow-card)`.
3. Заголовок страницы: `h1` в шапке или `.page-section-title` — шрифт display подтянется из CSS.
4. Кнопка основного действия: `.btn-primary` (уже на токенах).
5. Поля: `.form-group` + инпуты; фокус — `border-color: var(--accent)` и при необходимости `box-shadow` с `--accent-ring`.
6. Не вводите новые хексы без причины; при исключении оставьте комментарий в CSS.

## Чеклист экранов (приёмка визуала)

- [ ] Лендинг (`#page-landing`) — hero, кнопки, списки
- [ ] Вход / регистрация
- [ ] Подписки, ключи, покупка / продление
- [ ] Профиль, карта, события (если используются)
- [ ] Админ: статистика, пользователи, серверы, группы, коммерция, рассылки
- [ ] Модалки и диалоги
- [ ] Нижняя навигация (тёмная / светлая тема)
- [ ] WebView Telegram (шрифты, скролл, safe-area)

## Атмосфера

- **Mesh:** `--bg-page-mesh` на `body`, `--landing-mesh` на лендинге.
- **Шум:** `body::before` — низкая opacity, `pointer-events: none`.

## Версия стилей

После крупных правок поднимайте `?v=` у `style.css` в [`index.html`](../index.html).

## PWA / meta

[`manifest.json`](../manifest.json) и `theme-color` в `index.html`: `#1a1a1a` совпадает с `--bg-page` (тёмная шапка браузера / splash). Автономные страницы [`offline.html`](../offline.html) и fallback в `sw.js` оставлены с явными хексами без подключения `style.css`.
