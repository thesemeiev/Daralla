#!/usr/bin/env python3
"""
Simple architecture guardrails checker.

Current rules:
1) Route modules must not import bot.*.db* directly.
2) webapp/app.js should stay a thin entrypoint (limited passthrough wrappers).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = ROOT / "bot" / "web" / "routes"
APP_JS = ROOT / "webapp" / "app.js"

ROUTE_DB_IMPORT = re.compile(
    r"^\s*(from\s+bot\.db(?:\.[\w_]+)*\s+import|import\s+bot\.db(?:\.[\w_]+)*)",
    re.MULTILINE,
)
ROUTE_ANY_DB_IMPORT = re.compile(
    r"^\s*(from\s+bot\.[\w\.]*db(?:\.[\w_]+)*\s+import|import\s+bot\.[\w\.]*db(?:\.[\w_]+)*)",
    re.MULTILINE,
)
APP_PASSTHROUGH_WRAPPER = re.compile(
    r"(?:async\s+)?function\s+[A-Za-z0-9_]+\([^)]*\)\s*\{\s*return\s+[A-Za-z0-9_]+Feature\.[A-Za-z0-9_]+\([^)]*\);\s*\}",
    re.MULTILINE,
)
MAX_APP_PASSTHROUGH_WRAPPERS = 15
BASELINE_APP_PASSTHROUGH_WRAPPERS = 15

# Transitional baseline. Keep empty and expand only if explicitly approved.
ALLOWED_ROUTE_DB_IMPORTS = set()


def main() -> int:
    violations = []
    observed = []
    for route_file in sorted(ROUTES_DIR.glob("*.py")):
        text = route_file.read_text(encoding="utf-8")
        if ROUTE_DB_IMPORT.search(text) or ROUTE_ANY_DB_IMPORT.search(text):
            rel = route_file.relative_to(ROOT).as_posix()
            observed.append(rel)
            if rel not in ALLOWED_ROUTE_DB_IMPORTS:
                violations.append(rel)

    if violations:
        print("Architecture rule violation: new routes import bot.db in route layer.")
        for item in violations:
            print(f" - {item}")
        return 1

    app_js_text = APP_JS.read_text(encoding="utf-8")
    passthrough_count = len(APP_PASSTHROUGH_WRAPPER.findall(app_js_text))
    if passthrough_count > MAX_APP_PASSTHROUGH_WRAPPERS:
        print(
            "Architecture rule violation: app.js passthrough wrappers grew too much "
            f"({passthrough_count} > {MAX_APP_PASSTHROUGH_WRAPPERS})."
        )
        return 1
    if passthrough_count > BASELINE_APP_PASSTHROUGH_WRAPPERS:
        print(
            "Architecture rule violation: app.js passthrough wrappers regressed above baseline "
            f"({passthrough_count} > {BASELINE_APP_PASSTHROUGH_WRAPPERS})."
        )
        return 1

    print(f"Architecture checks passed. Baseline direct route->db imports: {len(observed)}")
    print(f"Architecture checks passed. app.js passthrough wrappers: {passthrough_count}")
    print("Architecture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
