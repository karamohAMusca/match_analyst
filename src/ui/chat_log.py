"""The app's conversations saved for later analysis: one JSON Lines file per chat in `chats/`
(git-ignored), one line per answer, appended as soon as the answer is given (a chat stopped halfway
keeps its turns).

Each line holds what the app showed (question, answer, consulted cards, searches, guardrails, meta)
and the turns this answer added to the agent's memory, serialized with datapizza's `Memory`: tool
calls and their results included, as the model saw them while answering (the agent's live memory
keeps only the questions and the answers once a turn is closed). `load_chat()` reads a file back,
`load_memory()` rebuilds the whole datapizza `Memory` of the chat, searches included.

What is written is redacted (src/guardrails/redact.py): a key, an email, a phone number... the coach typed
are hidden in every field of the line, the question as the coach wrote it included.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from datapizza.memory import Memory

import src.core.config as config
from src.guardrails.redact import redact_all

__all__ = ["ChatLog", "load_chat", "load_memory"]


class ChatLog:
    """The file of one conversation, named after the time it started."""

    def __init__(self, folder: Path | None = None, started: datetime | None = None) -> None:
        folder = folder or config.CHATS_DIR
        stem = f"{(started or datetime.now()):%Y-%m-%d_%H%M%S}"
        self.path = folder / f"{stem}.jsonl"
        n = 2
        while self.path.exists():   # two chats started in the same second
            self.path, n = folder / f"{stem}-{n}.jsonl", n + 1

    def append(self, question: str, message: dict[str, Any], turns: list[dict[str, Any]]) -> None:
        """Write one answer: the app message for `question` and the memory turns it added
        (`Turn.to_dict()` each)."""
        line = redact_all({"time": datetime.now().isoformat(timespec="seconds"), "question": question,
                           **{k: v for k, v in message.items() if k != "role"}, "memory": turns})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def load_chat(path: Path) -> list[dict[str, Any]]:
    """The answers of a saved chat, in order."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_memory(answers: list[dict[str, Any]]) -> Memory:
    """The datapizza `Memory` of a saved chat: every turn, tool calls included."""
    memory = Memory()
    memory.json_loads(json.dumps([turn for a in answers for turn in a["memory"]]))
    return memory
