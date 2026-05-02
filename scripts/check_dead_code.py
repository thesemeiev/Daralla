#!/usr/bin/env python3
"""
Запуск Vulture по настройке из pyproject.toml ([tool.vulture]).

Зависимость: pip install vulture  (см. requirements-dev.txt)

Из корня репозитория:
  python scripts/check_dead_code.py
или:
  python -m vulture
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    return subprocess.call([sys.executable, "-m", "vulture"], cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
