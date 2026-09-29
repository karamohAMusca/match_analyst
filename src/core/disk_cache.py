"""A disk cache with datapizza's `Cache` interface: what was paid for once is read back, even after a restart.

A datapizza client takes a `cache` (`Client(cache=...)`): before every `invoke` or
`structured_response` it looks the call up (key: input, model, system prompt, output type) and,
if found, returns the saved answer without calling the API. The library's only implementation
(`MemoryCache`) lives in memory and is lost when the process ends; this one is a JSON file in
`.cache/` (git-ignored), readable by eye. Two uses:
- the judge of the gold run: a re-judge stopped halfway (a hung call, Ctrl+C) starts again without
  paying the verdicts it already has, and the same answers get the same verdicts;
- the query embeddings (`CachedEmbedder`): the gold questions are embedded once, then every
  retrieval run works offline.
Every new value is saved at once, so a run stopped halfway keeps what it already paid for. The
file is written in place: writing it aside and swapping it in can fail on Windows while another
program holds the file (a cloud sync client, an antivirus).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datapizza.core.cache import Cache
from datapizza.core.clients import ClientResponse
from datapizza.type import Block, StructuredBlock
from pydantic import BaseModel


class DiskCache(Cache):
    """A JSON file of key -> value. A value is JSON data (an embedding) or a client's answer
    (`ClientResponse`); a typed answer is rebuilt with its class, which must be one of `models`."""

    def __init__(self, path: Path, models: tuple[type[BaseModel], ...] = ()) -> None:
        self.path = path
        self.models = {m.__name__: m for m in models}
        self.data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.hits = 0   # values read back instead of paid again

    def get(self, key: str) -> Any:
        value = self.data.get(key)
        if value is None:
            return None
        value = self._load(value)
        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        self.data[key] = self._dump(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _dump(value: Any) -> Any:
        if not isinstance(value, ClientResponse):
            return value
        blocks = [{"type": "structured", "model": type(b.content).__name__, "content": b.content.model_dump()}
                  if isinstance(b, StructuredBlock) else b.to_dict() for b in value.content]
        return {"response": blocks, "stop_reason": value.stop_reason}

    def _load(self, value: Any) -> Any:
        if not (isinstance(value, dict) and "response" in value):
            return value
        # An unknown class raises KeyError: datapizza then logs it and calls the model instead.
        blocks = [StructuredBlock(content=self.models[b["model"]].model_validate(b["content"]))
                  if b["type"] == "structured" else Block.from_dict(b) for b in value["response"]]
        return ClientResponse(content=blocks, stop_reason=value.get("stop_reason"))
