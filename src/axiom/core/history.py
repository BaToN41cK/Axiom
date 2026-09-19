"""Conversation persistence — plain JSON files, no external database."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from axiom.core.config import axiom_home
from axiom.core.events import Message


class Conversation(BaseModel):
    """A stored chat session."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "New conversation"
    model: str | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    messages: list[Message] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = time.time()

    def derive_title(self) -> None:
        """Use the first real user message as the conversation title."""
        for message in self.messages:
            if message.role == "user" and message.content.strip():
                title = " ".join(message.content.split())
                self.title = title[:48] + ("…" if len(title) > 48 else "")
                return


class HistoryStore:
    """Reads and writes conversations under ``~/.axiom/history``.

    A size limit keeps the directory from growing forever: when ``limit`` is
    set, the oldest conversations are pruned on every save.
    """

    def __init__(self, directory: Path | None = None, limit: int | None = None) -> None:
        self._dir = directory or (axiom_home() / "history")
        self._limit = limit

    @property
    def directory(self) -> Path:
        return self._dir

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id: str) -> Path:
        safe = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("Invalid conversation id")
        return self._dir / f"{safe}.json"

    def save(self, conversation: Conversation) -> None:
        self._ensure_dir()
        conversation.touch()
        path = self._path(conversation.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(conversation.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
        self._prune()

    def _prune(self) -> None:
        """Keep at most ``limit`` newest conversations (``None`` = keep all)."""
        if not self._limit or self._limit < 1:
            return
        for old in self.list()[self._limit:]:
            try:
                self._path(old.id).unlink()
            except OSError:
                continue

    def set_limit(self, limit: int | None) -> None:
        """Change the size limit at runtime (``None`` = unlimited)."""
        self._limit = limit

    def rename(self, conversation_id: str, title: str) -> bool:
        """Rename a stored conversation (the real title lives on disk)."""
        clean = " ".join((title or "").split())
        if not clean:
            return False
        conversation = self.load(conversation_id)
        if conversation is None:
            return False
        conversation.title = clean[:80]
        try:
            self.save(conversation)
        except OSError:
            return False
        return True

    def show(self, conversation_id: str) -> str | None:
        """Raw JSON of one conversation — the ``show`` half of list/show/rm."""
        path = self._path(conversation_id)
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def load(self, conversation_id: str) -> Conversation | None:
        path = self._path(conversation_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return Conversation.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def list(self) -> list[Conversation]:
        """All conversations, newest first. Corrupt files are skipped."""
        if not self._dir.exists():
            return []
        conversations: list[Conversation] = []
        for path in self._dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                conversations.append(Conversation.model_validate(raw))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations

    def delete(self, conversation_id: str) -> bool:
        path = self._path(conversation_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False
