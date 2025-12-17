"""
Менеджер синхронизации между БД и X-UI серверами.
Решает проблему рассинхронизации данных.
"""
import logging
import asyncio
from typing import List, Dict, Tuple

from ..db.subscribers_db import (
    get_all_active_subscriptions,
    get_subscription_servers,
    update_subscription_status,
)
from .server_manager import MultiServerManager

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Управляет синхронизацией между БД подписок и реальными клиентами на X-UI серверах.
    
    Архитектура: БД является источником истины (Source of Truth).
    X-UI серверы синхронизируются с БД, а не наоборот.
    
    Решает проблемы:
    - Клиент в БД, но не на сервере (нужно создать на сервере)
    - Клиент на сервере, но не в БД (orphaned - нужно удалить с сервера или добавить в БД)
    - Несоответствие статусов (активен в БД, но истек на сервере - обновляем сервер)
    """
    
    def __init__(self, server_manager: MultiServerManager):
        self.server_manager = server_manager
    
    async def sync_subscription_with_servers(self, subscription_id: int, auto_fix: bool = False) -> Dict[str, any]:
        """
        Синхронизирует одну подписку с серверами X-UI.
        
        Args:
            subscription_id: ID подписки для синхронизации
            auto_fix: Если True, автоматически создает отсутствующих клиентов на серверах
        
        Returns:
            dict с результатами синхронизации:
            {
                'subscription_id': int,
                'servers_checked': int,
                'servers_synced': int,
                'clients_created': int,
                'clients_removed': int,
                'errors': List[str]
            }
        """
        from ..db.subscribers_db import get_subscription_by_token
        
        # Получаем информацию о подписке
        servers = await get_subscription_servers(subscription_id)
        if not servers:
            logger.warning(f"Подписка {subscription_id} не имеет привязанных серверов")
            return {
                'subscription_id': subscription_id,
                'servers_checked': 0,
                'servers_synced': 0,
                'clients_created': 0,
                'clients_removed': 0,
                'errors': []
            }
        
        result = {
            'subscription_id': subscription_id,
            'servers_checked': 0,
            'servers_synced': 0,
            'clients_created': 0,
            'clients_removed': 0,
            'errors': []
        }
        
        # Проверяем каждый сервер
        for server_info in servers:
            server_name = server_info['server_name']
            client_email = server_info['client_email']
            
            try:
                result['servers_checked'] += 1
                
                # Получаем X-UI объект для сервера
                xui, resolved_name = self.server_manager.get_server_by_name(server_name)
                if not xui:
                    result['errors'].append(f"Сервер {server_name} недоступен")
                    continue
                
                # Проверяем, существует ли клиент на сервере
                client_exists = xui.client_exists(client_email)
                
                if not client_exists:
                    # Клиент должен быть на сервере, но его нет
                    logger.warning(
                        f"Клиент {client_email} не найден на сервере {server_name} для подписки {subscription_id}"
                    )
                    
                    if auto_fix:
                        # Автоматическое восстановление: создаем отсутствующего клиента
                        try:
                            # Получаем информацию о подписке для восстановления
                            from ..db.subscribers_db import get_all_active_subscriptions
                            
                            # Находим подписку по ID
                            all_subs = await get_all_active_subscriptions()
                            subscription = None
                            for sub in all_subs:
                                if sub['id'] == subscription_id:
                                    subscription = sub
                                    break
                            
                            if subscription:
                                # Вычисляем оставшиеся дни до истечения
                                import time
                                current_time = int(time.time())
                                expires_at = subscription.get('expires_at', 0)
                                
                                if expires_at > current_time:
                                    # Подписка еще активна, вычисляем дни
                                    remaining_seconds = expires_at - current_time
                                    remaining_days = max(1, remaining_seconds // (24 * 60 * 60))  # Минимум 1 день
                                    
                                    # Извлекаем user_id из email (формат: user_id_uuid)
                                    user_id = client_email.split('_')[0] if '_' in client_email else None
                                    
                                    if user_id:
                                        logger.info(
                                            f"Автоматическое восстановление клиента {client_email} на сервере {server_name}, "
                                            f"осталось дней: {remaining_days}"
                                        )
                                        
                                        # Создаем клиента
                                        try:
                                            response = xui.addClient(
                                                day=remaining_days,
                                                tg_id=user_id,
                                                user_email=client_email,
                                                timeout=15,
                                                key_name=subscription.get('subscription_token', '')
                                            )
                                            
                                            # Проверяем успешность
                                            if response.status_code == 200:
                                                try:
                                                    response_json = response.json()
                                                    if response_json.get('success', False):
                                                        result['clients_created'] += 1
                                                        result['servers_synced'] += 1
                                                        logger.info(
                                                            f"Клиент {client_email} успешно восстановлен на сервере {server_name}"
                                                        )
                                                        continue  # Пропускаем добавление ошибки
                                                except:
                                                    pass
                                            
                                            # Если создание не удалось, но клиент уже существует (duplicate)
                                            try:
                                                if xui.client_exists(client_email):
                                                    result['servers_synced'] += 1
                                                    logger.info(
                                                        f"Клиент {client_email} уже существует на сервере {server_name} после попытки восстановления"
                                                    )
                                                    continue
                                            except:
                                                pass
                                            
                                            result['errors'].append(
                                                f"Не удалось восстановить клиента {client_email} на сервере {server_name}"
                                            )
                                        except Exception as create_e:
                                            logger.error(f"Ошибка создания клиента при восстановлении: {create_e}")
                                            result['errors'].append(
                                                f"Ошибка восстановления клиента {client_email}: {create_e}"
                                            )
                                    else:
                                        result['errors'].append(
                                            f"Не удалось извлечь user_id из email {client_email}"
                                        )
                                else:
                                    result['errors'].append(
                                        f"Подписка {subscription_id} истекла, восстановление не требуется"
                                    )
                            else:
                                result['errors'].append(
                                    f"Подписка {subscription_id} не найдена для восстановления"
                                )
                        except Exception as fix_e:
                            logger.error(f"Ошибка автоматического восстановления клиента: {fix_e}")
                            result['errors'].append(
                                f"Клиент {client_email} отсутствует на сервере {server_name} (ошибка восстановления: {fix_e})"
                            )
                    else:
                        result['errors'].append(
                            f"Клиент {client_email} отсутствует на сервере {server_name}"
                        )
                else:
                    # Клиент существует - проверяем его статус
                    result['servers_synced'] += 1
                    logger.debug(
                        f"Клиент {client_email} синхронизирован на сервере {server_name}"
                    )
                    
            except Exception as e:
                error_msg = f"Ошибка синхронизации сервера {server_name}: {e}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
        
        return result
    
    async def find_orphaned_clients(self) -> List[Dict[str, any]]:
        """
        Находит клиентов на серверах X-UI, которые не привязаны ни к одной подписке в БД.
        
        Returns:
            Список словарей с информацией об orphaned клиентах:
            [
                {
                    'server_name': str,
                    'client_email': str,
                    'client_id': str,
                    'inbound_id': int
                },
                ...
            ]
        """
        orphaned = []
        
        # Получаем все email'ы из БД подписок
        all_subscriptions = await get_all_active_subscriptions()
        db_emails = set()
        
        for sub in all_subscriptions:
            servers = await get_subscription_servers(sub['id'])
            for server_info in servers:
                db_emails.add(server_info['client_email'])
        
        # Проверяем всех клиентов на всех серверах
        for server in self.server_manager.servers:
            server_name = server['name']
            xui = server.get('x3')
            
            if not xui:
                continue
            
            try:
                inbounds_list = xui.list()
                if not inbounds_list.get('success', False):
                    continue
                
                for inbound in inbounds_list.get('obj', []):
                    inbound_id = inbound.get('id')
                    settings = inbound.get('settings', '{}')
                    
                    import json
                    try:
                        clients = json.loads(settings).get('clients', [])
                    except:
                        continue
                    
                    for client in clients:
                        client_email = client.get('email', '')
                        # Пропускаем клиентов, которые не созданы ботом (не имеют формата user_id_*)
                        if not client_email or '_' not in client_email:
                            continue
                        
                        # Если клиент не в БД, он orphaned
                        if client_email not in db_emails:
                            orphaned.append({
                                'server_name': server_name,
                                'client_email': client_email,
                                'client_id': client.get('id'),
                                'inbound_id': inbound_id
                            })
                            
            except Exception as e:
                logger.error(f"Ошибка поиска orphaned клиентов на сервере {server_name}: {e}")
                continue
        
        return orphaned
    
    async def sync_all_subscriptions(self, auto_fix: bool = False) -> Dict[str, any]:
        """
        Синхронизирует все активные подписки с серверами.
        
        Args:
            auto_fix: Если True, автоматически восстанавливает отсутствующих клиентов
        
        Returns:
            Общая статистика синхронизации
        """
        logger.info(f"Начало синхронизации всех подписок (auto_fix={auto_fix})")
        
        all_subscriptions = await get_all_active_subscriptions()
        total_stats = {
            'subscriptions_checked': len(all_subscriptions),
            'subscriptions_synced': 0,
            'total_servers_checked': 0,
            'total_servers_synced': 0,
            'total_clients_created': 0,
            'total_errors': 0,
            'errors': []
        }
        
        for sub in all_subscriptions:
            sub_id = sub['id']
            try:
                result = await self.sync_subscription_with_servers(sub_id, auto_fix=auto_fix)
                
                total_stats['total_servers_checked'] += result['servers_checked']
                total_stats['total_servers_synced'] += result['servers_synced']
                total_stats['total_clients_created'] += result.get('clients_created', 0)
                total_stats['total_errors'] += len(result['errors'])
                
                if result['servers_synced'] == result['servers_checked'] and not result['errors']:
                    total_stats['subscriptions_synced'] += 1
                else:
                    total_stats['errors'].extend(result['errors'])
                    
            except Exception as e:
                error_msg = f"Ошибка синхронизации подписки {sub_id}: {e}"
                logger.error(error_msg)
                total_stats['total_errors'] += 1
                total_stats['errors'].append(error_msg)
        
        logger.info(
            f"Синхронизация завершена: "
            f"проверено подписок {total_stats['subscriptions_checked']}, "
            f"синхронизировано {total_stats['subscriptions_synced']}, "
            f"создано клиентов {total_stats['total_clients_created']}, "
            f"ошибок {total_stats['total_errors']}"
        )
        
        return total_stats
    
    async def verify_client_exists(self, server_name: str, client_email: str) -> Tuple[bool, str]:
        """
        Проверяет существование клиента на сервере и возвращает детальную информацию.
        
        Returns:
            (exists: bool, message: str)
        """
        try:
            xui, resolved_name = self.server_manager.get_server_by_name(server_name)
            if not xui:
                return False, f"Сервер {server_name} недоступен"
            
            exists = xui.client_exists(client_email)
            if exists:
                return True, f"Клиент {client_email} существует на сервере {resolved_name}"
            else:
                return False, f"Клиент {client_email} не найден на сервере {resolved_name}"
                
        except Exception as e:
            return False, f"Ошибка проверки клиента: {e}"

