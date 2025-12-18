# Быстрый деплой в тестовую среду

## Команды для деплоя из редактора

### 1. Переключитесь на ветку test

```bash
git checkout test
```

Если ветки `test` еще нет:
```bash
git checkout -b test
```

### 2. Добавьте изменения

```bash
git add .
```

Или добавьте конкретные файлы:
```bash
git add bot/bot.py
git add bot/handlers/admin/admin_test_payment.py
# и т.д.
```

### 3. Закоммитьте изменения

```bash
git commit -m "Fix: исправлена проблема с app в admin_test_payment"
```

Или более описательное сообщение:
```bash
git commit -m "Fix: исправлен get_globals() в admin_test_payment для правильного получения app из sys.modules"
```

### 4. Запушьте в ветку test

```bash
git push origin test
```

Если ветка `test` еще не существует на удаленном репозитории:
```bash
git push -u origin test
```

### 5. Деплой запустится автоматически!

После пуша GitHub Actions автоматически:
- Запустит тесты
- Задеплоит код на тестовый сервер
- Пересоберет и перезапустит контейнеры

## Полная последовательность команд (копировать целиком)

```bash
# 1. Переключиться на ветку test
git checkout test

# 2. Добавить все изменения
git add .

# 3. Закоммитить
git commit -m "Описание изменений"

# 4. Запушить
git push origin test
```

## Проверка деплоя

После пуша:

1. **Проверьте статус в GitHub Actions:**
   - Перейдите: `https://github.com/thesemeiev/Daralla/actions`
   - Найдите workflow "Deploy Daralla Bot to Test Server"
   - Проверьте, что он запустился и выполняется успешно

2. **Проверьте логи на сервере:**
   ```bash
   ssh root@your-test-server
   cd /root/Daralla
   sudo docker compose logs -f telegram-bot
   ```

## Если нужно задеплоить конкретные файлы

```bash
# Переключиться на test
git checkout test

# Добавить только нужные файлы
git add bot/bot.py
git add bot/handlers/admin/admin_test_payment.py

# Закоммитить
git commit -m "Fix: исправлена проблема с app"

# Запушить
git push origin test
```

## Если нужно обновить код из main в test

```bash
# Переключиться на test
git checkout test

# Получить последние изменения
git pull origin test

# Если нужно взять изменения из main
git merge main

# Или взять конкретные коммиты
git cherry-pick <commit-hash>

# Запушить
git push origin test
```

## Быстрая команда одной строкой

Если вы уже в ветке `test` и хотите быстро задеплоить все изменения:

```bash
git add . && git commit -m "Update" && git push origin test
```

## Откат изменений (если что-то пошло не так)

```bash
# Отменить последний коммит (но оставить изменения)
git reset --soft HEAD~1

# Или полностью отменить изменения
git reset --hard HEAD~1

# Если уже запушили, нужно сделать force push (осторожно!)
git push origin test --force
```

## Полезные команды для проверки

```bash
# Проверить текущую ветку
git branch

# Проверить статус изменений
git status

# Посмотреть последние коммиты
git log --oneline -5

# Посмотреть различия
git diff

# Посмотреть что будет закоммичено
git diff --cached
```

## Настройка Git (если еще не настроен)

```bash
# Установить имя пользователя
git config --global user.name "Your Name"

# Установить email
git config --global user.email "your.email@example.com"

# Сохранить учетные данные (чтобы не вводить пароль каждый раз)
git config --global credential.helper store
```

## Автоматизация через скрипт

Можно создать скрипт `deploy-test.sh`:

```bash
#!/bin/bash
# deploy-test.sh

echo "🚀 Деплой в тестовую среду..."

# Проверка текущей ветки
current_branch=$(git branch --show-current)
if [ "$current_branch" != "test" ]; then
    echo "⚠️  Вы не в ветке test. Переключаюсь..."
    git checkout test
fi

# Добавление изменений
echo "📦 Добавляю изменения..."
git add .

# Коммит
echo "💾 Коммичу изменения..."
read -p "Введите сообщение коммита: " commit_message
git commit -m "$commit_message"

# Пуш
echo "🚀 Пущу в ветку test..."
git push origin test

echo "✅ Готово! Деплой запущен автоматически через GitHub Actions."
echo "📊 Проверьте статус: https://github.com/thesemeiev/Daralla/actions"
```

Сделать скрипт исполняемым:
```bash
chmod +x deploy-test.sh
```

Использовать:
```bash
./deploy-test.sh
```

