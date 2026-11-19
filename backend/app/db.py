"""SQLite storage with versioned SQL migrations.

A fresh connection is opened per unit of work, which is safe for FastAPI's
thread pool and for the background analysis worker. WAL mode allows reads while
an analysis is being written.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import Settings


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, settings: Settings, migrations_dir: Path | None = None):
        self.path = settings.database_path
        self.migrations_dir = migrations_dir or Path(__file__).parent / "migrations"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            known = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            for sql_file in sorted(self.migrations_dir.glob("*.sql")):
                version = sql_file.stem
                if version in known:
                    continue
                conn.executescript(sql_file.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utcnow()),
                )
                applied.append(version)
        return applied

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, params)

    def audit(self, owner_hash: str, action: str, target: str = "", detail: str = "") -> None:
        import uuid

        self.execute(
            "INSERT INTO audit_log(id, owner_hash, action, target, created_at, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, owner_hash, action, target, utcnow(), detail),
        )
