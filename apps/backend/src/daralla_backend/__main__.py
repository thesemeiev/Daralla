"""
Точка входа при запуске `python -m daralla_backend`.
Гарантирует однократную загрузку runtime-модуля и один вызов set_ctx().
"""
from .bot import run

if __name__ == "__main__":
    run()
