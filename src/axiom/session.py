"""SQLite-backed session storage (messages, tool calls, summaries)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axiom.core.logging import get_logger

logger = get_logger("session")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    model TEXT,
    provider TEXT,
    task TEXT,
    state TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    name TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    timestamp REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


@dataclass
class Session:
    """A persisted conversation session."""

    id: str
    title: str
    created_at: float
    updated_at: float
    model: str = ""
    provider: str = ""
    task: str = ""
    state: str = "active"
    summary: str = ""


@dataclass
class StoredMessage:
    role: str
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0


class SessionManager:
    """SQLite-backed session manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            base = Path.home() / ".axiom" / "sessions"
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / "sessions.db"
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- sessions ----------------------------------------------------------
    def create_session(self, title: str = "New Session", model: str = "",
                       provider: str = "", task: str = "") -> Session:
        now = time.time()
        session = Session(
            id=uuid.uuid4().hex[:12], title=title or "New Session",
            created_at=now, updated_at=now, model=model, provider=provider, task=task,
        )
        self._conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, model, provider, task, state)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (session.id, session.title, session.created_at, session.updated_at,
             session.model, session.provider, session.task),
        )
        self._conn.commit()
        return session


    def update_session(
        self, session_id: str, *, title: str | None = None, model: str | None = None,
        provider: str | None = None, task: str | None = None, state: str | None = None,
        summary: str | None = None,
    ) -> None:
        updates: list[str] = []
        values: list[Any] = []
        for column, value in (("title", title), ("model", model), ("provider", provider),
                              ("task", task), ("state", state), ("summary", summary)):
            if value is not None:
                updates.append(f"{column} = ?")
                values.append(value)
        updates.append("updated_at = ?")
        values.append(time.time())
        values.append(session_id)
        self._conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", values)
        self._conn.commit()

    # -- messages ----------------------------------------------------------
    def add_message(self, session_id: str, message: StoredMessage) -> None:
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, name, tool_call_id, tool_calls, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, message.role, message.content, message.name,
                message.tool_call_id,
                json.dumps(message.tool_calls, ensure_ascii=False) if message.tool_calls else None,
                message.timestamp or time.time(),
            ),
        )
        self._conn.commit()

    def get_messages(self, session_id: str) -> list[StoredMessage]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY rowid", (session_id,)
        ).fetchall()
        messages = []
        for row in rows:
            tool_calls = []
            if row["tool_calls"]:
                try:
                    tool_calls = json.loads(row["tool_calls"])
                except json.JSONDecodeError:
                    tool_calls = []
            messages.append(
                StoredMessage(
                    role=row["role"], content=row["content"] or "", name=row["name"],
                    tool_call_id=row["tool_call_id"], tool_calls=tool_calls,
                    timestamp=row["timestamp"],
                )
            )
        return messages

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return Session(**{k: row[k] for k in row.keys()})

    def list_sessions(self, limit: int = 50) -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Session(**{k: r[k] for k in r.keys()}) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        return cursor.rowcount > 0
