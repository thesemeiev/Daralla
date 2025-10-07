import logging
import html
from logging.handlers import RotatingFileHandler
import datetime
import json
import uuid
import os
import requests
import asyncio
from dotenv import load_dotenv
import pathlib
import telegram
from telegram.helpers import escape_markdown

async def safe_edit_or_reply(message, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    if message is None:
        logger.error("safe_edit_or_reply: message is None")
        return
    
    # Дополнительное логирование для отладки
    logger.info(f"SAFE_EDIT_OR_REPLY: message={message}, text_length={len(text) if text else 0}, reply_markup={reply_markup is not None}")
    
    # Проверяем, есть ли у сообщения фото
    if message.photo:
        # Если сообщение содержит фото, используем edit_caption
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return
        except Exception as e:
            logger.warning(f"Failed to edit caption, falling back to reply: {e}")
            # Fallback: отправляем новое сообщение
            await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return
    
    # Максимальное количество попыток для сетевых ошибок
    max_retries = 3
    retry_delay = 2  # секунды
    
    for attempt in range(max_retries):
        try:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return  # Успешно отправлено
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_text'):
                # Пробуем отправить как новое сообщение с повторными попытками
                for reply_attempt in range(max_retries):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                        return  # Успешно отправлено
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"Сетевая ошибка при отправке сообщения (попытка {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"Не удалось отправить сообщение после {max_retries} попыток: {net_err}")
                            raise
            elif "can't parse entities" in str(e).lower() and hasattr(message, 'reply_text'):
                # Фолбэк: отправляем как обычный текст без форматирования
                await message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=disable_web_page_preview
                )
                return
            elif "Message is not modified" in str(e):
                # Игнорируем эту ошибку, так как сообщение уже содержит нужное содержимое
                return
            else:
                raise
        except telegram.error.NetworkError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Сетевая ошибка при редактировании сообщения (попытка {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                logger.error(f"Не удалось отредактировать сообщение после {max_retries} попыток: {e}")
                # Последняя попытка - пробуем отправить как новое сообщение
                if hasattr(message, 'reply_text'):
                    try:
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            disable_web_page_preview=disable_web_page_preview
                        )
                    except:
                        raise e  # Если и это не удалось, пробрасываем исходную ошибку
                else:
                    raise
        except Exception as e:
            if hasattr(message, 'reply_text'):
                await message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
            else:
                raise

async def safe_edit_or_reply_photo(message, photo_path, caption, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
    """Безопасная отправка или редактирование сообщения с фото"""
    if message is None:
        logger.error("safe_edit_or_reply_photo: message is None")
        return
    
    # Проверяем существование файла
    if not os.path.exists(photo_path):
        logger.warning(f"Photo file not found: {photo_path}, falling back to text message")
        await safe_edit_or_reply(message, caption, reply_markup, parse_mode, disable_web_page_preview)
        return
    
    # Максимальное количество попыток для сетевых ошибок
    max_retries = 3
    retry_delay = 2  # секунды
    
    for attempt in range(max_retries):
        try:
            # Пытаемся отредактировать существующее сообщение
            with open(photo_path, 'rb') as photo_file:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=photo_file,
                        caption=caption,
                        parse_mode=parse_mode
                    ),
                    reply_markup=reply_markup
                )
            return  # Успешно отправлено
        except telegram.error.BadRequest as e:
            if "can't be edited" in str(e) and hasattr(message, 'reply_photo'):
                # Пробуем отправить как новое сообщение с повторными попытками
                for reply_attempt in range(max_retries):
                    try:
                        with open(photo_path, 'rb') as photo_file:
                            await message.reply_photo(
                                photo=photo_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode=parse_mode
                            )
                        return  # Успешно отправлено
                    except telegram.error.NetworkError as net_err:
                        if reply_attempt < max_retries - 1:
                            logger.warning(f"Сетевая ошибка при отправке фото (попытка {reply_attempt + 1}/{max_retries}): {net_err}")
                            await asyncio.sleep(retry_delay * (reply_attempt + 1))
                        else:
                            logger.error(f"Не удалось отправить фото после {max_retries} попыток: {net_err}")
                            raise
            elif "can't parse entities" in str(e) and hasattr(message, 'reply_photo'):
                # Фолбэк: отправляем как обычный текст без форматирования
                with open(photo_path, 'rb') as photo_file:
                    await message.reply_photo(
                        photo=photo_file,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                return
            elif "Message is not modified" in str(e):
                # Сообщение не изменилось, это нормально
                return
            else:
                # Другие ошибки - пробуем отправить как новое сообщение
                if hasattr(message, 'reply_photo'):
                    try:
                        with open(photo_path, 'rb') as photo_file:
                            await message.reply_photo(
                                photo=photo_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode=parse_mode
                            )
                        return
                    except:
                        raise e  # Если и это не удалось, пробрасываем исходную ошибку
                else:
                    raise
        except Exception as e:
            if hasattr(message, 'reply_photo'):
                with open(photo_path, 'rb') as photo_file:
                    await message.reply_photo(
                        photo=photo_file,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
            else:
                raise

async def safe_edit_or_reply_universal(message, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None, menu_type=None):
    """Универсальная функция для отправки/редактирования сообщений с автоматическим выбором фото или текста"""
    if message is None:
        logger.error("safe_edit_or_reply_universal: message is None")
        return
    
    # Если указан тип меню и есть соответствующее изображение, используем фото
    if menu_type and menu_type in IMAGE_PATHS:
        photo_path = IMAGE_PATHS[menu_type]
        if os.path.exists(photo_path):
            await safe_edit_or_reply_photo(message, photo_path, text, reply_markup, parse_mode, disable_web_page_preview)
            return
    
    # Иначе используем обычное текстовое сообщение
    await safe_edit_or_reply(message, text, reply_markup, parse_mode, disable_web_page_preview)

# Определяем путь к файлу .env
current_dir = pathlib.Path(__file__).parent
project_root = current_dir.parent
env_path = project_root / '.env'

# Загружаем .env из корня проекта
if env_path.exists():
    load_dotenv(env_path)
else:
    print("ВНИМАНИЕ: Файл .env не найден! Создайте файл .env в корне проекта с переменными окружения.")
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

def mdv2(s):
    return escape_markdown(str(s), version=2)
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from yookassa import Payment, Configuration
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

from .keys_db import (
    init_payments_db, add_payment, get_payment, update_payment_status, get_all_pending_payments,
    get_pending_payment, cleanup_old_payments, cleanup_expired_pending_payments,
    init_referral_db, save_referral_connection, get_pending_referral, mark_referral_reward_given,
    add_points, spend_points, get_user_points, get_points_history, get_referral_stats,
    is_known_user, register_simple_user, get_all_user_ids,
    atomic_referral_reward, atomic_refund_points,
    get_config, set_config, get_all_config
)


from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_result

# ===== РЕФЕРАЛЬНАЯ СИСТЕМА =====

# Упрощенная реферальная система - используем только user_id

def generate_referral_code(user_id: str) -> str:
    """Генерирует простой реферальный код на основе user_id"""
    try:
        if not user_id:
            logger.error(f"GENERATE_REFERRAL_CODE: Invalid user_id - {user_id}")
            return None
            
        # Простой код - просто user_id
        logger.info(f"GENERATE_REFERRAL_CODE: Generated simple code for user {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"GENERATE_REFERRAL_CODE: Critical error - {e}")
        return None

def decode_referral_code(code: str) -> str:
    """Декодирует простой реферальный код (просто возвращает user_id)"""
    try:
        if not code:
            logger.error(f"DECODE_REFERRAL_CODE: Empty code")
            return None
            
        # Простая проверка - код должен быть числом (user_id)
        if not code.isdigit():
            logger.warning(f"DECODE_REFERRAL_CODE: Invalid code format - {code}")
            return None
            
        logger.info(f"DECODE_REFERRAL_CODE: Valid code for user {code}")
        return code
        
    except Exception as e:
        logger.error(f"DECODE_REFERRAL_CODE: Critical error - {e}")
        return None




YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Поддержка нескольких админов через переменную окружения
ADMIN_IDS_STR = os.getenv("ADMIN_ID", os.getenv("ADMIN_IDS", ""))
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()] if ADMIN_IDS_STR else []

# Пути к изображениям для меню
IMAGE_PATHS = {
    'main_menu': 'images/main_menu.jpg',
    'instruction_menu': 'images/instruction_menu.jpg',
    'buy_menu': 'images/buy_menu.jpg',
    'mykeys_menu': 'images/mykeys_menu.jpg',
    'admin_menu': 'images/admin_menu.jpg',
    'points_menu': 'images/points_menu.jpg',
    'referral_menu': 'images/referral_menu.jpg'
}

# Проверяем наличие обязательных переменных
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения! Создайте файл bot/.env")

if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    print("ВНИМАНИЕ: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены!")

# Конфигурация серверов по локациям
SERVERS_BY_LOCATION = {
    "Finland": [
        { 
            "name": "Finland-1", 
            "host": os.getenv("XUI_HOST_FINLAND_1"),
            "login": os.getenv("XUI_LOGIN_FINLAND_1"),
            "password": os.getenv("XUI_PASSWORD_FINLAND_1")
        },
        



        
    ],
    "Latvia": [
        {
            "name": "Latvia-1",
            "host": os.getenv("XUI_HOST_LATVIA_1"),
            "login": os.getenv("XUI_LOGIN_LATVIA_1"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_1")
        },
        {
            "name": "Latvia-2",
            "host": os.getenv("XUI_HOST_LATVIA_2"),
            "login": os.getenv("XUI_LOGIN_LATVIA_2"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_2")
        }
    ],
    "Estonia": [
        {
            "name": "Estonia-1",
            "host": os.getenv("XUI_HOST_ESTONIA_1"),
            "login": os.getenv("XUI_LOGIN_ESTONIA_1"),
            "password": os.getenv("XUI_PASSWORD_ESTONIA_1")
        }
    ]
}

# Создаем плоский список всех серверов для обратной совместимости
SERVERS = []
for location_servers in SERVERS_BY_LOCATION.values():
    SERVERS.extend(location_servers)

# Сервера для новых клиентов (теперь по локациям)
NEW_CLIENT_SERVERS = SERVERS_BY_LOCATION

# Проверяем конфигурацию серверов
for i, server in enumerate(SERVERS):
    if not server["host"] or not server["login"] or not server["password"]:
        print(f"ВНИМАНИЕ: Сервер {server['name']} не настроен! Проверьте переменные XUI_HOST_{server['name'].upper().replace('-', '_')}, XUI_LOGIN_{server['name'].upper().replace('-', '_')}, XUI_PASSWORD_{server['name'].upper().replace('-', '_')}")

# Настраиваем файловый лог с ротацией в папке data/logs
try:
    from .keys_db import DATA_DIR
except Exception:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

logs_dir = os.path.join(DATA_DIR, 'logs')
os.makedirs(logs_dir, exist_ok=True)
app_log_path = os.path.join(logs_dir, 'bot.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(app_log_path, maxBytes=1_048_576, backupCount=3, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

async def check_private_chat(update: Update) -> bool:
    """Проверяет, что команда используется в приватном чате.
    Возвращает True если чат приватный, False если нет."""
    if update.effective_chat.type != 'private':
        await safe_edit_or_reply(update.message,
            f"{UIEmojis.WARNING} Эта команда работает только в личных сообщениях.\n"
            f"Напишите мне в личку для работы с VPN-ключами.",
            parse_mode="HTML"
        )
        return False
    return True

class X3:
    def __init__(self, login, password, host):
        self.login = login
        self.password = password
        self.host = host
        self.ses = requests.Session()
        
        # Определяем протокол и настраиваем SSL соответственно
        if host.startswith('https://'):
            self.ses.verify = True
        else:
            self.ses.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Увеличиваем таймауты для лучшей стабильности
        self.ses.timeout = (30, 30)  # (connect timeout, read timeout)
        
        self.data = {"username": self.login, "password": self.password}
        logger.info(f"Подключение к XUI серверу: {host} (SSL: {self.ses.verify})")
        self._login()
    
    def _login(self):
        """Выполняет вход в XUI панель"""
        try:
            # Пробуем сначала с текущими настройками
            try:
                login_response = self.ses.post(f"{self.host}/login", data=self.data, timeout=30)
            except requests.exceptions.SSLError:
                # Если получили ошибку SSL, пробуем без проверки сертификата
                logger.warning(f"SSL ошибка при подключении к {self.host}, пробуем без проверки сертификата")
                self.ses.verify = False
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                login_response = self.ses.post(f"{self.host}/login", data=self.data, timeout=30)
            
            logger.info(f"XUI Login Response - Status: {login_response.status_code}")
            logger.info(f"XUI Login Response - Text: {login_response.text[:200]}...")
            
            if login_response.status_code != 200:
                logger.error(f"Ошибка входа в XUI: {login_response.status_code} - {login_response.text}")
                raise Exception(f"Login failed with status {login_response.status_code}")
            
            # Проверяем, что мы действительно вошли (обычно в ответе есть что-то, указывающее на успешный вход)
            if "error" in login_response.text.lower() or "invalid" in login_response.text.lower():
                logger.error(f"Ошибка аутентификации: {login_response.text[:200]}")
                raise Exception("Authentication failed")
                
        except Exception as e:
            logger.error(f"Ошибка при подключении к XUI серверу {self.host}: {e}")
            raise

    def _reconnect(self):
        """Переподключается к серверу при истечении сессии"""
        logger.info(f"Переподключение к серверу {self.host}")
        self.ses = requests.Session()
        
        # Восстанавливаем настройки SSL
        if self.host.startswith('https://'):
            self.ses.verify = True
        else:
            self.ses.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Восстанавливаем увеличенные таймауты
        self.ses.timeout = (30, 30)
        
        self._login()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))


    def addClient(self, day, tg_id, user_email, timeout=15, hours=None, key_name=""):
        if hours is not None:
            # Для тестовых ключей используем часы
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (hours * 3600000)
        else:
            # Для обычных ключей используем дни
            x_time = int(datetime.datetime.now().timestamp() * 1000) + (86400000 * day)
        header = {"Accept": "application/json"}
        client_data = {
            "id": str(uuid.uuid1()),
            "alterId": 90,
            "email": str(user_email),
            "limitIp": 1,
            "totalGB": 0,
            "expiryTime": x_time,
            "enable": True,
            "tgId": str(tg_id),
            "subId": key_name,  # Сохраняем имя ключа в поле subId
            "flow": "xtls-rprx-vision"
        }
        data1 = {
            "id": 1,
            "settings": json.dumps({"clients": [client_data]})
        }
        logger.info(f"Добавление клиента: {user_email} на сервер {self.host}")
        try:
            response = self.ses.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
            logger.info(f"XUI addClient Response - Status: {response.status_code}")
            logger.info(f"XUI addClient Response - Text: {response.text[:200]}...")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ, возможно истекла сессия. Переподключаюсь...")
                self._login()
                # Повторяем запрос после переподключения
                response = self.ses.post(f'{self.host}/panel/api/inbounds/addClient', headers=header, json=data1, timeout=timeout)
                logger.info(f"XUI addClient Response после переподключения - Status: {response.status_code}")
                logger.info(f"XUI addClient Response после переподключения - Text: {response.text[:200]}...")
            
            return response
        except Exception as e:
            logger.error(f"Ошибка при добавлении клиента {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def extendClient(self, user_email, extend_days, timeout=15):
        """
        Продлевает срок действия ключа клиента
        :param user_email: Email клиента
        :param extend_days: Количество дней для продления
        :param timeout: Таймаут запроса
        :return: Response объект
        """
        try:
            # Сначала получаем информацию о клиенте
            inbounds_data = self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("Не удалось получить список клиентов")
            
            client_found = False
            client_data = None
            inbound_id = None
            
            # Ищем клиента по email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        
                        # Вычисляем новое время истечения
                        current_expiry = int(client.get('expiryTime', 0))
                        if current_expiry == 0:
                            # Если время истечения не установлено, начинаем с текущего времени
                            current_expiry = int(datetime.datetime.now().timestamp() * 1000)
                        
                        # Добавляем дни к текущему времени истечения
                        new_expiry = current_expiry + (extend_days * 86400000)  # 86400000 мс = 1 день
                        client_data['expiryTime'] = new_expiry
                        
                        logger.info(f"Продление ключа {user_email}: старое время истечения = {current_expiry}, новое = {new_expiry}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"Клиент с email {user_email} не найден")
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            logger.info(f"Продление клиента: {user_email} на сервере {self.host} на {extend_days} дней")
            response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                   headers=header, json=data, timeout=timeout)
            
            logger.info(f"XUI extendClient Response - Status: {response.status_code}")
            logger.info(f"XUI extendClient Response - Text: {response.text[:200]}...")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ при продлении, переподключаюсь...")
                self._login()
                response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI extendClient Response после переподключения - Status: {response.status_code}")
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при продлении клиента {user_email}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_client_count(self, timeout=15):
        """Подсчитывает общее количество клиентов на сервере"""
        try:
            response_data = self.list(timeout=timeout)
            logger.info(f"XUI list response: {response_data}")
            if 'obj' not in response_data:
                logger.error(f"Неожиданный формат ответа XUI: {response_data}")
                return 0
            inbounds = response_data['obj']
            total_clients = 0
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                total_clients += len(settings.get("clients", []))
            return total_clients
        except Exception as e:
            logger.error(f"Ошибка при подсчете клиентов на {self.host}: {e}")
            return 0

    def get_clients_status_count(self, timeout=15):
        """Подсчитывает количество клиентов по статусу (активные/истекшие)"""
        try:
            response_data = self.list(timeout=timeout)
            if 'obj' not in response_data:
                logger.error(f"Неожиданный формат ответа XUI: {response_data}")
                return 0, 0, 0
            
            inbounds = response_data['obj']
            total_clients = 0
            active_clients = 0
            expired_clients = 0
            current_time = int(datetime.datetime.now().timestamp() * 1000)
            
            for inbound in inbounds:
                settings = json.loads(inbound['settings'])
                clients = settings.get("clients", [])
                total_clients += len(clients)
                
                for client in clients:
                    # Проверяем, активен ли клиент (не истек ли срок)
                    expiry_time = client.get('expiryTime', 0)
                    if expiry_time == 0 or current_time < expiry_time:
                        active_clients += 1
                    else:
                        expired_clients += 1
            
            return total_clients, active_clients, expired_clients
        except Exception as e:
            logger.error(f"Ошибка при подсчете статуса клиентов на {self.host}: {e}")
            return 0, 0, 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def client_exists(self, user_email):
        for inbound in self.list()['obj']:
            settings = json.loads(inbound['settings'])
            for client in settings.get("clients", []):
                if client['email'] == user_email:
                    return True
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2)
    )
    def list(self, timeout=15):
        try:
            url = f'{self.host}/panel/api/inbounds/list'
            logger.info(f"Отправка запроса к {url}")
            
            # Проверяем доступность сервера
            try:
                health_check = self.ses.get(f'{self.host}/ping', timeout=5)
                logger.info(f"Проверка доступности сервера {self.host}: {health_check.status_code}")
            except Exception as e:
                logger.warning(f"Сервер {self.host} недоступен: {e}")
            
            response = self.ses.get(url, json=self.data, timeout=timeout)
            logger.info(f"XUI API Response - URL: {url}")
            logger.info(f"XUI API Response - Status: {response.status_code}, Headers: {dict(response.headers)}")
            logger.info(f"XUI API Response - Text: {response.text[:500]}...")  # Логируем первые 500 символов
            
            # Проверяем статус ответа
            if response.status_code != 200:
                logger.error(f"XUI API вернул неверный статус: {response.status_code} для URL {url}")
                if response.status_code == 404:
                    logger.error(f"Endpoint не найден на сервере {self.host}. Возможно, сервер не поддерживает API или требует обновления.")
                    return {'success': False, 'error': '404 Not Found', 'obj': []}  # Возвращаем структуру, совместимую с ожидаемым форматом
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            # Проверяем, что ответ не пустой
            if not response.text.strip():
                logger.error("XUI API вернул пустой ответ")
                raise Exception("Пустой ответ от сервера")
            
            # Проверяем, что ответ начинается с '{' или '[' (признак JSON)
            if not response.text.strip().startswith(('{', '[')):
                logger.error(f"XUI API вернул не-JSON ответ: {response.text[:200]}")
                # Если получили HTML вместо JSON, возможно сессия истекла
                if "<html" in response.text.lower() or "login" in response.text.lower():
                    logger.warning("Обнаружена истекшая сессия, переподключаюсь...")
                    self._reconnect()
                    # Повторяем запрос после переподключения
                    response = self.ses.get(f'{self.host}/panel/api/inbounds/list', json=self.data, timeout=timeout)
                    logger.info(f"XUI API Response после переподключения - Status: {response.status_code}")
                    logger.info(f"XUI API Response после переподключения - Text: {response.text[:500]}...")
                    
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    
                    if not response.text.strip().startswith(('{', '[')):
                        raise Exception(f"Неверный формат ответа после переподключения: {response.text[:200]}")
                
                else:
                    raise Exception(f"Неверный формат ответа: {response.text[:200]}")
            
            try:
                return response.json()
            except json.JSONDecodeError as json_error:
                logger.error(f"Ошибка парсинга JSON: {json_error}")
                logger.error(f"Ответ сервера: {response.text[:500]}")
                raise Exception(f"Ошибка парсинга JSON: {json_error}")
                
        except Exception as e:
            logger.error(f"Ошибка при запросе к XUI API: {e}")
            logger.error(f"Response status: {getattr(response, 'status_code', 'N/A')}")
            logger.error(f"Response text: {getattr(response, 'text', 'N/A')}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def deleteClient(self, user_email, timeout=15):
        for inbound in self.list(timeout=timeout)['obj']:
            settings = json.loads(inbound['settings'])
            for client in settings.get("clients", []):
                if client['email'] == user_email:
                    client_id = client['id']
                    inbound_id = inbound['id']
                    url = f"{self.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                    logger.info(f"Удаляю VLESS клиента: inbound_id={inbound_id}, client_id={client_id}, email={user_email}")
                    result = self.ses.post(url, timeout=timeout)
                    logger.info(f"Ответ XUI: status_code={getattr(result, 'status_code', None)}, text={getattr(result, 'text', None)}")
                    if getattr(result, 'status_code', None) == 200:
                        logger.info(f"Клиент успешно удалён: {user_email}")
                    return result
        logger.warning(f"Клиент с email={user_email} не найден ни в одном inbound")
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def updateClientName(self, user_email, new_name, timeout=15):
        """
        Обновляет имя ключа (сохраняет в поле subId)
        :param user_email: Email клиента
        :param new_name: Новое имя ключа
        :param timeout: Таймаут запроса
        :return: Response объект
        """
        try:
            # Сначала получаем информацию о клиенте
            inbounds_data = self.list(timeout=timeout)
            if not inbounds_data.get('success', False):
                raise Exception("Не удалось получить список клиентов")
            
            client_found = False
            client_data = None
            inbound_id = None
            
            # Ищем клиента по email
            for inbound in inbounds_data.get('obj', []):
                settings = json.loads(inbound.get('settings', '{}'))
                clients = settings.get('clients', [])
                
                for client in clients:
                    if client.get('email') == user_email:
                        client_found = True
                        client_data = client.copy()
                        inbound_id = inbound.get('id')
                        
                        # Обновляем имя ключа в поле subId
                        client_data['subId'] = new_name
                        
                        logger.info(f"Обновление имени ключа {user_email}: новое имя = {new_name}")
                        break
                
                if client_found:
                    break
            
            if not client_found:
                raise Exception(f"Клиент с email {user_email} не найден")
            
            # Обновляем клиента
            header = {"Accept": "application/json"}
            data = {
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]})
            }
            
            response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', headers=header, json=data, timeout=timeout)
            logger.info(f"XUI updateClientName Response - Status: {response.status_code}")
            logger.info(f"XUI updateClientName Response - Text: {response.text[:200]}...")
            
            # Проверяем, не истекла ли сессия
            if response.status_code == 200 and not response.text.strip():
                logger.warning("Получен пустой ответ при обновлении имени, переподключаюсь...")
                self._login()
                response = self.ses.post(f'{self.host}/panel/api/inbounds/updateClient/{client_data["id"]}', 
                                       headers=header, json=data, timeout=timeout)
                logger.info(f"XUI updateClientName Response после переподключения - Status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"Имя ключа успешно обновлено: {user_email} -> {new_name}")
            else:
                logger.error(f"Ошибка обновления имени ключа: {response.status_code} - {response.text}")
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении имени ключа {user_email}: {e}")
            raise

    def link(self, user_id: str):
        inbounds_list = self.list()['obj']
        for inbounds in inbounds_list:
            settings = json.loads(inbounds['settings'])
            stream = json.loads(inbounds['streamSettings'])

            client = next((c for c in settings.get("clients", []) if c['email'] == user_id), None)
            if not client:
                continue

            host_part = self.host.split('//')[-1]
            host = host_part.split(':')[0] if ':' in host_part else host_part
            port = inbounds.get('port', 443)
            reality = stream.get('realitySettings', {})
            reality_settings = reality.get('settings', {})
            pbk = reality_settings.get('publicKey', '')
            fingerprint = reality_settings.get('fingerprint', 'chrome')
            spx = reality_settings.get('spiderX', '/')
            dest = reality.get('dest', '')
            sni = dest.split(':')[0] if dest else 'google.com'
            logger.info(f"Reality настройки для {self.host}: dest='{dest}', sni='{sni}'")
            short_ids = reality.get('shortIds', [''])
            sid = short_ids[0] if short_ids else ''
            network = stream.get('network', 'tcp')
            security = stream.get('security', 'reality')

            # Строго в правильном порядке
            params = [
                ("type", network),
                ("security", security),
                ("flow", "xtls-rprx-vision"),
                ("pbk", pbk),
                ("fp", fingerprint),
                ("sni", sni),
                ("sid", sid),
                ("spx", quote(spx)),
            ]
            query = "&".join(f"{k}={v}" for k, v in params)
            tag = f"Daralla-{user_id}"

            return f"vless://{client['id']}@{host}:{port}?{query}#{tag}"

        return 'Клиент не найден.'

class MultiServerManager:
    def __init__(self, servers_by_location):
        self.servers_by_location = {}
        self.server_health = {}  # Словарь для отслеживания состояния серверов
        self.servers = []  # Плоский список всех серверов
        
        # Инициализируем серверы по локациям
        for location, servers_config in servers_by_location.items():
            self.servers_by_location[location] = []
            
            for server_config in servers_config:
                try:
                    x3_server = X3(
                        login=server_config["login"],
                        password=server_config["password"], 
                        host=server_config["host"]
                    )
                    server_info = {
                        "name": server_config["name"],
                        "x3": x3_server,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    # Инициализируем состояние сервера
                    self.server_health[server_config["name"]] = {
                        "status": "unknown",
                        "last_check": None,
                        "last_error": None,
                        "consecutive_failures": 0,
                        "uptime_percentage": 100.0
                    }
                    logger.info(f"Сервер {server_config['name']} ({location}) успешно подключен")
                except Exception as e:
                    logger.error(f"Ошибка подключения к серверу {server_config['name']} ({location}): {e}")
                    # Даже если сервер недоступен при инициализации, добавляем его в список
                    server_info = {
                        "name": server_config["name"],
                        "x3": None,
                        "config": server_config
                    }
                    self.servers_by_location[location].append(server_info)
                    self.servers.append(server_info)
                    self.server_health[server_config["name"]] = {
                        "status": "offline",
                        "last_check": datetime.datetime.now(),
                        "last_error": str(e),
                        "consecutive_failures": 1,
                        "uptime_percentage": 0.0
                    }
    
    def get_server_by_name(self, server_name):
        """Возвращает конкретный сервер по имени"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                if server["name"].lower() == server_name.lower():
                    return server["x3"], server["name"]
        raise Exception(f"Сервер {server_name} не найден или недоступен")
    
    def get_server_with_least_clients_in_location(self, location):
        """Возвращает сервер с наименьшим количеством клиентов в конкретной локации"""
        if location not in self.servers_by_location:
            raise Exception(f"Локация {location} не найдена")
        
        servers = self.servers_by_location[location]
        if not servers:
            raise Exception(f"Нет доступных серверов в локации {location}")
        
        min_clients = float('inf')
        selected_server = None
        
        for server in servers:
            try:
                client_count = server["x3"].get_client_count()
                logger.info(f"Сервер {server['name']} ({location}): {client_count} клиентов")
                
                if client_count < min_clients:
                    min_clients = client_count
                    selected_server = server
            except Exception as e:
                logger.error(f"Ошибка при получении количества клиентов с сервера {server['name']} ({location}): {e}")
                continue
        
        if selected_server is None:
            # Если все серверы недоступны, используем первый
            selected_server = servers[0]
            logger.warning(f"Все серверы в локации {location} недоступны, использую {selected_server['name']}")
        
        logger.info(f"Выбран сервер {selected_server['name']} ({location}) с {min_clients} клиентами")
        logger.info(f"Reality настройки будут проверены для сервера: {selected_server['name']}")
        return selected_server["x3"], selected_server["name"]
    
    def get_server_by_user_choice(self, location, user_choice):
        """Возвращает сервер согласно выбору пользователя в конкретной локации"""
        if user_choice == "auto":
            return self.get_server_with_least_clients_in_location(location)
        else:
            return self.get_server_by_name(user_choice)
    
    def get_best_location_server(self):
        """Возвращает сервер с наименьшей нагрузкой из всех локаций"""
        best_server = None
        min_clients = float('inf')
        best_location = None
        
        for location, servers in self.servers_by_location.items():
            try:
                server, server_name = self.get_server_with_least_clients_in_location(location)
                # Получаем количество клиентов для сравнения
                client_count = server.get_client_count()
                if client_count < min_clients:
                    min_clients = client_count
                    best_server = server
                    best_location = location
            except Exception as e:
                logger.error(f"Ошибка при получении сервера из локации {location}: {e}")
                continue
        
        if best_server is None:
            raise Exception("Нет доступных серверов в любой локации")
        
        logger.info(f"Выбрана лучшая локация: {best_location} с {min_clients} клиентами")
        return best_server, best_location
    
    def find_client_on_any_server(self, user_email):
        """Ищет клиента на любом из серверов"""
        for location, servers in self.servers_by_location.items():
            for server in servers:
                try:
                    if server["x3"] and server["x3"].client_exists(user_email):
                        logger.info(f"Клиент {user_email} найден на сервере {server['name']} ({location})")
                        return server["x3"], server["name"]
                except Exception as e:
                    logger.error(f"Ошибка при поиске клиента на сервере {server['name']} ({location}): {e}")
                    continue
        return None, None
    
    
    def check_server_health(self, server_name):
        """Проверяет здоровье конкретного сервера"""
        server_info = None
        for server in self.servers:
            if server["name"] == server_name:
                server_info = server
                break
        
        if not server_info:
            return False
        
        try:
            if server_info["x3"] is None:
                # Пытаемся переподключиться
                server_config = server_info["config"]
                server_info["x3"] = X3(
                    login=server_config["login"],
                    password=server_config["password"], 
                    host=server_config["host"]
                )
            
            # Проверяем доступность API
            response = server_info["x3"].list(timeout=10)
            if response and 'obj' in response:
                # Сервер доступен
                self.server_health[server_name]["status"] = "online"
                self.server_health[server_name]["last_check"] = datetime.datetime.now()
                self.server_health[server_name]["last_error"] = None
                self.server_health[server_name]["consecutive_failures"] = 0
                return True
            else:
                raise Exception("Неверный ответ от сервера")
                
        except Exception as e:
            # Сервер недоступен
            self.server_health[server_name]["status"] = "offline"
            self.server_health[server_name]["last_check"] = datetime.datetime.now()
            self.server_health[server_name]["last_error"] = str(e)
            self.server_health[server_name]["consecutive_failures"] += 1
            
            # Если сервер долго недоступен, помечаем X3 как None
            if self.server_health[server_name]["consecutive_failures"] > 3:
                server_info["x3"] = None
            
            logger.warning(f"Сервер {server_name} недоступен: {e}")
            return False
    
    def check_all_servers_health(self):
        """Проверяет здоровье всех серверов"""
        results = {}
        for server in self.servers:
            server_name = server["name"]
            results[server_name] = self.check_server_health(server_name)
        return results
    
    
    
    def get_server_health_status(self):
        """Возвращает статус здоровья всех серверов"""
        return self.server_health
    
    def get_healthy_servers(self):
        """Возвращает список доступных серверов"""
        healthy_servers = []
        for server in self.servers:
            if self.server_health[server["name"]]["status"] == "online":
                healthy_servers.append(server)
        return healthy_servers

# Создаем глобальный экземпляр менеджера серверов
server_manager = MultiServerManager(SERVERS_BY_LOCATION)
# Менеджер только для новых клиентов
new_client_manager = MultiServerManager(SERVERS_BY_LOCATION)

def calculate_time_remaining(expiry_timestamp, show_expired_as_negative=False):
    """
    Вычисляет оставшееся время до деактивации ключа
    """
    if not expiry_timestamp or expiry_timestamp == 0:
        return "—"
    
    try:
        # Конвертируем timestamp в datetime
        expiry_dt = datetime.datetime.fromtimestamp(expiry_timestamp)
        now = datetime.datetime.now()
        
        # Вычисляем разность
        time_diff = expiry_dt - now
        
        if time_diff.total_seconds() <= 0:
            if show_expired_as_negative:
                # Показываем, сколько времени прошло с момента истечения
                expired_diff = now - expiry_dt
                days = expired_diff.days
                hours, remainder = divmod(expired_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                time_parts = []
                if days > 0:
                    time_parts.append(f"{days} дн.")
                if hours > 0:
                    time_parts.append(f"{hours} ч.")
                if minutes > 0:
                    time_parts.append(f"{minutes} мин.")
                
                if not time_parts:
                    return "Только что истек"
                
                return f"Истек {time_parts[0]}" if len(time_parts) == 1 else f"Истек {' '.join(time_parts)}"
            else:
                return "Истек"
        
        # Извлекаем дни, часы и минуты
        days = time_diff.days
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        # Формируем строку
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} дн.")
        if hours > 0:
            time_parts.append(f"{hours} ч.")
        if minutes > 0:
            time_parts.append(f"{minutes} мин.")
        
        if not time_parts:
            return "Менее минуты"
        
        return " ".join(time_parts)
        
    except Exception as e:
        logger.error(f"Ошибка вычисления оставшегося времени: {e}")
        return "—"

def format_vpn_key_message(email, status, server, expiry, key, expiry_timestamp=None):
    """
    Форматирует сообщение с информацией о VPN ключе
    """
    status_icon = UIEmojis.SUCCESS if status == "Активен" else UIEmojis.ERROR
    
    # Вычисляем оставшееся время
    time_remaining = calculate_time_remaining(expiry_timestamp) if expiry_timestamp else "—"
    
    message = (
        f"{UIStyles.header('Ваш VPN ключ')}\n\n"
        f"<b>Email:</b> <code>{email}</code>\n"
        f"<b>Статус:</b> {status_icon} {UIStyles.highlight(status)}\n"
        f"<b>Сервер:</b> {server}\n"
        f"<b>Осталось:</b> {time_remaining}\n\n"
        f"<code>{key}</code>\n"
        f"{UIStyles.description('Нажмите на ключ выше, чтобы скопировать')}"
    )
    
    return message


async def check_user_has_existing_keys(user_id: str, server_manager) -> bool:
    """
    Проверяет, есть ли у пользователя существующие ключи на серверах
    :param user_id: ID пользователя
    :param server_manager: Менеджер серверов
    :return: True если есть ключи, False если нет
    """
    try:
        logger.info(f"Проверка существующих ключей для пользователя {user_id}")
        
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                server_name = server['name']
                inbounds = xui.list()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    
                    for client in clients:
                        email = client.get('email', '')
                        # Проверяем, принадлежит ли ключ этому пользователю
                        if email.startswith(f"{user_id}_") or email.startswith(f"trial_{user_id}_"):
                            logger.info(f"Найден существующий ключ для пользователя {user_id}: {email} на сервере {server_name}")
                            return True
                            
            except Exception as e:
                logger.error(f"Ошибка проверки ключей на сервере {server['name']}: {e}")
                continue
        
        logger.info(f"У пользователя {user_id} нет существующих ключей")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка проверки существующих ключей для пользователя {user_id}: {e}")
        return False


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    user_id = str(update.effective_user.id)
    has_existing_keys = False  # Инициализируем переменную
    
    # Дополнительное логирование для отладки
    logger.info(f"START_DEBUG: user_id={user_id}, context.args={context.args}")
    
    # Регистрацию перенесли в конец start после обработки реферала и выдачи ключа
    
    # Проверяем реферальную ссылку
    # Telegram передает аргументы команды /start в context.args
    referral_code = None
    
    # Сначала проверяем context.args (основной способ)
    if context.args and len(context.args) > 0:
        logger.info(f"START_REFERRAL: context.args={context.args}")
        # Проверяем, является ли аргумент числом (user_id)
        if context.args[0].isdigit():
            referral_code = context.args[0]
            logger.info(f"START_REFERRAL: Found referral code in context.args: {referral_code}")
        else:
            logger.info(f"START_REFERRAL: context.args[0] is not a digit: {context.args[0]}")
    else:
        logger.info(f"START_REFERRAL: context.args is empty or None: {context.args}")
    
    # Если не нашли в context.args, проверяем update.message.text (резервный способ)
    if not referral_code and update.message and update.message.text:
        logger.info(f"START_REFERRAL: Checking message text: {update.message.text}")
        import re
        # Ищем числовые ID в тексте сообщения
        match = re.search(r'(\d+)', update.message.text)
        if match:
            referral_code = match.group(1)
            logger.info(f"START_REFERRAL: Found referral code in message text: {referral_code}")
        else:
            logger.info(f"START_REFERRAL: No numeric ID found in message text")
    
    if referral_code:
        referrer_id = decode_referral_code(referral_code)
        
        if referrer_id and referrer_id != user_id:
            # Логируем попытку создания реферальной связи
            logger.info(f"START_REFERRAL: referrer_id={referrer_id}, referred_id={user_id}")
            
            # Проверяем, есть ли у пользователя платные покупки
            has_paid_purchases = await is_known_user(user_id)
            
            # Проверяем, есть ли у пользователя существующие ключи на серверах
            has_existing_keys = await check_user_has_existing_keys(user_id, new_client_manager)
            
            if has_paid_purchases or has_existing_keys:
                # Пользователь уже имеет платные покупки или ключи - реферальная награда не будет выдана
                if has_paid_purchases:
                    logger.info(f"START_REFERRAL: User {user_id} has paid purchases, no referral reward")
                if has_existing_keys:
                    logger.info(f"START_REFERRAL: User {user_id} has existing keys on servers, no referral reward")
                welcome_text = UIMessages.welcome_referral_existing_user_message()
            else:
                # Пытаемся сохранить реферальную связь
                connection_saved = await save_referral_connection(referrer_id, user_id, server_manager)
                
                # Логируем результат
                logger.info(f"START_REFERRAL: connection_saved={connection_saved}")
                
                if connection_saved:
                    days = await get_config('points_days_per_point', '14')
                    logger.info(f"START_REFERRAL: Получено значение days из конфигурации = {days}")
                    welcome_text = UIMessages.welcome_referral_new_user_message(days)
                else:
                    # Пользователь уже участвовал в реферальной системе — показываем общее сообщение как для не нового пользователя
                    welcome_text = UIMessages.welcome_referral_existing_user_message()
        else:
            logger.info(f"START_DEBUG: Invalid referral - referrer_id={referrer_id}, user_id={user_id}")
            welcome_text = UIMessages.welcome_message()
    else:
        logger.info(f"START_DEBUG: No referral code found - context.args={context.args}, message_text={update.message.text if update.message else 'None'}")
        # Используем единый стиль для приветственного сообщения (только если не было реферальной ссылки)
        welcome_text = UIMessages.welcome_message()
    
    # Очищаем навигационный стек и добавляем главное меню
    context.user_data['nav_stack'] = ['main_menu']
    logger.info(f"START: Initialized stack: {context.user_data['nav_stack']}")
    
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return
    
    # Дополнительное логирование для отладки
    logger.info(f"START_MESSAGE: message={message}, welcome_text_length={len(welcome_text) if welcome_text else 0}")
    
    # Автовыдача обычного ключа на 14 дней новому клиенту (по БД реф. системы)
    try:
        user_id_str = str(update.effective_user.id)
        is_new = not await is_known_user(user_id_str)
        
        # Проверяем, есть ли у пользователя существующие ключи на серверах (если еще не проверяли)
        if not referral_code:
            has_existing_keys = await check_user_has_existing_keys(user_id_str, new_client_manager)
        # Если была реферальная ссылка, has_existing_keys уже проверен выше
        
        if is_new and not has_existing_keys:
            xui, server_name = new_client_manager.get_best_location_server()
            unique_email = f"{user_id_str}_{uuid.uuid4()}"
            response = xui.addClient(day=14, tg_id=user_id_str, user_email=unique_email, timeout=15)
            if response and getattr(response, 'status_code', None) == 200:
                link = xui.link(unique_email)
                expiry_time = datetime.datetime.now() + datetime.timedelta(days=14)
                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                expiry_ts = int(expiry_time.timestamp())
                welcome_text += "\n\n" + UIStyles.info_message("Вам выдан бесплатный ключ на 14 дней") + "\n\n"
                welcome_text += format_vpn_key_message(
                    email=unique_email,
                    status='Активен',
                    server=server_name,
                    expiry=expiry_str,
                    key=link,
                    expiry_timestamp=expiry_ts
                )
        elif is_new and has_existing_keys:
            logger.info(f"Пользователь {user_id_str} новый в БД, но уже имеет ключи на серверах - пропускаем выдачу")
        elif not is_new:
            logger.info(f"Пользователь {user_id_str} уже известен в БД - пропускаем выдачу")
    except Exception as e:
        logger.error(f"START free key issue error: {e}")

    # Теперь, когда все проверки выполнены, регистрируем пользователя
    try:
        await register_simple_user(user_id)
    except Exception as e:
        logger.error(f"Register user failed: {e}")
    # Отправляем меню с фото
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')

async def edit_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирует существующее сообщение на главное меню"""
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Используем единый стиль для приветственного сообщения
    welcome_text = UIMessages.welcome_message()
    message = update.callback_query.message
    logger.info(f"EDIT_MAIN_MENU: Редактируем сообщение {message.message_id}")
    try:
        # Отправляем меню с фото
        await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')
        logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано")
    except Exception as e:
        logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования сообщения: {e}")
        # Если не удалось отредактировать, отправляем новое
        logger.info("EDIT_MAIN_MENU: Вызываем start() как fallback")
        await start(update, context)

# Новая команда /instruction — с кнопками выбора платформы
async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    # Добавляем текущее состояние в навигационный стек
    if not context.user_data.get('nav_stack'):
        context.user_data['nav_stack'] = ['main_menu']
    stack = context.user_data['nav_stack']
    if not stack or stack[-1] != 'instruction_menu':
        push_nav(context, 'instruction_menu')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Android", callback_data="instr_android")],
        [InlineKeyboardButton("iOS", callback_data="instr_ios")],
        [InlineKeyboardButton("Windows", callback_data="instr_windows")],
        [InlineKeyboardButton("macOS", callback_data="instr_macos")],
        [InlineKeyboardButton("Android TV", callback_data="instr_tv")],
        [InlineKeyboardButton("FAQ", callback_data="instr_faq")],
        [UIButtons.back_button()],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("instruction_menu: message is None")
        return
    
    # Используем единый стиль для сообщения
    instruction_text = UIMessages.instruction_menu_message()
    await safe_edit_or_reply_universal(message, instruction_text, reply_markup=keyboard, parse_mode="HTML", menu_type='instruction_menu')

# Обработка кнопок инструкции
async def instruction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    texts = {
        "instr_android": (
            "<b>Android (v2RayTun)</b>\n"
            "1. <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">Скачайте v2RayRun из Google Play</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В приложении нажмите + → Добавить из буфера обмена.\n"
            "4. Подключитесь к VPN.\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или телефон.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_ios": (
            "<b>iPhone (v2RayTun)</b>\n"
            "1. <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=iphone\">Скачайте v2RayTun из App Store</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. Откройте приложение V2RayTun.\n"
            "4. Нажмите + → Добавить из буфера обмена.\n"
            "5. Выберите добавленный профиль и подключитесь.\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или телефон.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_windows": (
            "<b>Windows (v2RayTun)</b>\n"
            "1. <a href=\"https://storage.v2raytun.com/v2RayTun_Setup.exe\">Скачайте v2RayTun для Windows</a> и установите программу.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В v2RayTun нажмите на + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или компьютер.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_macos": (
            "<b>Mac (v2RayTun)</b>\n"
            "1. <a href=\"https://apps.apple.com/us/app/v2raytun/id6476628951?platform=mac\">Скачайте v2RayTun для Mac</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В v2RayTun нажмите на + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или Mac.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),
        "instr_tv": (
            "<b>Android TV (v2RayTun)</b>\n"
            "1. <a href=\"https://play.google.com/store/apps/details?id=com.v2raytun.android\">Скачайте v2RayTun для Android TV</a>.\n"
            "2. В боте нажмите 'Мои ключи' и скопируйте VLESS-ссылку.\n"
            "3. В v2RayTun нажмите на + → Добавить из буфера обмена.\n"
            "4. Включите профиль (нажмите на переключатель или кнопку 'Включить').\n"
            "\n<b>Советы:</b>\n- Если не удаётся подключиться, попробуйте перезапустить приложение или Android TV.\n- Используйте только одну VPN-программу одновременно.\n\n<b>Безопасность:</b> Не делитесь своим VPN-ключом с другими!"
        ),

        "instr_faq": (
            "<b>Часто задаваемые вопросы (FAQ)</b>\n\n"
            "<b>VPN не подключается</b>\n- Проверьте интернет-соединение (Wi-Fi/мобильный интернет).\n- Перезапустите приложение.\n- Убедитесь, что скопировали ссылку полностью.\n\n"
            "<b>Не удаётся импортировать ключ</b>\n- Проверьте, что скопировали именно VLESS-ссылку из бота.\n- Попробуйте ещё раз скопировать и импортировать.\n\n"
            "<b>Можно ли использовать один ключ на нескольких устройствах?</b>\n- Нет, ключ предназначен только для одного пользователя. Не делитесь им с другими.\n\n"
            "<b>Как продлить подписку?</b>\n- Просто купите новый ключ через бота — он заменит старый."
        )
    }
    if data == "back":
        await universal_back_callback(update, context)
        return
    elif data in ["instr_android", "instr_ios", "instr_windows", "instr_macos", "instr_faq", "instr_tv"]:
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'instruction_platform':
            push_nav(context, 'instruction_platform')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
    ])
    await safe_edit_or_reply(query.message, texts.get(data, "Инструкция не найдена."), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

async def update_payment_activation(payment_id: str, activated: int):
    import aiosqlite
    from .keys_db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET activated = ? WHERE payment_id = ?', (activated, payment_id))
        await db.commit()
    logger.info(f"Обновлен статус активации: payment_id={payment_id}, activated={activated}")


# === Обработка платежей ===

async def handle_payment(update, context, price, period):
    logger.info(f"handle_payment вызвана: price={price}, period={period}")
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'payment':
        push_nav(context, 'payment')
    user = update.effective_user if hasattr(update, 'effective_user') else update.from_user
    user_id = str(user.id)
    logger.info(f"handle_payment: user_id={user_id}")
    
    # Получаем правильный объект сообщения
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    logger.info(f"handle_payment: message={message}, message_id={getattr(message, 'message_id', 'None')}")
    try:
        # Проверка на существующий pending-платёж по user_id и period
        payment_info = await get_pending_payment(user_id, period)
        logger.info(f"Проверка существующих платежей: user_id={user_id}, period={period}, found={payment_info is not None}")
        
        # Проверяем pending платежи пользователя и отменяем только неоплаченные
        import aiosqlite
        from .keys_db import DB_PATH
        logger.info(f"HANDLE_PAYMENT: Подключаемся к базе данных по пути: {DB_PATH}")
        async with aiosqlite.connect(DB_PATH) as db:
            # Проверяем существование таблицы payments
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'") as cursor:
                table_exists = await cursor.fetchone()
                logger.info(f"HANDLE_PAYMENT: Таблица payments существует: {table_exists is not None}")
                if not table_exists:
                    logger.error("HANDLE_PAYMENT: Таблица payments не найдена! Создаем её...")
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS payments (
                            user_id TEXT,
                            payment_id TEXT PRIMARY KEY,
                            status TEXT,
                            created_at INTEGER,
                            meta TEXT,
                            activated INTEGER DEFAULT 0
                        )
                    ''')
                    await db.commit()
                    logger.info("HANDLE_PAYMENT: Таблица payments создана")
            
            # Получаем все pending платежи пользователя
            async with db.execute('''
                SELECT payment_id, status FROM payments WHERE user_id = ? AND status = ?
            ''', (user_id, 'pending')) as cursor:
                pending_payments = await cursor.fetchall()
                logger.info(f"Найдено {len(pending_payments)} pending платежей для user_id={user_id}")
            
            # Просто помечаем все pending платежи как отмененные в БД
            # YooKassa автоматически отменит их через 15 минут
            canceled_count = len(pending_payments)
            if canceled_count > 0:
                logger.info(f"Помечаем {canceled_count} pending платежей как отмененные (YooKassa отменит их автоматически через 15 минут)")
            
            # Обновляем статус в БД для отмененных платежей
            if canceled_count > 0:
                await db.execute('UPDATE payments SET status = ? WHERE user_id = ? AND status = ?', ('canceled', user_id, 'pending'))
                await db.commit()
                logger.info(f"Отменено {canceled_count} pending платежей для user_id={user_id}")
        
        # 2. Создаём новый платёж или обрабатываем покупку за баллы
        now = int(datetime.datetime.now().timestamp())
        key_id = str(uuid.uuid4())
        unique_email = f'{user_id}_{key_id}'
        
        # Проверяем, это покупка за баллы
        if period == "points_month":
            # Покупка за баллы - сначала создаем ключ, потом списываем баллы
            try:
                # Проверяем баллы
                points_info = await get_user_points(user_id)
                if points_info['points'] < 1:
                    await safe_edit_or_reply(message, f"{UIEmojis.ERROR} Недостаточно баллов!")
                    return
                
                # Создаем VPN ключ СНАЧАЛА
                selected_location = context.user_data.get("selected_location", "auto")
                if selected_location == "auto":
                    # Для автовыбора выбираем лучшую локацию
                    xui, server_name = new_client_manager.get_best_location_server()
                else:
                    xui, server_name = new_client_manager.get_server_by_user_choice(selected_location, "auto")
                points_days = int(await get_config('points_days_per_point', '14'))
                response = xui.addClient(day=points_days, tg_id=user.id, user_email=unique_email, timeout=15)
                
                if response and getattr(response, 'status_code', None) == 200:
                    # Ключ создан успешно - ТЕПЕРЬ списываем баллы
                    success = await spend_points(user_id, 1, "Покупка VPN за баллы", bot=context.bot)
                    if not success:
                        # Если не удалось списать баллы, удаляем созданный ключ
                        try:
                            xui.removeClient(unique_email)
                            logger.warning(f"Removed key {unique_email} due to points spending failure")
                        except Exception as e:
                            logger.error(f"Failed to remove key {unique_email} after points failure: {e}")
                            # Уведомляем админа о критической ошибке
                            await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось удалить ключ после неудачного списания баллов:\nКлюч: {unique_email}\nПользователь: {user_id}\nОшибка: {str(e)}")
                        await safe_edit_or_reply(message, f"{UIEmojis.ERROR} Ошибка при списании баллов!")
                        return
                    expiry_time = datetime.datetime.now() + datetime.timedelta(days=points_days)
                    expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                    expiry_timestamp = int(expiry_time.timestamp())
                    
                    msg = format_vpn_key_message(
                        email=unique_email,
                        status='Активен',
                        server=server_name,
                        expiry=expiry_str,
                        key=xui.link(unique_email),
                        expiry_timestamp=expiry_timestamp
                    )
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
                    ])
                    await safe_edit_or_reply(message, msg, reply_markup=keyboard, parse_mode="HTML")
                    
                    # Логика учёта покупок перенесена; агрегаты в users не ведём
                    
                    # Проверяем реферальную связь и выдаем баллы атомарно
                    try:
                        referrer_id = await get_pending_referral(user_id)
                        if referrer_id:
                            # Атомарно выдаем награду
                            reward_success = await atomic_referral_reward(referrer_id, user_id, f"points_{key_id}", server_manager)
                            
                            if reward_success:
                                # Уведомляем реферера
                                try:
                                    await context.bot.send_message(
                                        chat_id=referrer_id,
                                        text="Поздравляем! Ваш реферал купил VPN и вы получили 1 балл!"
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка отправки уведомления рефереру {referrer_id}: {e}")
                            else:
                                logger.error(f"Ошибка выдачи реферальной награды для {referrer_id}")
                                # Уведомляем админа о критической ошибке реферальной системы
                                await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось выдать реферальную награду:\nРеферер: {referrer_id}\nРеферал: {user_id}\nПлатеж: points_{key_id}")
                    except Exception as e:
                        logger.error(f"Ошибка обработки реферальной награды: {e}")
                        # Уведомляем админа о критической ошибке реферальной системы
                        await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Ошибка обработки реферальной награды:\nРеферер: {referrer_id}\nРеферал: {user_id}\nОшибка: {str(e)}")
                    
                    return
                else:
                    # Ключ не создан - баллы не списывались, просто сообщаем об ошибке
                    await safe_edit_or_reply(message, f"{UIEmojis.ERROR} Ошибка при создании ключа.")
                    return
                    
            except Exception as e:
                logger.error(f"Ошибка покупки за баллы: {e}")
                # Баллы не списывались, просто сообщаем об ошибке
                await safe_edit_or_reply(message, f"{UIEmojis.ERROR} Ошибка при покупке.")
                return
        
        # Обычная покупка за деньги
        try:
            payment = Payment.create({
                "amount": {"value": price, "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": f"https://t.me/{user.id}"},
                "capture": True,
                "description": f"VPN {period} для {user_id}",
                "metadata": {
                    "user_id": user_id, 
                    "key_id": key_id, 
                    "type": period,
                    "selected_location": context.user_data.get("selected_location", "auto")
                },
                "receipt": {
                    "customer": {"email": f"{user_id}@vpn-x3.ru"},
                    "items": [{
                        "description": f"VPN {period} для {user_id}",
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1
                    }]
                }
            })
            payment_id = payment.id
        except Exception as e:
            logger.exception(f"Ошибка создания платежа для user_id={user_id}")
            # Уведомляем админа о критической ошибке создания платежа
            await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать платеж:\nПользователь: {user_id}\nПериод: {period}\nЦена: {price}\nОшибка: {str(e)}")
            await safe_edit_or_reply(message, 'Ошибка при создании платежа. Попробуйте позже.')
            return
        
        # Показываем ссылку на оплату
        try:
            # Определяем переменные для текста
            if period.startswith('extend_'):
                # Для продления убираем префикс extend_
                actual_period = period.replace('extend_', '')
                period_text = "1 месяц" if actual_period == "month" else "3 месяца"
            else:
                # Для обычной покупки
                period_text = "1 месяц" if period == "month" else "3 месяца"
            payment_url = payment.confirmation.confirmation_url
            
            # Сохраняем message_id для отслеживания платежа
            payment_message_ids[payment.id] = message.message_id
            logger.info(f"Сохранен message_id {message.message_id} для payment_id {payment.id}")
            logger.info(f"Текущее состояние payment_message_ids: {payment_message_ids}")
            
            # Для продления сохраняем информацию о сообщении для последующего редактирования
            if period.startswith('extend_'):
                extension_messages[payment.id] = (message.chat_id, message.message_id)
                logger.info(f"Сохранена информация о сообщении продления: payment_id={payment.id}, chat_id={message.chat_id}, message_id={message.message_id}")
            
            # Редактируем сообщение с меню выбора периода на информацию об оплате
            try:
                # Получаем текст сообщения об оплате
                payment_text = (
                    f"<b>Оплата подписки на {period_text}</b>\n\n"
                    f"Сумма: <b>{price}₽</b>\n"
                    f"Период: <b>{period_text}</b>\n\n"
                    f"<a href='{payment_url}'>Перейти к оплате</a>\n\n"
                    f"{UIEmojis.WARNING} <i>Ссылка действительна 15 минут</i>\n\n"
                    f"После оплаты ключ будет активирован автоматически."
                )
                
                # Создаем кнопку "Назад"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
                ])
                
                await message.edit_text(payment_text, reply_markup=keyboard, parse_mode="HTML")
                logger.info(f"Отредактировано сообщение с меню выбора периода на информацию об оплате: message_id={message.message_id}")
            except Exception as e:
                logger.error(f"Не удалось отредактировать сообщение с меню выбора периода: {e}")
                # Если не удалось отредактировать, удаляем и отправляем новое
                try:
                    await message.delete()
                    logger.info(f"Удалено сообщение с меню выбора периода: message_id={message.message_id}")
                except Exception as delete_error:
                    logger.error(f"Не удалось удалить сообщение с меню выбора периода: {delete_error}")
            
            # Подготавливаем метаданные платежа
            payment_meta = {"price": price, "type": period, "key_id": key_id, "unique_email": unique_email}
            
            # Добавляем информацию о продлении, если это продление ключа
            if period.startswith('extend_') and context.user_data.get('extension_key_email'):
                payment_meta['extension_key_email'] = context.user_data['extension_key_email']
                logger.info(f"Добавлена информация о продлении в метаданные: {context.user_data['extension_key_email']}")
            
            await add_payment(user_id, payment.id, 'pending', now, payment_meta)
        except Exception as e:
            logger.exception(f"Ошибка отправки сообщения об оплате для user_id={user_id}")
            await safe_edit_or_reply(message, 'Ошибка при отправке информации об оплате.')
    except Exception as e:
        logger.exception(f"Ошибка в handle_payment для user_id={user_id}")
        await safe_edit_or_reply(message, 'Произошла внутренняя ошибка. Администратор уже уведомлён.')
        await notify_admin(context.bot, f"Ошибка в handle_payment для user_id={user_id}: {e}\n{traceback.format_exc()}")



async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if not context.user_data.get('nav_stack'):
        context.user_data['nav_stack'] = ['main_menu']
    stack = context.user_data['nav_stack']
    if not stack or stack[-1] != 'mykeys_menu':
        push_nav(context, 'mykeys_menu')
    user = update.effective_user
    user_id = str(user.id)
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("mykeys_menu: message is None")
        return
    
    # Получаем текущую страницу из callback_data или устанавливаем 0
    current_page = 0
    if update.callback_query and update.callback_query.data.startswith('keys_page_'):
        try:
            current_page = int(update.callback_query.data.split('_')[2])
            logger.info(f"Переход на страницу {current_page} для user_id={user_id}")
        except (ValueError, IndexError):
            current_page = 0
            logger.error(f"Ошибка парсинга номера страницы: {update.callback_query.data}")
    
    try:
        # Ищем клиентов на всех серверах
        all_clients = []
        unique_clients = {} # Словарь для хранения уникальных клиентов по email
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(user_id) or client['email'].startswith(f'trial_{user_id}'):
                            client['server_name'] = server['name']  # Добавляем имя сервера
                            if client['email'] not in unique_clients:
                                unique_clients[client['email']] = client
                                all_clients.append(client)
            except Exception as e:
                logger.error(f"Ошибка при получении клиентов с сервера {server['name']}: {e}")

        if not all_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
            ])
            await safe_edit_or_reply(message, 'У вас нет активных ключей.', reply_markup=keyboard)
            return

        # Настройки пагинации
        keys_per_page = 1  # Показываем по 1 ключу на страницу
        total_pages = (len(all_clients) + keys_per_page - 1) // keys_per_page
        
        # Ограничиваем текущую страницу
        current_page = max(0, min(current_page, total_pages - 1))
        
        # Получаем ключи для текущей страницы
        start_idx = current_page * keys_per_page
        end_idx = start_idx + keys_per_page
        page_clients = all_clients[start_idx:end_idx]
        
        # Формируем сообщение для текущей страницы
        now = int(datetime.datetime.now().timestamp())
        page_text = f"{UIStyles.header(f'Ваши ключи (стр. {current_page + 1}/{total_pages})')}\n\n"
        
        for i, client in enumerate(page_clients, start_idx + 1):
            expiry = int(client.get('expiryTime', 0) / 1000)
            is_active = client.get('enable', False) and expiry > now
            expiry_str = datetime.datetime.fromtimestamp(expiry).strftime('%d.%m.%Y %H:%M') if expiry else '—'
            status = 'Активен' if is_active else 'Неактивен'
            server_name = client.get('server_name', 'Неизвестный сервер')
            
            xui = None
            for server in server_manager.servers:
                if server['name'] == server_name:
                    xui = server['x3']
                    break
            
            if xui:
                link = xui.link(client["email"])
                
                # Добавляем информацию о ключе
                status_icon = UIEmojis.SUCCESS if status == "Активен" else UIEmojis.ERROR
                
                # Вычисляем оставшееся время
                time_remaining = calculate_time_remaining(expiry)
                
                # Получаем имя ключа из поля subId
                key_name = client.get('subId', '').strip()
                if key_name:
                    page_text += f"{UIStyles.subheader(f'{i}. {key_name}')}\n"
                else:
                    page_text += f"{UIStyles.subheader(f'{i}. Ключ #{i}')}\n"
                
                page_text += f"<b>Email:</b> <code>{client['email']}</code>\n"
                page_text += f"<b>Статус:</b> {status_icon} {status}\n"
                page_text += f"<b>Сервер:</b> {server_name}\n"
                page_text += f"<b>Осталось:</b> {time_remaining}\n\n"
                page_text += f"<code>{link}</code>\n\n"
                page_text += f"{UIStyles.description('Нажмите на ключ выше, чтобы скопировать')}\n\n"
        
        
        # Создаем клавиатуру с навигацией
        keyboard_buttons = []
        
        # Кнопка "Продлить" для текущего ключа (если ключ не истек)
        current_client = page_clients[0] if page_clients else None
        if current_client:
            expiry = int(current_client.get('expiryTime', 0) / 1000)
            now = int(datetime.datetime.now().timestamp())
            # Показываем кнопку продления если ключ активен или истек менее чем 30 дней назад
            if expiry > now - (30 * 24 * 3600):  # Можно продлить в течение 30 дней после истечения
                # Создаем короткий идентификатор для ключа
                import hashlib
                short_id = hashlib.md5(f"{user_id}:{current_client['email']}".encode()).hexdigest()[:8]
                extension_keys_cache[short_id] = current_client['email']
                keyboard_buttons.append([InlineKeyboardButton("Продлить ключ", callback_data=f"ext_key:{short_id}")])
            
            # Кнопка для переименования ключа
            rename_short_id = hashlib.md5(f"rename:{current_client['email']}".encode()).hexdigest()[:8]
            keyboard_buttons.append([InlineKeyboardButton("Переименовать ключ", callback_data=f"rename_key:{rename_short_id}")])
        
        # Кнопки навигации по страницам
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton(f"Пред. {UIEmojis.PREV}", callback_data=f"keys_page_{current_page - 1}"))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(f"След. {UIEmojis.NEXT}", callback_data=f"keys_page_{current_page + 1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        # Кнопка "Назад"
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        # Отправляем сообщение с пагинацией
        await safe_edit_or_reply_universal(message, page_text, reply_markup=keyboard, parse_mode="HTML", menu_type='mykeys_menu')
        
    except Exception as e:
        logger.exception(f"Ошибка в mykey для user_id={user_id}: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        await safe_edit_or_reply(message, f'{UIEmojis.ERROR} Ошибка: {e}', reply_markup=keyboard)




async def init_all_db():
    from .keys_db import init_payments_db, DB_PATH, REFERRAL_DB_PATH, DATA_DIR
    from .notifications_db import init_notifications_db, NOTIFICATIONS_DB_PATH
    
    # Создаем папку data если её нет
    import os
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Создана/проверена папка для баз данных: {DATA_DIR}")
    
    logger.info("Инициализация баз данных...")
    logger.info(f"Путь к базе платежей: {DB_PATH}")
    logger.info(f"Путь к реферальной базе: {REFERRAL_DB_PATH}")
    logger.info(f"Путь к базе уведомлений: {NOTIFICATIONS_DB_PATH}")
    
    logger.info("Вызываем init_payments_db()...")
    await init_payments_db()
    logger.info("init_payments_db() завершена")
    logger.info("База данных платежей инициализирована")
    
    await init_referral_db()  # Инициализируем реферальную систему и конфиг
    logger.info("Реферальная база данных инициализирована")
    
    await init_notifications_db()  # Инициализируем базу данных уведомлений
    logger.info("База данных уведомлений инициализирована")
    
    logger.info("Все базы данных успешно инициализированы")


async def auto_activate_keys(app):
    logger.info("Запуск auto_activate_keys")
    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            
            # Сначала очищаем просроченные pending платежи (каждый цикл)
            expired_count = await cleanup_expired_pending_payments(minutes_old=20)
            if expired_count > 0:
                logger.info(f"Удалено {expired_count} просроченных pending платежей")
                
                # Упрощенная очистка кэша сообщений продления
                # Очищаем записи старше 1 часа (платежи YooKassa истекают через 15 минут)
                hour_ago = int(datetime.datetime.now().timestamp()) - 3600
                expired_extension_messages = []
                
                for payment_id in list(extension_messages.keys()):
                    try:
                        # Получаем информацию о платеже из основного кэша
                        if payment_id in payment_message_ids:
                            # Платеж еще активен, не удаляем
                            continue
                        else:
                            # Платеж не найден в активных, можно удалить
                            expired_extension_messages.append(payment_id)
                            extension_messages.pop(payment_id, None)
                    except Exception as e:
                        logger.error(f"Ошибка проверки платежа {payment_id} для очистки кэша: {e}")
                
                if expired_extension_messages:
                    logger.info(f"Очищен кэш сообщений продления для {len(expired_extension_messages)} неактивных платежей")
            
            # Очищаем старые записи каждые 360 циклов (примерно каждый час при sleep=10)
            if cycle_count % 360 == 0:
                old_count = await cleanup_old_payments(days_old=7)
                if old_count > 0:
                    logger.info(f"Удалено {old_count} старых записей платежей (старше 7 дней)")
                
                # Очищаем кэш ключей для продления (старше 1 часа)
                hour_ago = int(datetime.datetime.now().timestamp()) - 3600
                old_keys = []
                for short_id, key_email in list(extension_keys_cache.items()):
                    # Проверяем, существует ли ключ на серверах
                    try:
                        xui, server_name = server_manager.find_client_on_any_server(key_email)
                        if not xui or not server_name:
                            old_keys.append(short_id)
                    except:
                        old_keys.append(short_id)
                
                for short_id in old_keys:
                    extension_keys_cache.pop(short_id, None)
                
                if old_keys:
                    logger.info(f"Очищено {len(old_keys)} старых записей из extension_keys_cache")
                
                # Очищаем кэш платежей (старше 1 часа)
                old_payments = []
                for payment_id in list(payment_message_ids.keys()):
                    # Проверяем, есть ли активный платеж в базе
                    try:
                        from .keys_db import get_all_pending_payments
                        pending_payments = await get_all_pending_payments()
                        pending_ids = [p['payment_id'] for p in pending_payments]
                        if payment_id not in pending_ids:
                            old_payments.append(payment_id)
                    except:
                        old_payments.append(payment_id)
                
                for payment_id in old_payments:
                    payment_message_ids.pop(payment_id, None)
                
                if old_payments:
                    logger.info(f"Очищено {len(old_payments)} старых записей из payment_message_ids")
                
                # Убрали очистку буфера - используем стандартный Docker подход
                
                cycle_count = 0  # Сбрасываем счетчик
            
            # Автоматическое удаление просроченных ключей каждые 720 циклов (каждые 2 часа при sleep=10)
            if cycle_count % 720 == 0:
                deleted_keys_count = await auto_cleanup_expired_keys()
                if deleted_keys_count > 0:
                    logger.info(f"Автоматически удалено {deleted_keys_count} просроченных ключей")
                    logger.info(f"🧹 Автоочистка: удалено {deleted_keys_count} просроченных ключей (старше 3 дней после истечения)")
                else:
                    logger.info("Автоочистка: просроченных ключей для удаления не найдено")
            
            from .keys_db import get_all_pending_payments
            pending_payments = await get_all_pending_payments()
            logger.info(f"Проверка pending платежей: найдено {len(pending_payments)} платежей")
            for payment in pending_payments:
                payment_id = payment['payment_id']
                user_id = payment['user_id']
                meta = payment.get('meta', {})
                key_id = meta.get('key_id')
                unique_email = meta.get('unique_email')
                
                logger.info(f"Обработка платежа: payment_id={payment_id}, user_id={user_id}, status={payment.get('status')}")
                
                try:
                    pay = Payment.find_one(payment_id)
                    logger.info(f"Статус платежа в YooKassa: {pay.status}")
                except Exception as e:
                    logger.error(f"Ошибка поиска платежа: {e}")
                    continue

                # Если платеж успешен
                if pay.status == 'succeeded':
                    period = meta.get('type', 'month')
                    
                    # Получаем message_id для редактирования сообщения
                    message_id = payment_message_ids.get(payment_id)
                    
                    # Проверяем, это продление или новая покупка
                    is_extension = period.startswith('extend_')
                    if is_extension:
                        # Это продление ключа
                        actual_period = period.replace('extend_', '')  # убираем префикс extend_
                        days = 90 if actual_period == '3month' else 30
                        extension_email = meta.get('extension_key_email')
                        
                        logger.info(f"Обработка продления ключа: email={extension_email}, period={actual_period}, days={days}")
                        
                        if not extension_email:
                            logger.error(f"Не найден email ключа для продления в meta: {meta}")
                            continue
                        
                        # Ищем сервер с ключом для продления
                        try:
                            xui, server_name = server_manager.find_client_on_any_server(extension_email)
                            if not xui or not server_name:
                                logger.error(f"Ключ для продления не найден: {extension_email}")
                                await update_payment_status(payment_id, 'failed')
                                continue
                            
                            # Продлеваем ключ
                            response = xui.extendClient(extension_email, days)
                            if response and response.status_code == 200:
                                await update_payment_status(payment_id, 'succeeded')
                                await update_payment_activation(payment_id, 1)
                                
                                # Проверяем реферальную связь и выдаем баллы
                                try:
                                    referrer_id = await get_pending_referral(user_id)
                                    if referrer_id:
                                        # Выдаем 1 балл рефереру (связь уже проверена при переходе по ссылке)
                                        await add_points(
                                            referrer_id, 
                                            1, 
                                            f"Реферал: {user_id} продлил VPN",
                                            payment_id
                                        )
                                        
                                        # Отмечаем награду как выданную
                                        await mark_referral_reward_given(referrer_id, user_id, payment_id)
                                        
                                        # Уведомляем реферера
                                        try:
                                            points_days = await get_config('points_days_per_point', '14')
                                            await app.bot.send_message(
                                                chat_id=referrer_id,
                                                text=(
                                                    f"Поздравляем!\n\n"
                                                    "Ваш друг продлил VPN по вашей реферальной ссылке!\n"
                                                    f"Вы получили 1 балл!\n"
                                                    f"1 балл = {points_days} дней VPN бесплатно!\n\n"
                                                    "Используйте баллы для покупки или продления VPN!"
                                                )
                                            )
                                        except:
                                            pass
                                except Exception as e:
                                    logger.error(f"Ошибка выдачи реферальных баллов при продлении в auto_activate_keys: {e}")
                                    # Уведомляем админа о критической ошибке реферальной системы
                                    await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Ошибка выдачи реферальных баллов при продлении:\nПользователь: {user_id}\nПлатеж: {payment_id}\nОшибка: {str(e)}")
                                
                                # Логика учёта покупок перенесена; агрегаты в users не ведём
                                
                                # Отправляем уведомление о продлении
                                try:
                                    # Получаем новое время истечения
                                    clients_response = xui.list()
                                    expiry_str = "—"
                                    if clients_response.get('success', False):
                                        for inbound in clients_response.get('obj', []):
                                            settings = json.loads(inbound.get('settings', '{}'))
                                            for client in settings.get('clients', []):
                                                if client.get('email') == extension_email:
                                                    expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                                    expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                                                    break
                                    
                                    # Очищаем старые уведомления об истечении для продленного ключа
                                    if notification_manager:
                                        await notification_manager.clear_key_notifications(user_id, extension_email)
                                        await notification_manager.record_key_extension(user_id, extension_email)
                                    
                                    extension_message = UIMessages.key_extended_message(
                                        email=extension_email,
                                        server_name=server_name,
                                        days=days,
                                        expiry_str=expiry_str,
                                        period=actual_period
                                    )
                                    
                                    # Проверяем, есть ли сохраненная информация о сообщении продления
                                    extension_msg_info = extension_messages.get(payment_id)
                                    if extension_msg_info:
                                        chat_id, message_id = extension_msg_info
                                        try:
                                            # Редактируем существующее сообщение
                                            keyboard = InlineKeyboardMarkup([
                                                [InlineKeyboardButton("Мои ключи", callback_data="mykey")],
                                                [InlineKeyboardButton("Главное меню", callback_data="main_menu")]
                                            ])
                                            await app.bot.edit_message_text(
                                                chat_id=chat_id,
                                                message_id=message_id,
                                                text=extension_message,
                                                parse_mode="HTML",
                                                reply_markup=keyboard
                                            )
                                            logger.info(f"Отредактировано сообщение о продлении ключа {extension_email} пользователю {user_id}")
                                            # Удаляем из кэша после успешного редактирования
                                            extension_messages.pop(payment_id, None)
                                        except Exception as edit_error:
                                            logger.error(f"Ошибка редактирования сообщения продления: {edit_error}")
                                            # Fallback: отправляем новое сообщение
                                            try:
                                                await app.bot.send_message(
                                                    chat_id=user_id,
                                                    text=extension_message,
                                                    parse_mode="HTML"
                                                )
                                            except telegram.error.Forbidden:
                                                logger.warning(f"Пользователь {user_id} заблокировал бота (продление ключа)")
                                            except telegram.error.BadRequest as e:
                                                if "Chat not found" in str(e):
                                                    logger.warning(f"Пользователь {user_id} заблокировал бота (продление ключа): {e}")
                                                else:
                                                    logger.error(f"BadRequest ошибка отправки сообщения о продлении: {e}")
                                            except Exception as send_error:
                                                logger.error(f"Ошибка отправки сообщения о продлении: {send_error}")
                                    else:
                                        # Fallback: отправляем новое сообщение, если нет сохраненной информации
                                        try:
                                            await app.bot.send_message(
                                                chat_id=user_id,
                                                text=extension_message,
                                                parse_mode="HTML"
                                            )
                                            logger.info(f"Отправлено новое сообщение о продлении ключа {extension_email} пользователю {user_id}")
                                        except telegram.error.Forbidden:
                                            logger.warning(f"Пользователь {user_id} заблокировал бота (продление ключа fallback)")
                                        except telegram.error.BadRequest as e:
                                            if "Chat not found" in str(e):
                                                logger.warning(f"Пользователь {user_id} заблокировал бота (продление ключа fallback): {e}")
                                            else:
                                                logger.error(f"BadRequest ошибка fallback сообщения о продлении: {e}")
                                        except Exception as send_error:
                                            logger.error(f"Ошибка отправки fallback сообщения о продлении: {send_error}")
                                    
                                except Exception as e:
                                    logger.error(f"Ошибка отправки уведомления о продлении: {e}")
                                
                            else:
                                logger.error(f"Ошибка продления ключа {extension_email}: статус {response.status_code if response else 'None'}")
                                await update_payment_status(payment_id, 'failed')
                                
                        except Exception as e:
                            logger.error(f"Ошибка при продлении ключа {extension_email}: {e}")
                            await update_payment_status(payment_id, 'failed')
                        
                        continue  # Переходим к следующему платежу
                    
                    # Обычная покупка нового ключа
                    days = 90 if period == '3month' else 30
                    
                    # Создание ключа
                    try:
                        # В auto_activate_keys используем сохраненный выбор пользователя из метаданных платежа YooKassa
                        selected_location = pay.metadata.get("selected_location", "auto")
                        if selected_location == "auto":
                            # Для автовыбора выбираем лучшую локацию
                            xui, server_name = new_client_manager.get_best_location_server()
                        else:
                            xui, server_name = new_client_manager.get_server_by_user_choice(selected_location, "auto")
                        response = xui.addClient(day=days, tg_id=user_id, user_email=unique_email, timeout=15)
                        
                        if response.status_code == 200:
                            await update_payment_status(payment_id, 'succeeded')
                            await update_payment_activation(payment_id, 1)
                            
                            # Проверяем реферальную связь и выдаем баллы
                            try:
                                referrer_id = await get_pending_referral(user_id)
                                if referrer_id:
                                    # Выдаем 1 балл рефереру (связь уже проверена при переходе по ссылке)
                                    await add_points(
                                        referrer_id, 
                                        1, 
                                        f"Реферал: {user_id} купил VPN",
                                        payment_id
                                    )
                                    
                                    # Отмечаем награду как выданную
                                    await mark_referral_reward_given(referrer_id, user_id, payment_id)
                                    
                                    # Уведомляем реферера
                                    try:
                                        points_days = await get_config('points_days_per_point', '14')
                                        await app.bot.send_message(
                                            chat_id=referrer_id,
                                            text=(
                                                f"Поздравляем!\n\n"
                                                "Ваш друг купил VPN по вашей реферальной ссылке!\n"
                                                f"Вы получили 1 балл!\n"
                                                f"1 балл = {points_days} дней VPN бесплатно!\n\n"
                                                "Используйте баллы для покупки или продления VPN!"
                                            )
                                        )
                                    except:
                                        pass
                            except Exception as e:
                                logger.error(f"Ошибка выдачи реферальных баллов в auto_activate_keys: {e}")
                                # Уведомляем админа о критической ошибке реферальной системы
                                await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Ошибка выдачи реферальных баллов в auto_activate_keys:\nПользователь: {user_id}\nПлатеж: {payment_id}\nОшибка: {str(e)}")
                            
                            # Логика учёта покупок перенесена; агрегаты в users не ведём
                            
                            # 3. Отправка ключа пользователю с отслеживанием сообщений
                            # Получаем реальное время истечения из XUI API
                            try:
                                # Получаем список клиентов для получения точного времени истечения
                                clients_response = xui.list()
                                if clients_response.get('success', False):
                                    clients = clients_response.get('obj', [])
                                    for inbound in clients:
                                        settings = json.loads(inbound.get('settings', '{}'))
                                        for client in settings.get('clients', []):
                                            if client.get('email') == unique_email:
                                                # Получаем точное время истечения из API
                                                expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                                expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                                                break
                                        else:
                                            continue
                                        break
                                else:
                                    # Fallback: вычисляем время истечения
                                    expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
                                    expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                                    expiry_timestamp = int(expiry_time.timestamp())
                            except Exception as e:
                                logger.error(f"Ошибка получения времени истечения: {e}")
                                # Fallback: вычисляем время истечения
                                expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
                                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                                expiry_timestamp = int(expiry_time.timestamp())
                            
                            msg = format_vpn_key_message(
                                email=unique_email,
                                status='Активен',
                                server=server_name,
                                expiry=expiry_str,
                                key=xui.link(unique_email),
                                expiry_timestamp=expiry_timestamp
                            )
                            
                            keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
                            ])
                            
                            # Формируем полное сообщение о покупке используя единый стиль
                            success_text = UIMessages.success_purchase_message(period, meta.get('price', '100'))
                            
                            # Объединяем сообщения
                            full_message = success_text + msg
                            
                            # Если есть сообщение с оплатой, редактируем его
                            if message_id:
                                try:
                                    await app.bot.edit_message_text(
                                        chat_id=int(user_id),
                                        message_id=message_id,
                                        text=full_message,
                                        reply_markup=keyboard,
                                        parse_mode="HTML"
                                    )
                                    logger.info(f"Отредактировано сообщение с оплатой {message_id} на информацию о ключе")
                                except Exception as edit_error:
                                    logger.error(f"Ошибка редактирования сообщения {message_id}: {edit_error}")
                                    # Если редактирование не удалось, отправляем новое сообщение
                                    try:
                                        await app.bot.send_message(
                                            chat_id=int(user_id),
                                            text=full_message,
                                            reply_markup=keyboard,
                                            parse_mode="HTML"
                                        )
                                        logger.info(f"Отправлено новое сообщение с ключом для user_id={user_id}")
                                    except telegram.error.Forbidden:
                                        logger.warning(f"Пользователь {user_id} заблокировал бота (активация ключа)")
                                    except telegram.error.BadRequest as e:
                                        if "Chat not found" in str(e):
                                            logger.warning(f"Пользователь {user_id} заблокировал бота (активация ключа): {e}")
                                        else:
                                            logger.error(f"BadRequest ошибка отправки ключа после активации: {e}")
                                    except Exception as send_error:
                                        logger.error(f"Ошибка отправки ключа после активации: {send_error}")
                            else:
                                # Если нет сообщения с оплатой, отправляем новое
                                try:
                                    await app.bot.send_message(
                                        chat_id=int(user_id),
                                        text=full_message,
                                        reply_markup=keyboard,
                                        parse_mode="HTML"
                                    )
                                    logger.info(f"Отправлено новое сообщение с ключом для user_id={user_id}")
                                except telegram.error.Forbidden:
                                    logger.warning(f"Пользователь {user_id} заблокировал бота (новый ключ)")
                                except telegram.error.BadRequest as e:
                                    if "Chat not found" in str(e):
                                        logger.warning(f"Пользователь {user_id} заблокировал бота (новый ключ): {e}")
                                    else:
                                        logger.error(f"BadRequest ошибка отправки нового ключа: {e}")
                                except Exception as send_error:
                                    logger.error(f"Ошибка отправки нового ключа: {send_error}")
                            
                            # Удаляем message_id из отслеживания
                            payment_message_ids.pop(payment_id, None)
                            
                    except requests.exceptions.Timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Ошибка активации ключа: {e}")
                        # Уведомляем админа о критической ошибке активации ключа
                        await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось активировать ключ:\nПлатеж: {payment_id}\nПользователь: {user_id}\nОшибка: {str(e)}")
                        continue

                # Если платеж отменен
                elif pay.status in ['canceled', 'refunded']:
                    await update_payment_status(payment_id, pay.status)
                    await update_payment_activation(payment_id, 0)
                    
        except Exception as e:
            logger.error(f"Ошибка в auto_activate_keys: {e}")
            await notify_admin(app.bot, f"Ошибка в auto_activate_keys: {e}\n{traceback.format_exc()}")
        
        await asyncio.sleep(10)


async def auto_cleanup_expired_keys():
    """
    Автоматически удаляет просроченные ключи со всех серверов
    Удаляет ключи, которые истекли более 3 дней назад
    """
    logger.info("Запуск автоматической очистки просроченных ключей...")
    
    try:
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        # 3 дня после истечения = 3 * 24 * 60 * 60 * 1000 миллисекунд
        threshold_ms = now_ms - 3 * 24 * 60 * 60 * 1000
        total_deleted_count = 0
        
        # Очищаем все серверы
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                deleted_count = 0
                inbounds = xui.list()['obj']
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients_to_delete = []
                    
                    # Собираем список клиентов для удаления
                    for client in settings.get("clients", []):
                        expiry = client.get('expiryTime', 0)
                        email = client.get('email', '')
                        
                        # Проверяем, что ключ просрочен более 3 дней
                        if expiry and expiry < threshold_ms:
                            # Удаляем только пользовательские ключи (с подчеркиванием)
                            if '_' in email:
                                clients_to_delete.append(client)
                    
                    # Удаляем найденных клиентов
                    for client in clients_to_delete:
                        try:
                            client_id = client.get('id')
                            inbound_id = inbound['id']
                            email = client.get('email', '')
                            
                            # Извлекаем user_id из email (формат: user_id_email@domain.com)
                            user_id = None
                            if '_' in email:
                                user_id = email.split('_')[0]
                            
                            # Формируем URL для удаления
                            url = f"{xui.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                            logger.info(f"Автоудаление просроченного ключа: inbound_id={inbound_id}, client_id={client_id}, email={email}")
                            
                            # Отправляем запрос на удаление
                            result = xui.ses.post(url)
                            if getattr(result, 'status_code', None) == 200:
                                deleted_count += 1
                                total_deleted_count += 1
                                
                                # Вычисляем, сколько дней назад истек ключ
                                expiry_date = datetime.datetime.fromtimestamp(client.get('expiryTime', 0) / 1000)
                                days_expired = (datetime.datetime.now() - expiry_date).days
                                
                                logger.info(f'Автоудален просроченный ключ: {email} с сервера {server["name"]} (истек {days_expired} дней назад)')
                                
                                # Очищаем связанные данные из кэшей
                                try:
                                    # Очищаем extension_keys_cache
                                    keys_to_remove = []
                                    for short_id, key_email in extension_keys_cache.items():
                                        if key_email == email:
                                            keys_to_remove.append(short_id)
                                    for short_id in keys_to_remove:
                                        extension_keys_cache.pop(short_id, None)
                                    
                                    if keys_to_remove:
                                        logger.info(f"Очищено {len(keys_to_remove)} записей из extension_keys_cache для удаленного ключа {email}")
                                    
                                    # Очищаем payment_message_ids (платежи для этого ключа)
                                    payments_to_remove = []
                                    for payment_id in list(payment_message_ids.keys()):
                                        # Проверяем, связан ли платеж с этим ключом
                                        try:
                                            from .keys_db import get_all_pending_payments
                                            pending_payments = await get_all_pending_payments()
                                            for payment in pending_payments:
                                                if payment['payment_id'] == payment_id:
                                                    meta = payment.get('meta', {})
                                                    if meta.get('key_email') == email:
                                                        payments_to_remove.append(payment_id)
                                                    break
                                        except:
                                            pass
                                    
                                    for payment_id in payments_to_remove:
                                        payment_message_ids.pop(payment_id, None)
                                        extension_messages.pop(payment_id, None)
                                    
                                    if payments_to_remove:
                                        logger.info(f"Очищено {len(payments_to_remove)} записей из payment_message_ids и extension_messages для удаленного ключа {email}")
                                    
                                    # Очищаем уведомления для удаленного ключа
                                    if user_id:
                                        try:
                                            # Используем глобальный notification_manager, инициализируемый в on_startup
                                            if notification_manager:
                                                await notification_manager.clear_key_notifications(user_id, email)
                                        except Exception as e:
                                            logger.error(f"Ошибка очистки уведомлений для удаленного ключа {email}: {e}")
                                        
                                except Exception as e:
                                    logger.error(f"Ошибка очистки кэшей при удалении ключа {email}: {e}")
                                
                                # Отправляем уведомление пользователю об удалении ключа
                                if user_id:
                                    try:
                                        if notification_manager:
                                            await notification_manager._send_deletion_notification(
                                                user_id=user_id,
                                                email=email,
                                                server_name=server["name"],
                                                days_expired=days_expired
                                            )
                                    except Exception as e:
                                        logger.error(f"Ошибка отправки уведомления об удалении пользователю {user_id}: {e}")
                            else:
                                logger.warning(f"Не удалось удалить ключ {email}: status_code={getattr(result, 'status_code', None)}")
                                
                        except Exception as e:
                            logger.error(f"Ошибка при автоудалении ключа {client.get('email', 'unknown')}: {e}")
                            continue
                
                if deleted_count > 0:
                    logger.info(f"Автоудалено {deleted_count} просроченных ключей с сервера {server['name']}")
                    
            except Exception as e:
                logger.error(f"Ошибка при автоочистке сервера {server['name']}: {e}")
                # Уведомляем админа о критической ошибке автоочистки
                await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при автоочистке сервера:\nСервер: {server['name']}\nОшибка: {str(e)}")
                continue
        
        logger.info(f"Автоочистка завершена. Всего удалено просроченных ключей: {total_deleted_count}")
        return total_deleted_count
        
    except Exception as e:
        logger.error(f"Критическая ошибка в auto_cleanup_expired_keys: {e}")
        # Уведомляем админа о критической ошибке автоочистки
        await notify_admin(app.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Критическая ошибка в auto_cleanup_expired_keys:\nОшибка: {str(e)}")
        return 0


# Старые функции уведомлений удалены - теперь используется NotificationManager


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальная обработка необработанных ошибок"""
    
    # Проверяем тип ошибки
    error = context.error
    error_type = type(error).__name__
    
    # Список временных ошибок, которые не требуют уведомления админа
    temporary_errors = [
        'NetworkError',
        'TimedOut',
        'RetryAfter',
        'Conflict'
    ]
    
    # Проверяем, является ли ошибка временной сетевой проблемой
    is_network_error = (
        error_type in temporary_errors or
        'httpx' in str(error).lower() or
        'ReadError' in str(error) or
        'ConnectError' in str(error) or
        'TimeoutError' in str(error)
    )
    
    if is_network_error:
        # Для сетевых ошибок только логируем, не спамим админов
        logger.warning(f"Временная сетевая ошибка (будет автоматически повторена): {error_type}: {str(error)}")
        return
    
    # Для остальных ошибок - полное логирование
    logger.error("Необработанная ошибка:", exc_info=context.error)
    
    # Уведомляем админа только о критических ошибках (не сетевых)
    try:
        error_message = f"🚨 Критическая ошибка в боте:\n\n{str(context.error)}"
        if update and hasattr(update, 'effective_user') and update.effective_user:
            error_message += f"\n\nПользователь: {update.effective_user.id}"
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=error_message[:4000])
            except telegram.error.Forbidden:
                logger.warning(f"Админ {admin_id} заблокировал бота (error_handler)")
            except telegram.error.BadRequest as e:
                if "Chat not found" in str(e):
                    logger.warning(f"Админ {admin_id} заблокировал бота (error_handler): {e}")
                else:
                    pass  # Другие BadRequest ошибки игнорируем в error_handler
            except:
                pass  # Если не удается отправить админу, продолжаем работу
    except:
        pass  # Не прерываем работу бота из-за ошибки в error_handler

async def notify_server_issues(bot, server_name, issue_type, details=""):
    """Уведомляет админа о проблемах с серверами"""
    try:
        message = f"🚨 Проблема с сервером {server_name}\n\n"
        message += f"Тип проблемы: {issue_type}\n"
        message += f"Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        message += f"Статус: Требует внимания\n\n"
        
        if details:
            message += f"Детали: {details}\n\n"
        
        message += "Рекомендуемые действия:\n"
        message += "• Проверить доступность сервера\n"
        message += "• Уведомить клиентов о возможных проблемах\n"
        message += "• Проверить логи сервера"
        
        await notify_admin(bot, message)
        logger.warning(f"Отправлено уведомление о проблеме с сервером {server_name}: {issue_type}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о проблеме с сервером: {e}")

async def server_health_monitor(app):
    """Периодический мониторинг состояния серверов"""
    logger.info("Запуск мониторинга серверов")
    
    # Словарь для отслеживания предыдущего состояния серверов
    previous_server_status = {}
    
    while True:
        try:
            # Проверяем все серверы
            health_results = server_manager.check_all_servers_health()
            new_client_health = new_client_manager.check_all_servers_health()
            
            # Проверяем изменения в состоянии серверов
            current_time = datetime.datetime.now()
            
            for server_name, is_healthy in health_results.items():
                previous_status = previous_server_status.get(server_name, "unknown")
                current_status = "online" if is_healthy else "offline"
                
                # Если статус изменился, отправляем уведомление
                if previous_status != current_status:
                    if current_status == "offline":
                        health_status = server_manager.get_server_health_status()[server_name]
                        last_error = health_status.get("last_error", "Неизвестная ошибка")
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер недоступен",
                            f"Ошибка: {last_error}"
                        )
                    elif current_status == "online":
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер восстановлен",
                            "Сервер снова доступен"
                        )
                
                previous_server_status[server_name] = current_status
            
            # Проверяем серверы с длительными проблемами
            for server_name, is_healthy in health_results.items():
                if not is_healthy:
                    health_status = server_manager.get_server_health_status()[server_name]
                    consecutive_failures = health_status.get("consecutive_failures", 0)
                    last_check = health_status.get("last_check")
                    
                    # Если сервер недоступен более 15 минут (3 проверки по 5 минут)
                    if consecutive_failures >= 3 and last_check:
                        time_since_last_check = current_time - last_check
                        if time_since_last_check.total_seconds() > 900:  # 15 минут
                            await notify_server_issues(
                                app.bot, 
                                server_name, 
                                "Длительная недоступность",
                                f"Сервер недоступен более 15 минут. Неудачных попыток: {consecutive_failures}"
                            )
            
            # Логируем статус всех серверов
            logger.info(f"Статус серверов: {health_results}")
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге серверов: {e}")
        
        # Ждем 5 минут до следующей проверки
        await asyncio.sleep(300)

# Глобальный менеджер уведомлений
notification_manager = None

async def on_startup(app):
    global notification_manager
    
    logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")
    
    await init_all_db()  # Уже включает init_referral_db()
    
    # Инициализируем менеджер уведомлений
    logger.info("Инициализация менеджера уведомлений...")
    notification_manager = NotificationManager(app.bot, server_manager, ADMIN_IDS)
    await notification_manager.initialize()
    await notification_manager.start()
    logger.info("Менеджер уведомлений запущен")
    
    logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
    
    # Запускаем остальные задачи
    asyncio.create_task(auto_activate_keys(app))
    asyncio.create_task(server_health_monitor(app))


# ==================== СТИЛЬ ИНТЕРФЕЙСА ====================

# Эмодзи для различных элементов интерфейса
class UIEmojis:
    
    # Навигация
    BACK = "←"
    NEXT = "→"
    PREV = "←"
    CLOSE = "✕"
    REFRESH = "↻"
    
    # Статусы
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    


class UIStyles:
    @staticmethod
    def header(text: str) -> str:
        """Основной заголовок"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def subheader(text: str) -> str:
        """Подзаголовок"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def description(text: str) -> str:
        """Описание"""
        return f"<i>{text}</i>"
    
    @staticmethod
    def highlight(text: str) -> str:
        """Выделенный текст"""
        return f"<b>{text}</b>"
    
    @staticmethod
    def code_block(text: str) -> str:
        """Блок кода"""
        return f"<code>{text}</code>"
    
    @staticmethod
    def success_message(text: str) -> str:
        """Сообщение об успехе"""
        return f"{UIEmojis.SUCCESS} <b>{text}</b>"
    
    @staticmethod
    def error_message(text: str) -> str:
        """Сообщение об ошибке"""
        return f"{UIEmojis.ERROR} <b>{text}</b>"
    
    @staticmethod
    def warning_message(text: str) -> str:
        """Предупреждение"""
        return f"{UIEmojis.WARNING} <b>{text}</b>"
    
    @staticmethod
    def info_message(text: str) -> str:
        """Информационное сообщение"""
        return f"<i>{text}</i>"

# Шаблоны кнопок для единообразия
class UIButtons:
    @staticmethod
    def main_menu_buttons(is_admin=False):
        """Кнопки главного меню"""
        buttons = [
            [InlineKeyboardButton("Купить", callback_data="buy_menu")],
            [InlineKeyboardButton("Мои ключи", callback_data="mykey"), 
             InlineKeyboardButton("Инструкция", callback_data="instruction")],
            [InlineKeyboardButton("Рефералы", callback_data="referral"), 
             InlineKeyboardButton("Мои баллы", callback_data="points")],
            [InlineKeyboardButton("Наш канал", url="https://t.me/DarallaNews")],
        ]
        
        if is_admin:
            buttons.append([InlineKeyboardButton("Админ-меню", callback_data="admin_menu")])
        
        return buttons
    
    @staticmethod
    def back_button():
        """Кнопка назад"""
        return InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")
    
    @staticmethod
    def refresh_button(callback_data="refresh"):
        """Кнопка обновления"""
        return InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=callback_data)

# Шаблоны сообщений
class UIMessages:
    @staticmethod
    def welcome_message():
        """Приветственное сообщение"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}"
        )
    
    @staticmethod
    def buy_menu_message():
        """Сообщение меню покупки"""
        return (
            f"{UIStyles.header('Выберите период подписки')}\n\n"
            f"{UIStyles.description('Доступные тарифы:')}\n"
            f"• <b>1 месяц</b> — 100₽\n"
            f"• <b>3 месяца</b> — 250₽ <i>(выгода 50₽)</i>"
        )
    
    @staticmethod
    def instruction_menu_message():
        """Сообщение меню инструкций"""
        return (
            f"{UIStyles.header('Инструкции по настройке')}\n\n"
            f"{UIStyles.description('Выберите вашу платформу для получения подробной инструкции:')}"
        )
    
    @staticmethod
    def admin_menu_message():
        """Сообщение админ-меню"""
        return f"{UIStyles.header('Панель администратора')}"

    @staticmethod
    def broadcast_intro_message():
        return (
            f"{UIStyles.header('Создание рассылки')}\n\n"
            f"{UIStyles.description('Отправьте текст сообщения, которое нужно разослать всем пользователям.')}\n"
            f"{UIStyles.info_message('Поддерживается HTML. Предпросмотр будет показан перед отправкой.')}"
        )

    @staticmethod
    def broadcast_preview_message(text: str):
        return (
            f"{UIStyles.header('Предпросмотр рассылки')}\n\n"
            f"{text}"
        )
    
    @staticmethod
    def success_purchase_message(period, price):
        """Сообщение об успешной покупке"""
        period_text = "1 месяц" if period == "month" else "3 месяца"
        return (
            f"{UIStyles.success_message('Покупка прошла успешно!')}\n\n"
            f"<b>Подписка:</b> {period_text}\n"
            f"<b>Сумма:</b> {price}₽\n\n"
        )
    
    @staticmethod
    def key_expiring_message(email, server, time_remaining):
        """Сообщение об истекающем ключе"""
        return (
            f"{UIStyles.warning_message('Внимание! Ключ скоро истечет')}\n\n"
            f"<b>Ключ:</b> <code>{email}</code>\n"
            f"<b>Сервер:</b> {server}\n"
            f"<b>Осталось:</b> {time_remaining}\n\n"
            f"{UIStyles.description('Продлите ключ, чтобы не потерять доступ к VPN!')}"
        )
    
    @staticmethod
    def key_deleted_message(email, server, days_expired):
        """Сообщение об удаленном ключе"""
        return (
            f"{UIStyles.error_message('Ключ был удален')}\n\n"
            f"<b>Ключ:</b> <code>{email}</code>\n"
            f"<b>Сервер:</b> {server}\n"
            f"<b>Истек:</b> {days_expired} дней назад\n\n"
            f"{UIStyles.description('Ключ был автоматически удален из-за истечения срока действия.')}\n"
            f"{UIStyles.description('Купите новый ключ, чтобы продолжить пользоваться VPN.')}"
        )
    
    @staticmethod
    def no_keys_message():
        """Сообщение об отсутствии ключей"""
        return (
            f"{UIStyles.info_message('У вас пока нет активных ключей')}\n\n"
            f"{UIStyles.description('Купите подписку для начала использования VPN.')}"
        )
    
    @staticmethod
    def key_extended_message(email, server_name, days, expiry_str, period=None):
        """Сообщение о продлении ключа"""
        # Определяем текст периода
        if period:
            if period == '3month':
                period_text = "3 месяца"
            elif period == 'month':
                period_text = "1 месяц"
            else:
                period_text = f"{days} дней"
        else:
            period_text = f"{days} дней"
        
        return (
            f"{UIEmojis.SUCCESS} Ключ успешно продлен!\n\n"
            f"Ключ: `{email}`\n"
            f"Сервер: {server_name}\n"
            f"Продлен на: {period_text}\n"
            f"Новое время истечения: {expiry_str}"
        )
    
    
    @staticmethod
    def server_selection_message():
        """Сообщение выбора сервера"""
        return (
            f"{UIStyles.header('Выбор сервера')}\n\n"
            f"{UIStyles.description('Выберите локацию для вашего VPN-ключа:')}\n"
            f"{UIStyles.info_message('Рекомендуется выбрать ближайший к вам сервер для лучшей скорости.')}"
        )
    
    @staticmethod
    def referral_menu_message(points, total_referrals, active_referrals, ref_link):
        """Сообщение реферального меню"""
        return (
            f"{UIStyles.header('Реферальная программа')}\n\n"
            f"<b>Ваши баллы:</b> {UIStyles.highlight(str(points))}\n\n"
            f"<b>Статистика рефералов:</b>\n"
            f"• Всего приглашено: {total_referrals}\n"
            f"• Активных: {active_referrals}\n\n"
            f"<b>Как заработать баллы:</b>\n"
            f"• Пригласите друга — получите 1 балл\n"
            f"• 1 балл = 14 дней VPN\n"
            f"• 1 балл = продление на 14 дней\n\n"
            f"{UIStyles.warning_message('Важно: Балл выдается только за привлечение новых клиентов!')}\n\n"
            f"<b>Ваша реферальная ссылка:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"<b>Как поделиться:</b>\n"
            f"{UIStyles.description('Отправьте ссылку друзьям или опубликуйте в социальных сетях')}"
        )
    
    @staticmethod
    def welcome_referral_new_user_message(days):
        """Приветственное сообщение для нового пользователя по реферальной ссылке"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Вы пришли по реферальной ссылке!')}\n\n"
            f"После покупки VPN ваш друг получит 1 балл!\n"
            f"1 балл = {days} дней VPN бесплатно!"
            
        )
    
    @staticmethod
    def welcome_referral_existing_user_message():
        """Приветственное сообщение для существующего пользователя по реферальной ссылке"""
        terms_url = "https://teletype.in/@daralla/support"
        warning_msg = "Используя данный сервис, вы соглашаетесь с <a href=\"" + terms_url + "\">условиями использования</a> и обязуетесь соблюдать законодательство РФ."
        return (
            f"{UIStyles.header('Добро пожаловать в Daralla VPN!')}\n\n"
            f"{UIStyles.warning_message(warning_msg)}\n\n"
            f"{UIStyles.success_message('Вы пришли по реферальной ссылке')}\n\n"
            f"Но вы не новый пользователь.\n"
            f"Реферальная награда не будет выдана."
            
        )

# Глобальный словарь для хранения message_id платежей
# Ключ: payment_id, Значение: message_id
payment_message_ids = {}

# Глобальный словарь для хранения коротких идентификаторов ключей для продления
# Ключ: короткий_id, Значение: key_email
extension_keys_cache = {}

# Глобальный словарь для хранения сообщений продления
# Ключ: payment_id, Значение: (chat_id, message_id)
extension_messages = {}

# Импорт нового модуля уведомлений
try:
    from .notifications import NotificationManager
except ImportError:
    from .notifications import NotificationManager

import traceback

async def notify_admin(bot, text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=f"❗️[VPNBot ERROR]\n{text}")
        except telegram.error.Forbidden:
            logger.warning(f"Админ {admin_id} заблокировал бота")
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Админ {admin_id} заблокировал бота: {e}")
            else:
                logger.error(f'BadRequest ошибка отправки уведомления админу: {e}')
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления админу: {e}')


async def admin_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_errors':
            push_nav(context, 'admin_errors')
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        # Читаем ротационный файл логов приложения
        from .keys_db import DATA_DIR
        import os
        logs_path = os.path.join(DATA_DIR, 'logs', 'bot.log')
        logs = ''
        if os.path.exists(logs_path):
            with open(logs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = ''.join(lines[-200:])  # последние ~200 строк
        else:
            logs = 'Файл логов не найден. Он будет создан автоматически при работе бота.'

        if len(logs) > 4000:
            logs = logs[-4000:]

        # Экранируем HTML и выводим как код
        escaped = html.escape(logs)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_errors")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, f"<b>Последние логи:</b>\n\n<pre><code>{escaped}</code></pre>", 
                               parse_mode='HTML', reply_markup=keyboard)
            
    except Exception as e:
        logger.exception("Ошибка в admin_errors")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, f'{UIEmojis.ERROR} Ошибка при чтении логов: {str(e)}', reply_markup=keyboard)

async def admin_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дашборд уведомлений для админа"""
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_notifications':
            push_nav(context, 'admin_notifications')
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        if notification_manager is None:
            await safe_edit_or_reply(update.callback_query.message, 
                                   f"{UIEmojis.ERROR} Менеджер уведомлений не инициализирован")
            return
        
        # Получаем дашборд
        dashboard_text = await notification_manager.get_notification_dashboard()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_notifications")],
            [UIButtons.back_button()]
        ])
        
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, dashboard_text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_notifications: {e}")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, f"{UIEmojis.ERROR} Ошибка загрузки дашборда: {e}", reply_markup=keyboard)



async def admin_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.callback_query:
        await update.callback_query.answer()
        stack = context.user_data.setdefault('nav_stack', [])
        if not stack or stack[-1] != 'admin_check_servers':
            push_nav(context, 'admin_check_servers')
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        # Проверяем здоровье всех серверов
        health_results = server_manager.check_all_servers_health()
        health_status = server_manager.get_server_health_status()
        
        message = "🔍 Детальная проверка серверов:\n\n"
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_info = health_status.get(server_name, {})
            
            if is_healthy:
                # Получаем дополнительную информацию о сервере
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн\n"
                    message += f"   Всего клиентов: {total_clients}\n"
                    message += f"   Активных клиентов: {active_clients}\n"
                    message += f"   Истекших клиентов: {expired_clients}\n"
                    message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
                except Exception as e:
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн (ошибка получения деталей: {str(e)[:50]}...)\n"
            else:
                message += f"{UIEmojis.ERROR} {server_name}: Офлайн\n"
                message += f"   Ошибка: {status_info.get('last_error', 'Неизвестно')}\n"
                message += f"   {UIEmojis.REFRESH} Неудачных попыток: {status_info.get('consecutive_failures', 0)}\n"
                message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
            
            message += "\n"
        
        # Добавляем общую статистику
        total_servers = len(server_manager.servers)
        online_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
        offline_servers = total_servers - online_servers
        
        # Подсчитываем общее количество клиентов
        total_clients_all = 0
        active_clients_all = 0
        expired_clients_all = 0
        
        for server in server_manager.servers:
            if health_results.get(server["name"], False):
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_all += total_clients
                    active_clients_all += active_clients
                    expired_clients_all += expired_clients
                except:
                    pass
        
        message += f"Общая статистика:\n"
        message += f"   Всего серверов: {total_servers}\n"
        message += f"   Онлайн: {online_servers}\n"
        message += f"   Офлайн: {offline_servers}\n"
        message += f"   Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"Клиенты:\n"
        message += f"   Всего клиентов: {total_clients_all}\n"
        message += f"   Активных: {active_clients_all}\n"
        message += f"   Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="admin_check_servers")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, message, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка в admin_check_servers")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
        ])
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, f'Ошибка при проверке серверов: {e}', reply_markup=keyboard)


# Callback для продления ключей
async def extend_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # Извлекаем short_id из callback_data
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await query.answer("Ошибка: неверный формат данных")
        return
    
    short_id = parts[1]
    
    # Получаем email ключа из кэша
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        # Пытаемся найти ключ по short_id, созданному из уведомления
        # Проверяем все возможные форматы short_id
        import hashlib
        
        # Ищем ключ пользователя на серверах
        try:
            all_clients = []
            for server in server_manager.servers:
                try:
                    xui = server["x3"]
                    inbounds = xui.list()['obj']
                    for inbound in inbounds:
                        settings = json.loads(inbound['settings'])
                        clients = settings.get("clients", [])
                        for client in clients:
                            if client['email'].startswith(f"{user_id}_") or client['email'].startswith(f"trial_{user_id}_"):
                                all_clients.append(client)
                except Exception as e:
                    logger.error(f"Ошибка при поиске ключей на сервере {server['name']}: {e}")
                    continue
            
            # Ищем ключ, который соответствует short_id
            for client in all_clients:
                email = client['email']
                # Проверяем разные форматы short_id
                possible_short_ids = [
                    hashlib.md5(f"{user_id}:{email}".encode()).hexdigest()[:8],
                    hashlib.md5(f"extend:{email}".encode()).hexdigest()[:8]
                ]
                
                if short_id in possible_short_ids:
                    key_email = email
                    # Добавляем в кэш для будущих использований
                    extension_keys_cache[short_id] = email
                    logger.info(f"Найден ключ по short_id: {short_id} -> {email}")
                    break
            
            if not key_email:
                await query.answer("Ошибка: ключ не найден")
                logger.error(f"Не найден key_email для short_id: {short_id}")
                return
                
        except Exception as e:
            logger.error(f"Ошибка поиска ключа по short_id: {e}")
            await query.answer("Ошибка: ключ не найден")
            return
    
    await query.answer()
    
    logger.info(f"Запрос на продление ключа: user_id={user_id}, key_email={key_email}")
    
    # Проверяем, что ключ принадлежит пользователю
    if not (key_email.startswith(f"{user_id}_") or key_email.startswith(f"trial_{user_id}_")):
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: ключ не принадлежит вам.")
        return
    
    # Разрешаем продление любых ключей, включая старые trial
    
    # Проверяем, что ключ существует на серверах
    try:
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            await safe_edit_or_reply(query.message, "❌ Ключ не найден на серверах.")
            return
    except Exception as e:
        logger.error(f"Ошибка поиска ключа для продления: {e}")
        await safe_edit_or_reply(query.message, "❌ Ошибка при поиске ключа.")
        return
    
    # Создаем короткий идентификатор для ключа
    import hashlib
    short_id = hashlib.md5(f"{user_id}:{key_email}".encode()).hexdigest()[:8]
    extension_keys_cache[short_id] = key_email
    logger.info(f"Создан короткий ID для продления: {short_id} -> {key_email}")
    
    # Показываем меню выбора периода продления
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 месяц - 100₽", callback_data=f"ext_per:month:{short_id}")],
        [InlineKeyboardButton("3 месяца - 250₽", callback_data=f"ext_per:3month:{short_id}")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад к ключам", callback_data="mykey")]
    ])
    
    message_text = (
        f"{UIStyles.header('Продление ключа')}\n\n"
        f"<b>Ключ:</b> <code>{key_email}</code>\n"
        f"<b>Сервер:</b> {server_name}\n\n"
        f"{UIStyles.description('Выберите период продления:')}"
    )
    
    await safe_edit_or_reply(query.message, message_text, reply_markup=keyboard, parse_mode="HTML")

# Callback для выбора периода продления
async def extend_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    
    # Извлекаем период и short_id из callback_data: ext_per:month:short_id
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await query.answer("Ошибка: неверный формат данных")
        return
    
    period = parts[1]  # month или 3month
    short_id = parts[2]
    
    # Получаем email ключа из кэша
    key_email = extension_keys_cache.get(short_id)
    if not key_email:
        await query.answer("Ошибка: ключ не найден в кэше")
        logger.error(f"Не найден key_email для short_id: {short_id}")
        return
    
    await query.answer()
    
    logger.info(f"Выбран период продления: user_id={user_id}, period={period}, key_email={key_email}")
    
    # Определяем цену (такую же как при покупке)
    price = "100.00" if period == "month" else "250.00"  # в рублях
    
    # Создаем платеж для продления (используем существующую функцию handle_payment)
    try:
        # Сохраняем информацию о продлении в контексте
        context.user_data['extension_key_email'] = key_email
        context.user_data['extension_period'] = period
        
        # Вызываем функцию создания платежа
        await handle_payment(update, context, price, f"extend_{period}")
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа для продления: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад к ключам", callback_data="mykey")]
        ])
        await safe_edit_or_reply(query.message, "❌ Ошибка при создании платежа. Попробуйте позже.", reply_markup=keyboard)

# admin_delete_all удалена по требованию

async def admin_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущую конфигурацию баллов"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        config = await get_all_config()
        if not config:
            await safe_edit_or_reply(update.message, 'Конфигурация не найдена.')
            return
        
        message = "⚙️ Конфигурация баллов:\n\n"
        for key, data in config.items():
            if key.startswith('points_'):
                message += f"• {data['description']}: {data['value']}\n"
        
        message += "\n📝 Команды:\n"
        message += "• `/admin_set_days <дни>` - изменить количество дней за 1 балл\n"
        message += "• `/admin_set_days 14` - установить 14 дней за балл\n"
        message += "• `/admin_set_days 30` - установить 30 дней за балл\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
        ])
        
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, message, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Ошибка в admin_config")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} Ошибка: {e}')

async def admin_set_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает количество дней за 1 балл"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else update.callback_query.message
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    if not context.args:
        await safe_edit_or_reply(update.message, 'Используйте: /admin_set_days <количество_дней>\nПример: /admin_set_days 14')
        return
    
    try:
        days = int(context.args[0])
        
        # Проверяем лимиты
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            await safe_edit_or_reply(update.message, f'Количество дней должно быть от {min_days} до {max_days}')
            return
        
        # Сохраняем новое значение
        success = await set_config('points_days_per_point', str(days), 'Количество дней VPN за 1 балл')
        
        if success:
            await safe_edit_or_reply(update.message, f'{UIEmojis.SUCCESS} Установлено: 1 балл = {days} дней VPN', parse_mode="Markdown")
        else:
            await safe_edit_or_reply(update.message, '❌ Ошибка при сохранении конфигурации')
            
    except ValueError:
        await safe_edit_or_reply(update.message, 'Количество дней должно быть числом')
    except Exception as e:
        logger.exception("Ошибка в admin_set_days")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} Ошибка: {e}')

# Состояние для ConversationHandler
WAITING_FOR_DAYS = 1

async def admin_set_days_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало интерактивного изменения дней за балл"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(query.message, 'Нет доступа.')
        return ConversationHandler.END
    
    # Получаем текущее значение
    current_days = await get_config('points_days_per_point', '14')
    min_days = await get_config('points_min_days', '1')
    max_days = await get_config('points_max_days', '365')
    
    message = (
        f"⚙️ <b>Настройка дней за балл</b>\n\n"
        f"Текущее значение: <b>1 балл = {current_days} дней VPN</b>\n\n"
        f"Введите новое количество дней (от {min_days} до {max_days}):"
    )
    
    # Создаем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
    ])
    
    # Сохраняем message_id для последующего редактирования
    context.user_data['config_message_id'] = query.message.message_id
    context.user_data['config_chat_id'] = query.message.chat_id
    
    await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
    
    return WAITING_FOR_DAYS

async def admin_set_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода количества дней"""
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    try:
        # Удаляем сообщение пользователя
        await update.message.delete()
        
        days = int(update.message.text.strip())
        
        # Проверяем лимиты
        min_days = int(await get_config('points_min_days', '1'))
        max_days = int(await get_config('points_max_days', '365'))
        
        if days < min_days or days > max_days:
            message = (
                f"{UIEmojis.ERROR} <b>Ошибка</b>\n\n"
                f"Количество дней должно быть от {min_days} до {max_days}\n\n"
                f"Текущее значение: <b>1 балл = {await get_config('points_days_per_point', '14')} дней</b>\n\n"
                f"Введите новое количество дней:"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
            ])
            
            await context.bot.edit_message_text(
                chat_id=context.user_data['config_chat_id'],
                message_id=context.user_data['config_message_id'],
                text=message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            return WAITING_FOR_DAYS
        
        # Сохраняем новое значение
        success = await set_config('points_days_per_point', str(days), 'Количество дней VPN за 1 балл')
        logger.info(f"ADMIN_SET_DAYS: Сохранение конфигурации points_days_per_point = {days}, success = {success}")
        
        # Проверяем, что значение действительно сохранилось
        saved_days = await get_config('points_days_per_point', '14')
        logger.info(f"ADMIN_SET_DAYS: Проверка сохраненного значения = {saved_days}")
        
        if success:
            message = (
                f"{UIEmojis.SUCCESS} <b>Настройка изменена!</b>\n\n"
                f"<b>1 балл = {days} дней VPN</b>\n\n"
                f"Введите другое значение для изменения или нажмите «Назад»:"
            )
        else:
            message = (
                f"{UIEmojis.ERROR} <b>Ошибка сохранения</b>\n\n"
                f"Попробуйте еще раз или нажмите «Назад»:"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="admin_set_days_cancel")]
        ])
        
        await context.bot.edit_message_text(
            chat_id=context.user_data['config_chat_id'],
            message_id=context.user_data['config_message_id'],
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        return WAITING_FOR_DAYS
        
    except ValueError:
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        message = (
            f"{UIEmojis.ERROR} <b>Ошибка</b>\n\n"
            f"Введите число, например: 14, 30, 60\n\n"
            f"Текущее значение: <b>1 балл = {await get_config('points_days_per_point', '14')} дней</b>\n\n"
            f"Введите новое количество дней:"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data="admin_set_days_cancel")]
        ])
        
        await context.bot.edit_message_text(
            chat_id=context.user_data['config_chat_id'],
            message_id=context.user_data['config_message_id'],
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        return WAITING_FOR_DAYS
        
    except Exception as e:
        logger.exception("Ошибка в admin_set_days_input")
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        await context.bot.edit_message_text(
            chat_id=context.user_data['config_chat_id'],
            message_id=context.user_data['config_message_id'],
            text=f'{UIEmojis.ERROR} Ошибка: {e}',
            parse_mode="HTML"
        )
        
        return ConversationHandler.END

async def admin_set_days_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена изменения конфига - возврат в админ меню"""
    query = update.callback_query
    await query.answer()
    
    # Возвращаемся в админ меню
    await admin_menu(update, context)
    
    return ConversationHandler.END

# Обработка callback-кнопок для start
async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Обработка callback: {query.data}")
    if query.data == "buy_menu":
        await buy_menu_handler(update, context)
    elif query.data.startswith("select_period_"):
        await select_period_callback(update, context)
    elif query.data.startswith("select_server_"):
        await select_server_callback(update, context)
    elif query.data == "mykey":
        await mykey(update, context)
    elif query.data.startswith("keys_page_"):
        logger.info(f"Переход на страницу ключей: {query.data}")
        await mykey(update, context)
    elif query.data == "instruction":
        await instruction(update, context)


# Обработчик для кнопки "Купить" в меню покупки
async def buy_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'buy_menu':
        push_nav(context, 'buy_menu')
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("buy_menu_handler: message is None")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 месяц — 100₽", callback_data="select_period_month")],
        [InlineKeyboardButton("3 месяца — 250₽", callback_data="select_period_3month")],
        [UIButtons.back_button()],
    ])
    
    # Используем единый стиль для сообщения меню покупки
    buy_menu_text = UIMessages.buy_menu_message()
    await safe_edit_or_reply_universal(message, buy_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='buy_menu')

# Новый обработчик выбора периода, который переводит к выбору сервера
async def select_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Сохраняем выбранный период
    if query.data == "select_period_month":
        context.user_data["pending_period"] = "month"
        context.user_data["pending_price"] = "100.00"
    elif query.data == "select_period_3month":
        context.user_data["pending_period"] = "3month"
        context.user_data["pending_price"] = "250.00"
    
    # Переходим к выбору сервера
    await server_selection_menu(update, context)

# Меню выбора сервера
async def server_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'server_selection':
        push_nav(context, 'server_selection')
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("server_selection_menu: message is None")
        return
    
    # Проверяем доступность всех серверов
    health_results = new_client_manager.check_all_servers_health()
    
    # Создаем кнопки для локаций с флагами и статусом
    location_buttons = []
    location_flags = {
        "Finland": "🇫🇮",
        "Latvia": "🇱🇻", 
        "Estonia": "🇪🇪"
    }
    
    # Формируем текст с информацией о локациях
    location_info_text = ""
    
    for location, servers in SERVERS_BY_LOCATION.items():
        if not servers:
            continue
            
        # Проверяем доступность серверов в локации
        available_servers = 0
        total_servers = 0
        
        for server in servers:
            if server["host"] and server["login"] and server["password"]:
                total_servers += 1
                if health_results.get(server['name'], False):
                    available_servers += 1
        
        if total_servers == 0:
            continue
            
        flag = location_flags.get(location)
        
        # Определяем статус локации
        if available_servers > 0:
            status_icon = UIEmojis.SUCCESS
            status_text = f"Доступно {available_servers}/{total_servers} серверов"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"select_server_{location.lower()}"
        else:
            status_icon = UIEmojis.ERROR
            status_text = "Недоступно"
            button_text = f"{flag} {location} {status_icon}"
            callback_data = f"server_unavailable_{location.lower()}"
        
        location_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Добавляем информацию о локации в текст
        location_info_text += f"{flag} <b>{location}</b> - {status_text}\n"
    
    # Добавляем кнопку "Автовыбор" (только если есть доступные серверы)
    available_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
    if available_servers > 0:
        location_buttons.append([InlineKeyboardButton("🎯 Автовыбор", callback_data="select_server_auto")])
        location_info_text += "<b>🎯 Автовыбор</b> - Локация с наименьшей нагрузкой\n"
    
    location_buttons.append([InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data="refresh_servers")])
    
    # Определяем текст периода и кнопку назад в зависимости от типа покупки
    pending_period = context.user_data.get("pending_period")
    if pending_period == "month":
        period_text = "1 месяц за 100₽"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "3month":
        period_text = "3 месяца за 250₽"
        location_buttons.append([UIButtons.back_button()])
    elif pending_period == "points_month":
        period_text = "1 месяц за 1 балл"
        location_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="spend_points")])
    else:
        period_text = "Неизвестный период"
        location_buttons.append([UIButtons.back_button()])
    
    keyboard = InlineKeyboardMarkup(location_buttons)
    
    message_text = f"{UIStyles.subheader(f'Выбран период: {period_text}')}\n\n{UIMessages.server_selection_message()}\n\n{location_info_text}"
    
    await safe_edit_or_reply(message, message_text, reply_markup=keyboard, parse_mode="HTML")

# Обработчик выбора сервера
async def select_server_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Обработка обновления списка серверов
    if query.data == "refresh_servers":
        await server_selection_menu(update, context)
        return
    
    # Обработка недоступных локаций
    if query.data.startswith("server_unavailable_"):
        location_name = query.data.replace("server_unavailable_", "").title()
        await safe_edit_or_reply(
            query.message, 
            f"{UIEmojis.ERROR} Локация {location_name} временно недоступна\n\n"
            f"Пожалуйста, выберите другую локацию или попробуйте позже.\n\n"
            f"Для обновления статуса серверов нажмите кнопку \"{UIEmojis.REFRESH} Обновить\"",
            parse_mode="HTML"
        )
        return
    
    # Сохраняем выбранную локацию
    selected_location = None
    if query.data == "select_server_auto":
        selected_location = "auto"
    elif query.data == "select_server_finland":
        selected_location = "Finland"
    elif query.data == "select_server_latvia":
        selected_location = "Latvia"
    elif query.data == "select_server_estonia":
        selected_location = "Estonia"
    
    if not selected_location:
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Неверный выбор локации")
        return
    
    # Проверяем доступность выбранной локации
    if selected_location != "auto":
        # Проверяем, есть ли доступные серверы в локации
        available_servers = 0
        for server in SERVERS_BY_LOCATION.get(selected_location, []):
            if server["host"] and server["login"] and server["password"]:
                if new_client_manager.check_server_health(server["name"]):
                    available_servers += 1
        
        if available_servers == 0:
            await safe_edit_or_reply(
                query.message, 
                f"❌ Локация {selected_location} недоступна\n\n"
                f"Все серверы в этой локации временно недоступны. Пожалуйста, выберите другую локацию.",
                parse_mode="HTML"
            )
            return
    else:
        # Для автовыбора проверяем, есть ли доступные серверы в любой локации
        total_available = 0
        for location, servers in SERVERS_BY_LOCATION.items():
            for server in servers:
                if server["host"] and server["login"] and server["password"]:
                    if new_client_manager.check_server_health(server["name"]):
                        total_available += 1
        
        if total_available == 0:
            await safe_edit_or_reply(
                query.message, 
                "❌ Нет доступных серверов\n\n"
                "Все серверы временно недоступны. Попробуйте позже.",
                parse_mode="HTML"
            )
            return
    
    # Сохраняем выбранную локацию
    context.user_data["selected_location"] = selected_location
    
    # Получаем сохраненные данные
    period = context.user_data.get("pending_period")
    price = context.user_data.get("pending_price")
    
    # Запускаем процесс оплаты
    await handle_payment(update, context, price, period)



# === Навигационный стек и универсальный обработчик "Назад" ===
def push_nav(context, state, max_size=10):
    stack = context.user_data.setdefault('nav_stack', [])
    
    # Ограничиваем размер стека
    if len(stack) >= max_size:
        stack.pop(0)  # Удаляем самый старый элемент
    
    stack.append(state)
    logger.info(f"PUSH: {state} -> Stack: {stack}")

def pop_nav(context):
    stack = context.user_data.get('nav_stack', [])
    if stack:
        popped = stack.pop()
        logger.info(f"POP: {popped} -> Stack: {stack}")
        return stack[-1] if stack else None
    logger.info(f"POP: empty stack")
    return None


async def universal_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    logger.info(f"BACK: Current stack before pop: {context.user_data.get('nav_stack', [])}")
    prev_state = pop_nav(context)
    logger.info(f"BACK: Previous state: {prev_state}")
    
    logger.info(f"BACK: Navigating to {prev_state}")
    
    # Если стек пустой — возвращаемся в главное меню
    if prev_state is None:
        logger.info("BACK: prev_state is None, calling start()")
        await start(update, context)
    elif prev_state == 'main_menu':
        # Если возвращаемся в main_menu, редактируем существующее сообщение
        logger.info("BACK: prev_state == 'main_menu', calling edit_main_menu")
        await edit_main_menu(update, context)
    elif prev_state == 'instruction_menu':
        await instruction(update, context)
    elif prev_state == 'instruction_platform':
        # Возвращаемся к выбору платформы
        await instruction(update, context)

    elif prev_state == 'payment':
        # После активации ключа возвращаемся в главное меню
        await start(update, context)
    elif prev_state == 'mykeys_menu':
        await mykey(update, context)
    elif prev_state == 'admin_menu':
        await admin_menu(update, context)
    elif prev_state == 'admin_errors':
        await admin_errors(update, context)
    elif prev_state == 'admin_check_servers':
        await admin_check_servers(update, context)
    elif prev_state == 'admin_notifications':
        await admin_notifications(update, context)
    elif prev_state == 'buy_menu':
        await buy_menu_handler(update, context)
    else:
        logger.warning(f"BACK: Unknown state {prev_state}, returning to main menu")
        await start(update, context)



async def force_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная проверка всех серверов"""
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'Нет доступа.')
        return
    
    try:
        await safe_edit_or_reply(update.message, '🔄 Принудительная проверка серверов...')
        
        # Проверяем все серверы
        health_results = server_manager.check_all_servers_health()
        new_client_health = new_client_manager.check_all_servers_health()
        
        # Формируем отчет
        message = "🔍 Результаты принудительной проверки:\n\n"
        
        # Основные серверы
        message += "Основные серверы:\n"
        total_clients_main = 0
        active_clients_main = 0
        expired_clients_main = 0
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
            
            if is_healthy:
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_main += total_clients
                    active_clients_main += active_clients
                    expired_clients_main += expired_clients
                    message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                except:
                    message += f"{status_icon} {server_name} (ошибка получения данных)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        message += "\nСерверы для новых клиентов:\n"
        total_clients_new = 0
        active_clients_new = 0
        expired_clients_new = 0
        
        for server in new_client_manager.servers:
            server_name = server["name"]
            is_healthy = new_client_health.get(server_name, False)
            status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
            
            if is_healthy:
                try:
                    xui = server["x3"]
                    total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    total_clients_new += total_clients
                    active_clients_new += active_clients
                    expired_clients_new += expired_clients
                    message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                except:
                    message += f"{status_icon} {server_name} (ошибка получения данных)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        # Статистика
        total_servers = len(health_results) + len(new_client_health)
        online_servers = sum(1 for is_healthy in list(health_results.values()) + list(new_client_health.values()) if is_healthy)
        total_clients_all = total_clients_main + total_clients_new
        active_clients_all = active_clients_main + active_clients_new
        expired_clients_all = expired_clients_main + expired_clients_new
        
        message += f"\nСтатистика серверов:\n"
        message += f"Всего серверов: {total_servers}\n"
        message += f"Онлайн: {online_servers}\n"
        message += f"Офлайн: {total_servers - online_servers}\n"
        message += f"Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"Статистика клиентов:\n"
        message += f"Всего клиентов: {total_clients_all}\n"
        message += f"Активных: {active_clients_all}\n"
        message += f"Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await safe_edit_or_reply(update.message, message, parse_mode="HTML")
        
    except Exception as e:
        logger.exception("Ошибка в force_check_servers")
        await safe_edit_or_reply(update.message, f'Ошибка при проверке серверов: {e}')

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЛЛАМИ И РЕФЕРАЛАМИ =====

async def points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает баллы пользователя"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    history = await get_points_history(user_id, 5)
    points_days = await get_config('points_days_per_point', '14')
    
    message = (
        f"*Ваши баллы*\n\n"
        f"Текущий баланс: *{mdv2(points_info['points'])} баллов*\n"
        f"Всего заработано: {mdv2(points_info['total_earned'])}\n"
        f"Всего потрачено: {mdv2(points_info['total_spent'])}\n\n"
        f"*1 балл \\= {mdv2(points_days)} дней VPN\\!*\n\n"
    )
    
    if history:
        message += "*Последние операции:*\n"
        for trans in history:
            icon = "\\+" if trans['type'] == 'earned' else "\\-"
            date_str = datetime.datetime.fromtimestamp(trans['created_at']).strftime('%d.%m %H:%M')
            message += f"{icon} {mdv2(trans['amount'])} \\- {mdv2(trans['description'])} \\({mdv2(date_str)}\\)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Потратить баллы", callback_data="spend_points")],
        [InlineKeyboardButton("Поделиться ссылкой", callback_data="referral")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="back")]
    ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"points_callback: failed to edit message: {e}")

async def spend_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню траты баллов"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '14')
    
    if points_info['points'] < 1:
        message = (
            f"{UIEmojis.ERROR} *Недостаточно баллов*\n\n"
            "У вас нет баллов для траты\\.\n"
            "Приглашайте друзей, чтобы заработать баллы\\!\n\n"
            f"1 реферал \\= {mdv2(points_days)} дней VPN"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Поделиться ссылкой", callback_data="referral")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="points")]
        ])
    else:
        message = (
            f"*Потратить баллы*\n\n"
            f"У вас есть: *{mdv2(points_info['points'])} баллов*\n\n"
            f"*Доступные покупки:*\n"
            f"• 1 балл \\= {mdv2(points_days)} дней VPN\n"
            f"• 1 балл \\= продление на {mdv2(points_days)} дней\n\n"
            f"Выберите действие:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Купить {mdv2(points_days)} дней за 1 балл", callback_data="buy_with_points")],
            [InlineKeyboardButton(f"Продлить ключ на {mdv2(points_days)} дней за 1 балл", callback_data="extend_with_points")],
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="points")]
        ])
    
    try:
        await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="MarkdownV2", menu_type='points_menu')
    except Exception as e:
        logger.exception(f"spend_points_callback: failed to edit message: {e}")

async def buy_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка VPN за баллы - выбор сервера"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Недостаточно баллов!")
        return
    
    # Сохраняем информацию о покупке за баллы
    context.user_data["pending_period"] = "points_month"
    context.user_data["pending_price"] = "1 балл"
    
    # Переходим к выбору сервера
    await server_selection_menu(update, context)

async def extend_with_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продление ключа за баллы - выбор ключа"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    points_info = await get_user_points(user_id)
    
    if points_info['points'] < 1:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="spend_points")]
        ])
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Недостаточно баллов!", reply_markup=keyboard)
        return
    
    # Ищем активные ключи пользователя
    try:
        all_clients = []
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(user_id):
                            client['server_name'] = server['name']
                            client['xui'] = xui
                            # Добавляем информацию о времени истечения
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            if expiry_timestamp > 0:
                                expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M')
                                client['expiry_str'] = expiry_str
                            else:
                                client['expiry_str'] = '—'
                            all_clients.append(client)
            except Exception as e:
                logger.error(f"Ошибка при получении клиентов с сервера {server['name']}: {e}")

        if not all_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="spend_points")]
            ])
            await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} У вас нет активных ключей для продления!", reply_markup=keyboard)
            return
        
        # Если только один ключ - продлеваем сразу
        if len(all_clients) == 1:
            client = all_clients[0]
            await extend_selected_key_with_points(update, context, client, user_id)
            return
        
        # Показываем список ключей для выбора
        keyboard_buttons = []
        for i, client in enumerate(all_clients, 1):
            email = client['email']
            server_name = client.get('server_name', 'Неизвестно')
            expiry_str = client.get('expiry_str', '—')
            
            # Создаем короткий ID для ключа
            import hashlib
            short_id = hashlib.md5(f"{user_id}:{email}:extend_points".encode()).hexdigest()[:8]
            extension_keys_cache[short_id] = {
                'email': email,
                'xui': client['xui'],
                'server_name': server_name,
                'user_id': user_id
            }
            
            button_text = f"Ключ #{i} ({server_name}) - {expiry_str}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"extend_points_key:{short_id}")])
        
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="spend_points")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        points_days = await get_config('points_days_per_point', '14')
        message = (
            f"{UIStyles.header('Продление ключа за баллы')}\n\n"
            f"<b>У вас есть:</b> {points_info['points']} баллов\n"
            f"<b>1 балл</b> = продление на {points_days} дней\n\n"
            f"{UIStyles.description('Выберите ключ для продления:')}"
        )
        
        await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка ключей: {e}")
        await safe_edit_or_reply(update.callback_query.message, "❌ Ошибка при получении списка ключей.")

async def extend_selected_key_with_points(update: Update, context: ContextTypes.DEFAULT_TYPE, client: dict, user_id: str):
    """Продлевает выбранный ключ за баллы"""
    try:
        xui = client['xui']
        email = client['email']
        server_name = client.get('server_name', 'Неизвестно')
        
        # Продлеваем ключ СНАЧАЛА
        points_days = int(await get_config('points_days_per_point', '14'))
        response = xui.extendClient(email, points_days)
        if response and response.status_code == 200:
            # Ключ продлен успешно - ТЕПЕРЬ списываем баллы
            success = await spend_points(user_id, 1, f"Продление ключа {email} за баллы", bot=context.bot)
            if not success:
                # Если не удалось списать баллы, откатываем продление
                try:
                    # Откатываем продление (уменьшаем на те же дни)
                    xui.extendClient(email, -points_days)
                    logger.warning(f"Rolled back extension for key {email} due to points spending failure")
                except Exception as e:
                    logger.error(f"Failed to rollback extension for key {email} after points failure: {e}")
                    # Уведомляем админа о критической ошибке
                    await notify_admin(context.bot, f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Не удалось откатить продление ключа после неудачного списания баллов:\nКлюч: {email}\nПользователь: {user_id}\nОшибка: {str(e)}")
                await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при списании баллов!")
                return
            # Очищаем старые уведомления об истечении для продленного ключа
            if notification_manager:
                await notification_manager.clear_key_notifications(user_id, email)
            
            # Получаем новое время истечения
            clients_response = xui.list()
            expiry_str = "—"
            if clients_response.get('success', False):
                for inbound in clients_response.get('obj', []):
                    settings = json.loads(inbound.get('settings', '{}'))
                    for client in settings.get('clients', []):
                        if client.get('email') == email:
                            expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                            expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                            break
            
            message = UIMessages.key_extended_message(
                email=email,
                server_name=server_name,
                days=points_days,
                expiry_str=expiry_str,
                period=None  # Для продления за баллы период не указываем
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data="back")]
            ])
            
            await safe_edit_or_reply(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML")
        else:
            # Ключ не продлен - баллы не списывались, просто сообщаем об ошибке
            await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при продлении ключа.")
            
    except Exception as e:
        logger.error(f"Ошибка продления выбранного ключа за баллы: {e}")
        # Баллы не списывались, просто сообщаем об ошибке
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Ошибка при продлении.")

async def extend_points_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора ключа для продления за баллы"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    callback_data = update.callback_query.data
    
    # Извлекаем short_id из callback_data
    if not callback_data.startswith("extend_points_key:"):
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Неверный запрос!")
        return
    
    short_id = callback_data.split(":", 1)[1]
    
    # Получаем информацию о ключе из кэша
    if short_id not in extension_keys_cache:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Ключ не найден или устарел!")
        return
    
    key_info = extension_keys_cache[short_id]
    
    # Проверяем, что ключ принадлежит пользователю
    if key_info['user_id'] != user_id:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Доступ запрещен!")
        return
    
    # Создаем объект client для совместимости
    client = {
        'email': key_info['email'],
        'xui': key_info['xui'],
        'server_name': key_info['server_name']
    }
    
    # Продлеваем ключ
    await extend_selected_key_with_points(update, context, client, user_id)

async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает реферальную информацию"""
    await update.callback_query.answer()
    
    user_id = str(update.callback_query.from_user.id)
    
    # Добавляем логирование для диагностики
    logger.info(f"REFERRAL_CALLBACK: user_id={user_id}")
    
    stats = await get_referral_stats(user_id)
    points_info = await get_user_points(user_id)
    points_days = await get_config('points_days_per_point', '30')
    
    # Логируем полученную статистику
    logger.info(f"REFERRAL_CALLBACK: stats={stats}, points={points_info}")
    
    # Генерируем реферальную ссылку
    referral_code = generate_referral_code(user_id)
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Используем единый стиль для реферального меню
    message = (
        f"{UIStyles.header('Реферальная программа')}\n\n"
        f"<b>Ваши баллы:</b> {UIStyles.highlight(str(points_info['points']))}\n\n"
        f"<b>Статистика рефералов:</b>\n"
        f"Всего приглашено: {stats['total_referrals']}\n"
        f"Успешных рефералов: {stats['successful_referrals']}\n"
        f"Ожидают покупки: {stats['pending_referrals']}\n\n"
        f"<b>Как заработать баллы:</b>\n"
        f"1. Поделитесь ссылкой с друзьями\n"
        f"2. Друг переходит по ссылке\n"
        f"3. Если друг НИКОГДА не пользовался ботом - он покупает и вы получаете 1 балл!\n"
        f"4. Если друг УЖЕ пользовался ботом - балл не выдается\n"
        f"5. 1 балл = {points_days} дней VPN бесплатно!\n\n"
        f"{UIStyles.warning_message('Важно: Балл выдается только за привлечение новых клиентов!')}\n\n"
        f"<b>Ваша реферальная ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"<b>Как поделиться:</b>\n"
        f"{UIStyles.description('• Нажмите на ссылку выше, чтобы скопировать')}\n"
        + UIStyles.description('• Или используйте кнопку "Поделиться в Telegram"')
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Поделиться в Telegram", url=f"https://t.me/share/url?url={referral_link}")],
        [UIButtons.back_button()]
    ])
    
    await safe_edit_or_reply_universal(update.callback_query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='referral_menu')

async def rename_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик переименования ключа"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    short_id = query.data.split(':')[1]
    
    try:
        # Ищем ключ по short_id
        key_email = None
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(f"{user_id}_") or client['email'].startswith(f"trial_{user_id}_"):
                            # Проверяем short_id
                            import hashlib
                            possible_short_ids = [
                                hashlib.md5(f"rename:{client['email']}".encode()).hexdigest()[:8]
                            ]
                            if short_id in possible_short_ids:
                                key_email = client['email']
                                break
                    if key_email:
                        break
                if key_email:
                    break
            except Exception as e:
                logger.error(f"Ошибка при поиске ключа на сервере {server['name']}: {e}")
                continue
        
        if not key_email:
            await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ключ не найден!")
            return
        
        # Сохраняем email ключа и message_id в контексте для последующего использования
        context.user_data['rename_key_email'] = key_email
        context.user_data['rename_message_id'] = query.message.message_id
        context.user_data['rename_chat_id'] = query.message.chat_id
        
        # Запрашиваем новое имя ключа
        message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"<b>Текущий ключ:</b> <code>{key_email}</code>\n\n"
            f"{UIStyles.description('Введите новое имя для ключа (максимум 50 символов):')}\n\n"
            f"{UIStyles.warning_message('Имя будет отображаться в списке ваших ключей')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        await safe_edit_or_reply(query.message, message, reply_markup=keyboard, parse_mode="HTML")
        
        # Устанавливаем состояние ожидания ввода имени
        context.user_data['waiting_for_key_name'] = True
        
    except Exception as e:
        logger.error(f"Ошибка в rename_key_callback: {e}")
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка при переименовании ключа!")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для переименования ключей"""
    if not await check_private_chat(update):
        return
    
    # Проверяем, ожидаем ли мы ввод имени ключа
    if not context.user_data.get('waiting_for_key_name', False):
        return
    
    user_id = str(update.message.from_user.id)
    new_name = update.message.text.strip()
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Получаем данные из контекста
    message_id = context.user_data.get('rename_message_id')
    chat_id = context.user_data.get('rename_chat_id')
    
    if not message_id or not chat_id:
        logger.error("Не найдены message_id или chat_id в контексте")
        return
    
    # Валидация имени
    if len(new_name) > 50:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя ключа слишком длинное!\n\n"
            f"{UIStyles.description('Максимум 50 символов. Попробуйте еще раз.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    if not new_name:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя ключа не может быть пустым!\n\n"
            f"{UIStyles.description('Введите корректное имя для ключа.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    try:
        key_email = context.user_data.get('rename_key_email')
        if not key_email:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден в контексте!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
            return
        
        # Находим сервер с ключом
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден на серверах!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
            return
        
        # Обновляем имя ключа
        response = xui.updateClientName(key_email, new_name)
        
        if response and response.status_code == 200:
            # Очищаем состояние
            context.user_data.pop('waiting_for_key_name', None)
            context.user_data.pop('rename_key_email', None)
            context.user_data.pop('rename_message_id', None)
            context.user_data.pop('rename_chat_id', None)
            
            # Показываем успешное сообщение в том же окне
            success_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.SUCCESS} <b>Ключ успешно переименован!</b>\n\n"
                f"<b>Новое имя:</b> {new_name}\n"
                f"<b>Email:</b> <code>{key_email}</code>\n\n"
                f"{UIStyles.description('Имя будет отображаться в списке ваших ключей')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Мои ключи", callback_data="mykey")],
                [UIButtons.back_button()]
            ])
            
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=success_message,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
        else:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Не удалось обновить имя ключа на сервере!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при переименовании ключа: {e}")
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> {str(e)}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as edit_e:
            logger.error(f"Ошибка редактирования сообщения: {edit_e}")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'Нет доступа.')
        return
    stack = context.user_data.setdefault('nav_stack', [])
    if not stack or stack[-1] != 'admin_menu':
        push_nav(context, 'admin_menu')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Логи", callback_data="admin_errors")],
        [InlineKeyboardButton("Проверка серверов", callback_data="admin_check_servers")],
        [InlineKeyboardButton("Уведомления", callback_data="admin_notifications")],
        [InlineKeyboardButton("Рассылка", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("Изменить дни за балл", callback_data="admin_set_days_start")],
        [UIButtons.back_button()],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("admin_menu: message is None")
        return
    
    # Используем единый стиль для админ-меню
    admin_menu_text = UIMessages.admin_menu_message()
    await safe_edit_or_reply_universal(message, admin_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')


# ===== РАССЫЛКА ДЛЯ АДМИНА =====
BROADCAST_WAITING_TEXT = 1001
BROADCAST_CONFIRM = 1002

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.callback_query.message, 'Нет доступа.')
        return
    await update.callback_query.answer()
    # Сохраняем исходное сообщение для дальнейших редактирований
    context.user_data['broadcast_text'] = None
    context.user_data['broadcast_msg_chat_id'] = update.callback_query.message.chat_id
    context.user_data['broadcast_msg_id'] = update.callback_query.message.message_id
    keyboard = InlineKeyboardMarkup([[UIButtons.back_button()]])
    await update.callback_query.message.edit_text(UIMessages.broadcast_intro_message(), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    return BROADCAST_WAITING_TEXT

async def admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    text = update.message.text
    context.user_data['broadcast_text'] = text
    # Удаляем сообщение админа с текстом
    try:
        await update.message.delete()
    except Exception:
        pass
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Отправить", callback_data="admin_broadcast_send")],
        [UIButtons.back_button()]
    ])
    # Редактируем исходное сообщение на предпросмотр
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
            text=UIMessages.broadcast_preview_message(text), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await safe_edit_or_reply(update.effective_message, UIMessages.broadcast_preview_message(text), reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        context.user_data['broadcast_msg_chat_id'] = update.effective_message.chat_id
        context.user_data['broadcast_msg_id'] = update.effective_message.message_id
    return BROADCAST_CONFIRM

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.callback_query.answer()
    text = context.user_data.get('broadcast_text')
    if not text:
        await safe_edit_or_reply(update.callback_query.message, f"{UIEmojis.ERROR} Текст рассылки пуст.")
        return ConversationHandler.END

    # Получаем список получателей и исключаем админов
    recipients = await get_all_user_ids()
    admin_set = set(str(a) for a in ADMIN_IDS)
    recipients = [uid for uid in recipients if str(uid) not in admin_set]
    total = len(recipients)
    sent = 0
    failed = 0
    # собираем подробную статистику
    details = []  # [{'user_id': str, 'status': 'ok'|'failed'}]
    batch = 40

    # Готовим исходное сообщение к показу прогресса
    chat_id = context.user_data.get('broadcast_msg_chat_id')
    msg_id = context.user_data.get('broadcast_msg_id')
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
            text=f"<b>Отправка рассылки</b>\n\nОтправлено: 0/{total}. Ошибок: 0.", parse_mode="HTML")
    except Exception:
        pass
    for i in range(0, total, batch):
        chunk = recipients[i:i+batch]
        for user_id in chunk:
            try:
                await context.bot.send_message(chat_id=int(user_id), text=text, parse_mode="HTML", disable_web_page_preview=True)
                sent += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'ok'})
            except telegram.error.Forbidden:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            except telegram.error.BadRequest as e:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(int(getattr(e, 'retry_after', 1)))
                try:
                    await context.bot.send_message(chat_id=int(user_id), text=text, parse_mode="HTML", disable_web_page_preview=True)
                    sent += 1
                    if len(details) < 10000:
                        details.append({'user_id': str(user_id), 'status': 'ok'})
                except Exception:
                    failed += 1
                    if len(details) < 10000:
                        details.append({'user_id': str(user_id), 'status': 'failed'})
            except Exception:
                failed += 1
                if len(details) < 10000:
                    details.append({'user_id': str(user_id), 'status': 'failed'})
            # лёгкая задержка между сообщениями
            await asyncio.sleep(0.05)
        # пауза между батчами
        await asyncio.sleep(1.0)
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                text=f"<b>Отправка рассылки</b>\n\nОтправлено: {sent}/{total}. Ошибок: {failed}.", parse_mode="HTML")
        except Exception:
            pass

    # сохраняем детали в user_data для кнопок
    context.user_data['broadcast_details'] = details
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Экспорт CSV", callback_data="admin_broadcast_export")],
        [UIButtons.back_button()]
    ])
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
            text=f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.", reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await safe_edit_or_reply(update.callback_query.message, f"<b>Рассылка завершена</b>\n\nУспешно: {sent}, ошибок: {failed} из {total}.", reply_markup=keyboard, parse_mode="HTML")
    return ConversationHandler.END

async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await admin_menu(update, context)
    return ConversationHandler.END

async def admin_broadcast_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.callback_query.answer()
    import io, csv
    details = context.user_data.get('broadcast_details') or []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "status"])
    for row in details:
        writer.writerow([row.get('user_id',''), row.get('status','')])
    output.seek(0)
    bio = io.BytesIO(output.read().encode('utf-8'))
    bio.name = 'broadcast_report.csv'
    await context.bot.send_document(chat_id=update.effective_user.id, document=bio, caption="Отчёт рассылки")

# Регистрируем команды
if __name__ == '__main__':
    # Создаем HTTPXRequest с увеличенными таймаутами для стабильной работы
    request = HTTPXRequest(
        connection_pool_size=8,  # Размер пула соединений
        connect_timeout=30.0,    # Таймаут на установку соединения (увеличен с дефолтных 5)
        read_timeout=30.0,       # Таймаут на чтение ответа (увеличен с дефолтных 5)
        write_timeout=30.0,      # Таймаут на отправку данных
        pool_timeout=30.0        # Таймаут ожидания свободного соединения в пуле
    )
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).post_init(on_startup).build()
    
    # Добавляем глобальную обработку ошибок
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('mykey', mykey))
    app.add_handler(CommandHandler('instruction', instruction))
   
    app.add_handler(CommandHandler('check_servers', force_check_servers))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^instr_"))
    app.add_handler(CallbackQueryHandler(instruction_callback, pattern="^back_instr$"))
    app.add_handler(CallbackQueryHandler(extend_key_callback, pattern="^ext_key:"))
    app.add_handler(CallbackQueryHandler(extend_period_callback, pattern="^ext_per:"))

    # ConversationHandler для интерактивной настройки дней за балл
    admin_set_days_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_set_days_start, pattern="^admin_set_days_start$")],
        states={
            WAITING_FOR_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_days_input),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin_set_days_cancel, pattern="^admin_set_days_cancel$")
        ],
        per_user=True,
        per_chat=True,
        per_message=False
    )
    app.add_handler(admin_set_days_conv)
    
    app.add_handler(CommandHandler('admin_errors', admin_errors))
    app.add_handler(CommandHandler('admin_check_servers', admin_check_servers))
    app.add_handler(CommandHandler('admin_notifications', admin_notifications))
    app.add_handler(CommandHandler('admin_config', admin_config))
    app.add_handler(CommandHandler('admin_set_days', admin_set_days))
    app.add_handler(CallbackQueryHandler(start_callback_handler, pattern="^(buy_menu|buy_month|buy_3month|select_period_.*|select_server_.*|mykey|instruction|keys_page_.*)$"))
    app.add_handler(CallbackQueryHandler(select_server_callback, pattern="^(select_server_.*|server_unavailable_.*|refresh_servers)$"))
    app.add_handler(CallbackQueryHandler(universal_back_callback, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(admin_menu, pattern="^admin_menu$"))
    # Добавляем обработчики для админ-меню
    app.add_handler(CallbackQueryHandler(admin_errors, pattern="^admin_errors$"))
    app.add_handler(CallbackQueryHandler(admin_check_servers, pattern="^admin_check_servers$"))
    app.add_handler(CallbackQueryHandler(admin_notifications, pattern="^admin_notifications$"))
    
    # Рассылка
    admin_broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast_start$")],
        states={
            BROADCAST_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_input),
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_send, pattern="^admin_broadcast_send$"),
                CallbackQueryHandler(admin_broadcast_cancel, pattern="^back$")
            ]
        },
        fallbacks=[CallbackQueryHandler(admin_broadcast_cancel, pattern="^back$")],
        per_user=True,
        per_chat=True,
        per_message=False
    )
    app.add_handler(admin_broadcast_conv)
    # Глобальный обработчик экспорта, чтобы работал и после завершения диалога
    app.add_handler(CallbackQueryHandler(admin_broadcast_export, pattern="^admin_broadcast_export$"))

    
    # Обработчики для реферальной системы
    app.add_handler(CallbackQueryHandler(points_callback, pattern="^points$"))
    app.add_handler(CallbackQueryHandler(spend_points_callback, pattern="^spend_points$"))
    app.add_handler(CallbackQueryHandler(buy_with_points_callback, pattern="^buy_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_with_points_callback, pattern="^extend_with_points$"))
    app.add_handler(CallbackQueryHandler(extend_points_key_callback, pattern="^extend_points_key:"))
    app.add_handler(CallbackQueryHandler(referral_callback, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(rename_key_callback, pattern="^rename_key:"))
    
    # Обработчик текстовых сообщений для переименования ключей
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    app.run_polling()
