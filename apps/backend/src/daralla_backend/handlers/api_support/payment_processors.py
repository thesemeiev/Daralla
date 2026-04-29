"""
Обработчики платежей из webhook'ов YooKassa
"""
import logging
import json
import datetime

from ...db import get_payment_by_id, update_payment_status, update_payment_activation

logger = logging.getLogger(__name__)


def get_globals():
    """Получает сервисы из AppContext."""
    from ...app_context import get_ctx
    ctx = get_ctx()
    return {
        'server_manager': ctx.server_manager,
        'notification_manager': ctx.notification_manager,
        'subscription_manager': ctx.subscription_manager,
    }


async def process_payment_webhook(payment_id, status):
    """Обрабатывает платеж из webhook'а (YooKassa и CryptoCloud)."""
    try:
        # Нормализуем статус: CryptoCloud может присылать "cancelled"
        if status == "cancelled":
            status = "canceled"
        # Получаем информацию о платеже из базы данных
        payment_info = await get_payment_by_id(payment_id)
        if not payment_info:
            logger.warning(f"Платеж {payment_id} не найден в базе данных")
            return
        
        # Проверяем, не обработан ли уже этот платеж
        current_status = payment_info.get('status', 'pending')
        is_activated = payment_info.get('activated', 0)
        
        if status == 'succeeded' and current_status == 'succeeded' and is_activated == 1:
            logger.info(f"Платеж {payment_id} уже обработан, пропускаем повторную обработку")
            return
        
        user_id = payment_info['user_id']
        raw_meta = payment_info.get('meta')
        if raw_meta is None:
            meta = {}
        elif isinstance(raw_meta, dict):
            meta = raw_meta
        elif isinstance(raw_meta, str):
            try:
                meta = json.loads(raw_meta) if raw_meta.strip() else {}
            except (json.JSONDecodeError, AttributeError):
                meta = {}
        else:
            meta = {}
        
        logger.info(f"Обработка webhook платежа: payment_id={payment_id}, user_id={user_id}, status={status}, current_status={current_status}, activated={is_activated}")
        
        # Обрабатываем платеж в зависимости от статуса
        if status == 'succeeded':
            # Успешная оплата - создаем или продлеваем подписку
            await process_successful_payment(payment_id, user_id, meta)
        elif status in ['canceled', 'refunded']:
            # Отмененная/возвращенная оплата
            await process_canceled_payment(payment_id, user_id, status)
        elif status not in ['pending']:
            # Любой другой неуспешный статус
            await process_failed_payment(payment_id, user_id, status)
        
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки webhook платежа {payment_id}: {e}")


async def process_successful_payment(payment_id, user_id, meta):
    """Обрабатывает успешный платеж"""
    try:
        period = meta.get('type', 'month')

        # Проверяем, это продление или новая покупка
        is_extension = period.startswith('extend_')
        if is_extension:
            await process_extension_payment(payment_id, user_id, meta)
        else:
            await process_new_purchase_payment(payment_id, user_id, meta)
            
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_extension_payment(payment_id, user_id, meta):
    """Обрабатывает продление подписки"""
    try:
        period = meta.get('type', 'month')
        # Убираем префиксы: extend_sub_month -> month, extend_sub_3month -> 3month
        actual_period = period
        if period.startswith('extend_sub_'):
            actual_period = period.replace('extend_sub_', '', 1)
        elif period.startswith('extend_'):
            actual_period = period.replace('extend_', '', 1)
        try:
            days = int(meta.get("period_days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days <= 0:
            from ...prices_config import get_tariff_days
            days = get_tariff_days(actual_period, default_days=30)
        
        # Проверяем, это продление подписки
        is_subscription_extension = period.startswith('extend_sub_')
        extension_subscription_id = meta.get('extension_subscription_id')
        
        if is_subscription_extension:
            # Продление подписки
            logger.info(f"Обработка продления подписки: subscription_id={extension_subscription_id}, period={period}, actual_period={actual_period}, days={days}")
            
            if not extension_subscription_id:
                logger.error(f"Не найден subscription_id для продления в meta: {meta}")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Получаем глобальные переменные
            globals_dict = get_globals()
            subscription_manager = globals_dict.get('subscription_manager')
            server_manager = globals_dict.get('server_manager')
            
            if not subscription_manager or not server_manager:
                logger.error("subscription_manager или server_manager не доступен")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Проверяем, что подписка принадлежит пользователю
            from ...db.subscriptions_db import (
                get_subscription_by_id,
                get_subscription_servers,
                update_subscription_expiry,
                update_subscription_price,
            )
            sub = await get_subscription_by_id(extension_subscription_id, user_id)
            
            if not sub:
                logger.error(f"Попытка продлить чужую подписку: user_id={user_id}, subscription_id={extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                return

            if sub.get("status") == "deleted":
                logger.warning(
                    "Продление удалённой подписки: subscription_id=%s, user_id=%s, payment_id=%s. Платёж засчитан, подписка не продлевается.",
                    extension_subscription_id, user_id, payment_id,
                )
                await update_payment_status(payment_id, "succeeded")
                await update_payment_activation(payment_id, 1)
                return
            
            # Получаем информацию о подписке
            servers = await get_subscription_servers(extension_subscription_id)
            
            if not servers:
                logger.error(f"Не найдены серверы для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Считаем новый срок и (при необходимости) цену после конвертации пробной — в БД пишем только
            # после успешной синхронизации хотя бы на одном сервере, иначе платёж failed, а срок уже
            # увеличен в БД (рассинхрон с оплатой).
            import time
            current_time = int(time.time())
            paid_price_after_trial = None
            sub_price = float(sub.get('price') or 0)
            if sub_price == 0:
                from ...prices_config import PRICES
                paid_price_after_trial = float(PRICES.get(actual_period, 150))

            current_expires_at = sub['expires_at']
            base_time = max(current_expires_at, current_time)
            new_expires_at = base_time + days * 24 * 60 * 60

            # Шаг 1: панели — reconcile по переданному expires_at (без предварительного update в БД)
            successful_extensions = []
            failed_extensions = []
            
            # Получаем device_limit из подписки для передачи в ensure_client_on_server
            device_limit = sub.get('device_limit', 1) if sub else 1
            
            for server_info in servers:
                server_name = server_info['server_name']
                client_email = server_info['client_email']
                
                try:
                    # Используем ensure_client_on_server с целевым expires_at (запись в БД — после успеха)
                    client_exists, client_created = await subscription_manager.ensure_client_on_server(
                        subscription_id=extension_subscription_id,
                        server_name=server_name,
                        client_email=client_email,
                        user_id=user_id,
                        expires_at=new_expires_at,
                        token=sub['subscription_token'] if sub else '',
                        device_limit=device_limit  # Передаем device_limit для синхронизации limitIp
                    )
                    
                    if client_exists:
                        successful_extensions.append(server_name)
                        if client_created:
                            logger.info(f"Клиент создан на сервере {server_name} для подписки {extension_subscription_id}")
                        else:
                            logger.info(f"Время клиента синхронизировано на сервере {server_name} для подписки {extension_subscription_id}")
                    else:
                        logger.warning(f"Не удалось синхронизировать клиента на сервере {server_name}")
                        failed_extensions.append(server_name)
                except Exception as e:
                    # Ошибка при синхронизации - логируем и добавляем в failed
                    logger.error(f"Ошибка синхронизации клиента на сервере {server_name}: {e}")
                    failed_extensions.append(server_name)
            
            # Проверяем, что синхронизация прошла успешно хотя бы на одном сервере
            if not successful_extensions:
                logger.error(f"Не удалось синхронизировать клиентов ни на одном сервере для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                return

            if paid_price_after_trial is not None:
                await update_subscription_price(extension_subscription_id, paid_price_after_trial)
                logger.info(
                    "Пробная подписка %s конвертирована в платную (price=%s) после успешной синхронизации на панели",
                    extension_subscription_id,
                    paid_price_after_trial,
                )
            await update_subscription_expiry(extension_subscription_id, new_expires_at)
            logger.info(
                "Подписка %s продлена до %s в БД (после успешной синхронизации хотя бы на одном сервере)",
                extension_subscription_id,
                new_expires_at,
            )

            # Проверяем, что синхронизация прошла на всех серверах
            if failed_extensions:
                logger.warning(
                    f"Продление подписки {extension_subscription_id} прошло не на всех серверах: "
                    f"успешно на {len(successful_extensions)} серверах, "
                    f"ошибки на {len(failed_extensions)} серверах: {failed_extensions}. "
                    f"Серверы будут синхронизированы при следующей автоматической синхронизации."
                )
            
            await update_payment_status(payment_id, 'succeeded')
            await update_payment_activation(payment_id, 1)

            try:
                from daralla_backend.events import EVENTS_MODULE_ENABLED, on_payment_success as events_on_payment_success
                if EVENTS_MODULE_ENABLED:
                    await events_on_payment_success(user_id, payment_id, meta)
            except (ImportError, RuntimeError, ValueError) as events_e:
                logger.debug("events.on_payment_success (extension): %s", events_e)

            expiry_str = datetime.datetime.fromtimestamp(new_expires_at).strftime('%d.%m.%Y %H:%M')
            logger.info(
                "Продление подписки оплачено: user_id=%s payment_id=%s subscription_id=%s expires=%s ok=%s/%s failed=%s",
                user_id,
                payment_id,
                extension_subscription_id,
                expiry_str,
                len(successful_extensions),
                len(servers),
                failed_extensions or "-",
            )
            return
        else:
            # Это не продление подписки - ошибка
            logger.error(f"Неизвестный тип продления: period={period}, meta={meta}")
            await update_payment_status(payment_id, 'failed')
            return
                    
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки продления подписки {payment_id}: {e}")


async def process_new_purchase_payment(payment_id, user_id, meta):
    """Обрабатывает новую покупку - создаёт подписку и клиентов на всех доступных серверах"""
    try:
        period = str(meta.get('type', 'month') or 'month')
        try:
            days = int(meta.get("period_days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days <= 0:
            from ...prices_config import get_tariff_days
            days = get_tariff_days(period, default_days=30)
        device_limit = int(meta.get('device_limit', 1))
        unique_email = meta.get('unique_email')
        
        logger.info(f"Обработка новой покупки: period={period}, days={days}, email={unique_email}")
        
        if not unique_email:
            logger.error(f"Не найден unique_email в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Получаем глобальные переменные
        globals_dict = get_globals()
        server_manager = globals_dict.get('server_manager')
        subscription_manager = globals_dict.get('subscription_manager')
        
        if not server_manager:
            logger.error("server_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return
        
        if not subscription_manager:
            logger.error("subscription_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Шаг 1: Создаём подписку в БД (Saga Pattern: сначала БД, потом внешние системы)
        # Это гарантирует, что у нас есть запись в БД даже если создание на серверах не удастся
        price = float(meta.get('price', '0') or 0)
        sub_dict = None
        token = None
        subscription_created = False
        try:
            sub_dict, token = await subscription_manager.create_subscription_for_user(
                user_id=str(user_id),
                period=period,
                device_limit=device_limit,
                price=price,
            )
            subscription_created = True
            logger.info(f"Подписка создана: sub_id={sub_dict['id']}, token={token}")
            
            # Используем правильный формат email: {user_id}_{subscription_id}
            # Вместо UUID из метаданных платежа используем реальный subscription_id
            unique_email = f"{user_id}_{sub_dict['id']}"
            logger.info(f"Используется правильный формат email: {unique_email} (вместо UUID из метаданных)")
        except Exception as sub_e:
            logger.error(f"Ошибка при создании подписки для user_id={user_id}: {sub_e}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Шаг 2: Получаем серверы только из группы подписки (sub_dict['group_id'])
        # Подписка создана с конкретным group_id (наименее загруженная группа);
        # привязываем и создаём клиентов только на серверах этой группы.
        from ...db.servers_db import get_servers_config
        
        subscription_group_id = sub_dict.get('group_id')
        servers_in_db = await get_servers_config(
            group_id=subscription_group_id,
            only_active=True
        ) if subscription_group_id is not None else await get_servers_config(only_active=True)
        
        if not servers_in_db or len(servers_in_db) == 0:
            logger.error("Нет серверов в БД для создания подписки")
            await update_payment_status(payment_id, 'failed')
            return

        # Преобразуем список серверов из БД в список имен серверов
        all_configured_servers = [s["name"] for s in servers_in_db]
        
        # Шаг 3: Создаём клиента на каждом сервере из конфигурации
        # Используем единую функцию ensure_client_on_server для гарантии наличия клиента
        # Используем токен подписки как subId для связи клиента с подпиской в X-UI
        # Гибридный подход: привязываем все серверы к подписке, создаем клиентов на доступных
        successful_servers = []
        failed_servers = []
        
        # Получаем expires_at из подписки
        expires_at = sub_dict.get('expires_at') if sub_dict else None
        if not expires_at:
            import time
            expires_at = int(time.time()) + days * 24 * 60 * 60
        
        # Сначала привязываем ВСЕ серверы к подписке в БД (даже если недоступны)
        # Это гарантирует, что все серверы будут в подписке сразу
        for server_name in all_configured_servers:
            try:
                # Привязываем сервер к подписке в БД (даже если он недоступен)
                # Клиент будет создан автоматически при синхронизации, если сервер недоступен сейчас
                await subscription_manager.attach_server_to_subscription(
                    subscription_id=sub_dict["id"],
                    server_name=server_name,
                    client_email=unique_email,
                    client_id=None,
                )
                logger.info(f"Сервер {server_name} привязан к подписке {sub_dict['id']}")
            except Exception as attach_e:
                # Если сервер уже привязан, это нормально (идемпотентность)
                if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                    logger.info(f"Сервер {server_name} уже привязан к подписке {sub_dict['id']}")
                else:
                    logger.error(f"Ошибка привязки сервера {server_name} к подписке: {attach_e}")
        
        # Теперь пытаемся создать клиентов на всех серверах
        # Если сервер недоступен - клиент будет создан при синхронизации
        for server_name in all_configured_servers:
            try:
                # Используем единую функцию ensure_client_on_server
                # Она гарантирует наличие клиента и синхронизирует время истечения
                client_exists, client_created = await subscription_manager.ensure_client_on_server(
                    subscription_id=sub_dict["id"],
                    server_name=server_name,
                    client_email=unique_email,
                    user_id=user_id,
                    expires_at=expires_at,
                    token=token
                )
                
                if client_exists:
                    successful_servers.append((server_name, unique_email))
                    # Сервер уже привязан к подписке выше, просто логируем результат
                    if client_created:
                        logger.info(f"Клиент создан на сервере {server_name} для подписки {sub_dict['id']}")
                    else:
                        logger.info(f"Клиент уже существует на сервере {server_name}")
                else:
                    # Сервер недоступен или ошибка создания
                    # Это не критично - клиент будет создан при синхронизации
                    # Сервер уже привязан к подписке выше
                    logger.warning(f"Не удалось создать клиента на сервере {server_name} (будет создан при синхронизации)")
                    failed_servers.append(server_name)
            except Exception as e:
                logger.error(f"Ошибка создания клиента на сервере {server_name}: {e}")
                failed_servers.append(server_name)
        
        if not successful_servers:
            logger.error("Не удалось создать клиента ни на одном сервере")
            
            # Компенсирующая транзакция (Saga Pattern): откатываем создание подписки в БД
            if subscription_created and sub_dict:
                try:
                    from ...db.subscriptions_db import update_subscription_status
                    await update_subscription_status(sub_dict['id'], 'deleted')
                    logger.info(f"Подписка {sub_dict['id']} удалена из-за ошибки создания клиентов (компенсирующая транзакция)")
                except Exception as rollback_e:
                    logger.error(f"Ошибка отката подписки {sub_dict['id']}: {rollback_e}")
            
            await update_payment_status(payment_id, 'failed')
            return

        # Шаг 4: Обновляем статус платежа
        # Подписка создана успешно, если хотя бы на одном сервере клиент создан
        # Нездоровые серверы уже привязаны к подписке, клиенты будут созданы при синхронизации
        await update_payment_status(payment_id, 'succeeded')
        await update_payment_activation(payment_id, 1)

        try:
            from daralla_backend.events import EVENTS_MODULE_ENABLED, on_payment_success as events_on_payment_success
            if EVENTS_MODULE_ENABLED:
                await events_on_payment_success(user_id, payment_id, meta)
        except Exception as events_e:
            logger.debug("events.on_payment_success (new purchase): %s", events_e)
        
        # Логируем результаты
        if failed_servers:
            logger.info(
                f"Подписка {sub_dict['id']} создана: "
                f"клиенты созданы на {len(successful_servers)} серверах, "
                f"на {len(failed_servers)} серверах будут созданы при синхронизации: {failed_servers}"
            )
        else:
            logger.info(f"Подписка {sub_dict['id']} создана: клиенты созданы на всех {len(successful_servers)} серверах")
        
        # Шаг 5: публичный URL подписки в лог (статус и ссылка пользователь видит в веб/Mini App)
        try:
            import os
            import urllib.parse

            expiry_str = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime('%d.%m.%Y %H:%M')
            webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
            subscription_base_url = os.getenv("SUBSCRIPTION_URL", "").rstrip("/")
            if subscription_base_url:
                base_url = subscription_base_url
            elif webhook_url:
                parsed = urllib.parse.urlparse(webhook_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                base_url = None
            if base_url:
                subscription_url = f"{base_url}/sub/{token}"
            else:
                subscription_url = f"http://localhost:5000/sub/{token}"
                logger.warning(
                    "WEBHOOK_URL/SUBSCRIPTION_URL не заданы — в логе URL с localhost; payment_id=%s",
                    payment_id,
                )
            logger.info(
                "Новая подписка активирована: user_id=%s payment_id=%s sub_id=%s period=%s expires=%s "
                "servers_ok=%s subscription_url=%s deferred_servers=%s",
                user_id,
                payment_id,
                sub_dict["id"],
                period,
                expiry_str,
                len(successful_servers),
                subscription_url,
                ",".join(failed_servers) if failed_servers else "-",
            )
        except (RuntimeError, ValueError, TypeError, KeyError) as e:
            logger.warning("Не удалось залогировать URL новой подписки: %s", e)
            
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки новой покупки {payment_id}: {e}")
        await update_payment_status(payment_id, 'failed')


async def process_canceled_payment(payment_id, user_id, status):
    """Обрабатывает отмененный/возвращенный платеж. В БД сохраняем реальный статус (canceled/refunded) для корректного отображения на фронте."""
    try:
        await update_payment_status(payment_id, status if status in ('canceled', 'refunded') else 'failed')
        await update_payment_activation(payment_id, 0)
        logger.info("Платёж отменён/возвращён: payment_id=%s user_id=%s status=%s", payment_id, user_id, status)
    except (RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {e}")


async def process_failed_payment(payment_id, user_id, status):
    """Обрабатывает неудачный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        logger.info("Платёж неуспешен: payment_id=%s user_id=%s status=%s", payment_id, user_id, status)
    except (RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка обработки неудачного платежа {payment_id}: {e}")

