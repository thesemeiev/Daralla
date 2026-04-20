#!/usr/bin/env python3
"""
Collects simple architecture baseline metrics for Daralla.

Usage:
    python scripts/collect_baseline_metrics.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HOTSPOT_FILES = [
    "apps/frontend/webapp/app.js",
    "apps/frontend/webapp/index.html",
    "apps/frontend/webapp/style.css",
    "apps/backend/src/daralla_backend/web/routes/api_user.py",
    "apps/backend/src/daralla_backend/services/xui_service.py",
    "apps/backend/src/daralla_backend/services/subscription_manager.py",
]


def _count_lines(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def _count_matches(path: Path, pattern: str) -> int:
    rgx = re.compile(pattern)
    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if rgx.search(line):
                total += 1
    return total


def main() -> None:
    file_lines = {}
    for rel_path in HOTSPOT_FILES:
        file_path = ROOT / rel_path
        file_lines[rel_path] = _count_lines(file_path)

    tests_dir = ROOT / "tests"
    test_files = sorted(tests_dir.rglob("test_*.py"))

    payload = {
        "generated_at": "manual-run",
        "hotspot_lines": file_lines,
        "function_counts": {
            "apps/frontend/webapp/app.js:function": _count_matches(
                ROOT / "apps/frontend/webapp/app.js", r"^\s*function\s+[A-Za-z0-9_]+\s*\("
            ),
            "apps/backend/src/daralla_backend/web/routes/api_user.py:def": _count_matches(
                ROOT / "apps/backend/src/daralla_backend/web/routes/api_user.py", r"^\s*(async\s+def|def)\s+[A-Za-z0-9_]+\s*\("
            ),
            "apps/backend/src/daralla_backend/services/xui_service.py:def": _count_matches(
                ROOT / "apps/backend/src/daralla_backend/services/xui_service.py", r"^\s*(async\s+def|def)\s+[A-Za-z0-9_]+\s*\("
            ),
            "apps/backend/src/daralla_backend/services/subscription_manager.py:def": _count_matches(
                ROOT / "apps/backend/src/daralla_backend/services/subscription_manager.py",
                r"^\s*(async\s+def|def)\s+[A-Za-z0-9_]+\s*\(",
            ),
        },
        "test_files": len(test_files),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
