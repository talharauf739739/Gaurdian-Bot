"""SQLite log of every moderation action the bot takes."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    chat_id   INTEGER,
    user_id   INTEGER,
    username  TEXT,
    action    TEXT    NOT NULL,
    detail    TEXT
)
"""


class ActionLog:
    """Append-only log of actions (link_deleted, scam_phrase, impersonator_flagged, ...)."""

    def __init__(self, path: str | Path = "guardian.db") -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def log(self, action: str, chat_id: int | None = None, user_id: int | None = None,
            username: str | None = None, detail: str = "") -> None:
        """Record one action."""
        self._conn.execute(
            "INSERT INTO actions (ts, chat_id, user_id, username, action, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), chat_id, user_id, username, action, detail[:500]),
        )
        self._conn.commit()

    def counts(self, chat_id: int | None = None) -> dict[str, int]:
        """Number of actions per type, optionally for one chat."""
        query = "SELECT action, COUNT(*) FROM actions"
        params: tuple = ()
        if chat_id is not None:
            query += " WHERE chat_id = ?"
            params = (chat_id,)
        return dict(self._conn.execute(query + " GROUP BY action", params).fetchall())

    def recent(self, limit: int = 10) -> list[tuple]:
        """Most recent actions, newest first."""
        return self._conn.execute(
            "SELECT ts, chat_id, username, action, detail FROM actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
