"""
Pytest configuration and fixtures. DARALLA_TEST_DB and TELEGRAM_TOKEN must be set
before any bot.db or bot imports.
"""
import os
import tempfile
import pytest

# Use a temp file so all connections share the same DB (SQLite :memory: is per-connection)
_test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db_path = _test_db_file.name
_test_db_file.close()
os.environ.setdefault("DARALLA_TEST_DB", _test_db_path)
os.environ.setdefault("TELEGRAM_TOKEN", "test_token")


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db():
    """Initialize test database and yield. All bot.db modules use DARALLA_TEST_DB."""
    from bot.db import init_all_db
    await init_all_db()
    yield
    # Temp file is left for next run; optional: os.unlink(_test_db_path) in a finalizer
