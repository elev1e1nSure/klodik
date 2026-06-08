"""SQLite-backed memory for agent interactions and user preferences."""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from config import settings


class Memory:
    """Stores interactions and preferences in a local SQLite database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.memory_db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    task TEXT,
                    response TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )"""
            )

    def save_interaction(self, task: str, response: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO interactions (timestamp, task, response) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), task, response),
            )

    def get_recent(self, limit: int = 10) -> list[dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT timestamp, task, response FROM interactions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_preference(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_preference(self, key: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None


# Global singleton instance
memory = Memory()
