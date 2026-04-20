"""
Pytest configuration and fixtures. DARALLA_TEST_DB and TELEGRAM_TOKEN must be set
before any daralla_backend.db or daralla_backend imports.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Use a temp file so all connections share the same DB (SQLite :memory: is per-connection)
_test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db_path = _test_db_file.name
_test_db_file.close()
os.environ.setdefault("DARALLA_TEST_DB", _test_db_path)
os.environ.setdefault("TELEGRAM_TOKEN", "test_token")

# Ensure apps-first backend package is importable during tests.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "apps" / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


@pytest.fixture
def event_loop():
    """Create and gracefully close event loop per test case."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    # Let aiosqlite/async generators finish close callbacks before shutdown.
    loop.run_until_complete(asyncio.sleep(0))
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


@pytest.fixture
async def db():
    """Initialize test database and yield. All daralla_backend.db modules use DARALLA_TEST_DB."""
    from daralla_backend.db import init_all_db
    await init_all_db()
    try:
        from daralla_backend.events.db.migrations import init_events_tables
        await init_events_tables()
    except Exception:
        pass
    yield
    # Temp file is left for next run; optional: os.unlink(_test_db_path) in a finalizer


