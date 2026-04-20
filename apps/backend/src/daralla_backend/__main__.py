"""
Точка входа при запуске `python -m bot`.
Гарантирует однократную загрузку модуля bot.bot и один вызов set_ctx().
"""
from .bot import run

if __name__ == "__main__":
    run()
