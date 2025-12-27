import atexit
import json
import sqlite3
import threading
import time
from types import TracebackType
from typing import Any, Optional, cast

from .settings import DB_PATH


class MarketCache:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path if db_path else str(DB_PATH)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._opened_count = 0
        self._closed_count = 0
        self._conn_threads: dict[sqlite3.Connection, int] = {}
        self._init_db()

    def __enter__(self) -> "MarketCache":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close_all()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL;")
            self._local.conn.execute("PRAGMA synchronous=NORMAL;")
            with self._connections_lock:
                self._connections.add(self._local.conn)
                self._conn_threads[self._local.conn] = threading.get_ident()
                self._opened_count += 1
        return cast(sqlite3.Connection, self._local.conn)

    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expiry INTEGER
                )
            """)
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        conn = self._get_conn()
        now = int(time.time())
        cursor = conn.execute("SELECT value FROM cache WHERE key = ? AND expiry > ?", (key, now))
        row = cursor.fetchone()
        if row:
            try:
                return cast(Any, json.loads(str(row[0])))
            except json.JSONDecodeError:
                return None
        return None

    def get_any(self, key: str) -> Optional[Any]:
        """Return cached value even if expired (used for after-hours reads)."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT value FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            try:
                return cast(Any, json.loads(str(row[0])))
            except json.JSONDecodeError:
                return None
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if value is None:
            return
        with self._write_lock:
            conn = self._get_conn()
            expiry = int(time.time()) + ttl_seconds
            val_str = json.dumps(value)
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                (key, val_str, expiry),
            )
            conn.commit()

    def close(self) -> None:
        """Close the current thread's connection if present."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            with self._connections_lock:
                self._connections.discard(conn)
                self._conn_threads.pop(conn, None)
                self._closed_count += 1
            delattr(self._local, "conn")

    def close_all(self) -> None:
        """Close all tracked connections."""
        with self._connections_lock:
            conns = list(self._connections)
            self._connections.clear()
            self._conn_threads.clear()
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass
            self._closed_count += 1

    def __del__(self) -> None:
        self.close_all()

    def health(self) -> dict[str, Any]:
        with self._connections_lock:
            active = len(self._connections)
            threads = sorted(set(self._conn_threads.values()))
        return {
            "db_path": self.db_path,
            "active_connections": active,
            "total_opened": self._opened_count,
            "total_closed": self._closed_count,
            "thread_ids": threads,
            "leaked_connections": max(self._opened_count - self._closed_count, 0),
        }


cache = MarketCache()
atexit.register(cache.close_all)

__all__ = ["MarketCache", "cache"]
