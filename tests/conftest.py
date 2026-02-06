"""
Shared test fixtures for all integration tests.
"""
import os
import asyncio
import tempfile
import pytest
import pytest_asyncio
from flask import Flask
from datetime import datetime, timedelta

# Configure test database
TEST_DB_PATH = None


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Configure environment for testing."""
    global TEST_DB_PATH
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp()
    TEST_DB_PATH = os.path.join(temp_dir, "test.db")
    
    # Set environment variables for testing
    os.environ["DATABASE_PATH"] = TEST_DB_PATH
    os.environ["BOT_TOKEN"] = "test_token_12345:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    os.environ["TELEGRAM_TOKEN"] = "12345:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    
    yield
    
    # Cleanup
    if TEST_DB_PATH and os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def db():
    """Create and initialize test database."""
    import aiosqlite
    from bot.db import init_all_db, DB_PATH
    
    # Initialize all database tables
    await init_all_db()
    
    # Open connection to the initialized database
    database = await aiosqlite.connect(DB_PATH)
    database.row_factory = aiosqlite.Row
    
    # Initialize schema
    await database.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            last_seen INTEGER NOT NULL
        )
        """
    )
    
    await database.execute(
        """
        CREATE TABLE IF NOT EXISTS identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(provider, provider_user_id),
            FOREIGN KEY(account_id) REFERENCES accounts(account_id)
        )
        """
    )
    
    await database.execute(
        """
        CREATE TABLE IF NOT EXISTS account_auth_tokens (
            token TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(account_id)
        )
        """
    )
    
    await database.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            meta TEXT,
            activated INTEGER DEFAULT 0
        )
        """
    )
    
    await database.commit()
    
    yield database
    
    # Cleanup: drop all tables (except SQLite system tables)
    cursor = await database.cursor()
    await cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = await cursor.fetchall()
    
    # SQLite system tables that should not be dropped
    system_tables = {'sqlite_sequence', 'sqlite_stat1', 'sqlite_stat2', 'sqlite_stat3', 'sqlite_stat4'}
    
    for (table_name,) in tables:
        if table_name not in system_tables:
            await database.execute(f"DROP TABLE IF EXISTS {table_name}")
    
    await database.commit()


@pytest.fixture
def mock_bot_app():
    """Create a mock bot application for testing."""
    from unittest.mock import MagicMock
    mock_app = MagicMock()
    return mock_app


@pytest.fixture
def app(mock_bot_app):
    """Create Flask test application with registered routes."""
    from bot.handlers.webhooks.webhook_app import create_webhook_app
    from bot.context import AppContext
    
    # Create minimal app context
    app_context = AppContext()
    app_context.telegram_app = mock_bot_app
    
    # Create webhook app with routes
    app = create_webhook_app(mock_bot_app, app_context)
    app.config['TESTING'] = True
    
    return app


@pytest.fixture
def app_context(app):
    """Create Flask application context for testing."""
    return app.app_context()


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest_asyncio.fixture
async def test_account(db):
    """Create a test account."""
    import time
    
    cursor = await db.cursor()
    now = int(time.time())
    
    await cursor.execute(
        "INSERT INTO accounts (created_at, last_seen) VALUES (?, ?)",
        (now, now)
    )
    
    await db.commit()
    account_id = cursor.lastrowid
    
    return {
        "account_id": account_id,
        "created_at": now,
        "last_seen": now
    }


@pytest_asyncio.fixture
async def test_auth_token(db, test_account):
    """Create a test auth token."""
    import time
    import secrets
    
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    account_id = test_account["account_id"]
    
    await db.execute(
        "INSERT INTO account_auth_tokens (token, account_id, created_at) VALUES (?, ?, ?)",
        (token, account_id, now)
    )
    
    await db.commit()
    
    return {
        "token": token,
        "account_id": account_id,
        "created_at": now
    }


@pytest_asyncio.fixture
async def test_payment(db, test_account):
    """Create a test payment."""
    import time
    import json
    
    cursor = await db.cursor()
    now = int(time.time())
    payment_id = f"test_payment_{now}"
    account_id = test_account["account_id"]
    
    meta = json.dumps({
        "type": "month",
        "device_limit": 1,
        "message_id": None
    })
    
    await cursor.execute(
        """
        INSERT INTO payments 
        (payment_id, account_id, status, activated, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (payment_id, str(account_id), "pending", 0, meta, now)
    )
    
    await db.commit()
    
    return {
        "payment_id": payment_id,
        "account_id": account_id,
        "status": "pending",
        "activated": 0,
        "meta": json.loads(meta),
        "created_at": now
    }


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
