"""Embeddings saved on disk: the same text is never embedded (and paid for) twice.

Used by the retrieval evaluation: the gold questions are embedded once with the API key, then
every later run (and every retrieval experiment) reuses the saved vectors, even without a key.
The vectors are kept in a `DiskCache` (datapizza's `Cache` interface, file in `.cache/`), one entry
per text, keyed by its hash: datapizza's `cacheable` keeps one entry per call, so a batch with a
single new text would be paid whole.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from datapizza.core.embedder import BaseEmbedder

from src.core.config import CACHE_DIR
from src.core.disk_cache import DiskCache


class CachedEmbedder(BaseEmbedder):
    """Wraps an embedder; with `inner=None` it works offline and fails on texts not cached yet."""

    def __init__(self, inner: BaseEmbedder | None, model_name: str, path: Path | None = None) -> None:
        self.inner = inner
        self.model_name = model_name
        self.cache = DiskCache(path or CACHE_DIR / f"embeddings_{model_name}.json")
        self.new_texts = 0   # texts embedded through the API by this instance

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def missing(self, texts: list[str]) -> list[str]:
        return [t for t in dict.fromkeys(texts) if self.cache.get(self._key(t)) is None]

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
                self.cache.set(self._key(t), v)
            self.new_texts += len(missing)
        vectors = [self.cache.get(self._key(t)) for t in texts]
        return vectors[0] if isinstance(text, str) else vectors
