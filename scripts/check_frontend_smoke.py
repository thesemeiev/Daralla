#!/usr/bin/env python3
"""Lightweight frontend smoke checks for CI."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "webapp" / "index.html"
APP_JS = ROOT / "webapp" / "app.js"
STYLE_CSS = ROOT / "webapp" / "style.css"


def main() -> int:
    missing = [str(p.relative_to(ROOT)) for p in (INDEX_HTML, APP_JS, STYLE_CSS) if not p.exists()]
    if missing:
        print("Frontend smoke failed: missing required files:")
        for item in missing:
            print(f" - {item}")
        return 1

    html = INDEX_HTML.read_text(encoding="utf-8")
    required_script_paths = [
        "/js/api/client.js",
        "/js/ui/messages.js",
        "/js/auth/session.js",
        "/js/shared/clipboard.js",
        "/js/platform/runtime.js",
        "/js/platform/ui-guards.js",
        "/js/features/routing.js",
        "/js/features/auth/core.js",
        "/js/features/auth/forms.js",
        "/js/features/auth/account.js",
        "/js/features/subscriptions/list.js",
        "/js/features/admin/users.js",
        "/js/features/admin/users-list.js",
        "/js/features/admin/users-actions.js",
        "/js/features/admin/subscription-edit.js",
        "/js/features/admin/subscription-create.js",
        "/js/features/admin/stats-dashboard.js",
        "/js/features/admin/broadcast.js",
        "/js/features/admin/commerce.js",
        "/js/features/admin/servers.js",
        "/js/features/servers/list.js",
        "/js/features/events/core.js",
        "/js/features/notifications/rules.js",
        "/js/features/payments/checkout.js",
        "/js/features/instructions/modal.js",
        "/js/features/instructions/setup.js",
        "/js/features/navigation/indicator.js",
        "/js/features/about/scene.js",
        "/app.js",
    ]
    for script_path in required_script_paths:
        if script_path not in html:
            print(f"Frontend smoke failed: index.html does not reference {script_path}")
            return 1

    if not re.search(r'<link\s+rel="stylesheet"\s+href="/style\.css\?v=', html):
        print("Frontend smoke failed: index.html stylesheet version marker is missing")
        return 1

    print("Frontend smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
