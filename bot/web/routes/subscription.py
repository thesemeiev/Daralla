"""
Quart Blueprint: GET /sub/<token> (subscription VLESS links).
Async implementation — no asyncio.new_event_loop / run_until_complete.
"""
import base64
import datetime
import logging
import os
import re
import time

from quart import Blueprint, request

from bot.db.subscriptions_db import (
    get_subscription_by_token,
    get_subscription_servers,
    is_subscription_active,
)

logger = logging.getLogger(__name__)


def create_subscription_blueprint(bot_app):
    bp = Blueprint("subscription", __name__)

    @bp.route("/sub/<token>", methods=["GET", "OPTIONS"])
    async def subscription(token):
        """
        Эндпоинт для получения VLESS ссылок подписки.
        Возвращает список VLESS ссылок для всех серверов в подписке.
        """
        user_agent = (request.headers.get("User-Agent") or "").lower()
        x_client = (request.headers.get("X-Client") or "").lower()
        is_happ_client = "happ" in user_agent or "happ" in x_client
        is_v2raytun_client = "v2raytun" in user_agent or "v2raytun" in x_client

        if user_agent or x_client:
            logger.debug(
                "Определение клиента: User-Agent='%s', X-Client='%s', is_happ=%s, is_v2raytun=%s",
                user_agent[:100],
                x_client,
                is_happ_client,
                is_v2raytun_client,
            )

        if request.method == "OPTIONS":
            return "", 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }

        logger.info("Входящий запрос subscription: token=%s, method=%s", token, request.method)

        try:
            from bot.handlers.api_support.webhook_auth import get_subscription_manager

            subscription_manager = get_subscription_manager()
            if not subscription_manager:
                logger.error("subscription_manager не доступен")
                return "Service unavailable", 503

            sub = await get_subscription_by_token(token)
            if not sub:
                logger.warning("Подписка с токеном %s не найдена", token)
                return "Subscription not found", 404

            logger.info(
                "Запрос подписки: token=%s, subscription_id=%s, status=%s, expires_at=%s",
                token,
                sub["id"],
                sub["status"],
                sub["expires_at"],
            )

            if not is_subscription_active(sub):
                expires_str = datetime.datetime.fromtimestamp(sub["expires_at"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                current_str = datetime.datetime.fromtimestamp(int(time.time())).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                error_msg = (
                    f"Subscription is not active (status: {sub['status']}, "
                    f"expires_at: {expires_str}, current: {current_str})"
                )
                logger.warning("Подписка с токеном %s не активна: %s", token, error_msg)
                return error_msg, 403

            logger.info("Подписка %s валидна, генерируем ссылки...", sub["id"])

            links = await subscription_manager.build_vless_links_for_subscription(sub["id"])
            servers = await get_subscription_servers(sub["id"])
            logger.info("Сгенерировано %s VLESS ссылок для подписки %s", len(links), sub["id"])

            if not links:
                logger.warning("Серверов в подписке: %s", len(servers))
                for s in servers:
                    logger.warning("  - %s: %s", s["server_name"], s["client_email"])
                return "No servers available", 503

            from bot.handlers.api_support.webhook_auth import get_bot_module

            bot_module = get_bot_module()
            vpn_brand_name = (
                getattr(bot_module, "VPN_BRAND_NAME", "Daralla VPN")
                if bot_module
                else os.getenv("VPN_BRAND_NAME", "Daralla VPN")
            )

            clean_name = re.sub(r"[^\w\s-]", "", vpn_brand_name)
            domain_name = re.sub(r"\s+", "-", clean_name.strip()).lower()
            if not domain_name or len(domain_name) > 63:
                domain_name = re.sub(
                    r"\s+", "-", os.getenv("VPN_BRAND_NAME", "daralla-vpn").strip().lower()
                )
                if not domain_name or len(domain_name) > 63:
                    domain_name = "daralla-vpn"

            website_url = os.getenv("WEBSITE_URL", "").strip()
            telegram_url = os.getenv("TELEGRAM_URL", "").strip()

            expire_timestamp_seconds = sub["expires_at"]
            expire_timestamp_ms = expire_timestamp_seconds * 1000

            total_upload = 0
            total_download = 0
            total_traffic = 0

            logger.info(
                "Начало получения статистики трафика для подписки %s с %s серверами",
                sub["id"],
                len(servers),
            )

            try:
                from bot.handlers.api_support.webhook_auth import get_server_manager

                server_manager = get_server_manager()
                if server_manager and servers:
                    for s in servers:
                        server_name = s["server_name"]
                        client_email = s["client_email"]
                        try:
                            xui, _ = server_manager.get_server_by_name(server_name)
                            if xui:
                                traffic_stats = await xui.get_client_traffic(client_email)
                                if traffic_stats:
                                    total_upload += traffic_stats.get("upload", 0)
                                    total_download += traffic_stats.get("download", 0)
                                    total_traffic = max(
                                        total_traffic, traffic_stats.get("total", 0)
                                    )
                                    logger.debug(
                                        "Статистика трафика для %s на %s: upload=%s, download=%s, total=%s",
                                        client_email,
                                        server_name,
                                        traffic_stats.get("upload", 0),
                                        traffic_stats.get("download", 0),
                                        traffic_stats.get("total", 0),
                                    )
                        except Exception as e:
                            logger.warning(
                                "Не удалось получить статистику трафика для %s на %s: %s",
                                client_email,
                                server_name,
                                e,
                            )
                logger.info(
                    "Общая статистика трафика подписки: upload=%s, download=%s, total=%s",
                    total_upload,
                    total_download,
                    total_traffic,
                )
            except Exception as e:
                logger.warning(
                    "Ошибка получения статистики трафика: %s, используем значения по умолчанию", e
                )

            response_lines = []
            response_lines.append(f"#new-domain {domain_name}")
            response_lines.append(f"# name: {vpn_brand_name}")
            response_lines.append(f"#title: {vpn_brand_name}")
            expire_datetime = datetime.datetime.fromtimestamp(expire_timestamp_seconds)
            expire_str = expire_datetime.strftime("%Y-%m-%d %H:%M:%S")
            response_lines.append(f"#expire: {expire_timestamp_seconds}")
            response_lines.append(f"#expiryTime: {expire_timestamp_ms}")
            response_lines.append(f"#expire-date: {expire_str}")

            def format_bytes(bytes_value):
                if bytes_value == 0:
                    return "0 B"
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if bytes_value < 1024.0:
                        return f"{bytes_value:.2f} {unit}"
                    bytes_value /= 1024.0
                return f"{bytes_value:.2f} PB"

            total_used = total_upload + total_download
            response_lines.append(f"#upload: {total_upload}")
            response_lines.append(f"#download: {total_download}")
            response_lines.append(f"#total: {total_traffic if total_traffic > 0 else 0}")
            response_lines.append(f"#used: {total_used}")
            response_lines.append(f"#upload-formatted: {format_bytes(total_upload)}")
            response_lines.append(f"#download-formatted: {format_bytes(total_download)}")
            response_lines.append(
                f"#total-formatted: {format_bytes(total_traffic) if total_traffic > 0 else 'Unlimited'}"
            )
            response_lines.append(f"#used-formatted: {format_bytes(total_used)}")

            subscription_userinfo_happ = (
                f"upload={total_upload}; "
                f"download={total_download}; "
                f"total={total_traffic if total_traffic > 0 else 0}; "
                f"expire={expire_timestamp_seconds}"
            )

            clean_name_for_header = re.sub(r"[^\w\s-]", "", vpn_brand_name).strip()
            if not clean_name_for_header:
                clean_name_for_header = os.getenv("VPN_BRAND_NAME", "Daralla VPN").strip()
            if len(clean_name_for_header) > 25:
                clean_name_for_header = clean_name_for_header[:25]
                logger.warning("profile-title обрезан до 25 символов: '%s'", clean_name_for_header)

            if website_url:
                response_lines.append(f"#profile-web-page-url: {website_url}")
                response_lines.append(f"#website: {website_url}")
                response_lines.append(f"#support-url: {website_url}")
            if telegram_url:
                response_lines.append(f"#support-url: {telegram_url}")
                response_lines.append(f"#telegram: {telegram_url}")
                response_lines.append(f"#telegram-url: {telegram_url}")
                response_lines.append(f"#tg: {telegram_url}")

            response_lines.append(f"#subscription-userinfo: {subscription_userinfo_happ}")
            response_lines.append(f"#profile-title: {clean_name_for_header}")
            response_lines.append("#profile-update-interval: 1")

            if telegram_url and is_happ_client:
                logger.debug(
                    "Пропущен announce в комментариях для Happ клиента (используются кнопки через заголовки)"
                )

            links_plain = "\n".join(links)
            response_text = base64.b64encode(links_plain.encode("utf-8")).decode("ascii")

            if links:
                first_link = links[0]
                if "#" in first_link:
                    tag_part = first_link.split("#")[1]
                    logger.info("Проверка tag в первой ссылке: '%s' (URL-decoded)", tag_part)
                else:
                    logger.warning("В первой ссылке отсутствует tag!")

            logger.info(
                "Возвращаем %s VLESS ссылок для подписки %s с названием группы: '%s'",
                len(links),
                sub["id"],
                vpn_brand_name,
            )
            logger.info(
                "Статистика трафика в ответе: upload=%s, download=%s, total=%s, expire=%s",
                total_upload,
                total_download,
                total_traffic,
                expire_timestamp_seconds,
            )
            logger.info(
                "subscription-userinfo (строковый формат для Happ и V2RayTun): %s",
                subscription_userinfo_happ,
            )
            logger.info(
                "Устанавливаем название группы подписки (Remarks для V2RayTun): '%s'",
                vpn_brand_name,
            )
            logger.info(
                "Время истечения подписки: %s (timestamp: %s)", expire_str, sub["expires_at"]
            )
            logger.info("Домен для Happ клиента: '%s' (из '%s')", domain_name, vpn_brand_name)
            if website_url:
                logger.info("Ссылка на сайт: %s", website_url)
            if telegram_url:
                logger.info("Ссылка на Telegram: %s", telegram_url)

            clean_filename = (
                re.sub(r"[^\w\s-]", "", vpn_brand_name).strip().replace(" ", "-").lower()
            )
            if not clean_filename:
                clean_filename = re.sub(
                    r"\s+", "-", os.getenv("VPN_BRAND_NAME", "daralla-vpn").strip().lower()
                )
                if not clean_filename:
                    clean_filename = "daralla-vpn"

            headers = {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "subscription-userinfo": subscription_userinfo_happ,
                "Content-Disposition": f'attachment; filename="{clean_filename}"',
                "new-domain": domain_name,
                "X-Subscription-Name": clean_name_for_header,
                "profile-title": clean_name_for_header,
                "profile-update-interval": "1",
            }

            if website_url:
                headers["profile-web-page-url"] = website_url
                headers["website"] = website_url

            if telegram_url:
                headers["support-url"] = telegram_url
                headers["telegram-url"] = telegram_url
                headers["telegram"] = telegram_url
                headers["tg"] = telegram_url
                if not is_happ_client:
                    announce_text = "#0088cc📱 Telegram"
                    announce_base64 = base64.b64encode(announce_text.encode("utf-8")).decode(
                        "utf-8"
                    )
                    headers["announce"] = f"base64:{announce_base64}"
                    headers["announce-url"] = telegram_url
                    logger.debug(
                        "Добавлен announce в заголовках для V2RayTun (клиент: %s)",
                        user_agent[:50] if user_agent else "unknown",
                    )
                else:
                    logger.debug(
                        "Пропущен announce в заголовках для Happ клиента (используются кнопки через заголовки)"
                    )

            return response_text, 200, headers

        except Exception as e:
            logger.error("Ошибка в эндпоинте /sub/<token>: %s", e, exc_info=True)
            return "Internal server error", 500

    return bp
