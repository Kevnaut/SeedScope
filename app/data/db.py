from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_db_path() -> Path:
    base = Path.home() / ".seedscope"
    base.mkdir(parents=True, exist_ok=True)
    return base / "seedscope.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                use_https INTEGER NOT NULL DEFAULT 0,
                completed_path TEXT,
                webui_path TEXT,
                transfer_path TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()
        _ensure_column(conn, "clients", "completed_path", "TEXT")
        _ensure_column(conn, "clients", "webui_path", "TEXT")
        _ensure_column(conn, "clients", "transfer_path", "TEXT")
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()


def get_clients() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, host, port, username, password, use_https, completed_path, webui_path, transfer_path FROM clients ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def add_client(data: Dict[str, Any]) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO clients (name, host, port, username, password, use_https, webui_path, transfer_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["host"],
                int(data["port"]),
                data["username"],
                data["password"],
                1 if data.get("use_https") else 0,
                data.get("webui_path"),
                data.get("transfer_path"),
            ),
        )
        if data.get("completed_path"):
            conn.execute(
                "UPDATE clients SET completed_path = ? WHERE id = ?",
                (data.get("completed_path"), int(cur.lastrowid)),
            )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_client(client_id: int, data: Dict[str, Any]) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE clients
            SET name = ?, host = ?, port = ?, username = ?, password = ?, use_https = ?, completed_path = ?, webui_path = ?, transfer_path = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["host"],
                int(data["port"]),
                data["username"],
                data["password"],
                1 if data.get("use_https") else 0,
                data.get("completed_path"),
                data.get("webui_path"),
                data.get("transfer_path"),
                int(client_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def delete_client(client_id: int) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM clients WHERE id = ?", (int(client_id),))
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return str(row["value"])
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()
