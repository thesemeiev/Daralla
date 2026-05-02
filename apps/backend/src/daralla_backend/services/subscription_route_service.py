"""Service layer for subscription route response generation."""

from __future__ import annotations

import base64
import datetime
import logging
import os
import re
import time

from daralla_backend.app_context import get_ctx
from daralla_backend.db.subscriptions_db import (
    get_subscription_by_token,
    get_subscription_servers,
    is_subscription_active,
)
from daralla_backend.utils.logging_helpers import mask_secret

logger = logging.getLogger(__name__)

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def _format_bytes(bytes_value):
    if bytes_value == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def _classify_inactive_subscription(sub: dict, now_ts: int) -> str:
    """deleted | expired | inactive (не активна по статусу, срок ещё не прошёл)."""
    if sub.get("status") == "deleted":
        return "deleted"
    if int(sub.get("expires_at") or 0) < now_ts:
        return "expired"
    return "inactive"


def _inactive_announce_text(reason: str) -> str:
    if reason == "deleted":
        return "Подписка удалена. Оформите новую в приложении или боте."
    if reason == "expired":
        return "Подписка истекла. Продлите в приложении или боте."
    return "Подписка неактивна. Откройте приложение или бота."


def _announce_header_value(text: str) -> str:
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"base64:{b64}"


def _looks_like_telegram_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return (
        "t.me/" in u
        or "telegram.me/" in u
        or "telegram.dog/" in u
        or u.startswith("tg:")
    )


def _resolve_button_urls() -> tuple[str, str]:
    """
    Две кнопки: «сайт/канал» и поддержка.

    Сайт: WEBSITE_URL → WEBAPP_URL → TELEGRAM_CHANNEL_URL (канал/новости — отдельно от поддержки).
    Поддержка: SUPPORT_URL → TELEGRAM_URL (legacy).
    Если не хватает одной стороны — дублируем (последний fallback).
    """
    webapp = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    site = (os.getenv("WEBSITE_URL") or "").strip()
    channel = (os.getenv("TELEGRAM_CHANNEL_URL") or "").strip()
    support = (os.getenv("SUPPORT_URL") or "").strip()
    legacy_tg = (os.getenv("TELEGRAM_URL") or "").strip()

    support_btn = support or legacy_tg
    site_btn = site or webapp or channel

    if support_btn and not site_btn:
        site_btn = webapp or channel or support_btn
    if site_btn and not support_btn:
        support_btn = legacy_tg or support or site_btn

    return site_btn, support_btn


def _build_subscription_headers(
    *,
    vpn_brand_name: str,
    expire_timestamp_seconds: int,
    total_upload: int,
    total_download: int,
    total_traffic: int,
    is_v2raytun_client: bool,
    user_agent: str,
    inactive_reason: str | None,
    now_ts: int,
) -> dict:
    """Общие заголовки для 200-ответа /sub (активная и неактивная подписка)."""
    expire_timestamp_ms = expire_timestamp_seconds * 1000
    expire_datetime = datetime.datetime.fromtimestamp(expire_timestamp_seconds)
    expire_str = expire_datetime.strftime("%Y-%m-%d %H:%M:%S")
    total_used = total_upload + total_download

    # total=0 в панели и в userinfo — де-факто «безлимит»; без подстановки PiB (клиенты показывают нормальный текст).
    quota_total = total_traffic
    subscription_userinfo_happ = (
        f"upload={total_upload}; "
        f"download={total_download}; "
        f"total={quota_total}; "
        f"expire={expire_timestamp_seconds}"
    )

    if inactive_reason:
        remaining_seconds = 0
    else:
        remaining_seconds = max(0, int(expire_timestamp_seconds) - int(now_ts))

    clean_name_for_header = re.sub(r"[^\w\s-]", "", vpn_brand_name).strip()
    if not clean_name_for_header:
        clean_name_for_header = os.getenv("VPN_BRAND_NAME", "Daralla VPN").strip()
    if len(clean_name_for_header) > 25:
        clean_name_for_header = clean_name_for_header[:25]
        logger.warning("profile-title обрезан до 25 символов: '%s'", clean_name_for_header)

    clean_name = re.sub(r"[^\w\s-]", "", vpn_brand_name)
    domain_name = re.sub(r"\s+", "-", clean_name.strip()).lower()
    if not domain_name or len(domain_name) > 63:
        domain_name = re.sub(
            r"\s+", "-", os.getenv("VPN_BRAND_NAME", "daralla-vpn").strip().lower()
        )
        if not domain_name or len(domain_name) > 63:
            domain_name = "daralla-vpn"

    site_btn, support_btn = _resolve_button_urls()
    is_telegram_like = _looks_like_telegram_url(support_btn)

    clean_filename = re.sub(r"[^\w\s-]", "", vpn_brand_name).strip().replace(" ", "-").lower()
    if not clean_filename:
        clean_filename = re.sub(
            r"\s+", "-", os.getenv("VPN_BRAND_NAME", "daralla-vpn").strip().lower()
        )
        if not clean_filename:
            clean_filename = "daralla-vpn"

    response_headers = {
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
        "expire": str(expire_timestamp_seconds),
        "expiryTime": str(expire_timestamp_ms),
        "expire-date": expire_str,
        "upload": str(total_upload),
        "download": str(total_download),
        "total": str(quota_total),
        "used": str(total_used),
        "upload-formatted": _format_bytes(total_upload),
        "download-formatted": _format_bytes(total_download),
        "total-formatted": _format_bytes(total_traffic) if total_traffic > 0 else "Unlimited",
        "used-formatted": _format_bytes(total_used),
        "X-Subscription-Remaining-Seconds": str(remaining_seconds),
        "remaining-seconds": str(remaining_seconds),
    }

    logger.debug(
        "subscription buttons: site=%s support=%s telegram_like=%s",
        "set" if site_btn else "",
        "set" if support_btn else "",
        is_telegram_like,
    )

    if inactive_reason:
        response_headers["X-Subscription-State"] = inactive_reason
        ann_text = _inactive_announce_text(inactive_reason)
        response_headers["announce"] = _announce_header_value(ann_text)
        if support_btn:
            response_headers["announce-url"] = support_btn
        elif site_btn:
            response_headers["announce-url"] = site_btn

    if site_btn:
        response_headers["profile-web-page-url"] = site_btn
        response_headers["website"] = site_btn

    if support_btn:
        response_headers["support-url"] = support_btn
        if is_telegram_like:
            response_headers["telegram-url"] = support_btn
            response_headers["telegram"] = support_btn
            response_headers["tg"] = support_btn

    # Баннер announce с эмодзи — только V2RayTun; Incy/Hiddify и др. не трогаем (иначе дубль с кнопками).
    if not inactive_reason and is_v2raytun_client and support_btn:
        if is_telegram_like:
            announce_text = "#0088cc📱 Telegram"
        else:
            announce_text = "Поддержка"
        announce_base64 = base64.b64encode(announce_text.encode("utf-8")).decode("utf-8")
        response_headers["announce"] = f"base64:{announce_base64}"
        response_headers["announce-url"] = support_btn
        logger.debug(
            "Добавлен announce для V2RayTun (клиент: %s)",
            user_agent[:50] if user_agent else "unknown",
        )

    return response_headers


async def _sum_traffic_from_servers(subscription_id: int, servers: list) -> tuple[int, int, int]:
    total_upload = 0
    total_download = 0
    total_traffic = 0
    server_manager = get_ctx().server_manager
    if not server_manager or not servers:
        return total_upload, total_download, total_traffic
    for server in servers:
        server_name = server["server_name"]
        client_email = server["client_email"]
        try:
            xui, _ = server_manager.get_server_by_name(server_name)
            if xui:
                traffic_stats = await xui.get_client_traffic(client_email)
                if traffic_stats:
                    total_upload += traffic_stats.get("upload", 0)
                    total_download += traffic_stats.get("download", 0)
                    total_traffic = max(total_traffic, traffic_stats.get("total", 0))
        except Exception as exc:
            logger.warning(
                "Не удалось получить статистику трафика для %s на %s: %s",
                client_email,
                server_name,
                exc,
            )
    return total_upload, total_download, total_traffic


async def handle_subscription_request(token: str, method: str, headers: dict):
    user_agent = (headers.get("User-Agent") or "").lower()
    x_client = (headers.get("X-Client") or "").lower()
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

    if method == "OPTIONS":
        return "", 200, _cors_headers()

    token_masked = mask_secret(token)
    logger.info("Входящий запрос subscription: token=%s, method=%s", token_masked, method)

    try:
        subscription_manager = get_ctx().subscription_manager
        if not subscription_manager:
            logger.error("subscription_manager не доступен")
            return "Service unavailable", 503, None

        sub = await get_subscription_by_token(token)
        if not sub:
            logger.warning("Подписка с токеном %s не найдена", token_masked)
            return "Subscription not found", 404, None

        logger.info(
            "Запрос подписки: token=%s, subscription_id=%s, status=%s, expires_at=%s",
            token_masked,
            sub["id"],
            sub["status"],
            sub["expires_at"],
        )

        if not is_subscription_active(sub):
            now_ts = int(time.time())
            expires_at = int(sub.get("expires_at") or 0)
            expires_str = datetime.datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
            current_str = datetime.datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d %H:%M:%S")
            inactive_reason = _classify_inactive_subscription(sub, now_ts)
            logger.warning(
                "Подписка с токеном %s не активна (%s): status=%s, expires_at=%s, current=%s",
                token_masked,
                inactive_reason,
                sub.get("status"),
                expires_str,
                current_str,
            )
            servers = await get_subscription_servers(sub["id"])
            if inactive_reason == "deleted":
                total_upload, total_download, total_traffic = 0, 0, 0
            else:
                total_upload, total_download, total_traffic = await _sum_traffic_from_servers(
                    sub["id"], servers
                )
                logger.info(
                    "Неактивная подписка %s: трафик upload=%s download=%s total=%s",
                    sub["id"],
                    total_upload,
                    total_download,
                    total_traffic,
                )

            expire_ts = int(sub.get("expires_at") or 0)
            if expire_ts <= 0:
                expire_ts = now_ts

            vpn_brand_name = get_ctx().vpn_brand_name
            response_headers = _build_subscription_headers(
                vpn_brand_name=vpn_brand_name,
                expire_timestamp_seconds=expire_ts,
                total_upload=total_upload,
                total_download=total_download,
                total_traffic=total_traffic,
                is_v2raytun_client=is_v2raytun_client,
                user_agent=user_agent,
                inactive_reason=inactive_reason,
                now_ts=now_ts,
            )
            empty_b64 = base64.b64encode(b"").decode("ascii")
            logger.info(
                "Возвращаем пустую подписку 200 для token=%s state=%s",
                token_masked,
                inactive_reason,
            )
            return empty_b64, 200, response_headers

        logger.info("Подписка %s валидна, генерируем ссылки...", sub["id"])

        links = await subscription_manager.build_links_for_subscription(sub["id"])
        servers = await get_subscription_servers(sub["id"])
        logger.info("Сгенерировано %s ссылок для подписки %s", len(links), sub["id"])

        if not links:
            logger.warning("Серверов в подписке: %s", len(servers))
            for server in servers:
                logger.warning("  - %s", server["server_name"])
            return "No servers available", 503, None

        vpn_brand_name = get_ctx().vpn_brand_name

        expire_timestamp_seconds = sub["expires_at"]

        logger.info(
            "Начало получения статистики трафика для подписки %s с %s серверами",
            sub["id"],
            len(servers),
        )

        total_upload, total_download, total_traffic = await _sum_traffic_from_servers(
            sub["id"], servers
        )
        logger.info(
            "Общая статистика трафика подписки: upload=%s, download=%s, total=%s",
            total_upload,
            total_download,
            total_traffic,
        )

        expire_str = datetime.datetime.fromtimestamp(expire_timestamp_seconds).strftime(
            "%Y-%m-%d %H:%M:%S"
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
            "Возвращаем %s ссылок для подписки %s с названием группы: '%s'",
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
            "subscription-userinfo (строковый формат для Happ и V2RayTun): upload=%s; download=%s; total=%s; expire=%s",
            total_upload,
            total_download,
            total_traffic,
            expire_timestamp_seconds,
        )
        logger.info(
            "Устанавливаем название группы подписки (Remarks для V2RayTun): '%s'",
            vpn_brand_name,
        )
        logger.info(
            "Время истечения подписки: %s (timestamp: %s)",
            expire_str,
            sub["expires_at"],
        )
        clean_name = re.sub(r"[^\w\s-]", "", vpn_brand_name)
        domain_name = re.sub(r"\s+", "-", clean_name.strip()).lower()
        logger.info("Домен для Happ клиента: '%s' (из '%s')", domain_name, vpn_brand_name)
        site_b, sup_b = _resolve_button_urls()
        if sup_b or site_b:
            logger.info(
                "Подписка /sub: поддержка=%s сайт=%s",
                (sup_b or "")[:80],
                (site_b or "")[:80],
            )

        response_headers = _build_subscription_headers(
            vpn_brand_name=vpn_brand_name,
            expire_timestamp_seconds=expire_timestamp_seconds,
            total_upload=total_upload,
            total_download=total_download,
            total_traffic=total_traffic,
            is_v2raytun_client=is_v2raytun_client,
            user_agent=user_agent,
            inactive_reason=None,
            now_ts=int(time.time()),
        )

        return response_text, 200, response_headers
    except Exception as exc:
        logger.error("Ошибка в эндпоинте /sub/<token>: %s", exc, exc_info=True)
        return "Internal server error", 500, None
