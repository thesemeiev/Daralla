# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY bot/ ./bot/

# Копируем изображения для меню
COPY images/ ./images/

# Копируем веб-приложение
COPY webapp/ ./webapp/

# Копируем скрипты (миграции и т.д.)
COPY scripts/ ./scripts/

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Открываем порт для webhook'ов (Quart + Hypercorn)
EXPOSE 5000

# Запускаем бота (Telegram polling + веб-сервер Quart/Hypercorn на 5000)
CMD ["python", "-m", "bot"]
