"""
Обработчик callback'ов для инструкций
"""
import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...utils import safe_edit_or_reply_universal, safe_answer_callback_query
from ...navigation import CallbackData, nav_manager, NavigationBuilder

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot (как это сделано в других местах)
        # Когда модуль запускается через "python -m bot.bot", он доступен как '__main__'
        # но мы также сохраняем ссылку на него под именем 'bot.bot'
        bot_module = None
        nav_system = None
        
        # Сначала пробуем получить из bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
            nav_system = getattr(bot_module, 'nav_system', None)
        
        # Если не нашли, пробуем __main__
        if nav_system is None and '__main__' in sys.modules:
            main_module = sys.modules['__main__']
            nav_system = getattr(main_module, 'nav_system', None)
            if nav_system is not None:
                bot_module = main_module
        
        # Если все еще не нашли, пробуем импортировать
        if nav_system is None:
            try:
                bot_module = importlib.import_module('bot.bot')
                nav_system = getattr(bot_module, 'nav_system', None)
            except ImportError:
                pass
        
        return {
            'nav_system': nav_system,
        }
    except (ImportError, AttributeError) as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'nav_system': None,
        }


async def instruction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'ов для инструкций"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    data = query.data
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    
    texts = {
        "instr_android": (
            "<b>Android (v2RayTun, Hiddify)</b>\n"
            "1. Выберите приложение:\n"
            "   • <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">v2RayTun из Google Play</a>\n"
            "   • <a href=\"https://play.google.com/store/apps/details?id=app.hiddify.com\">Hiddify из Google Play</a>\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В приложении нажмите + → Добавить из буфера обмена.\n"
            "4. Подключитесь к VPN.\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или телефон.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_ios": (
            "<b>iPhone (v2RayTun, Hiddify)</b>\n"
            "1. Выберите приложение:\n"
            "   • <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=iphone\">v2RayTun из App Store</a>\n"
            "   • <a href=\"https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532?platform=iphone\">Hiddify из App Store</a>\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. Откройте выбранное приложение.\n"
            "4. Нажмите + → Добавить из буфера обмена.\n"
            "5. Выберите добавленный профиль и подключитесь.\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или телефон.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_windows": (
            "<b>Windows (v2RayTun, Hiddify)</b>\n"
            "1. Выберите приложение:\n"
            "   • <a href=\"https://storage.v2raytun.com/v2RayTun_Setup.exe\">v2RayTun для Windows</a>\n"
            "   • <a href=\"https://app.hiddify.com/windows\">Hiddify для Windows</a>\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В выбранном приложении нажмите + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или компьютер.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_macos": (
            "<b>Mac (v2RayTun, Hiddify)</b>\n"
            "1. Выберите приложение:\n"
            "   • <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=mac\">v2RayTun для Mac</a>\n"
            "   • <a href=\"https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532?platform=iphone\">Hiddify для Mac</a>\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В выбранном приложении нажмите + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или Mac.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_tv": (
            "<b>Android TV (v2RayTun)</b>\n"
            "1. <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">Скачайте v2RayTun для Android TV</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В v2RayTun нажмите + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или Android TV.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_linux": (
            "<b>Linux (Hiddify)</b>\n"
            "1. <a href=\"https://app.hiddify.com/linux\">Скачайте Hiddify для Linux</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В Hiddify нажмите + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или компьютер.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_faq": (
            "<b>FAQ - Частые вопросы</b>\n\n"
            "<b>VPN не подключается:</b>\n"
            "• Проверьте интернет\n"
            "• Перезапустите v2RayTun\n"
            "• Скопируйте ссылку полностью\n"
            "• Отключите другие VPN\n\n"
            "<b>Не импортируется ключ:</b>\n"
            "• Скопируйте ссылку заново\n"
            "• Проверьте 'vless://' в начале\n"
            "• Обновите приложение\n\n"
            "<b>Один ключ = одно устройство</b>\n"
            "<b>Продление:</b> Купите новый ключ или продлите\n\n"
            "<b>Нужна помощь?</b> Обратитесь в поддержку"
        )
    }
    
    if data == CallbackData.BACK:
        # === НОВАЯ СИСТЕМА НАВИГАЦИИ ===
        await nav_manager.handle_back_navigation(update, context)
        return
    elif data in ["instr_android", "instr_ios", "instr_windows", "instr_macos", "instr_linux", "instr_tv", "instr_faq"]:
        # === НОВАЯ СИСТЕМА НАВИГАЦИИ ===
        logger.info(f"INSTRUCTION_CALLBACK: Platform selected: {data}")
        from ...navigation import NavStates
        # ВАЖНО: Убеждаемся, что INSTRUCTION_MENU в стеке перед добавлением INSTRUCTION_PLATFORM
        current_stack = nav_manager.get_stack(context)
        logger.info(f"INSTRUCTION_CALLBACK: Current stack before: {current_stack}")
        if NavStates.INSTRUCTION_MENU not in current_stack:
            nav_manager.push_state(context, NavStates.INSTRUCTION_MENU)
        
        # Добавляем INSTRUCTION_PLATFORM в стек навигации
        nav_manager.push_state(context, NavStates.INSTRUCTION_PLATFORM)
        logger.info(f"INSTRUCTION_CALLBACK: Stack after: {nav_manager.get_stack(context)}")
        
        # Определяем menu_type для каждой платформы
        menu_type_map = {
            "instr_android": "instruction_android",
            "instr_ios": "instruction_ios", 
            "instr_windows": "instruction_windows",
            "instr_macos": "instruction_macos",
            "instr_linux": "instruction_linux",
            "instr_tv": "instruction_tv",
            "instr_faq": "instruction_faq"
        }
        
        menu_type = menu_type_map.get(data, 'instruction_platform')
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(query.message, texts.get(data, "Инструкция не найдена."), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True, menu_type=menu_type)

