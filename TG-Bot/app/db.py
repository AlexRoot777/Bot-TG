import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    user_id: int
    username: str | None
    is_active: bool
    is_admin: bool
    device_id: str | None
    created_at: str


@dataclass
class ProxyKey:
    key_id: int
    user_id: int
    device_id: str
    secret: str
    connection_uri: str
    is_active: bool
    created_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    device_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proxy_keys (
                    key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    secret TEXT NOT NULL,
                    connection_uri TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_key_per_user
                    ON proxy_keys(user_id)
                    WHERE is_active = 1;
                """
            )

            # Migration for older DBs
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "device_id" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN device_id TEXT")

            pcolumns = {
                row["name"] for row in conn.execute("PRAGMA table_info(proxy_keys)").fetchall()
            }
            if "device_id" not in pcolumns:
                conn.execute("ALTER TABLE proxy_keys ADD COLUMN device_id TEXT NOT NULL DEFAULT ''")
            if "is_active" not in pcolumns:
                conn.execute("ALTER TABLE proxy_keys ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    def upsert_user(self, user_id: int, username: str | None, is_admin: bool) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, is_active, is_admin, created_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    is_admin = excluded.is_admin
                """,
                (user_id, username, int(is_admin), now),
            )

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, is_active, is_admin, device_id, created_at FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(
            user_id=row["user_id"],
            username=row["username"],
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
            device_id=row["device_id"] or None,
            created_at=row["created_at"],
        )

    def bind_device(self, user_id: int, device_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET device_id = ? WHERE user_id = ?", (device_id, user_id))

    def set_user_status(self, user_id: int, is_active: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET is_active = ? WHERE user_id = ?",
                (int(is_active), user_id),
            )
            if not is_active:
                conn.execute("UPDATE proxy_keys SET is_active = 0 WHERE user_id = ?", (user_id,))
            return cur.rowcount > 0

    def is_active_user(self, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_active FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None:
                return False
            return bool(row["is_active"])

    def get_active_key(self, user_id: int) -> ProxyKey | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT key_id, user_id, device_id, secret, connection_uri, is_active, created_at
                FROM proxy_keys
                WHERE user_id = ? AND is_active = 1
                ORDER BY key_id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return ProxyKey(
            key_id=row["key_id"],
            user_id=row["user_id"],
            device_id=row["device_id"],
            secret=row["secret"],
            connection_uri=row["connection_uri"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    def create_proxy_key(self, user_id: int, device_id: str, secret: str, connection_uri: str) -> ProxyKey:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute("UPDATE proxy_keys SET is_active = 0 WHERE user_id = ?", (user_id,))
            cur = conn.execute(
                """
                INSERT INTO proxy_keys (user_id, device_id, secret, connection_uri, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (user_id, device_id, secret, connection_uri, now),
            )
            key_id = cur.lastrowid

        return ProxyKey(
            key_id=key_id,
            user_id=user_id,
            device_id=device_id,
            secret=secret,
            connection_uri=connection_uri,
            is_active=True,
            created_at=now,
        )

    def list_users(self) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, username, is_active, is_admin, device_id, created_at FROM users ORDER BY created_at DESC"
            ).fetchall()
        return [
            User(
                user_id=row["user_id"],
                username=row["username"],
                is_active=bool(row["is_active"]),
                is_admin=bool(row["is_admin"]),
                device_id=row["device_id"] or None,
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_active_keys(self) -> list[ProxyKey]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key_id, user_id, device_id, secret, connection_uri, is_active, created_at
                FROM proxy_keys
                WHERE is_active = 1
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            ProxyKey(
                key_id=row["key_id"],
                user_id=row["user_id"],
                device_id=row["device_id"],
                secret=row["secret"],
                connection_uri=row["connection_uri"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]