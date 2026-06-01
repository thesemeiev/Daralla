#!/usr/bin/env python3
"""
Проверка Clash/Mihomo subscription на панели 3x-ui (без Daralla).

Пример:
  python scripts/check_panel_clash_subscription.py \\
    --subscription-url https://141.98.7.234:2096/daralla/sub \\
    --sub-id a0ad0b82a9904f8381bff5ed

Сравнивает обычную подписку /sub/{id} и варианты Clash URL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from daralla_backend.services.clash_subscription_service import is_valid_panel_clash_body  # noqa: E402


def _clash_base_candidates(subscription_url: str, clash_path: str) -> list[str]:
    sub_base = subscription_url.rstrip("/")
    seg = clash_path.strip("/") or "clash"
    out: list[str] = []
    if sub_base.endswith("/sub"):
        out.append(f"{sub_base}/{seg}")
        out.append(f"{sub_base[:-4]}/{seg}")
    else:
        out.append(f"{sub_base.rstrip('/')}/{seg}")
    seen: set[str] = set()
    ordered: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _probe(url: str) -> tuple[int, str]:
    try:
        r = httpx.get(url, verify=False, timeout=15.0)
        return r.status_code, (r.text or "").strip()
    except Exception as exc:
        return -1, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe 3x-ui /sub and /clash subscription URLs")
    parser.add_argument(
        "--subscription-url",
        required=True,
        help="Базовый URL подписки с панели (как в админке Daralla), напр. https://IP:2096/daralla/sub",
    )
    parser.add_argument("--sub-id", required=True, help="Sub ID клиента (subId на панели или токен Daralla)")
    parser.add_argument(
        "--clash-path",
        default="clash",
        help="Сегмент clash на панели (subClashPath без слэшей), по умолчанию clash",
    )
    args = parser.parse_args()

    sub_url = f"{args.subscription_url.rstrip('/')}/{args.sub_id}"
    print(f"=== Обычная подписка ===\nGET {sub_url}")
    status, body = _probe(sub_url)
    print(f"  status={status}  len={len(body)}")
    if status == 200 and body and "://" not in body[:80]:
        print("  (похоже на base64 — нормально для /sub)")

    print("\n=== Clash / Mihomo ===")
    any_ok = False
    for base in _clash_base_candidates(args.subscription_url, args.clash_path):
        url = f"{base.rstrip('/')}/{args.sub_id}"
        status, body = _probe(url)
        valid = status == 200 and is_valid_panel_clash_body(body)
        mark = "OK" if valid else "FAIL"
        print(f"\n[{mark}] GET {url}")
        print(f"  status={status}  len={len(body)}")
        if body:
            preview = body[:200].replace("\n", "\\n")
            print(f"  preview={preview}")
        if valid:
            any_ok = True
            print("  → валидный YAML с proxies (панель отдаёт Clash)")

    if not any_ok:
        print(
            "\nНи один Clash URL не вернул YAML.\n"
            "Проверьте в 3x-ui: Panel Settings → Subscription\n"
            "  - Sub Clash Enable = on\n"
            "  - Sub URI и Sub Clash Path (часто …/daralla/sub + clash → …/daralla/sub/clash/)\n"
            "  - Sub ID клиента совпадает с --sub-id\n"
            "Если инбаунды только VLESS+xhttp, панель может отвечать Error! — см. "
            "https://github.com/MHSanaei/3x-ui/issues/4347"
        )
        return 1

    print("\nИспользуйте рабочий URL (с [OK]) в DARALLA_CLASH_SUB_BASE_URL или subscription_clash_url сервера.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
