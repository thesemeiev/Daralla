"""
Начальная схема БД.
Использует CREATE TABLE IF NOT EXISTS — безопасно для существующих баз.
"""
import aiosqlite

DESCRIPTION = "Создание всех таблиц (config, users, servers, subscriptions, payments, notifications)"


async def up(db: aiosqlite.Connection) -> None:
    # === config ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT,
            updated_at INTEGER
        )
    """)

    # === users ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL,
            username TEXT,
            password_hash TEXT,
            is_web INTEGER DEFAULT 0,
            auth_token TEXT,
            telegram_id TEXT
        )
    """)
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id) WHERE telegram_id IS NOT NULL")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS link_telegram_states (
            state TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS telegram_links (
            telegram_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            linked_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_links_user_id ON telegram_links(user_id)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS known_telegram_ids (
            telegram_id TEXT PRIMARY KEY,
            first_seen_at INTEGER NOT NULL
        )
    """)

    # === servers ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS server_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS servers_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT,
            host TEXT NOT NULL,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            vpn_host TEXT,
            lat REAL,
            lng REAL,
            is_active INTEGER DEFAULT 1,
            subscription_port INTEGER DEFAULT 2096,
            subscription_url TEXT,
            client_flow TEXT,
            map_label TEXT,
            location TEXT,
            max_concurrent_clients INTEGER DEFAULT 50,
            FOREIGN KEY (group_id) REFERENCES server_groups(id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS server_load_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            online_clients INTEGER NOT NULL,
            total_active INTEGER NOT NULL,
            offline_clients INTEGER NOT NULL,
            recorded_at INTEGER NOT NULL,
            UNIQUE(server_name, recorded_at)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_server_load_server_time
        ON server_load_history(server_name, recorded_at DESC)
    """)

    # === subscriptions ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            period TEXT NOT NULL,
            device_limit INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            subscription_token TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            name TEXT,
            group_id INTEGER,
            FOREIGN KEY (subscriber_id) REFERENCES users(id),
            FOREIGN KEY (group_id) REFERENCES server_groups(id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS subscription_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            client_id TEXT,
            UNIQUE(subscription_id, server_name),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        )
    """)
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_servers_unique ON subscription_servers(subscription_id, server_name)")

    # === payments ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            meta TEXT,
            activated INTEGER DEFAULT 0
        )
    """)

    # === notifications ===
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            subscription_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            sent_at INTEGER NOT NULL,
            server_name TEXT
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS notification_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total_sent INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            blocked_users INTEGER DEFAULT 0,
            notification_type TEXT NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at INTEGER
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS notification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            trigger_hours INTEGER NOT NULL,
            message_template TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            repeat_every_hours INTEGER DEFAULT 0,
            max_repeats INTEGER DEFAULT 1
        )
    """)
