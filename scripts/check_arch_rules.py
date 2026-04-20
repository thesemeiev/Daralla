#!/usr/bin/env python3
"""
Simple architecture guardrails checker.

Current rule:
1) Route modules must not import bot.db directly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = ROOT / "bot" / "web" / "routes"

ROUTE_DB_IMPORT = re.compile(r"^\s*(from\s+bot\.db\s+import|import\s+bot\.db)", re.MULTILINE)

# Transitional baseline. Refactor should shrink this set over time.
ALLOWED_ROUTE_DB_IMPORTS = {
    "bot/web/routes/admin_broadcast.py",
    "bot/web/routes/admin_stats.py",
    "bot/web/routes/admin_subscriptions.py",
    "bot/web/routes/admin_users.py",
    "bot/web/routes/api_user.py",
    "bot/web/routes/payment.py",
}


def main() -> int:
    violations = []
    observed = []
    for route_file in sorted(ROUTES_DIR.glob("*.py")):
        text = route_file.read_text(encoding="utf-8")
        if ROUTE_DB_IMPORT.search(text):
            rel = route_file.relative_to(ROOT).as_posix()
            observed.append(rel)
            if rel not in ALLOWED_ROUTE_DB_IMPORTS:
                violations.append(rel)

    if violations:
        print("Architecture rule violation: new routes import bot.db directly.")
        for item in violations:
            print(f" - {item}")
        return 1

    print(f"Architecture checks passed. Baseline direct bot.db imports: {len(observed)}")
    print("Architecture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
