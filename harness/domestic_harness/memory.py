from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time


@dataclass(frozen=True)
class Message:
    role: str
    content: str


class ConversationStore:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = state_dir / "harness.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                   id INTEGER PRIMARY KEY,
                   session TEXT NOT NULL,
                   role TEXT NOT NULL CHECK(role IN ('system','user','assistant')),
                   content TEXT NOT NULL,
                   created REAL NOT NULL
               )"""
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS messages_session_id ON messages(session, id)"
        )
        self.connection.commit()

    def append(self, session: str, role: str, content: str) -> None:
        if not session or role not in {"system", "user", "assistant"} or not content:
            raise ValueError("invalid conversation message")
        self.connection.execute(
            "INSERT INTO messages(session, role, content, created) VALUES (?, ?, ?, ?)",
            (session, role, content, time.time()),
        )
        self.connection.commit()

    def recent(self, session: str, limit: int) -> list[Message]:
        rows = self.connection.execute(
            """SELECT role, content FROM (
                   SELECT id, role, content FROM messages
                   WHERE session = ? ORDER BY id DESC LIMIT ?
               ) ORDER BY id""",
            (session, limit),
        ).fetchall()
        return [Message(role=row[0], content=row[1]) for row in rows]

    def clear(self, session: str) -> None:
        self.connection.execute("DELETE FROM messages WHERE session = ?", (session,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
