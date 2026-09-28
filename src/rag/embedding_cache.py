"""Disk cache for embeddings: the same text is never embedded (and paid for) twice.

Used by the retrieval evaluation: the gold questions are embedded once with the API key, then
every later run (and every retrieval experiment) reuses the saved vectors, even without a key.
The cache lives in `.cache/` (git-ignored) and is keyed by model and text.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from datapizza.core.embedder import BaseEmbedder

from src.core.config import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / ".cache"


class CachedEmbedder(BaseEmbedder):
    """Wraps an embedder; with `inner=None` it works offline and fails on texts not cached yet."""

    def __init__(self, inner: BaseEmbedder | None, model_name: str, path: Path | None = None) -> None:
        self.inner = inner
        self.model_name = model_name
        self.path = path or CACHE_DIR / f"embeddings_{model_name}.json"
        self._vectors: dict[str, list[float]] = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        )
        self.new_texts = 0   # texts embedded through the API by this instance

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def missing(self, texts: list[str]) -> list[str]:
        return [t for t in dict.fromkeys(texts) if self._key(t) not in self._vectors]

    def embed(self, text: str | list[str], model_name: str | None = None):
        texts = [text] if isinstance(text, str) else list(text)
        missing = self.missing(texts)
        if missing:
            if self.inner is None:
                raise LookupError(
                    f"{len(missing)} text(s) not in the embedding cache: run once with the API key."
                )
            vectors = self.inner.embed(missing)          # one API call for all missing texts
            for t, v in zip(missing, vectors, strict=True):
                self._vectors[self._key(t)] = v
            self.new_texts += len(missing)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._vectors), encoding="utf-8")
        vectors = [self._vectors[self._key(t)] for t in texts]
        return vectors[0] if isinstance(text, str) else vectors
