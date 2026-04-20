"""
Правила логина и пароля: один источник правды для регистрации и смены логина/пароля.
Логин: только a-z, 0-9, _, длина 3–30. Пароль: 8–128 символов, минимум 1 буква (a–z, A–Z) и 1 цифра.
"""
import re
from typing import Optional, Tuple

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 30
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]+$")

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
PASSWORD_HAS_LETTER = re.compile(r"[a-zA-Z]")
PASSWORD_HAS_DIGIT = re.compile(r"[0-9]")


def validate_username_format(username: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет формат логина. Возвращает (True, None) если ок, иначе (False, сообщение об ошибке).
    Логин должен быть уже .strip().lower() перед вызовом.
    """
    if not username:
        return False, "Логин обязателен"
    if len(username) < USERNAME_MIN_LEN:
        return False, f"Логин слишком короткий (минимум {USERNAME_MIN_LEN} символа)"
    if len(username) > USERNAME_MAX_LEN:
        return False, f"Логин слишком длинный (максимум {USERNAME_MAX_LEN} символов)"
    if not USERNAME_PATTERN.match(username):
        return False, "Логин: только латиница (a–z), цифры и подчёркивание, 3–30 символов"
    return True, None


def validate_password_format(password: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет формат пароля. Возвращает (True, None) если ок, иначе (False, сообщение об ошибке).
    """
    if not password:
        return False, "Пароль обязателен"
    if len(password) < PASSWORD_MIN_LEN:
        return False, f"Пароль слишком короткий (минимум {PASSWORD_MIN_LEN} символов)"
    if len(password) > PASSWORD_MAX_LEN:
        return False, f"Пароль слишком длинный (максимум {PASSWORD_MAX_LEN} символов)"
    if not PASSWORD_HAS_LETTER.search(password):
        return False, "Пароль должен содержать хотя бы одну букву (a–z или A–Z)"
    if not PASSWORD_HAS_DIGIT.search(password):
        return False, "Пароль должен содержать хотя бы одну цифру"
    return True, None
