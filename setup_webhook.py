#!/usr/bin/env python3
"""
Скрипт для автоматической настройки webhook в YooKassa
"""

import os
import requests
import json
import time
import sys

def get_ngrok_url():
    """Получает URL ngrok туннеля"""
    try:
        response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
        if response.status_code == 200:
            data = response.json()
            for tunnel in data.get('tunnels', []):
                if tunnel.get('proto') == 'https':
                    return tunnel.get('public_url')
    except Exception as e:
        print(f"Ошибка получения ngrok URL: {e}")
    return None

def setup_yookassa_webhook(webhook_url, shop_id, secret_key):
    """Настраивает webhook в YooKassa"""
    try:
        # YooKassa API endpoint для webhook'ов
        url = f"https://api.yookassa.ru/v3/webhooks"
        
        headers = {
            'Authorization': f'Basic {shop_id}:{secret_key}',
            'Content-Type': 'application/json',
            'Idempotence-Key': f'webhook_{int(time.time())}'
        }
        
        data = {
            'event': 'payment.succeeded',
            'url': webhook_url
        }
        
        print(f"Настройка webhook: {webhook_url}")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            print("✅ Webhook успешно настроен!")
            return True
        else:
            print(f"❌ Ошибка настройки webhook: {response.status_code}")
            print(f"Ответ: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при настройке webhook: {e}")
        return False

def main():
    """Основная функция"""
    print("🚀 Настройка webhook для YooKassa...")
    
    # Получаем переменные окружения
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        print("❌ Не найдены YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY")
        return False
    
    # Ждем запуска ngrok
    print("⏳ Ожидание запуска ngrok...")
    for i in range(30):  # Ждем до 30 секунд
        ngrok_url = get_ngrok_url()
        if ngrok_url:
            break
        time.sleep(1)
        print(f"Попытка {i+1}/30...")
    
    if not ngrok_url:
        print("❌ Не удалось получить ngrok URL")
        return False
    
    webhook_url = f"{ngrok_url}/webhook/yookassa"
    print(f"📡 Ngrok URL: {ngrok_url}")
    print(f"🔗 Webhook URL: {webhook_url}")
    
    # Настраиваем webhook в YooKassa
    success = setup_yookassa_webhook(webhook_url, shop_id, secret_key)
    
    if success:
        print("🎉 Webhook успешно настроен!")
        print(f"URL: {webhook_url}")
        return True
    else:
        print("💥 Не удалось настроить webhook")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
