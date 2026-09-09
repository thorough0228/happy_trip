"""SQLite 数据库初始化与连接管理（用户系统专用）。"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "users.db"


def get_db_path() -> Path:
    return _DB_PATH


def init_db() -> None:
    """初始化用户数据库（users + trips 表）。"""
    db_path = _DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trips (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                title       TEXT NOT NULL,
                destination TEXT NOT NULL,
                date_range  TEXT NOT NULL,
                plan_json   TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)


@contextmanager
def get_conn(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = Path(path) if path is not None else _DB_PATH
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_user(username: str, password_hash: str) -> str:
    """创建新用户，返回 user_id。"""
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, password_hash, now),
        )
    return user_id


def get_user_by_username(username: str) -> dict | None:
    """根据用户名查找用户。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    """根据用户ID查找用户。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def create_trip(user_id: str, title: str, destination: str, date_range: str, plan_json: str) -> str:
    """创建行程记录，返回 trip_id。"""
    trip_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO trips (id, user_id, title, destination, date_range, plan_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trip_id, user_id, title, destination, date_range, plan_json, now),
        )
    return trip_id


def get_user_trips(user_id: str) -> list[dict]:
    """获取用户所有行程，按创建时间倒序。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, destination, date_range, created_at FROM trips WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_trip_by_id(trip_id: str) -> dict | None:
    """根据 trip_id 查找行程。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, title, destination, date_range, plan_json, created_at FROM trips WHERE id = ?",
            (trip_id,),
        ).fetchone()
        return dict(row) if row else None


def delete_trip(trip_id: str, user_id: str) -> bool:
    """删除行程，仅允许删除属于自己的行程。"""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM trips WHERE id = ? AND user_id = ?",
            (trip_id, user_id),
        )
        return cursor.rowcount > 0
