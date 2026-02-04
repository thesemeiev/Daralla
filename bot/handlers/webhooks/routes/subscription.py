"""
Blueprint: GET /sub/<token> (subscription VLESS links).
"""
import asyncio
import base64
import datetime
import logging
import os
import re
import time
import urllib.parse
from flask import Blueprint, request, Response

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('subscription', __name__)

    @bp.route('/sub/<token>', methods=['GET'])
    def subscription(token):
        """
        Эндпоинт для получения VLESS ссылок подписки.
        Возвращает список VLESS ссылок для всех серверов в подписке.
        """
        user_agent = request.headers.get('User-Agent', '').lower()
        x_client = request.headers.get('X-Client', '').lower()
        is_happ_client = 'happ' in user_agent or 'happ' in x_client
        is_v2raytun_client = 'v2raytun' in user_agent or 'v2raytun' in x_client

        if user_agent or x_client:
            logger.debug(f"Определение клиента: User-Agent='{user_agent[:100]}', X-Client='{x_client}', is_happ={is_happ_client}, is_v2raytun={is_v2raytun_client}")

        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })

        logger.info(f"Входящий запрос subscription: token={token}, method={request.method}")

        try:
            # Remnawave: token = short_uuid, отдаём контент подписки из Remnawave
            try:
                from ....services.remnawave_service import is_remnawave_configured, load_remnawave_config, RemnawaveClient
                if is_remnawave_configured() and token and len(token) >= 8:
                    cfg = load_remnawave_config()
                    client = RemnawaveClient(cfg)
                    raw = client.get_sub_raw(token)
                    return Response(raw, mimetype="text/plain; charset=utf-8")
            except Exception as remna_e:
                logger.debug("Remnawave sub proxy failed for token=%s: %s", token, remna_e)

            logger.warning(f"Подписка с токеном {token} не найдена")
            return ("Subscription not found", 404)

        except Exception as e:
            logger.error(f"Ошибка в эндпоинте /sub/<token>: {e}")
            return ("Internal server error", 500)

    return bp
