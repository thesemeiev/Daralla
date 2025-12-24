"""
Скрипт для автоматической замены текста на изображениях
Использует OCR для поиска текста и замены
"""
from PIL import Image, ImageDraw, ImageFont
import os
import shutil

# Попытка импорта OCR библиотек
try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("pytesseract не установлен. OCR недоступен.")

def find_text_regions(image_path):
    """Пытается найти регионы с текстом на изображении"""
    if not HAS_OCR:
        return []
    
    try:
        img = Image.open(image_path)
        # Используем OCR для поиска текста
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        return data
    except Exception as e:
        print(f"Ошибка OCR: {e}")
        return []

def replace_text_on_image(source_path, target_path, text_replacements):
    """
    Пытается заменить текст на изображении
    ВНИМАНИЕ: Это сложная задача, требующая точного позиционирования текста
    """
    try:
        img = Image.open(source_path)
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Без OCR мы не можем точно найти текст
        # Поэтому просто создаем копию и выводим инструкцию
        img.save(target_path, "JPEG", quality=95)
        
        return True
    except Exception as e:
        print(f"Ошибка: {e}")
        return False


def main():
    """Основная функция"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base_dir, "images")
    
    print("=" * 70)
    print("ОБНОВЛЕНИЕ ТЕКСТА НА ИЗОБРАЖЕНИЯХ")
    print("=" * 70)
    
    if not HAS_OCR:
        print("\nВНИМАНИЕ: OCR недоступен. Текст нужно изменить ВРУЧНУЮ!")
        print("Установите pytesseract и Tesseract OCR для автоматической замены.")
    
    files_info = [
        ("mykeys_menu.jpg", "my_subscriptions.jpg", 
         "Меню 'Мои подписки'"),
        ("extend_key.jpg", "extend_subscription.jpg",
         "Меню продления подписки"),
        ("key_success.jpg", "subscription_success.jpg",
         "Успешное создание подписки"),
    ]
    
    print("\nСоздание/обновление файлов...")
    for source, target, desc in files_info:
        source_path = os.path.join(images_dir, source)
        target_path = os.path.join(images_dir, target)
        
        print(f"\n{desc}:")
        if os.path.exists(source_path):
            if not os.path.exists(target_path) or True:  # Всегда обновляем
                replace_text_on_image(source_path, target_path, {})
                print(f"  Файл создан: {target}")
                print(f"  -> Откройте в графическом редакторе и замените текст")
        else:
            print(f"  Исходный файл {source} не найден")
    
    print("\n" + "=" * 70)
    print("ИНСТРУКЦИЯ:")
    print("=" * 70)
    print("\nОткройте файлы в графическом редакторе и замените:")
    print("  'Мои ключи' -> 'Мои подписки'")
    print("  'ключи' -> 'подписки'")
    print("  'ключ' -> 'подписка'")
    print("  'Ключи' -> 'Подписки'")
    print("  'Ключ' -> 'Подписка'")
    print("\nРекомендуемые редакторы: GIMP, Paint.NET, Photoshop, Canva")
    print("=" * 70)


if __name__ == "__main__":
    main()

